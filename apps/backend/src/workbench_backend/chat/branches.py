"""Explicit Chat branches using public checkpoint and existing snapshot APIs."""

from __future__ import annotations

import copy

import shutil

from pathlib import Path

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from workbench_backend.agents.schemas import AgentStartRequest

from workbench_backend.chat.schemas import ChatDraft

from workbench_backend.contracts.lifecycle import is_run_lifecycle_live

from workbench_backend.errors import ChatError

from workbench_backend.inference.ids import new_id, utc_now

from workbench_backend.lab.schemas import LabWorkspace, SnapshotManifest

from workbench_backend.lab.snapshot import restore_snapshot_tree

from workbench_backend.state.checkpointer import open_sqlite_checkpointer, delete_checkpoint_thread

class BranchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_run_id: str
    mode: Literal["continue", "retry", "edit", "regenerate"] = "continue"
    edited_task: str | None = None
    acknowledge_repeated_effects: bool = False

class ReplyActions(BaseModel):
    branch_available: bool
    retry_available: bool
    regenerate_available: bool = False
    branch_reason: str | None = None
    retry_reason: str | None = None
    regenerate_reason: str | None = None

class ChatBranches:

    def __init__(self, chat):
        self.chat = chat

    def actions(self, conversation_id: str, run_id: str) -> ReplyActions:
        conversation, run = self._source(conversation_id, run_id)
        branch_reason = self._reason(conversation, run, "continue")
        retry_reason = self._reason(conversation, run, "retry")
        regenerate_reason = self._reason(conversation, run, "regenerate")
        return ReplyActions(branch_available=branch_reason is None, retry_available=retry_reason is None,
            branch_reason=branch_reason, retry_reason=retry_reason,
            regenerate_available=regenerate_reason is None, regenerate_reason=regenerate_reason)

    def create(self, conversation_id: str, request: BranchRequest):
        chat = self.chat
        with chat.manager.lifecycle.mutate("chat_branch"), chat.store.conversation_lock(conversation_id):
            conversation, run = self._source(conversation_id, request.source_run_id)
            reason = self._reason(conversation, run, request.mode)
            if reason:
                raise ChatError(reason, code="branch_unavailable", status_code=409)

            if request.mode not in {"continue", "regenerate"} and not request.acknowledge_repeated_effects:
                raise ChatError("Retry may repeat file changes or external actions. Confirm before preparing this attempt.", code="retry_confirmation_required", status_code=409)

            if request.mode == "edit" and not (request.edited_task or "").strip():
                raise ChatError("An edited task is required.", code="task_required", status_code=400)
            index = conversation.run_ids.index(run.id)
            source_checkpoint = (
                find_pre_answer_checkpoint(
                    chat.manager.paths.checkpoints_db,
                    run.thread_id,
                    set(run.checkpoint_ids),
                    state_reader=lambda checkpoint_id: chat.harness.checkpoint_state_for_run(run, checkpoint_id),
                )
                if request.mode == "regenerate"
                else self._checkpoint(conversation, run, request.mode)
            )
            source_run = run if request.mode in {"continue", "regenerate"} or index == 0 else chat.harness.get_run(conversation.run_ids[index - 1])
            branch = conversation.model_copy(deep=True)
            branch.id = new_id("chat")
            branch.thread_id = new_id("thread")
            label = "branch" if request.mode == "continue" else ("regenerate" if request.mode == "regenerate" else "retry")
            branch.title = f"{conversation.title or 'Chat'} — {label}"
            branch.source_conversation_id = conversation.id
            branch.source_run_id = run.id
            branch.source_checkpoint_id = source_checkpoint
            branch.branch_head_checkpoint_id = source_checkpoint
            branch.current_run_id = None
            branch.archived = False
            branch.archived_at = None
            branch.queue = []
            branch.created_at = branch.updated_at = utc_now()
            kept = set(conversation.run_ids[:index + (1 if request.mode in {"continue", "regenerate"} else 0)])
            branch.run_ids = [ident for ident in conversation.run_ids if ident in kept]
            branch.transcript = [
                message for message in conversation.transcript
                if message.run_id in kept and not (request.mode == "regenerate" and message.run_id == run.id and message.role == "assistant")
            ]
            branch.deployment_id = run.deployment_id
            branch.profile_id = run.profile_id
            branch.memory_version_refs = list(run.memory_version_refs)
            branch.skill_version_refs = list(run.skill_version_refs)
            branch.protected_instruction_version_refs = list(run.protected_instruction_version_refs)
            branch.embedding_deployment_id = run.embedding_deployment_id
            branch.retrieval_project_paths = [] if run.project_path else list(run.retrieval_project_paths)
            branch.draft = None if request.mode in {"continue", "regenerate"} else ChatDraft(
                content=request.edited_task if request.mode == "edit" else run.task,
                content_blocks=[block.model_dump(mode="json") for block in run.content_blocks] if run.content_blocks else None,
                intended_config={"deployment_id": run.deployment_id, "profile_id": run.profile_id,
                    "presented_tools": list(run.presented_tools),
                    "per_request_overrides": dict(run.effective_setup.bags.per_request.requested) if run.effective_setup else {}},
                updated_at=utc_now())
            workspace = None
            destination = None
            if run.project_path:
                snapshot_id = run.final_snapshot_id if request.mode in {"continue", "regenerate"} else run.starting_snapshot_id
                manifest = SnapshotManifest.model_validate_json((chat.manager.paths.snapshots / snapshot_id / "manifest.json").read_text(encoding="utf-8"))
                workspace_id = new_id("ws")
                destination = chat.manager.paths.workspaces / workspace_id
                workspace = LabWorkspace(id=workspace_id, display_name=branch.title, path=str(destination),
                    origin="restored", parent_workspace_id=run.workspace_id, snapshot_id=manifest.id, created_at=utc_now())
                branch.workspace_id = workspace.id
                branch.project_path = workspace.path
            try:
                if source_checkpoint:
                    clone_terminal_checkpoint(
                        chat.manager.paths.checkpoints_db, source_run.thread_id, source_checkpoint, branch.thread_id,
                        include_tip_writes=request.mode != "regenerate",
                    )

                if workspace is not None:
                    restore_snapshot_tree(Path(manifest.tree_path), destination, included_files=manifest.included_files)
                    chat.lab.store.put_workspace(workspace)
                saved = chat.store.put(branch)
                if request.mode == "regenerate":
                    accepted = self._find_existing_regeneration_run(run.id, branch.thread_id)
                    if accepted is None:
                        accepted = chat.harness.start(
                            AgentStartRequest(
                                deployment_id=branch.deployment_id,
                                task=run.task,
                                input_message_id=run.input_message_id,
                                content_blocks=run.content_blocks,
                                output_schema=run.output_schema,
                                presented_tools=[],
                                system_prompt=run.system_prompt,
                                workspace_id=branch.workspace_id,
                                project_path=branch.project_path,
                                profile_id=branch.profile_id,
                                inherit_deployment_settings=branch.inherit_deployment_settings,
                                per_request_overrides=(run.effective_setup.bags.per_request.requested if run.effective_setup else {}),
                                source_surface="chat",
                                thread_id=branch.thread_id,
                                resume_checkpoint_id=source_checkpoint,
                                parent_run_id=run.id,
                                memory_version_refs=branch.memory_version_refs,
                                skill_version_refs=branch.skill_version_refs,
                                protected_instruction_version_refs=branch.protected_instruction_version_refs,
                                embedding_deployment_id=branch.embedding_deployment_id,
                                retrieval_project_paths=list(branch.retrieval_project_paths),
                            )
                        )
                    saved = saved.model_copy(deep=True)
                    saved.current_run_id = accepted.id
                    if accepted.id not in saved.run_ids:
                        saved.run_ids.append(accepted.id)
                    saved.updated_at = utc_now()
                    saved = chat.store.put(saved)
            except Exception:
                accepted = self._find_existing_regeneration_run(run.id, branch.thread_id) if request.mode == "regenerate" else None
                if accepted is None:
                    _delete_branch_conversation(chat, branch.id)
                    delete_checkpoint_thread(chat.manager.paths.checkpoints_db, branch.thread_id)
                    if workspace is not None:
                        chat.lab.store.delete_workspace_record(workspace.id)
                    if destination is not None and destination.is_relative_to(chat.manager.paths.workspaces.resolve()) and destination.is_dir():
                        shutil.rmtree(destination)
                raise
            return chat._view(saved)

    def _find_existing_regeneration_run(self, source_run_id: str, branch_thread_id: str):
        for candidate in self.chat.harness.list_runs():
            if (
                candidate.source_surface == "chat"
                and candidate.parent_run_id == source_run_id
                and candidate.thread_id == branch_thread_id
                and candidate.resume_checkpoint_id
            ):
                return candidate
        return None

    def _source(self, conversation_id, run_id):
        conversation = self.chat._require(conversation_id)
        if run_id not in conversation.run_ids:
            raise ChatError("This reply does not belong to the conversation.", code="branch_source_missing", status_code=404)

        return conversation, self.chat.harness.get_run(run_id)

    def _checkpoint(self, conversation, run, mode):
        selected = run
        if mode != "continue":
            index = conversation.run_ids.index(run.id)
            if index == 0:
                return None
            selected = self.chat.harness.get_run(conversation.run_ids[index - 1])
        retained = set(selected.checkpoint_ids)
        saver = open_sqlite_checkpointer(self.chat.manager.paths.checkpoints_db)
        # Application linkage is an unordered set. Saver history is newest-first.
        for saved in saver.list({"configurable": {"thread_id": selected.thread_id, "checkpoint_ns": ""}}):
            ident = saved.config["configurable"]["checkpoint_id"]
            if ident in retained:
                return ident

        return None

    def _reason(self, conversation, run, mode):
        if conversation.current_run_id:
            current = self.chat.harness.get_run(conversation.current_run_id)
            if is_run_lifecycle_live(current.status):
                return "Wait for the active turn to stop before branching."

        if mode == "regenerate":
            return self._regenerate_reason(conversation, run)

        if mode == "continue" and run.status != "completed":
            return "Only a completed turn has a supported continuation boundary. Use Retry task for a failed attempt."

        if mode == "continue" and not run.checkpoint_ids:
            return "This reply has no retained checkpoint."

        if mode == "continue" and not self._checkpoint(conversation, run, mode):
            return "This reply's retained checkpoint is unavailable."

        if mode != "continue" and conversation.run_ids.index(run.id) > 0:
            previous = self.chat.harness.get_run(conversation.run_ids[conversation.run_ids.index(run.id) - 1])
            if previous.status != "completed":
                return "The preceding turn has no completed boundary safe to retry from."

        if mode != "continue" and conversation.run_ids.index(run.id) > 0 and not self._checkpoint(conversation, run, mode):
            return "The checkpoint before this task is unavailable."

        if run.project_path:
            snapshot = run.final_snapshot_id if mode == "continue" else run.starting_snapshot_id
            if not snapshot or not (self.chat.manager.paths.snapshots / snapshot / "manifest.json").is_file():
                return "This turn has no matching retained project snapshot."

        return None

    def _regenerate_reason(self, conversation, run) -> str | None:
        if run.status != "completed":
            return "Only a completed assistant reply can be considered for answer regeneration."
        if not run.checkpoint_ids:
            return "This reply has no retained checkpoints to inspect for a pre-answer boundary."
        if run.project_path and (
            not run.final_snapshot_id
            or not (self.chat.manager.paths.snapshots / run.final_snapshot_id / "manifest.json").is_file()
        ):
            return "This turn has no matching retained project snapshot."
        try:
            checkpoint_id = find_pre_answer_checkpoint(
                self.chat.manager.paths.checkpoints_db,
                run.thread_id,
                set(run.checkpoint_ids),
                state_reader=lambda checkpoint_id: self.chat.harness.checkpoint_state_for_run(run, checkpoint_id),
            )
        except ChatError as exc:
            return str(exc)

        if checkpoint_id is None:
            return "No public LangGraph state-history checkpoint before this assistant answer was found."

        return None

