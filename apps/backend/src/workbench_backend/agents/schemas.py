"""Harness run records. Application DB is the run SoR (STATE-001)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from workbench_backend.agents.effective_setup import EffectiveSetup, LoadedKnowledgeFact
from workbench_backend.contracts.lifecycle import RunLifecycleStatus
from workbench_backend.knowledge.schemas import KnowledgeBinding, RedactionMode
from workbench_backend.state.schemas import RelatedFile

# Harness run records use the shared #41 lifecycle vocabulary. Do not keep a
# second enum of queued/running/cancel_requested/cancelled/completed/failed.
AgentRunStatus = RunLifecycleStatus


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
    request_prepared: bool = True
    transport_attempted: bool = False
    transport_attempt_count: int = 0
    response_observed: bool = False
    handler_returned: bool = False
    failure: dict[str, Any] | None = None
    instructions: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    presented_tools: list[str] = Field(default_factory=list)
    generation_settings: dict[str, Any] = Field(default_factory=dict)
    memory_versions: list[str] = Field(default_factory=list)
    skill_versions: list[str] = Field(default_factory=list)
    loaded_knowledge: list[LoadedKnowledgeFact] = Field(default_factory=list)
    retrieved_material: list[str] = Field(default_factory=list)
    capture_gaps: list[str] = Field(default_factory=list)
    http_payload: dict[str, Any] | None = None
    http_payloads: list[dict[str, Any]] = Field(default_factory=list)
    selected_profile_id: str | None = None
    applied_per_request: dict[str, Any] = Field(default_factory=dict)
    startup_mismatches: list[dict[str, Any]] = Field(default_factory=list)
    redaction_mode: RedactionMode = "redact_secrets"
    retention_seconds: int | None = None
    expires_at: str | None = None
    retained: bool = True
    redacted: bool = False
    discarded: bool = False
    expired: bool = False
    redacted_fields: list[str] = Field(default_factory=list)


class ToolMode(str, Enum):
    live_tool = "live-tool"
    recorded_tool = "recorded-tool"


def label_for_tool_mode(mode: ToolMode) -> str:
    if mode is ToolMode.recorded_tool:
        return "recorded-tool — not proof of a current live integration"
    return "live-tool"


SourceSurface = Literal["agent-run", "chat", "lab"]

HOST_SHELL_NOTE = (
    "Host shell has no isolation. Commands run through Deep Agents "
    "LocalShellBackend with the bound project as cwd. permissions= apply to "
    "routed filesystem prefixes only while the default backend is a sandbox. "
    "interrupt_on pauses dangerous execute calls. Not a durable Approvals "
    "inbox (OQ-011)."
)


class HostShellFacts(BaseModel):
    """Declared first worker environment for one run. Not WSL or Docker."""

    available: bool = False
    environment: Literal["windows_host_shell"] = "windows_host_shell"
    isolation: Literal["none"] = "none"
    cwd: str | None = None
    inherit_env: bool = True
    note: str = HOST_SHELL_NOTE


class PendingInterruptAction(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    allowed_decisions: list[str] = Field(default_factory=lambda: ["approve", "reject"])


class PendingInterrupt(BaseModel):
    """Deep Agents interrupt_on payload. Not a durable product inbox (OQ-011)."""

    kind: Literal["deepagents_interrupt_on"] = "deepagents_interrupt_on"
    environment: Literal["windows_host_shell"] = "windows_host_shell"
    isolation: Literal["none"] = "none"
    note: str = HOST_SHELL_NOTE
    action_requests: list[PendingInterruptAction] = Field(default_factory=list)


class InterruptDecision(BaseModel):
    type: Literal["approve", "reject"]
    message: str | None = None


class InterruptDecisionRequest(BaseModel):
    decisions: list[InterruptDecision]


class AgentStartRequest(BaseModel):
    deployment_id: str
    task: str
    presented_tools: list[str] | None = None
    system_prompt: str | None = None
    criteria: TaskCriteria | None = None
    budgets: AgentBudgets | None = None
    workspace_id: str | None = None
    project_path: str | None = None
    profile_id: str | None = None
    inherit_deployment_settings: bool = True
    parent_run_id: str | None = None
    tool_mode: ToolMode = ToolMode.live_tool
    recorded_fixtures: list[dict[str, Any]] | None = None
    memory_version_refs: list[str] = Field(default_factory=list)
    skill_version_refs: list[str] = Field(default_factory=list)
    protected_instruction_version_refs: list[str] = Field(default_factory=list)
    knowledge_version_refs: list[str] = Field(default_factory=list)
    embedding_deployment_id: str | None = None
    retrieval_project_paths: list[str] = Field(default_factory=list)
    source_surface: SourceSurface = "agent-run"
    thread_id: str | None = None


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
    project_path: str | None = None
    profile_id: str | None = None
    parent_run_id: str | None = None
    source_surface: SourceSurface = "agent-run"
    tool_mode: ToolMode = ToolMode.live_tool
    tool_mode_label: str = "live-tool"
    recorded_is_not_live_proof: bool = False
    recorded_fixtures: list[dict[str, Any]] = Field(default_factory=list)
    harness: Literal["deepagents"] = "deepagents"
    outer_graph: Literal["deepagents-compiled-state-graph"] = "deepagents-compiled-state-graph"
    knowledge: KnowledgeBinding = "none"
    memory_version_refs: list[str] = Field(default_factory=list)
    skill_version_refs: list[str] = Field(default_factory=list)
    protected_instruction_version_refs: list[str] = Field(default_factory=list)
    embedding_deployment_id: str | None = None
    retrieval_project_paths: list[str] = Field(default_factory=list)
    retrieved_material: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    checkpoint_ids: list[str] = Field(default_factory=list)
    related_files: list[RelatedFile] = Field(default_factory=list)
    effective_setup: EffectiveSetup | None = None
    starting_snapshot_id: str | None = None
    host_shell: HostShellFacts = Field(default_factory=HostShellFacts)
    pending_interrupt: PendingInterrupt | None = None
