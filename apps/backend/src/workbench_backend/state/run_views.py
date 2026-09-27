"""Read-only run views; none are complete persistence records.

The execution owner keeps AgentRun. Operational readers deliberately cannot
receive captured model history or write a projection back as that owner.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from workbench_backend.agents.schemas import AgentRun, ChildRunActivity, SourceSurface
from workbench_backend.contracts.lifecycle import RunLifecycleStatus
from workbench_backend.inference.schemas import SettingsBag


class ReadOnlyRunView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# Reuse the canonical operational field definitions without inheriting from
# AgentRun. In particular, isinstance(view, AgentRun) must remain false.
AgentRunOperational = create_model(
    "AgentRunOperational",
    __base__=ReadOnlyRunView,
    __module__=__name__,
    **{
        name: (field.annotation, deepcopy(field))
        for name, field in AgentRun.model_fields.items()
        if name != "model_requests"
    },
)


class LifecycleToolOutcomeProjection(ReadOnlyRunView):
    model_config = ConfigDict(frozen=True, extra="ignore")
    outcome: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class RunLifecycleProjection(ReadOnlyRunView):
    id: str
    status: RunLifecycleStatus
    thread_id: str | None = None
    workspace_id: str | None = None
    project_path: str | None = None
    parent_run_id: str | None = None
    source_surface: SourceSurface = "agent-run"
    created_at: str
    updated_at: str
    finished_at: str | None = None
    task: str = ""
    child_runs: tuple[ChildRunActivity, ...] = ()
    finalization_phase: Literal["saving_changes"] | None = None
    tool_outcomes: dict[str, LifecycleToolOutcomeProjection] = Field(default_factory=dict)


class BrowserSettingsBagProjection(SettingsBag):
    # Capability identity recognizes the canonical SettingsBag type and hashes
    # its applied values. Keep that integration contract while freezing this
    # read-only bag; the store selects only requested/applied operational data.
    model_config = ConfigDict(frozen=True, extra="forbid")


class BrowserSettingsBagsProjection(ReadOnlyRunView):
    per_request: BrowserSettingsBagProjection = Field(default_factory=BrowserSettingsBagProjection)


class BrowserEffectiveSetupProjection(ReadOnlyRunView):
    bags: BrowserSettingsBagsProjection = Field(default_factory=BrowserSettingsBagsProjection)


class BrowserRunProjection(ReadOnlyRunView):
    id: str
    thread_id: str | None = None
    status: RunLifecycleStatus
    browser_control: Literal["agent", "taking_control", "user"] = "agent"
    source_surface: SourceSurface = "agent-run"
    project_path: str | None = None
    retained_asset_ids: tuple[str, ...] = ()
    deployment_id: str
    presented_tools: tuple[str, ...] = ()
    work_mode: Literal["work", "plan"] = "work"
    effective_setup: BrowserEffectiveSetupProjection | None = None


class AttentionInterruptProjection(ReadOnlyRunView):
    interrupt_id: str | None = None
    action_names: tuple[str, ...] = ()


class RunAttentionProjection(ReadOnlyRunView):
    id: str
    status: RunLifecycleStatus
    source_surface: SourceSurface = "agent-run"
    pending_interrupt: AttentionInterruptProjection | None = None
    checkpoint_ids: tuple[str, ...] = ()
    finished_at: str | None = None