def clone_terminal_checkpoint(
    path: Path, source_thread: str, checkpoint_id: str, target_thread: str, *, include_tip_writes: bool = True,
) -> None:
    saver = open_sqlite_checkpointer(path)
    source = saver.get_tuple({"configurable": {"thread_id": source_thread, "checkpoint_ns": "", "checkpoint_id": checkpoint_id}})
    if source is None:
        raise ChatError("The source checkpoint is no longer available.", code="branch_checkpoint_missing", status_code=409)

    if any(channel == "__interrupt__" for _task, channel, _value in source.pending_writes or []):
        raise ChatError("Interrupted checkpoints cannot be copied as completed branches.", code="branch_unavailable", status_code=409)
    # LangGraph delta channels require the original ancestor checkpoints and
    # their pending writes. Copy the complete lineage through saver APIs.
    lineage = []
    seen = set()
    current = source
    while current is not None:
        ident = current.config["configurable"]["checkpoint_id"]
        if ident in seen:
            raise ChatError("Checkpoint ancestry is cyclic.", code="branch_checkpoint_invalid", status_code=409)
        seen.add(ident)
        lineage.append(current)
        if current.parent_config is None:
            break
        current = saver.get_tuple(current.parent_config)
        if current is None:
            raise ChatError("A required ancestor checkpoint is unavailable.", code="branch_checkpoint_missing", status_code=409)
    parent = None
    for saved in reversed(lineage):
        config = {"configurable": {"thread_id": target_thread, "checkpoint_ns": ""}}
        if parent:
            config["configurable"]["checkpoint_id"] = parent
        checkpoint = copy.deepcopy(saved.checkpoint)
        metadata = copy.deepcopy(saved.metadata)
        metadata["parents"] = {}
        written = saver.put(config, checkpoint, metadata, checkpoint.get("channel_versions", {}))
        by_task = {}
        # A pre-answer checkpoint's pending writes can contain the original
        # model answer. Explicit checkpoint replay ignores those future writes,
        # but latest-state reads apply them and would seed the replaced answer
        # into Chat. Retain ancestor writes needed by delta channels only.
        writes_to_copy = saved.pending_writes if include_tip_writes or checkpoint["id"] != checkpoint_id else []
        for task_id, channel, value in writes_to_copy or []:
            by_task.setdefault(task_id, []).append((channel, copy.deepcopy(value)))

        for task_id, writes in by_task.items():
            saver.put_writes(written, writes, task_id)
        parent = checkpoint["id"]

