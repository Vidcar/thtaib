"""STATE-005 knowledge write policy, versions and context-capture retention."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Iterable

from workbench_backend.errors import KnowledgeError
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.knowledge.redaction import apply_redaction
from workbench_backend.knowledge.schemas import (
    ContextCapture,
    ContextCaptureRequest,
    KnowledgeConfig,
    KnowledgeConfigUpdateRequest,
    KnowledgeCreateRequest,
    KnowledgeEditRequest,
    KnowledgeEntry,
    KnowledgeEntryView,
    KnowledgeKind,
    KnowledgeProvenance,
    KnowledgeRefs,
    KnowledgeRevertRequest,
    KnowledgeScope,
    KnowledgeVersion,
)
from workbench_backend.knowledge.store import KnowledgeStore
from workbench_backend.paths import WorkbenchPaths

PROTECTED_KIND = "protected_instruction"
AGENT_ACTOR = "agent"


class KnowledgeService:
    def __init__(self, paths: WorkbenchPaths) -> None:
        self.paths = paths.ensure()
        self.store = KnowledgeStore(self.paths)
        self._lock = threading.Lock()

    def get_config(self) -> KnowledgeConfig:
        return self.store.read_config()

    def update_config(self, request: KnowledgeConfigUpdateRequest) -> KnowledgeConfig:
        current = self.store.read_config()
        payload = current.model_dump()
        if request.context_captures is not None:
            payload["context_captures"] = request.context_captures.model_dump()
        if request.scope_policies is not None:
            policies = current.scope_policies | request.scope_policies
            payload["scope_policies"] = {
                scope: policy.model_dump() for scope, policy in policies.items()
            }
        return self.store.write_config(KnowledgeConfig.model_validate(payload))

    def create(self, request: KnowledgeCreateRequest) -> KnowledgeEntryView:
        self._assert_write_allowed(request.kind, request.scope, request.provenance)
        with self._lock:
            return self._create_locked(request)

    def _create_locked(self, request: KnowledgeCreateRequest) -> KnowledgeEntryView:
        now = utc_now()
        entry_id = new_id("kn")
        version_id = new_id("knv")
        version = KnowledgeVersion(
            id=version_id,
            entry_id=entry_id,
            scope=request.scope,
            scope_id=request.scope_id,
            kind=request.kind,
            content=request.content,
            provenance=request.provenance,
            previous_version_id=None,
            created_at=now,
        )
        entry = KnowledgeEntry(
            id=entry_id,
            scope=request.scope,
            scope_id=request.scope_id,
            kind=request.kind,
            display_name=request.display_name,
            current_version_id=version_id,
            created_at=now,
            updated_at=now,
        )
        self.store.append_version(version)
        self.store.put_entry(entry)
        return self._view(entry, version)

    def list_entries(self) -> list[KnowledgeEntryView]:
        return [self._require_view(entry) for entry in self.store.list_entries()]

    def get_entry(self, entry_id: str) -> KnowledgeEntryView:
        entry = self.store.get_entry(entry_id)
        if entry is None:
            raise KnowledgeError("Unknown knowledge entry", code="entry_missing", status_code=404)
        return self._require_view(entry)

    def list_versions(self, entry_id: str) -> list[KnowledgeVersion]:
        self.get_entry(entry_id)
        versions = self.store.list_versions(entry_id)
        return sorted(versions, key=lambda item: item.created_at)

    def get_version(self, version_id: str) -> KnowledgeVersion:
        version = self.store.get_version(version_id)
        if version is None:
            raise KnowledgeError(
                "Unknown knowledge version",
                code="knowledge_version_missing",
                status_code=404,
            )
        return version

    def edit(self, entry_id: str, request: KnowledgeEditRequest) -> KnowledgeEntryView:
        with self._lock:
            entry = self._require_entry(entry_id)
            self._assert_base_version(entry, request.base_version)
            self._assert_write_allowed(entry.kind, entry.scope, request.provenance)
            return self._append_version(
                entry,
                content=request.content,
                provenance=request.provenance,
                previous_version_id=entry.current_version_id,
            )

    def revert(self, entry_id: str, request: KnowledgeRevertRequest) -> KnowledgeEntryView:
        with self._lock:
            entry = self._require_entry(entry_id)
            self._assert_base_version(entry, request.base_version)
            self._assert_write_allowed(entry.kind, entry.scope, request.provenance)
            target = self.get_version(request.target_version_id)
            if target.entry_id != entry.id:
                raise KnowledgeError(
                    "Revert target does not belong to this entry.",
                    code="revert_target_mismatch",
                    status_code=400,
                )
            return self._append_version(
                entry,
                content=target.content,
                provenance=request.provenance,
                previous_version_id=entry.current_version_id,
                reverted_from_version_id=target.id,
            )

    def capture(self, request: ContextCaptureRequest) -> ContextCapture:
        config = self.get_config()
        settings = config.context_captures
        stored, redacted, fields = apply_redaction(request.content, settings.redaction_mode)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        expires_at = None
        if settings.retention_seconds is not None:
            expires_at = now + timedelta(seconds=settings.retention_seconds)
        discarded = settings.redaction_mode == "discard"
        record = ContextCapture(
            id=new_id("kcap"),
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat() if expires_at else None,
            retention_seconds=settings.retention_seconds,
            redaction_mode=settings.redaction_mode,
            content=None if discarded else stored,
            retained=not discarded,
            redacted=redacted,
            discarded=discarded,
            redacted_fields=fields,
            run_id=request.run_id,
            source=request.source,
        )
        self.store.put_capture(record)
        self._expire_captures()
        return record

    def list_captures(self) -> list[ContextCapture]:
        self._expire_captures()
        return self.store.list_captures()

    def get_capture(self, capture_id: str) -> ContextCapture:
        self._expire_captures()
        capture = self.store.get_capture(capture_id)
        if capture is None:
            raise KnowledgeError("Unknown context capture", code="capture_missing", status_code=404)
        return capture

    def resolve_refs(
        self,
        *,
        memory_version_refs: Iterable[str] | None = None,
        skill_version_refs: Iterable[str] | None = None,
        protected_instruction_version_refs: Iterable[str] | None = None,
        knowledge_version_refs: Iterable[str] | None = None,
    ) -> KnowledgeRefs:
        refs = KnowledgeRefs(
            memory_version_refs=list(memory_version_refs or []),
            skill_version_refs=list(skill_version_refs or []),
            protected_instruction_version_refs=list(protected_instruction_version_refs or []),
        )
        for version_id in knowledge_version_refs or []:
            version = self.get_version(version_id)
            if version.kind == "memory" and version.id not in refs.memory_version_refs:
                refs.memory_version_refs.append(version.id)
            elif version.kind == "skill" and version.id not in refs.skill_version_refs:
                refs.skill_version_refs.append(version.id)
            elif (
                version.kind == PROTECTED_KIND
                and version.id not in refs.protected_instruction_version_refs
            ):
                refs.protected_instruction_version_refs.append(version.id)
        for version_id in refs.all_ids():
            self.get_version(version_id)
        return refs

    def _append_version(
        self,
        entry: KnowledgeEntry,
        *,
        content: str,
        provenance: KnowledgeProvenance,
        previous_version_id: str,
        reverted_from_version_id: str | None = None,
    ) -> KnowledgeEntryView:
        now = utc_now()
        version = KnowledgeVersion(
            id=new_id("knv"),
            entry_id=entry.id,
            scope=entry.scope,
            scope_id=entry.scope_id,
            kind=entry.kind,
            content=content,
            provenance=provenance,
            previous_version_id=previous_version_id,
            reverted_from_version_id=reverted_from_version_id,
            created_at=now,
        )
        updated = entry.model_copy(
            update={"current_version_id": version.id, "updated_at": now}
        )
        self.store.append_version(version)
        self.store.put_entry(updated)
        return self._view(updated, version)

    def _require_entry(self, entry_id: str) -> KnowledgeEntry:
        entry = self.store.get_entry(entry_id)
        if entry is None:
            raise KnowledgeError("Unknown knowledge entry", code="entry_missing", status_code=404)
        return entry

    def _assert_base_version(self, entry: KnowledgeEntry, base_version: str) -> None:
        if entry.current_version_id == base_version:
            return
        raise KnowledgeError(
            (
                "Knowledge conflict: expected base_version "
                f"{base_version} but current is {entry.current_version_id}"
            ),
            code="knowledge_conflict",
            status_code=409,
            details={
                "current_version_id": entry.current_version_id,
                "expected_base_version": base_version,
            },
        )

    def _assert_write_allowed(
        self,
        kind: KnowledgeKind,
        scope: KnowledgeScope,
        provenance: KnowledgeProvenance,
    ) -> None:
        if provenance.actor != AGENT_ACTOR:
            return
        if kind == PROTECTED_KIND:
            raise KnowledgeError(
                "Protected instructions reject agent-origin writes.",
                code="protected_instruction_denied",
                status_code=403,
            )
        config = self.get_config()
        policy = config.scope_policies.get(scope)
        allowed = policy.automatic_agent_writes if policy is not None else False
        if not allowed:
            raise KnowledgeError(
                "Automatic agent writes require an explicit scope policy.",
                code="scope_policy_denied",
                status_code=403,
            )

    def _require_view(self, entry: KnowledgeEntry) -> KnowledgeEntryView:
        version = self.store.get_version(entry.current_version_id)
        if version is None:
            raise KnowledgeError(
                "Knowledge entry is missing its current version file.",
                code="knowledge_version_missing",
                status_code=409,
            )
        return self._view(entry, version)

    def _view(self, entry: KnowledgeEntry, version: KnowledgeVersion) -> KnowledgeEntryView:
        return KnowledgeEntryView(
            **entry.model_dump(),
            content=version.content,
            provenance=version.provenance,
            previous_version_id=version.previous_version_id,
            reverted_from_version_id=version.reverted_from_version_id,
            version_created_at=version.created_at,
        )

    def _expire_captures(self) -> None:
        now = datetime.now(timezone.utc)
        for capture in self.store.list_captures():
            if capture.expires_at is None:
                continue
            expires = datetime.fromisoformat(capture.expires_at)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= now:
                expired = capture.model_copy(
                    update={"expired": True, "content": None, "retained": False}
                )
                self.store.put_capture(expired)

