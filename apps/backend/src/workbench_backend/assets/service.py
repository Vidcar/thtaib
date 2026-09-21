"""Retained asset validation, access checks and current-user content assembly."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import uuid
from pathlib import Path, PurePath
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from workbench_backend.agents.schemas import AgentRun
from workbench_backend.assets.schemas import (
    AssetContentKind,
    RegisterVerifiedOutputRequest,
    RetainedAsset,
    RetainedAssetContent,
    RetainedAssetDeletionPreview,
    RetainedAssetDeletionRequest,
    RetainedAssetListFilters,
    RetainedAssetOrigin,
    RetainedAssetPreview,
    RetainedAssetReuseRequest,
    RetainedAssetScope,
    RetainedUploadRequest,
)
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.assets.store import RetainedAssetStore
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.user_content import TextContentBlock
from workbench_backend.state.store import ApplicationStore

MAX_ASSET_BYTES = 1_000_000
PREVIEW_CHARS = 4_000
SUPPORTED_TEXT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/x-yaml",
    "text/yaml",
    "application/xml",
    "text/xml",
}
SUPPORTED_CODE_PREFIXES = ("text/",)
SUPPORTED_CODE_TYPES = {
    "application/javascript",
    "application/typescript",
    "application/x-python-code",
    "application/x-powershell",
    "application/x-sh",
}


class RetainedAssetService:
    def __init__(self, app_store: ApplicationStore) -> None:
        self.store = RetainedAssetStore(app_store)
        self.app_store = app_store

    def retain_upload(self, request: RetainedUploadRequest) -> RetainedAsset:
        conversation = self._require_session(request.session_id)
        content = _decode_base64(request.content_base64)
        text = _validate_text_content(content, request.content_type, request.content_kind)
        return self._create_asset(
            origin=RetainedAssetOrigin.upload,
            session_id=request.session_id,
            project_path=_conversation_project_path(conversation),
            filename=request.filename,
            content_type=request.content_type,
            content_kind=request.content_kind,
            content=content,
            text=text,
        )

    def register_verified_output(self, request: RegisterVerifiedOutputRequest) -> RetainedAsset:
        conversation = self._require_session(request.session_id)
        run = self.app_store.get_run(request.run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found.")
        if run.id not in conversation.run_ids:
            raise HTTPException(status_code=403, detail="Run does not belong to the retained-output session.")
        project_path = _conversation_project_path(conversation) or run.project_path
        if not project_path:
            raise HTTPException(status_code=409, detail="Verified file outputs require a project-scoped run.")
        try:
            file_path = _resolve_scoped_file(project_path, request.mutable_reference)
            if file_path.stat().st_size > MAX_ASSET_BYTES:
                raise HTTPException(status_code=413, detail="Output exceeds the retained text/code size limit.")
        except OSError as exc:
            raise HTTPException(status_code=409, detail="The output is no longer available for verification.") from exc
        tool = self._require_successful_tool_observation(run, request, file_path=file_path, project_path=project_path)
        related_paths = {
            str(Path(item.path).resolve())
            for item in run.related_files
            if item.kind in {"written_file", "artifact"}
        }
        if str(file_path) not in related_paths:
            raise HTTPException(
                status_code=409,
                detail="Verified outputs require the exact observed project file record.",
            )
        try:
            content = file_path.read_bytes()
        except OSError as exc:
            raise HTTPException(status_code=409, detail="The output changed or became unavailable before retention.") from exc
        if len(content) > MAX_ASSET_BYTES:
            raise HTTPException(status_code=413, detail="Output exceeds the retained text/code size limit.")
        content_type = request.content_type or _guess_content_type(file_path.name)
        text = _validate_text_content(content, content_type, request.content_kind)
        digest = hashlib.sha256(content).hexdigest()
        result_hash = _tool_result_hash(tool)
        if result_hash and result_hash != digest:
            raise HTTPException(
                status_code=409,
                detail="Observed file hash does not match the successful tool result.",
            )
        if not result_hash and _later_tool_mentions_file(run, request.source_tool_call_id, file_path, project_path):
            raise HTTPException(
                status_code=409,
                detail="Cannot verify current bytes against the earlier successful tool result after a later write touched the same file.",
            )
        asset = self._create_asset(
            origin=RetainedAssetOrigin.verified_output,
            session_id=request.session_id,
            project_path=project_path,
            filename=request.filename or file_path.name,
            content_type=content_type,
            content_kind=request.content_kind,
            content=content,
            text=text,
            source_run_id=run.id,
            source_tool_call_id=request.source_tool_call_id,
            source_tool_name=str(tool.get("name") or tool.get("tool") or ""),
            mutable_reference=request.mutable_reference,
            observation=f"Observed {len(content)} bytes from {file_path}.",
        )
        self.store.add_consumer(asset.id, kind="run", consumer_id=run.id, recorded_at=asset.observed_at)
        return asset

    def list_assets(self, filters: RetainedAssetListFilters | None = None) -> list[RetainedAsset]:
        filters = filters or RetainedAssetListFilters()
        return self.store.list(
            session_id=filters.session_id,
            project_path=filters.project_path,
            origin=filters.origin.value if filters.origin else None,
            include_deleted=filters.include_deleted,
        )

    def preview(
        self,
        asset_id: str,
        *,
        session_id: str | None = None,
        project_path: str | None = None,
    ) -> RetainedAssetPreview:
        asset, text = self._load_text(asset_id, session_id=session_id, project_path=project_path)
        preview = text[:PREVIEW_CHARS]
        return RetainedAssetPreview(
            id=asset.id,
            filename=asset.filename,
            content_type=asset.content_type,
            size_bytes=asset.size_bytes,
            sha256=asset.sha256,
            preview=preview,
            truncated=len(text) > len(preview),
            source_status=_source_status(asset),
        )

    def content(
        self,
        asset_id: str,
        *,
        session_id: str | None = None,
        project_path: str | None = None,
    ) -> RetainedAssetContent:
        asset, text = self._load_text(asset_id, session_id=session_id, project_path=project_path)
        return RetainedAssetContent(
            id=asset.id,
            filename=asset.filename,
            content_type=asset.content_type,
            text=text,
            sha256=asset.sha256,
            size_bytes=asset.size_bytes,
            source_status=_source_status(asset),
        )

    def current_user_content(self, request: RetainedAssetReuseRequest) -> list[TextContentBlock]:
        with self.app_store._lock:
            blocks: list[TextContentBlock] = []
            total = 0
            for asset_id in request.asset_ids:
                asset, text = self._load_text(
                    asset_id,
                    session_id=request.session_id,
                    project_path=request.project_path,
                    allow_cross_session_reuse=request.allow_cross_session_reuse,
                )
                labelled = (
                    f"Source retained file: {asset.filename}\n"
                    f"Asset id: {asset.id}\n"
                    f"Origin: {asset.origin.value}\n"
                    f"SHA-256: {asset.sha256}\n\n"
                    f"{text}"
                )
                total += len(labelled)
                if total > request.max_chars:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            "Selected retained content does not fit in the current user input. "
                            "Choose fewer files or authorize a scoped read path."
                        ),
                    )
                try:
                    blocks.append(TextContentBlock(text=labelled))
                except ValidationError as exc:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            "Selected retained content does not fit in the current user input. "
                            "Choose fewer files or authorize a scoped read path."
                        ),
                    ) from exc
                if request.session_id:
                    self.store.add_consumer(asset.id, kind="session", consumer_id=request.session_id, recorded_at=utc_now())
            return blocks

    def require_active_assets(
        self,
        asset_ids: list[str],
        *,
        session_id: str | None = None,
        project_path: str | None = None,
    ) -> None:
        with self.app_store._lock:
            for asset_id in dict.fromkeys(asset_ids):
                self._load_text(asset_id, session_id=session_id, project_path=project_path)

    def deletion_preview(self, request: RetainedAssetDeletionRequest) -> RetainedAssetDeletionPreview:
        with self.app_store._lock:
            return self._deletion_preview_locked(request)

    def _deletion_preview_locked(self, request: RetainedAssetDeletionRequest) -> RetainedAssetDeletionPreview:
        requested = self._resolve_requested_asset_ids(request)
        consumers = self.store.consumers(requested)
        referenced_sessions = self._conversation_attachment_references(requested)
        affected_sessions: set[str] = set(request.session_ids)
        retained_sessions: set[str] = set()
        affected_runs: set[str] = set(request.run_ids)
        retained_runs: set[str] = set()
        affected_projects: set[str] = set(request.project_paths)
        retained_projects: set[str] = set()
        affected_branches: set[str] = set(request.branch_ids)
        retained_branches: set[str] = set()
        affected_cases: set[str] = set(request.case_ids)
        retained_cases: set[str] = set()
        affected_assets: list[str] = []
        preserved_assets: list[str] = []
        selected_sessions = set(request.session_ids)
        selected_runs = set(request.run_ids)
        selected_projects = set(request.project_paths)
        selected_branches = set(request.branch_ids)
        selected_cases = set(request.case_ids)
        selected_assets = set(request.asset_ids)
        assets = {
            asset_id: loaded[0]
            for asset_id in requested
            if (loaded := self.store.get(asset_id)) is not None
        }
        for asset_id in requested:
            asset = assets.get(asset_id)
            explicit_asset = asset_id in selected_assets
            shared = False
            for session_id in referenced_sessions.get(asset_id, set()):
                if session_id in selected_sessions:
                    affected_sessions.add(session_id)
                else:
                    retained_sessions.add(session_id)
                    shared = True
            for consumer in consumers.get(asset_id, []):
                kind = consumer["kind"]
                consumer_id = consumer["id"]
                if kind == "session":
                    if consumer_id in selected_sessions:
                        affected_sessions.add(consumer_id)
                    elif explicit_asset and asset is not None and consumer_id == asset.session_id:
                        affected_sessions.add(consumer_id)
                    else:
                        retained_sessions.add(consumer_id)
                        shared = True
                elif kind == "run":
                    if consumer_id in selected_runs:
                        affected_runs.add(consumer_id)
                    else:
                        retained_runs.add(consumer_id)
                        shared = True
                elif kind == "project":
                    if consumer_id in selected_projects:
                        affected_projects.add(consumer_id)
                    elif explicit_asset and asset is not None and consumer_id == asset.project_path:
                        affected_projects.add(consumer_id)
                    else:
                        retained_projects.add(consumer_id)
                        shared = True
                elif kind == "branch":
                    if consumer_id in selected_branches:
                        affected_branches.add(consumer_id)
                    else:
                        retained_branches.add(consumer_id)
                        shared = True
                elif kind == "case":
                    if consumer_id in selected_cases:
                        affected_cases.add(consumer_id)
                    else:
                        retained_cases.add(consumer_id)
                        shared = True
                elif kind == "tool_call":
                    # Collection deduplication belongs to the run; it is not
                    # an independent surviving consumer of its output bytes.
                    if consumer_id.partition(":")[0] not in selected_runs:
                        shared = True
                elif asset_id not in selected_assets:
                    shared = True
            if shared:
                preserved_assets.append(asset_id)
            else:
                affected_assets.append(asset_id)
        return RetainedAssetDeletionPreview(
            requested_asset_ids=requested,
            affected_asset_ids=affected_assets,
            preserved_asset_ids=preserved_assets,
            affected_sessions=sorted(affected_sessions),
            retained_sessions=sorted(retained_sessions),
            affected_runs=sorted(affected_runs),
            retained_runs=sorted(retained_runs),
            affected_projects=sorted(affected_projects),
            retained_projects=sorted(retained_projects),
            affected_branches=sorted(affected_branches),
            retained_branches=sorted(retained_branches),
            affected_cases=sorted(affected_cases),
            retained_cases=sorted(retained_cases),
        )

    def mark_deletable_assets_deleted(self, request: RetainedAssetDeletionRequest) -> RetainedAssetDeletionPreview:
        with self.app_store._lock:
            preview = self._deletion_preview_locked(request)
            selected = _selected_consumers(request)
            selected_runs = set(request.run_ids)
            for consumers in self.store.consumers(preview.requested_asset_ids).values():
                selected.extend(
                    consumer for consumer in consumers
                    if consumer["kind"] == "tool_call"
                    and consumer["id"].partition(":")[0] in selected_runs
                )
            for asset_id in preview.preserved_asset_ids:
                self.store.delete_consumers(asset_id, selected)
            now = utc_now()
            for asset_id in preview.affected_asset_ids:
                self.store.delete_consumers(asset_id, selected)
                self.store.mark_deleted(asset_id, now)
            return preview

    def _conversation_attachment_references(self, asset_ids: list[str]) -> dict[str, set[str]]:
        wanted = set(asset_ids)
        if not wanted:
            return {}
        rows = self.app_store._conn.execute("SELECT payload FROM conversations").fetchall()
        result: dict[str, set[str]] = {}
        for row in rows:
            conversation = ChatConversation.model_validate_json(row["payload"])
            referenced: set[str] = set()
            for message in conversation.transcript:
                referenced.update(message.attachment_ids)
            if conversation.draft is not None:
                referenced.update(conversation.draft.attachment_ids)
            for item in conversation.queue:
                referenced.update(item.attachment_ids)
            for asset_id in wanted & referenced:
                result.setdefault(asset_id, set()).add(conversation.id)
        return result

    def _create_asset(
        self,
        *,
        origin: RetainedAssetOrigin,
        session_id: str,
        project_path: str | None,
        filename: str,
        content_type: str,
        content_kind: AssetContentKind,
        content: bytes,
        text: str,
        source_run_id: str | None = None,
        source_tool_call_id: str | None = None,
        source_tool_name: str | None = None,
        mutable_reference: str | None = None,
        observation: str | None = None,
    ) -> RetainedAsset:
        filename = _safe_filename(filename)
        digest = hashlib.sha256(content).hexdigest()
        now = utc_now()
        asset = RetainedAsset(
            id=f"asset_{uuid.uuid4().hex}",
            origin=origin,
            scope=RetainedAssetScope.session,
            session_id=session_id,
            project_path=project_path,
            access_scope=f"session:{session_id}",
            filename=filename,
            content_type=content_type,
            content_kind=content_kind,
            size_bytes=len(content),
            sha256=digest,
            observed_at=now,
            source_run_id=source_run_id,
            source_tool_call_id=source_tool_call_id,
            source_tool_name=source_tool_name,
            mutable_reference=mutable_reference,
            observation=observation,
        )
        self.store.put(asset, content)
        self.store.add_consumer(asset.id, kind="session", consumer_id=session_id, recorded_at=now)
        if project_path:
            self.store.add_consumer(asset.id, kind="project", consumer_id=project_path, recorded_at=now)
        return asset

    def _load_text(
        self,
        asset_id: str,
        *,
        session_id: str | None,
        project_path: str | None,
        allow_cross_session_reuse: bool = False,
    ) -> tuple[RetainedAsset, str]:
        loaded = self.store.get(asset_id)
        if loaded is None:
            raise HTTPException(status_code=404, detail="Retained asset not found.")
        asset, content = loaded
        if asset.deleted_at is not None:
            raise HTTPException(status_code=410, detail="Retained asset was deleted.")
        self._check_access(
            asset,
            session_id=session_id,
            project_path=project_path,
            allow_cross_session_reuse=allow_cross_session_reuse,
        )
        return asset, content.decode("utf-8")

    def _check_access(
        self,
        asset: RetainedAsset,
        *,
        session_id: str | None,
        project_path: str | None,
        allow_cross_session_reuse: bool = False,
    ) -> None:
        if session_id == asset.session_id:
            return
        if session_id and self.store.has_consumer(asset.id, kind="session", consumer_id=session_id):
            return
        if asset.project_path and project_path == asset.project_path:
            return
        if allow_cross_session_reuse and session_id:
            return
        raise HTTPException(status_code=403, detail="Current session or project cannot access this retained asset.")

    def _resolve_requested_asset_ids(self, request: RetainedAssetDeletionRequest) -> list[str]:
        requested = list(dict.fromkeys(request.asset_ids))
        for session_id in request.session_ids:
            requested.extend(asset.id for asset in self.store.list(session_id=session_id, include_deleted=False))
            requested.extend(self.store.asset_ids_for_consumer(kind="session", consumer_id=session_id))
        for run_id in request.run_ids:
            requested.extend(self.store.asset_ids_for_consumer(kind="run", consumer_id=run_id))
        for project_path in request.project_paths:
            requested.extend(self.store.asset_ids_for_consumer(kind="project", consumer_id=project_path))
        for branch_id in request.branch_ids:
            requested.extend(self.store.asset_ids_for_consumer(kind="branch", consumer_id=branch_id))
        for case_id in request.case_ids:
            requested.extend(self.store.asset_ids_for_consumer(kind="case", consumer_id=case_id))
        return list(dict.fromkeys(requested))

    def _require_session(self, session_id: str):
        conversation = self.app_store.get_conversation(session_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation session not found.")
        return conversation

    def _require_terminal_run(self, run: AgentRun) -> None:
        if run.status.value not in {"completed", "failed", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail="Verified outputs require a terminal run with an observed successful tool call.",
            )

    def _require_successful_tool_observation(
        self,
        run: AgentRun,
        request: RegisterVerifiedOutputRequest,
        *,
        file_path: Path,
        project_path: str,
    ) -> dict[str, Any]:
        self._require_terminal_run(run)
        tool_matches = [
            item
            for item in _merged_tool_observations(run)
            if item.get("id") == request.source_tool_call_id
            or item.get("tool_call_id") == request.source_tool_call_id
        ]
        if not tool_matches:
            raise HTTPException(
                status_code=409,
                detail="Verified outputs require the exact successful tool call id.",
            )
        tool = next((item for item in tool_matches if _tool_invocation_succeeded(item)), None)
        if tool is None:
            raise HTTPException(
                status_code=409,
                detail="Failed or denied tool attempts are not retained outputs.",
            )
        if not _tool_result_mentions_file(tool, file_path, project_path):
            raise HTTPException(
                status_code=409,
                detail="Successful tool result does not match the requested mutable file.",
            )
        return tool


def _decode_base64(value: str) -> bytes:
    try:
        content = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="Invalid base64 content.") from exc
    if not content:
        raise HTTPException(status_code=422, detail="Retained content cannot be empty.")
    if len(content) > MAX_ASSET_BYTES:
        raise HTTPException(status_code=413, detail="Retained text/code content is over the size limit.")
    return content


def _validate_text_content(content: bytes, content_type: str, content_kind: AssetContentKind) -> str:
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    supported = normalized_type in SUPPORTED_TEXT_TYPES
    if content_kind is AssetContentKind.code:
        supported = supported or normalized_type in SUPPORTED_CODE_TYPES or normalized_type.startswith(SUPPORTED_CODE_PREFIXES)
    if not supported:
        raise HTTPException(status_code=415, detail="Only supported text/code content can be retained by this endpoint.")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Retained text/code content must be valid UTF-8.") from exc
    if "\x00" in text:
        raise HTTPException(status_code=422, detail="Retained text/code content cannot contain NUL bytes.")
    try:
        TextContentBlock(text=text)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Retained text/code content is not valid current-user text.") from exc
    return text


def _safe_filename(filename: str) -> str:
    name = PurePath(filename.replace("\\", "/")).name.strip()
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=422, detail="Filename must name a file, not a path.")
    return name


def _guess_content_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return {
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".json": "application/json",
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
        ".xml": "application/xml",
        ".py": "text/x-python",
        ".ts": "application/typescript",
        ".tsx": "application/typescript",
        ".js": "application/javascript",
        ".jsx": "application/javascript",
        ".ps1": "application/x-powershell",
        ".sh": "application/x-sh",
    }.get(suffix, "text/plain")


def _tool_invocation_succeeded(invocation: dict[str, Any]) -> bool:
    has_result_event = "result_status" in invocation or "content" in invocation or "result" in invocation
    if not has_result_event:
        return False
    status = str(invocation.get("status") or invocation.get("outcome") or "").lower()
    result_status = str(invocation.get("result_status") or "").lower()
    if result_status in {"failed", "error", "denied", "rejected"}:
        return False
    if status in {"failed", "error", "denied", "rejected"}:
        return False
    if invocation.get("error") or invocation.get("denied"):
        return False
    content = str(invocation.get("content") or invocation.get("message") or "")
    if content.lower().startswith(("error", "failed", "denied", "rejected")):
        return False
    if "content" in invocation:
        return True
    if result_status == "success":
        return True
    if status in {"succeeded", "success", "completed", "ok"}:
        return True
    result = invocation.get("result")
    return result is not None


def _event_tool_calls(run: AgentRun) -> list[dict[str, Any]]:
    return _merged_tool_observations(run)


def _conversation_project_path(conversation: object) -> str | None:
    area = getattr(conversation, "area_project_path", None)
    project = getattr(conversation, "project_path", None)
    return str(project or area) if area or project else None


def _source_status(asset: RetainedAsset) -> str:
    if not asset.mutable_reference or not asset.project_path:
        return "retained_only"
    try:
        source = _resolve_scoped_file(asset.project_path, asset.mutable_reference)
        if source.stat().st_size != asset.size_bytes:
            return "changed"
        return "unchanged" if hashlib.sha256(source.read_bytes()).hexdigest() == asset.sha256 else "changed"
    except FileNotFoundError:
        return "missing"
    except (OSError, HTTPException):
        return "unavailable"


def _resolve_scoped_file(project_path: str, mutable_reference: str) -> Path:
    project = Path(project_path).resolve(strict=True)
    candidate = Path(mutable_reference)
    if candidate.root and not candidate.drive:
        candidate = project / str(candidate).lstrip("\\/")
    elif not candidate.is_absolute():
        candidate = project / candidate
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(project)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Verified output path is outside the scoped project.") from exc
    if not resolved.is_file():
        raise HTTPException(status_code=409, detail="Verified output path is not a readable file.")
    return resolved


def _tool_result_paths(invocation: dict[str, Any]) -> list[str]:
    result = invocation.get("result")
    candidates: list[str] = []
    if isinstance(result, dict):
        for key in ("path", "file_path", "target", "written_path"):
            value = result.get(key)
            if isinstance(value, str):
                candidates.append(value)
    args = invocation.get("args")
    if isinstance(args, dict):
        for key in ("path", "file_path", "target", "written_path"):
            value = args.get(key)
            if isinstance(value, str):
                candidates.append(value)
    return candidates


def _tool_result_mentions_file(invocation: dict[str, Any], file_path: Path, project_path: str) -> bool:
    wanted = _path_key(file_path)
    return any(
        _scoped_observed_path(item, project_path) == wanted
        for item in _tool_result_paths(invocation)
    )


def _scoped_observed_path(value: str, project_path: str) -> str | None:
    if not value.strip():
        return None
    project = Path(project_path).resolve()
    candidate = Path(value)
    if candidate.root and not candidate.drive:
        candidate = project / str(candidate).lstrip("\\/")
    elif not candidate.is_absolute():
        candidate = project / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(project)
    except ValueError:
        return None
    return _path_key(resolved)


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=False)))


def _later_tool_mentions_file(run: AgentRun, source_tool_call_id: str, file_path: Path, project_path: str) -> bool:
    seen_source = False
    for invocation in _merged_tool_observations(run):
        call_id = str(invocation.get("id") or invocation.get("tool_call_id") or "")
        if call_id == source_tool_call_id:
            seen_source = True
            continue
        if not seen_source:
            continue
        if _tool_result_mentions_file(invocation, file_path, project_path):
            return True
    return False


def _merged_tool_observations(run: AgentRun) -> list[dict[str, Any]]:
    calls_by_id: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []

    def merge(value: dict[str, Any]) -> None:
        call = dict(value)
        if "id" not in call and call.get("tool_call_id"):
            call["id"] = call["tool_call_id"]
        if "name" not in call and call.get("tool"):
            call["name"] = call["tool"]
        call_id = str(call.get("id") or call.get("tool_call_id") or "")
        if not call_id:
            return
        if call_id not in calls_by_id:
            calls_by_id[call_id] = {"id": call_id}
            ordered_ids.append(call_id)
        calls_by_id[call_id].update(call)

    for item in run.tool_invocations:
        merge(item)
    for event in run.events:
        detail = event.detail
        if event.kind == "tool_call":
            merge(detail)
            continue
        if event.kind == "tool_result":
            call_id = str(detail.get("tool_call_id") or detail.get("id") or "")
            if call_id:
                observation: dict[str, Any] = {"id": call_id, "result_status": str(detail.get("status") or "").lower()}
                if detail.get("name"):
                    observation["name"] = detail.get("name")
                if detail.get("content") is not None:
                    observation["content"] = detail.get("content")
                if isinstance(detail.get("result"), dict):
                    observation["result"] = detail.get("result")
                merge(observation)
        for key in ("tool_call", "tool_invocation", "invocation"):
            value = detail.get(key)
            if isinstance(value, dict):
                merge(value)
        value = detail.get("tool_calls")
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    merge(item)
    return [calls_by_id[call_id] for call_id in ordered_ids]


def _tool_result_hash(invocation: dict[str, Any]) -> str | None:
    result = invocation.get("result")
    if not isinstance(result, dict):
        return None
    for key in ("sha256", "hash", "content_sha256"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _selected_consumers(request: RetainedAssetDeletionRequest) -> list[dict[str, str]]:
    consumers: list[dict[str, str]] = []
    consumers.extend({"kind": "session", "id": item} for item in request.session_ids)
    consumers.extend({"kind": "run", "id": item} for item in request.run_ids)
    consumers.extend({"kind": "project", "id": item} for item in request.project_paths)
    consumers.extend({"kind": "branch", "id": item} for item in request.branch_ids)
    consumers.extend({"kind": "case", "id": item} for item in request.case_ids)
    return consumers