def _delete_branch_conversation(chat: object, conversation_id: str) -> None:
    app_store = chat.app_store
    with app_store._lock:
        app_store._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        app_store._conn.commit()

def find_pre_answer_checkpoint(
    path: Path,
    source_thread: str,
    retained_checkpoint_ids: set[str],
    *,
    state_reader=None,
) -> str | None:
    """Find committed graph state immediately before a model answer.
    The returned checkpoint routes to the model, includes prior tool results
    when the source turn used tools, and excludes the final assistant answer
    being regenerated.
    """
    saver = open_sqlite_checkpointer(path)
    try:
        history = list(saver.list({"configurable": {"thread_id": source_thread, "checkpoint_ns": ""}}))
    except Exception as exc:
        raise ChatError("Could not inspect retained LangGraph checkpoint history.", code="branch_checkpoint_missing", status_code=409) from exc
    retained = [str(saved.config["configurable"].get("checkpoint_id")) for saved in history if saved.config["configurable"].get("checkpoint_id") in retained_checkpoint_ids]
    final_answer_count: int | None = None
    for checkpoint_id in retained:
        if state_reader is None:
            saved = next(item for item in history if item.config["configurable"].get("checkpoint_id") == checkpoint_id)
            values = getattr(saved, "checkpoint", {}).get("channel_values", {})
            state = {"values": values, "next": tuple(channel for channel in values if str(channel).startswith("branch:to:model"))}
        else:
            state = state_reader(checkpoint_id)
        values = state.get("values", {})
        messages = values.get("messages") or []
        answer_count = _assistant_answer_count(messages)
        if final_answer_count is None:
            final_answer_count = answer_count
            continue
        if (
            final_answer_count > 0
            and answer_count == final_answer_count - 1
            and any(str(node) == "model" or str(node).endswith(":model") for node in state.get("next", ()))
            and not _messages_have_unanswered_tool_call(messages)
        ):
            return checkpoint_id

    return None

def _messages_have_unanswered_tool_call(messages: list[Any]) -> bool:
    calls: set[str] = set()
    answered: set[str] = set()
    for message in messages:
        for call in getattr(message, "tool_calls", []) or []:
            if call.get("id"):
                calls.add(str(call["id"]))
        tool_call_id = getattr(message, "tool_call_id", None)
        if tool_call_id:
            answered.add(str(tool_call_id))
    return bool(calls - answered)

def _contains_assistant_answer(value: Any) -> bool:
    if isinstance(value, list):
        return any(_contains_assistant_answer(item) for item in value)

    return getattr(value, "type", None) == "ai" and not getattr(value, "tool_calls", None)

def _assistant_answer_count(messages: list[Any]) -> int:
    return sum(1 for message in messages if _contains_assistant_answer(message))
