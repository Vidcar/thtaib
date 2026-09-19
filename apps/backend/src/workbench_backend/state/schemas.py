"""Application-owned run linkage and external-effect records."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class RelatedFile(BaseModel):
    """A file the application associates with a run. Not a checkpointer row."""

    path: str
    kind: Literal["project_root", "written_file", "artifact"]


class RunLinkage(BaseModel):
    """Follow a persisted run to checkpoint ids and related files (STATE-001)."""

    run_id: str
    thread_id: str | None = None
    checkpoint_ids: list[str] = Field(default_factory=list)
    related_files: list[RelatedFile] = Field(default_factory=list)
    note: str = (
        "Application records link run → checkpoint id(s) → files. "
        "LangGraph owns checkpoint bytes. This is not an exactly-once claim."
    )


class ExternalEffectOutcome(str, Enum):
    dispatched = "dispatched"
    acknowledged = "acknowledged"
    unknown = "unknown"
    reconciled = "reconciled"
    failed = "failed"


class RecoverAction(str, Enum):
    reconnect = "reconnect"
    resume = "resume"
    restart = "restart"


class ExternalEffect(BaseModel):
    """STATE-004 side-effect record. Snapshots do not undo this."""

    id: str
    run_id: str | None = None
    adapter_id: str = "application-ledger"
    operation: str
    payload: dict[str, Any] = Field(default_factory=dict)
    outcome: ExternalEffectOutcome = ExternalEffectOutcome.dispatched
    unresolved: bool = True
    dispatched_at: str
    acknowledged_at: str | None = None
    recovered_at: str | None = None
    reconciled_at: str | None = None
    last_recovery_action: RecoverAction | None = None
    evidence: dict[str, Any] | None = None
    replay_count: Literal[0] = 0
    rollback_promise: Literal["none"] = "none"
    environment_restore: Literal["not_supported"] = "not_supported"
    adapter_snapshot_rollback: Literal["not_supported"] = "not_supported"
    note: str = (
        "External effect recorded before local acknowledgement. "
        "Unknown outcomes are reported, not replayed."
    )
