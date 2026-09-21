"""Public interaction stream application metadata schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from workbench_backend.agents.schemas import AgentRun


class InteractionRecovery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["replay_gap"]
    message: str


class WorkbenchInteractionMetadata(BaseModel):
    """Workbench-owned extension under native stream values.workbench."""

    model_config = ConfigDict(extra="ignore")

    run: AgentRun | None = None
    conversation_id: str | None = None
    incomplete_message_ids: list[str] = Field(default_factory=list)
    interrupt_run_id: str | None = None
    recovery: InteractionRecovery | None = None
