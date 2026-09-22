"""STATE-005 knowledge write policy, versions and context-capture retention."""

from __future__ import annotations

import threading
from pathlib import Path
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
    KnowledgeAutomaticPolicy,
    KnowledgeLifecycleRequest,
    KnowledgeProposal,
    KnowledgeScopeOption,
    SkillPackageImportRequest, SkillResource, SkillResourceView,
)
from workbench_backend.knowledge.store import KnowledgeStore
from workbench_backend.knowledge.packages import read_skill_package, safe_resource_path
from workbench_backend.paths import WorkbenchPaths

PROTECTED_KIND = "protected_instruction"
AGENT_ACTOR = "agent"


class KnowledgeService:
    def __init__(self, paths: WorkbenchPaths, *, app_store=None) -> None:
        self.paths = paths.ensure()
        self.store = KnowledgeStore(self.paths)
        self._lock = threading.RLock()
        self.app_store = app_store

    def get_config(self) -> KnowledgeConfig:
        return self.store.read_config()

    def update_config(self, request: KnowledgeConfigUpdateRequest) -> KnowledgeConfig:
        with self._lock:
            current = self.store.read_config()
            payload = current.model_dump()
            if request.context_captures is not None:
                payload["context_captures"] = request.context_captures.model_dump()
            if request.scope_policies is not None:
                if any(scope != "user" and policy.automatic_agent_writes for scope, policy in request.scope_policies.items()):
                    raise KnowledgeError("Automatic saving requires one specific project or agent destination.", code="scope_identity_required", status_code=400)
                policies = current.scope_policies | request.scope_policies
                payload["scope_policies"] = {
                    scope: policy.model_dump() for scope, policy in policies.items()
                }
                if "user" in request.scope_policies:
                    # Both public controls represent the same exact user
                    # permission. A stale copy must never keep writes allowed.
                    exact = KnowledgeAutomaticPolicy(scope="user", automatic_agent_writes=request.scope_policies["user"].automatic_agent_writes)
                    payload["automatic_save_policies"] = [
                        p.model_dump() for p in current.automatic_save_policies if p.scope != "user"
                    ] + [exact.model_dump()]
            return self.store.write_config(KnowledgeConfig.model_validate(payload))

    def create(self, request: KnowledgeCreateRequest, *, actor: str = "human", run_id: str | None = None) -> KnowledgeEntryView:
        provenance = self._assigned_provenance(request.provenance, actor=actor, run_id=run_id)
        request = request.model_copy(update={"provenance": provenance})
        with self._lock:
            self._require_scope(request.scope, request.scope_id)
            self._assert_write_allowed(request.kind, request.scope, provenance, request.scope_id)
            return self._create_locked(request)

    def _create_locked(self, request: KnowledgeCreateRequest, *, resources: list[SkillResource] | None = None, package_source: str | None = None) -> KnowledgeEntryView:
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
            resources=list(resources or []),
            package_source=package_source,
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

    def list_entries(self, *, include_inactive: bool = False) -> list[KnowledgeEntryView]:
        return [self._require_view(entry) for entry in self.store.list_entries() if entry.active or include_inactive]

    def get_entry(self, entry_id: str) -> KnowledgeEntryView:
        entry = self.store.get_entry(entry_id)
        if entry is None:
            raise KnowledgeError("Unknown knowledge entry", code="entry_missing", status_code=404)
        return self._require_view(entry)

    def list_versions(self, entry_id: str) -> list[KnowledgeVersion]:
        self.get_entry(entry_id)
        return self._order_versions(self.store.list_versions(entry_id))

    def get_version(self, version_id: str) -> KnowledgeVersion:
        version = self.store.get_version(version_id)
        if version is None:
            raise KnowledgeError(
                "Unknown knowledge version",
                code="knowledge_version_missing",
                status_code=404,
            )
        return version

    def edit(self, entry_id: str, request: KnowledgeEditRequest, *, actor: str = "human", run_id: str | None = None) -> KnowledgeEntryView:
        with self._lock:
            entry = self._require_entry(entry_id)
            self._assert_base_version(entry, request.base_version)
            self._require_scope(entry.scope, entry.scope_id)
            provenance = self._assigned_provenance(request.provenance, actor=actor, run_id=run_id)
            self._assert_write_allowed(entry.kind, entry.scope, provenance, entry.scope_id)
            return self._append_version(
                entry,
                content=request.content,
                provenance=provenance,
                previous_version_id=entry.current_version_id,
            )

    def revert(self, entry_id: str, request: KnowledgeRevertRequest, *, actor: str = "human", run_id: str | None = None) -> KnowledgeEntryView:
        with self._lock:
            entry = self._require_entry(entry_id)
            self._assert_base_version(entry, request.base_version)
            self._require_scope(entry.scope, entry.scope_id)
            provenance = self._assigned_provenance(request.provenance, actor=actor, run_id=run_id)
            self._assert_write_allowed(entry.kind, entry.scope, provenance, entry.scope_id)
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
                provenance=provenance,
                previous_version_id=entry.current_version_id,
                reverted_from_version_id=target.id,
                resources=target.resources,
                package_source=target.package_source,
            )

    def capture(self, request: ContextCaptureRequest) -> ContextCapture:
        config = self.get_config()
        settings = config.context_captures
        stored, redacted, fields = apply_redaction(request.content, settings.redaction_mode)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        expires_at = None
        expired = False
        if settings.retention_seconds is not None:
            expires_at = now + timedelta(seconds=settings.retention_seconds)
            expired = expires_at <= now
        discarded = settings.redaction_mode == "discard" or expired
        stored_content = None if discarded else stored
        record = ContextCapture(
            id=new_id("kcap"),
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat() if expires_at else None,
            retention_seconds=settings.retention_seconds,
            redaction_mode=settings.redaction_mode,
            content=stored_content,
            retained=stored_content is not None,
            redacted=False if discarded else redacted,
            discarded=settings.redaction_mode == "discard",
            expired=expired,
            redacted_fields=[] if discarded else fields,
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
            version = self.get_version(version_id)
            entry = self._require_entry(version.entry_id)
            if not entry.active or not entry.enabled:
                raise KnowledgeError("Selected knowledge is disabled or removed. Update the selection.", code="knowledge_inactive", status_code=409)
            self._require_scope(entry.scope, entry.scope_id)
        for field, kind in [(refs.memory_version_refs, "memory"), (refs.skill_version_refs, "skill"), (refs.protected_instruction_version_refs, "protected_instruction")]:
            if any(self.get_version(ref).kind != kind for ref in field):
                raise KnowledgeError("A selected knowledge version has the wrong kind.", code="knowledge_kind_mismatch", status_code=400)
        return refs

    def _append_version(
        self,
        entry: KnowledgeEntry,
        *,
        content: str,
        provenance: KnowledgeProvenance,
        previous_version_id: str,
        reverted_from_version_id: str | None = None,
        resources: list[SkillResource] | None = None,
        package_source: str | None = None,
    ) -> KnowledgeEntryView:
        now = utc_now()
        prior = self.get_version(previous_version_id)
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
            resources=list(resources if resources is not None else prior.resources),
            package_source=package_source if package_source is not None else prior.package_source,
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
        scope_id: str | None = None,
    ) -> None:
        if provenance.actor != AGENT_ACTOR:
            return
        if kind == PROTECTED_KIND:
            raise KnowledgeError(
                "Protected instructions reject agent-origin writes.",
                code="protected_instruction_denied",
                status_code=403,
            )
        allowed = self._automatic_allowed(scope, scope_id)
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
        option = next((item for item in self.scope_options(include_inactive=True) if item.scope == entry.scope and item.scope_id == entry.scope_id), None)
        return KnowledgeEntryView(
            **entry.model_dump(),
            content=version.content,
            provenance=version.provenance,
            previous_version_id=version.previous_version_id,
            reverted_from_version_id=version.reverted_from_version_id,
            version_created_at=version.created_at,
            scope_bound=option is not None,
            scope_label=option.label if option else "Unbound legacy scope",
            resources=version.resources,
            package_source=version.package_source,
        )

    def import_skill(self, request: SkillPackageImportRequest) -> KnowledgeEntryView:
        content, files = read_skill_package(Path(request.source_path))
        with self._lock:
            self._require_scope(request.scope, request.scope_id)
            entry = self._require_entry(request.entry_id) if request.entry_id else None
            if entry is not None:
                if entry.kind != "skill" or (entry.scope, entry.scope_id) != (request.scope, request.scope_id) or not entry.active:
                    raise KnowledgeError("Choose an active skill in the same scope for this update.", code="skill_update_mismatch", status_code=409)
                self._assert_base_version(entry, request.base_version or "")
            elif request.base_version is not None:
                raise KnowledgeError("A skill base version requires its entry.", code="knowledge_base_invalid", status_code=400)
            resources = [self.store.retain_resource(path, data) for path, data in sorted(files.items()) if path != "SKILL.md"]
            source = str(Path(request.source_path).expanduser().resolve())
            provenance = KnowledgeProvenance(actor="human", note="Imported inert skill package; no scripts or dependencies executed.")
            if entry is not None:
                return self._append_version(entry, content=content, provenance=provenance, previous_version_id=entry.current_version_id, resources=resources, package_source=source)
            return self._create_locked(KnowledgeCreateRequest(scope=request.scope, scope_id=request.scope_id, kind="skill", content=content, display_name=request.display_name or Path(source).stem, provenance=provenance), resources=resources, package_source=source)

    def resource_bytes(self, version: KnowledgeVersion, relative_path: str) -> bytes:
        path = safe_resource_path(relative_path)
        if path == "SKILL.md" and version.kind == "skill":
            return version.content.encode("utf-8")
        resource = next((r for r in version.resources if r.path == path), None)
        if resource is None:
            raise KnowledgeError("This resource is not part of the selected skill version.", code="skill_resource_missing", status_code=404)
        try:
            return self.store.read_resource(resource)
        except (OSError, ValueError) as exc:
            raise KnowledgeError(str(exc), code="skill_resource_corrupt", status_code=409) from exc

    def inspect_resource(self, version_id: str, relative_path: str) -> SkillResourceView:
        import hashlib
        version = self.get_version(version_id)
        data = self.resource_bytes(version, relative_path)
        try:
            text = data.decode("utf-8")
            if "\x00" in text:
                text = None
        except UnicodeDecodeError:
            text = None
        return SkillResourceView(version_id=version.id, path=relative_path, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data), content=text, binary=text is None)

    def scope_options(self, *, include_inactive: bool = False) -> list[KnowledgeScopeOption]:
        options = [KnowledgeScopeOption(scope="user", label="Personal knowledge")]
        if self.app_store is not None:
            options.extend(KnowledgeScopeOption(scope="project", scope_id=p.id, label=p.name, active=p.active) for p in self.app_store.list_projects() if p.active or include_inactive)
            for setup in self.app_store.list_agent_setups():
                version = self.app_store.get_agent_setup_version(setup.current_version_id)
                if version is not None and (setup.active or include_inactive):
                    options.append(KnowledgeScopeOption(scope="agent", scope_id=setup.id, label=version.name, active=setup.active))
        return options

    def _require_scope(self, scope: KnowledgeScope, scope_id: str | None) -> None:
        if not any(item.scope == scope and item.scope_id == scope_id for item in self.scope_options()):
            raise KnowledgeError("Choose an existing project or agent for this knowledge scope.", code="knowledge_scope_missing", status_code=409, details={"scope": scope, "scope_id": scope_id})

    @staticmethod
    def _assigned_provenance(supplied: KnowledgeProvenance | None, *, actor: str, run_id: str | None) -> KnowledgeProvenance:
        if supplied is not None and (supplied.actor != actor or supplied.run_id not in {None, run_id} or supplied.proposal_id is not None or supplied.reviewed_by is not None):
            raise KnowledgeError("Writer identity and run provenance are assigned by the backend.", code="knowledge_actor_forged", status_code=403)
        return KnowledgeProvenance(actor=actor, run_id=run_id, note=supplied.note if supplied else None)

    def update_lifecycle(self, entry_id: str, request: KnowledgeLifecycleRequest) -> KnowledgeEntryView:
        with self._lock:
            entry = self._require_entry(entry_id)
            if not entry.active:
                raise KnowledgeError("This knowledge entry was removed.", code="knowledge_inactive", status_code=409)
            updates = request.model_dump(exclude_unset=True)
            updates["updated_at"] = utc_now()
            entry = entry.model_copy(update=updates)
            self.store.put_entry(entry)
            return self._require_view(entry)

    def remove_entry(self, entry_id: str) -> KnowledgeEntryView:
        with self._lock:
            entry = self._require_entry(entry_id).model_copy(update={"active": False, "enabled": False, "updated_at": utc_now()})
            self.store.put_entry(entry)
            return self._require_view(entry)

    def set_automatic_policy(self, policy: KnowledgeAutomaticPolicy) -> KnowledgeConfig:
        with self._lock:
            self._require_scope(policy.scope, policy.scope_id)
            config = self.get_config()
            config.automatic_save_policies = [p for p in config.automatic_save_policies if (p.scope, p.scope_id) != (policy.scope, policy.scope_id)] + [policy]
            # The user-scope switch is retained for the existing Settings view,
            # but cannot authorize any project or reusable agent destination.
            if policy.scope == "user":
                config.scope_policies["user"].automatic_agent_writes = policy.automatic_agent_writes
            return self.store.write_config(config)

    def _automatic_allowed(self, scope: KnowledgeScope, scope_id: str | None) -> bool:
        config = self.get_config()
        exact = next((p for p in config.automatic_save_policies if (p.scope, p.scope_id) == (scope, scope_id)), None)
        if exact is not None:
            return exact.automatic_agent_writes
        return scope == "user" and scope_id is None and config.scope_policies.get("user") is not None and config.scope_policies["user"].automatic_agent_writes

    def propose_memory(self, *, run_id: str, content: str, scope: KnowledgeScope = "user", scope_id: str | None = None, display_name: str | None = None, entry_id: str | None = None, base_version: str | None = None) -> KnowledgeProposal:
        """Internal tool entry point: run identity is bound by the backend wrapper."""
        with self._lock:
            run = self.app_store.get_run(run_id) if self.app_store else None
            if run is None:
                raise KnowledgeError("Memory proposals require a real originating run.", code="knowledge_run_missing", status_code=409)
            self._require_scope(scope, scope_id)
            if scope == "project" and run.project_id != scope_id or scope == "agent" and run.agent_setup_id != scope_id:
                raise KnowledgeError("This run is not bound to that knowledge destination.", code="knowledge_scope_denied", status_code=403)
            if entry_id:
                entry = self._require_entry(entry_id)
                if entry.kind != "memory":
                    raise KnowledgeError("Agents may propose memory only; protected instructions and skills require human edits.", code="protected_instruction_denied", status_code=403)
                if (entry.scope, entry.scope_id) != (scope, scope_id):
                    raise KnowledgeError("The proposed destination does not match the memory.", code="knowledge_scope_denied", status_code=403)
                self._assert_base_version(entry, base_version or "")
            elif base_version is not None:
                raise KnowledgeError("A base version requires an existing memory entry.", code="knowledge_base_invalid", status_code=400)
            now = utc_now()
            proposal = KnowledgeProposal(id=new_id("proposal"), entry_id=entry_id, base_version=base_version, scope=scope, scope_id=scope_id, content=content, display_name=display_name, provenance=KnowledgeProvenance(actor="agent", run_id=run_id), created_at=now, updated_at=now)
            self.store.put_proposal(proposal)
            return self._commit_proposal(proposal, automatic=True) if self._automatic_allowed(scope, scope_id) else proposal

    def list_proposals(self, *, run_id: str | None = None) -> list[KnowledgeProposal]:
        return [self._recover_proposal(p) for p in self.store.list_proposals() if run_id is None or p.provenance.run_id == run_id]

    def review_proposal(self, proposal_id: str, decision: str) -> KnowledgeProposal:
        with self._lock:
            proposal = self.store.get_proposal(proposal_id)
            if proposal is None:
                raise KnowledgeError("Unknown memory proposal.", code="knowledge_proposal_missing", status_code=404)
            proposal = self._recover_proposal(proposal)
            if proposal.status != "pending":
                if proposal.status == ("accepted" if decision == "accept" else "rejected"):
                    return proposal
                raise KnowledgeError("This proposal has already been reviewed.", code="knowledge_proposal_resolved", status_code=409)
            if decision == "reject":
                return self.store.put_proposal(proposal.model_copy(update={"status": "rejected", "updated_at": utc_now()}))
            return self._commit_proposal(proposal, automatic=False)

    def _commit_proposal(self, proposal: KnowledgeProposal, *, automatic: bool) -> KnowledgeProposal:
        self._require_scope(proposal.scope, proposal.scope_id)
        provenance = proposal.provenance.model_copy(update={"proposal_id": proposal.id, "reviewed_by": None if automatic else "human"})
        if proposal.entry_id:
            entry = self._require_entry(proposal.entry_id)
            if not entry.active:
                raise KnowledgeError("This memory was removed before review.", code="knowledge_inactive", status_code=409)
            self._assert_base_version(entry, proposal.base_version or "")
            view = self._append_version(entry, content=proposal.content, provenance=provenance, previous_version_id=entry.current_version_id)
        else:
            view = self._create_locked(KnowledgeCreateRequest(scope=proposal.scope, scope_id=proposal.scope_id, kind="memory", content=proposal.content, display_name=proposal.display_name, provenance=provenance))
        return self.store.put_proposal(proposal.model_copy(update={"status": "accepted", "entry_id": view.id, "committed_version_id": view.current_version_id, "automatic": automatic, "updated_at": utc_now()}))

    def _recover_proposal(self, proposal: KnowledgeProposal) -> KnowledgeProposal:
        if proposal.status != "pending":
            return proposal
        # A crash after append but before marking reviewed must not append twice.
        entries = [self.store.get_entry(proposal.entry_id)] if proposal.entry_id else self.store.list_entries()
        for entry in entries:
            if entry is None:
                continue
            for version in self.store.list_versions(entry.id):
                if version.provenance.proposal_id == proposal.id:
                    # Only versions reachable from the durable entry head were
                    # committed; an orphan append must not become a saved claim.
                    reachable = set()
                    current = self.store.get_version(entry.current_version_id)
                    while current is not None and current.id not in reachable:
                        reachable.add(current.id)
                        current = self.store.get_version(current.previous_version_id) if current.previous_version_id else None
                    if version.id not in reachable:
                        continue
                    return self.store.put_proposal(proposal.model_copy(update={"status": "accepted", "entry_id": entry.id, "committed_version_id": version.id, "automatic": version.provenance.reviewed_by is None, "updated_at": utc_now()}))
        return proposal

    def _order_versions(self, versions: list[KnowledgeVersion]) -> list[KnowledgeVersion]:
        children: dict[str | None, list[KnowledgeVersion]] = {}
        for version in versions:
            children.setdefault(version.previous_version_id, []).append(version)
        ordered: list[KnowledgeVersion] = []
        pending = list(children.get(None, []))
        seen: set[str] = set()
        while pending:
            current = pending.pop(0)
            if current.id in seen:
                continue
            seen.add(current.id)
            ordered.append(current)
            pending.extend(children.get(current.id, []))
        leftovers = [item for item in versions if item.id not in seen]
        leftovers.sort(key=lambda item: (item.created_at, item.id))
        return ordered + leftovers

    def _expire_captures(self) -> None:
        now = datetime.now(timezone.utc)
        for capture in self.store.list_captures():
            if capture.expired or capture.expires_at is None:
                continue
            expires = datetime.fromisoformat(capture.expires_at)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= now:
                expired = capture.model_copy(
                    update={"expired": True, "content": None, "retained": False}
                )
                self.store.put_capture(expired)

