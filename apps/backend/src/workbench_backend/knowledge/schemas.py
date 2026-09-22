"""Durable knowledge records. Application-owned; not a retrieval index."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

KnowledgeScope = Literal["user", "agent", "project"]
KnowledgeKind = Literal["memory", "skill", "protected_instruction"]
KnowledgeActor = Literal["human", "api_maintainer", "agent"]
RedactionMode = Literal["retain", "redact_secrets", "discard"]
KnowledgeBinding = Literal["none", "application_owned"]


class KnowledgeProvenance(BaseModel):
    actor: KnowledgeActor
    run_id: str | None = None
    note: str | None = None
    proposal_id: str | None = None
    reviewed_by: Literal["human"] | None = None


class ScopeWritePolicy(BaseModel):
    automatic_agent_writes: bool = False


class KnowledgeAutomaticPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: KnowledgeScope
    scope_id: str | None = None
    automatic_agent_writes: bool = False


class KnowledgeScopeOption(BaseModel):
    scope: KnowledgeScope
    scope_id: str | None = None
    label: str
    active: bool = True


class SkillResource(BaseModel):
    path: str
    sha256: str
    size_bytes: int


class SkillPackageImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_path: str
    scope: KnowledgeScope = "user"
    scope_id: str | None = None
    display_name: str | None = None
    entry_id: str | None = None
    base_version: str | None = None


class SkillResourceView(SkillResource):
    version_id: str
    content: str | None = None
    binary: bool = False
    execution_available: Literal[False] = False


class ContextCaptureSettings(BaseModel):
    retention_seconds: int | None = None
    redaction_mode: RedactionMode = "redact_secrets"


class KnowledgeConfig(BaseModel):
    automatic_save_policies: list[KnowledgeAutomaticPolicy] = Field(default_factory=list)
    context_captures: ContextCaptureSettings = Field(default_factory=ContextCaptureSettings)
    scope_policies: dict[KnowledgeScope, ScopeWritePolicy] = Field(
        default_factory=lambda: {
            "user": ScopeWritePolicy(),
            "agent": ScopeWritePolicy(),
            "project": ScopeWritePolicy(),
        }
    )
    store: Literal["application_owned"] = "application_owned"
    not_checkpointer: Literal[True] = True
    not_git: Literal[True] = True
    not_rag: Literal[True] = True
    note: str = (
        "Durable knowledge versioning (STATE-005). This store is not a "
        "retrieval index. Query-time RAG is a derived per-run index (STATE-006). "
        "Automatic saves require permission for the exact destination scope."
    )


class KnowledgeVersion(BaseModel):
    resources: list[SkillResource] = Field(default_factory=list)
    package_source: str | None = None
    id: str
    entry_id: str
    scope: KnowledgeScope
    scope_id: str | None = None
    kind: KnowledgeKind
    content: str
    provenance: KnowledgeProvenance
    previous_version_id: str | None = None
    reverted_from_version_id: str | None = None
    created_at: str


class KnowledgeEntry(BaseModel):
    id: str
    scope: KnowledgeScope
    scope_id: str | None = None
    kind: KnowledgeKind
    display_name: str | None = None
    current_version_id: str
    created_at: str
    updated_at: str
    active: bool = True
    enabled: bool = True


class KnowledgeEntryView(KnowledgeEntry):
    resources: list[SkillResource] = Field(default_factory=list)
    package_source: str | None = None
    content: str
    provenance: KnowledgeProvenance
    previous_version_id: str | None = None
    reverted_from_version_id: str | None = None
    version_created_at: str
    scope_bound: bool = True
    scope_label: str | None = None


class KnowledgeCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: KnowledgeScope
    kind: KnowledgeKind
    content: str
    provenance: KnowledgeProvenance | None = None
    scope_id: str | None = None
    display_name: str | None = None


class KnowledgeEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str
    base_version: str
    provenance: KnowledgeProvenance | None = None


class KnowledgeRevertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_version_id: str
    base_version: str
    provenance: KnowledgeProvenance | None = None


class KnowledgeConfigUpdateRequest(BaseModel):
    context_captures: ContextCaptureSettings | None = None
    scope_policies: dict[KnowledgeScope, ScopeWritePolicy] | None = None


class KnowledgeLifecycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = None
    enabled: bool | None = None


class KnowledgeProposal(BaseModel):
    id: str
    status: Literal["pending", "accepted", "rejected"] = "pending"
    entry_id: str | None = None
    base_version: str | None = None
    scope: KnowledgeScope
    scope_id: str | None = None
    display_name: str | None = None
    content: str
    provenance: KnowledgeProvenance
    created_at: str
    updated_at: str
    committed_version_id: str | None = None
    automatic: bool = False


class KnowledgeProposalReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["accept", "reject"]


class ContextCaptureRequest(BaseModel):
    content: str
    run_id: str | None = None
    source: str | None = None


class ContextCapture(BaseModel):
    id: str
    created_at: str
    expires_at: str | None = None
    retention_seconds: int | None = None
    redaction_mode: RedactionMode
    content: str | None = None
    retained: bool
    redacted: bool
    discarded: bool
    expired: bool = False
    redacted_fields: list[str] = Field(default_factory=list)
    run_id: str | None = None
    source: str | None = None


class KnowledgeRefs(BaseModel):
    memory_version_refs: list[str] = Field(default_factory=list)
    skill_version_refs: list[str] = Field(default_factory=list)
    protected_instruction_version_refs: list[str] = Field(default_factory=list)

    def all_ids(self) -> list[str]:
        return [
            *self.memory_version_refs,
            *self.skill_version_refs,
            *self.protected_instruction_version_refs,
        ]

    def binding(self) -> KnowledgeBinding:
        return "application_owned" if self.all_ids() else "none"
