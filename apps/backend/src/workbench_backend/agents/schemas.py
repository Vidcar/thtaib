"""Harness run records. Application DB is the run SoR (STATE-001)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workbench_backend.agents.context import ContextObservation
from workbench_backend.agents.effective_setup import EffectiveSetup, LoadedKnowledgeFact
from workbench_backend.agents.structured import OutputSchemaRequest, StructuredOutputResult
from workbench_backend.agents.setup_schemas import AgentInputPolicy, InputSourceRow, FrozenHelperSelection, ReviewConfiguration
from workbench_backend.contracts.lifecycle import RunLifecycleStatus
from workbench_backend.connections.schemas import ConnectionSnapshot
from workbench_backend.inference.user_content import UserContentBlock
from workbench_backend.knowledge.schemas import KnowledgeBinding, RedactionMode
from workbench_backend.state.schemas import RelatedFile
from workbench_backend.state.preferences import MatchedPermissionGrant

# Harness run records use the shared #41 lifecycle vocabulary. Do not keep a
# second enum of queued/running/cancel_requested/cancelled/completed/failed.
AgentRunStatus = RunLifecycleStatus


class AgentBudgets(BaseModel):
    """Optional user-selected product budgets. Unset by default (AGT-003)."""

    max_steps: int | None = Field(default=None, gt=0)
    max_tool_calls: int | None = Field(default=None, gt=0)


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
    # Existing history remains readable; new completions never label the answer as review.
    source: Literal["assistant_message", "rubric_review", "not_requested"] = "not_requested"
    note: str = "No independent review was requested."


class ReviewObservation(BaseModel):
    enabled: bool = False
    max_revisions: Literal[2] = 2
    status: str = "not_requested"
    evaluations: list[dict[str, Any]] = Field(default_factory=list)
    evidence_scope: str = "Recent transcript excerpts; model judgement is not executable verification."


class ChildRunActivity(BaseModel):
    tool_call_id: str | None = None
    run_id: str
    agent_id: str
    version_id: str
    name: str
    namespace: list[str] = Field(default_factory=list)
    status: str = "queued"
    error: str | None = None


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
    purpose: Literal["work", "summary", "review", "probe"] = "work"
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
    input_sources: list[InputSourceRow] = Field(default_factory=list)
    tool_schemas: list[dict[str, Any]] = Field(default_factory=list)
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
    privacy_fingerprint: str | None = Field(default=None, max_length=64)
    context_observation: ContextObservation | None = None


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
    "interrupt_on pauses dangerous execute calls; the application persists "
    "native interrupts and surfaces them through shared Chat."
)


class HostShellFacts(BaseModel):
    """Declared first worker environment for one run. Not WSL or Docker."""

    available: bool = False
    environment: Literal["windows_host_shell"] = "windows_host_shell"
    isolation: Literal["none"] = "none"
    cwd: str | None = None
    inherit_env: bool = True
    note: str = HOST_SHELL_NOTE


class CapabilitySetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    capability: str
    id: str
    tool_names: list[str] = Field(default_factory=list)
    code: str
    message: str
    action: str
    target: Literal["settings", "browser", "windows", "agent", "knowledge", "project", "context"]
    target_id: str | None = None
    requires_new_input: bool = False


class PendingInterruptAction(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    allowed_decisions: list[str] = Field(default_factory=lambda: ["approve", "reject"])
    question: UserQuestion | None = None
    setup: CapabilitySetupRequest | None = None


class UserQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=4000)
    answer_type: Literal["text", "choice", "file", "folder"] = Field(default="text", description="Requested task-answer type; answering never grants tool access.")
    choices: list[str] = Field(default_factory=list, max_length=30, description="Required nonempty options when answer_type is choice.")

    @model_validator(mode="after")
    def choice_requires_options(self):
        if self.answer_type == "choice" and not self.choices:
            raise ValueError("A choice question requires choices.")
        return self


class PendingInterrupt(BaseModel):
    """Native Deep Agents interrupt persisted by the application and surfaced in Chat."""

    interrupt_id: str | None = None
    namespace: list[str] = Field(default_factory=list)
    kind: Literal["deepagents_interrupt_on", "browser_control", "capability_setup"] = "deepagents_interrupt_on"
    environment: Literal["windows_host_shell", "tool_actions", "user_input", "browser_control", "capability_setup"] = "windows_host_shell"
    isolation: Literal["none"] = "none"
    note: str = HOST_SHELL_NOTE
    action_requests: list[PendingInterruptAction] = Field(default_factory=list)


class InterruptDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["approve", "reject", "respond"]
    message: str | None = None
    scope: Literal["once", "session", "always"] = "once"


class InterruptDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisions: list[InterruptDecision]
    interrupt_id: str | None = Field(default=None, min_length=1, max_length=200)
    namespace: list[str] = Field(default_factory=list, max_length=20)


class AgentStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_policy: AgentInputPolicy | None = None

    deployment_id: str | None = None
    project_id: str | None = None
    agent_setup_version_id: str | None = None
    connection_ids: list[str] | None = None
    retained_asset_ids: list[str] = Field(default_factory=list, max_length=32)
    instructions: str | None = None
    per_request_overrides: dict[str, Any] | None = None
    model_configuration_id: str | None = None
    startup_overrides: dict[str, Any] | None = None
    work_mode: Literal["work", "plan"] = "work"
    desktop_access: Literal["off", "selected", "all"] = "off"
    helper_agent_ids: list[str] = Field(default_factory=list)
    review: ReviewConfiguration = Field(default_factory=ReviewConfiguration)
    task: str
    input_message_id: str | None = Field(default=None, min_length=1, max_length=200)
    content_blocks: list[UserContentBlock] | None = Field(default=None, max_length=32)
    presented_tools: list[str] | None = None
    approval_mode: Literal["ask", "full_access"] = "ask"
    system_prompt: str | None = None
    output_schema: OutputSchemaRequest | None = None
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
    resume_checkpoint_id: str | None = Field(default=None, min_length=1, max_length=200)


class GenerationObservation(BaseModel):
    purpose: Literal["work", "summary", "review", "probe"] = "work"
    request_id: str | None = None
    phase: Literal["prompt_processing", "generating", "completed", "interrupted"] = "completed"
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    processed_input_tokens: int | None = None
    prefill_seconds: float | None = Field(default=None, ge=0)
    request_started_at: str | None = None
    time_to_first_token_seconds: float | None = Field(default=None, ge=0)
    output_tokens: int | None = None
    context_limit: int | None = None
    context_used_tokens: int | None = None
    elapsed_seconds: float
    tokens_per_second: float | None = None
    measured_at: str
    basis: Literal["reported_tokens_model_call_wall_time", "llama_cpp_timings"] = "reported_tokens_model_call_wall_time"
    interval: Literal["last_completed_model_call_including_prompt_processing", "current_model_call_generation", "last_model_call_generation"] = "last_completed_model_call_including_prompt_processing"


class ToolOutcome(BaseModel):
    call_id: str
    name: str
    outcome: Literal["incomplete_arguments", "not_dispatched", "running", "succeeded", "failed", "uncertain"]
    failure_category: Literal["input", "permission", "tool", "runtime", "cancelled"] | None = None
    recovery_action: Literal["none", "continue", "inspect_effects", "ask"] = "none"
    detail: str | None = None
    result: Any = None
    result_metadata: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    updated_at: str


class RunFailure(BaseModel):
    category: Literal["input", "tool", "runtime", "cancelled", "capacity", "setup", "persistence", "uncertain_effects"]
    code: str
    message: str
    recovery_action: Literal["continue", "inspect_effects", "change_limit", "correct_setup", "ask"]


class AgentRun(BaseModel):
    input_policy: AgentInputPolicy | None = None
    input_sources: list[InputSourceRow] = Field(default_factory=list)
    id: str
    status: AgentRunStatus = AgentRunStatus.queued
    deployment_id: str
    project_id: str | None = None
    agent_setup_id: str | None = None
    agent_setup_version_id: str | None = None
    connection_ids: list[str] = Field(default_factory=list)
    connection_snapshots: list[ConnectionSnapshot] = Field(default_factory=list)
    retained_asset_ids: list[str] = Field(default_factory=list, max_length=32)
    task: str
    input_message_id: str | None = None
    content_blocks: list[UserContentBlock] | None = None
    enabled_tools: list[str]
    presented_tools: list[str]
    approval_mode: Literal["ask", "full_access"] = "ask"
    work_mode: Literal["work", "plan"] = "work"
    desktop_access: Literal["off", "selected", "all"] = "off"
    desktop_window: dict[str, int | float] | None = None
    capture_routes_enabled: bool = False
    requires_project: bool = False
    requires_host_shell: bool = False
    helper_agent_ids: list[str] = Field(default_factory=list)
    helper_snapshots: list[FrozenHelperSelection] = Field(default_factory=list)
    child_runs: list[ChildRunActivity] = Field(default_factory=list)
    review: ReviewConfiguration = Field(default_factory=ReviewConfiguration)
    review_observation: ReviewObservation = Field(default_factory=ReviewObservation)
    dispatched_tool_calls: int = 0
    dispatched_tool_ids: list[str] = Field(default_factory=list)
    completed_tool_ids: list[str] = Field(default_factory=list)
    tool_outcomes: dict[str, ToolOutcome] = Field(default_factory=dict)
    failure: RunFailure | None = None
    tool_authorizations: dict[str, str] = Field(default_factory=dict)
    tool_authorization_grants: dict[str, MatchedPermissionGrant] = Field(default_factory=dict)
    framework_read_paths: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    system_prompt: str | None = None
    criteria: TaskCriteria = Field(default_factory=TaskCriteria)
    budgets: AgentBudgets | None = None
    events: list[AgentEvent] = Field(default_factory=list)
    model_requests: list[ModelRequestCapture] = Field(default_factory=list)
    tool_invocations: list[dict[str, Any]] = Field(default_factory=list)
    completion: CompletionReport | None = None
    output_schema: OutputSchemaRequest | None = None
    structured_output: StructuredOutputResult | None = None
    context_observation: ContextObservation | None = None
    generation_observation: GenerationObservation | None = None
    generation_history: list[GenerationObservation] = Field(default_factory=list, max_length=64)
    housekeeping_context: dict[str, ContextObservation] = Field(default_factory=dict)
    housekeeping_generation: dict[str, GenerationObservation] = Field(default_factory=dict)
    project_outline: dict[str, Any] | None = None
    finalization_phase: Literal["saving_changes"] | None = None
    activity_phase: Literal["thinking", "using_tools", "summarizing", "checking_images"] | None = None
    settled_status: Literal["completed", "failed", "cancelled"] | None = None
    settled_stop_reason: str | None = None
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
    pre_run_checkpoint_id: str | None = None
    checkpoint_ids: list[str] = Field(default_factory=list)
    resume_checkpoint_id: str | None = None
    related_files: list[RelatedFile] = Field(default_factory=list)
    effective_setup: EffectiveSetup | None = None
    starting_snapshot_id: str | None = None
    final_snapshot_id: str | None = None
    host_shell: HostShellFacts = Field(default_factory=HostShellFacts)
    pending_interrupt: PendingInterrupt | None = None
    browser_control: Literal["agent", "taking_control", "user"] = "agent"
    browser_revision: int = 0
    browser_observation: str | None = None
    browser_pause_dispatches: dict[str, list[int]] = Field(default_factory=dict)
    browser_tool_proposals: dict[str, int] = Field(default_factory=dict)
