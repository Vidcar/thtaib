"""Conversation export, retained-output collection and dependency-aware deletion."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from contextlib import nullcontext
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from workbench_backend.agents.harness_backend import harness_scratch_root
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.assets.schemas import (
    RegisterVerifiedOutputRequest,
    RetainedAsset,
    RetainedAssetDeletionRequest,
)
from workbench_backend.assets.service import (
    RetainedAssetService,
    _event_tool_calls,
    _tool_invocation_succeeded,
    _tool_result_paths,
)
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.checkpointer import delete_checkpoint_thread
from workbench_backend.state.store import ApplicationStore

TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
WRITE_TOOLS = {"write_file", "edit_file"}


class ConversationExport(BaseModel):
    schema_version: Literal[1] = 1
    exported_at: str
    conversation: dict[str, Any]
    runs: list[dict[str, Any]] = Field(default_factory=list)
    retained_assets: list[dict[str, Any]] = Field(default_factory=list)
    note: str = (
        "Readable export only. It is not a restorable application backup and "
        "does not include project source files, model weights, credentials or checkpoint bytes."
    )


class ConversationDeleteRequest(BaseModel):
    execute: bool = False
    include_diagnostics: bool = True


class ConversationDeletePreview(BaseModel):
    conversation_id: str
    can_delete: bool
    blockers: list[dict[str, str]] = Field(default_factory=list)
    affected_sessions: list[str] = Field(default_factory=list)
    retained_sessions: list[str] = Field(default_factory=list)
    affected_runs: list[str] = Field(default_factory=list)
    retained_runs: list[str] = Field(default_factory=list)
    affected_assets: list[str] = Field(default_factory=list)
    retained_assets: list[str] = Field(default_factory=list)
    checkpoint_threads_deleted: list[str] = Field(default_factory=list)
    checkpoint_threads_retained: list[str] = Field(default_factory=list)
    scratch_deleted: list[str] = Field(default_factory=list)
    diagnostics_deleted: bool = False
    project_sources_deleted: Literal[False] = False
    model_files_deleted: Literal[False] = False
    note: str = (
        "Conversation deletion removes only application-owned conversation, run, "
        "asset, checkpoint-thread and scratch records with no surviving consumers. "
        "Project source files, model files, external copies and backups are retained."
    )


class OutputCollectionResult(BaseModel):
    run_id: str
    created_assets: list[RetainedAsset] = Field(default_factory=list)
    skipped: list[dict[str, str]] = Field(default_factory=list)


class AssetLifecycleService:
    def __init__(self, paths: WorkbenchPaths, app_store: ApplicationStore, *, harness_provider: Callable[[], Any] | None = None) -> None:
        self.paths = paths.ensure()
        self.app_store = app_store
        self.assets = RetainedAssetService(app_store)
        self._harness_provider = harness_provider

    def export_conversation(self, conversation_id: str) -> ConversationExport:
        conversation = self.app_store.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        runs = [
            run.model_dump(mode="json")
            for run_id in conversation.run_ids
            if (run := self.app_store.get_run(run_id)) is not None
        ]
        assets = [
            asset.model_dump(mode="json")
            for asset in self.assets.list_assets()
            if asset.session_id == conversation_id
            or self.assets.store.has_consumer(asset.id, kind="session", consumer_id=conversation_id)
        ]
        return ConversationExport(
            exported_at=utc_now(),
            conversation=conversation.model_dump(mode="json"),
            runs=runs,
            retained_assets=assets,
        )

    def preview_conversation_delete(self, conversation_id: str) -> ConversationDeletePreview:
        conversation = self.app_store.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        runs = [run for run_id in conversation.run_ids if (run := self.app_store.get_run(run_id)) is not None]
        blockers = [
            {"kind": "run", "id": run.id, "status": run.status.value}
            for run in runs
            if is_run_lifecycle_live(run.status)
        ]
        shared_run_ids = self._surviving_run_ids(conversation.id, {run.id for run in runs})
        asset_preview = self.assets.deletion_preview(
            RetainedAssetDeletionRequest(
                session_ids=[conversation_id],
                run_ids=[run.id for run in runs if run.id not in shared_run_ids],
            )
        )
        affected_threads, retained_threads = self._checkpoint_thread_plan(conversation, runs)
        return ConversationDeletePreview(
            conversation_id=conversation_id,
            can_delete=not blockers,
            blockers=blockers,
            affected_sessions=asset_preview.affected_sessions,
            retained_sessions=asset_preview.retained_sessions,
            affected_runs=asset_preview.affected_runs or [run.id for run in runs if run.id not in shared_run_ids],
            retained_runs=sorted(set(asset_preview.retained_runs) | shared_run_ids),
            affected_assets=asset_preview.affected_asset_ids,
            retained_assets=asset_preview.preserved_asset_ids,
            checkpoint_threads_deleted=affected_threads,
            checkpoint_threads_retained=retained_threads,
        )

    def delete_conversation(
        self,
        conversation_id: str,
        *,
        include_diagnostics: bool = True,
    ) -> ConversationDeletePreview:
        preview = self.preview_conversation_delete(conversation_id)
        if preview.blockers:
            raise HTTPException(status_code=409, detail={"code": "conversation_delete_active_runs", "preview": preview.model_dump(mode="json")})
        conversation = self.app_store.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        runs = [run for run_id in conversation.run_ids if (run := self.app_store.get_run(run_id)) is not None]
        shared_run_ids = self._surviving_run_ids(conversation.id, {run.id for run in runs})
        deletable_run_ids = [run.id for run in runs if run.id not in shared_run_ids]
        guard = self._harness_provider().deleting_idle_runs(deletable_run_ids) if self._harness_provider else nullcontext()
        with guard:
            asset_preview = self.assets.mark_deletable_assets_deleted(
                RetainedAssetDeletionRequest(session_ids=[conversation_id], run_ids=deletable_run_ids)
            )
            scratch_deleted = self._delete_owned_scratch(preview.checkpoint_threads_deleted)
            deleted_threads: list[str] = []
            for thread_id in preview.checkpoint_threads_deleted:
                if delete_checkpoint_thread(self.paths.checkpoints_db, thread_id):
                    deleted_threads.append(thread_id)
            self._delete_application_rows(conversation_id, deletable_run_ids,
                deleted_thread_ids=deleted_threads, include_diagnostics=include_diagnostics)
        return preview.model_copy(
            update={
                "affected_assets": asset_preview.affected_asset_ids,
                "retained_assets": asset_preview.preserved_asset_ids,
                "checkpoint_threads_deleted": deleted_threads,
                "scratch_deleted": scratch_deleted,
                "diagnostics_deleted": include_diagnostics,
            }
        )

    def collect_verified_outputs_for_run(self, session_id: str, run_id: str) -> OutputCollectionResult:
        conversation = self.app_store.get_conversation(session_id)
        run = self.app_store.get_run(run_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found.")
        if run.id not in conversation.run_ids:
            raise HTTPException(status_code=403, detail="Run does not belong to conversation.")
        if run.status.value not in TERMINAL_RUN_STATUSES:
            raise HTTPException(status_code=409, detail="Run must be terminal before collecting outputs.")
        created: list[RetainedAsset] = []
        skipped: list[dict[str, str]] = []
        for call in _successful_file_calls(run):
            call_id = str(call.get("id") or call.get("tool_call_id") or "")
            if not call_id:
                skipped.append({"reason": "missing_call_id", "tool": str(call.get("name") or call.get("tool") or "")})
                continue
            consumer_id = _tool_call_consumer_id(run.id, call_id)
            if self.assets.store.asset_ids_for_consumer(kind="tool_call", consumer_id=consumer_id):
                skipped.append({"reason": "already_collected", "call_id": call_id})
                continue
            path = _call_path(call)
            if not path:
                skipped.append({"reason": "missing_path", "call_id": call_id})
                continue
            try:
                asset = self.assets.register_verified_output(
                    RegisterVerifiedOutputRequest(
                        run_id=run.id,
                        session_id=session_id,
                        source_tool_call_id=call_id,
                        mutable_reference=path,
                    )
                )
            except HTTPException as exc:
                skipped.append({"reason": str(exc.detail), "call_id": call_id})
                continue
            self.assets.store.add_consumer(asset.id, kind="tool_call", consumer_id=consumer_id, recorded_at=asset.observed_at)
            created.append(asset)
        return OutputCollectionResult(run_id=run.id, created_assets=created, skipped=skipped)

    def _checkpoint_thread_plan(self, conversation: object, runs: list[AgentRun]) -> tuple[list[str], list[str]]:
        candidate_threads = {
            value
            for value in [getattr(conversation, "thread_id", None), *(run.thread_id for run in runs)]
            if value
        }
        surviving_threads = self._surviving_threads(
            excluding_conversation=getattr(conversation, "id"),
            excluding_run_ids={run.id for run in runs},
            source_conversation_id=getattr(conversation, "id"),
            source_run_ids={run.id for run in runs},
            source_threads=candidate_threads,
        )
        affected = sorted(thread for thread in candidate_threads if thread not in surviving_threads)
        retained = sorted(thread for thread in candidate_threads if thread in surviving_threads)
        return affected, retained

    def _surviving_threads(
        self,
        *,
        excluding_conversation: str,
        excluding_run_ids: set[str],
        source_conversation_id: str,
        source_run_ids: set[str],
        source_threads: set[str],
    ) -> set[str]:
        threads: set[str] = set()
        for conversation in self._all_conversations():
            if conversation.id == excluding_conversation:
                continue
            if (
                conversation.source_conversation_id == source_conversation_id
                or (conversation.source_run_id and conversation.source_run_id in source_run_ids)
            ):
                threads.update(source_threads)
            for value in (
                conversation.thread_id,
            ):
                if value:
                    threads.add(value)
        for run in self.app_store.list_runs():
            if run.id in excluding_run_ids:
                continue
            if run.thread_id:
                threads.add(run.thread_id)
        return threads

    def _surviving_run_ids(self, excluding_conversation: str, candidate_run_ids: set[str]) -> set[str]:
        surviving: set[str] = set()
        for conversation in self._all_conversations():
            if conversation.id == excluding_conversation:
                continue
            surviving.update(run_id for run_id in conversation.run_ids if run_id in candidate_run_ids)
            if conversation.source_run_id and conversation.source_run_id in candidate_run_ids:
                surviving.add(conversation.source_run_id)
        return surviving

    def _all_conversations(self) -> list[ChatConversation]:
        with self.app_store._lock:
            rows = self.app_store._conn.execute("SELECT payload FROM conversations").fetchall()
        return [ChatConversation.model_validate_json(row["payload"]) for row in rows]

    def _delete_owned_scratch(self, thread_ids: list[str]) -> list[str]:
        deleted: list[str] = []
        root = (self.paths.state / "harness").resolve()
        for thread_id in thread_ids:
            scratch = harness_scratch_root(self.paths, thread_id).resolve()
            try:
                scratch.relative_to(root)
            except ValueError:
                continue
            if scratch.exists():
                shutil.rmtree(scratch)
                deleted.append(str(scratch))
        return deleted

    def _delete_application_rows(
        self,
        conversation_id: str,
        run_ids: list[str],
        *,
        deleted_thread_ids: list[str],
        include_diagnostics: bool,
    ) -> None:
        with self.app_store._lock:
            selectors = ["conversation_id = ?"]
            parameters = [conversation_id]
            if deleted_thread_ids:
                selectors.append(f"graph_thread_id IN ({','.join('?' for _ in deleted_thread_ids)})")
                parameters.extend(deleted_thread_ids)
            thread_rows = self.app_store._conn.execute(
                "SELECT id FROM interaction_threads WHERE " + " OR ".join(selectors),
                parameters,
            ).fetchall()
            for row in thread_rows:
                self.app_store._conn.execute("DELETE FROM interaction_events WHERE thread_id = ?", (row["id"],))
                self.app_store._conn.execute("DELETE FROM interaction_threads WHERE id = ?", (row["id"],))
            for run_id in run_ids:
                self.app_store._conn.execute("DELETE FROM run_checkpoints WHERE run_id = ?", (run_id,))
                self.app_store._conn.execute("DELETE FROM run_files WHERE run_id = ?", (run_id,))
                if include_diagnostics:
                    self.app_store._conn.execute("DELETE FROM external_effects WHERE run_id = ?", (run_id,))
                self.app_store._conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            self.app_store._conn.execute(
                "DELETE FROM chat_submission_cancellations WHERE conversation_id = ?", (conversation_id,),
            )
            for thread_id in deleted_thread_ids:
                self.app_store._conn.execute(
                    "DELETE FROM permission_grants WHERE json_extract(payload, '$.scope') = 'session' "
                    "AND json_extract(payload, '$.thread_id') = ?", (thread_id,),
                )
            self.app_store._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            self.app_store._conn.commit()


def _successful_file_calls(run: AgentRun) -> list[dict[str, Any]]:
    calls = [
        item
        for item in [*run.tool_invocations, *_event_tool_calls(run)]
        if _tool_name(item) in WRITE_TOOLS and _tool_invocation_succeeded(item)
    ]
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for call in calls:
        call_id = str(call.get("id") or call.get("tool_call_id") or "")
        if not call_id or call_id in seen:
            continue
        seen.add(call_id)
        unique.append(call)
    return unique


def _tool_name(call: dict[str, Any]) -> str:
    return str(call.get("name") or call.get("tool") or "")


def _call_path(call: dict[str, Any]) -> str | None:
    for value in _tool_result_paths(call):
        if value.strip():
            return value
    return None


def _tool_call_consumer_id(run_id: str, call_id: str) -> str:
    return f"{run_id}:{call_id}"
