"""Harness run records. Enough events for one complete run; not OQ-004 recovery."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRunStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class AgentBudgets(BaseModel):
    """Optional user-selected product budgets. Unset by default (AGT-003)."""

    max_steps: int | None = None
    max_tool_calls: int | None = None


class ExecutableCheck(BaseModel):
    name: str
    kind: Literal["executable"] = "executable"
    passed: bool
    detail: str | None = None


class ExpectedArtifact(BaseModel):
    name: str
    present: bool
    detail: str | None = None


class ModelJudgement(BaseModel):
    model_review: str | None = None
    source: Literal["assistant_message"] = "assistant_message"
    note: str = "Model judgement, not an executable check."


class CompletionReport(BaseModel):
    evidence: dict[str, Any] = Field(default_factory=dict)
    judgement: ModelJudgement = Field(default_factory=ModelJudgement)


class TaskCriteria(BaseModel):
    checks: list[str] = Field(default_factory=lambda: ["enabled_tool_invoked"])
    expected_artifacts: list[str] = Field(default_factory=lambda: ["assistant_reply"])
    review_prompt: str | None = None


class AgentEvent(BaseModel):
    at: str
    kind: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ModelRequestCapture(BaseModel):
    at: str
    instructions: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    presented_tools: list[str] = Field(default_factory=list)
    generation_settings: dict[str, Any] = Field(default_factory=dict)
    memory_versions: list[str] = Field(default_factory=list)
    skill_versions: list[str] = Field(default_factory=list)
    retrieved_material: list[str] = Field(default_factory=list)
    capture_gaps: list[str] = Field(default_factory=list)
    http_payload: dict[str, Any] | None = None


class ToolMode(str, Enum):
    live_tool = "live-tool"
    recorded_tool = "recorded-tool"


def label_for_tool_mode(mode: ToolMode) -> str:
    if mode is ToolMode.recorded_tool:
        return "recorded-tool — not proof of a current live integration"
    return "live-tool"


class AgentStartRequest(BaseModel):
    deployment_id: str
    task: str
    presented_tools: list[str] | None = None
    system_prompt: str | None = None
    criteria: TaskCriteria | None = None
    budgets: AgentBudgets | None = None
    workspace_id: str | None = None
    parent_run_id: str | None = None
    tool_mode: ToolMode = ToolMode.live_tool
    recorded_fixtures: list[dict[str, Any]] | None = None


class AgentRun(BaseModel):
    id: str
    status: AgentRunStatus = AgentRunStatus.queued
    deployment_id: str
    task: str
    enabled_tools: list[str]
    presented_tools: list[str]
    denied_tools: list[str] = Field(default_factory=list)
    system_prompt: str | None = None
    criteria: TaskCriteria = Field(default_factory=TaskCriteria)
    budgets: AgentBudgets | None = None
    events: list[AgentEvent] = Field(default_factory=list)
    model_requests: list[ModelRequestCapture] = Field(default_factory=list)
    tool_invocations: list[dict[str, Any]] = Field(default_factory=list)
    completion: CompletionReport | None = None
    stop_reason: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str
    finished_at: str | None = None
    workspace_id: str | None = None
    parent_run_id: str | None = None
    tool_mode: ToolMode = ToolMode.live_tool
    tool_mode_label: str = "live-tool"
    recorded_is_not_live_proof: bool = False
    recorded_fixtures: list[dict[str, Any]] = Field(default_factory=list)
    harness: Literal["deepagents"] = "deepagents"
    outer_graph: Literal["deepagents-compiled-state-graph"] = "deepagents-compiled-state-graph"
    knowledge: Literal["none"] = "none"
