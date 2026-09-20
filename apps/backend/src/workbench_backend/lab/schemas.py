"""Lab case, snapshot and result records. Inspect-style building blocks only."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from workbench_backend.agents.schemas import AgentBudgets, TaskCriteria, ToolMode
from workbench_backend.knowledge.redaction import DETECTOR_LIMITATIONS
from workbench_backend.knowledge.schemas import KnowledgeBinding


class WorkspaceFileMap(BaseModel):
    files: dict[str, str] = Field(default_factory=dict)


class WorkspaceCreateRequest(BaseModel):
    display_name: str
    files: dict[str, str] = Field(default_factory=dict)
    allowlist: list[str] | None = None


class WorkspaceWriteRequest(BaseModel):
    files: dict[str, str] = Field(default_factory=dict)


class LabWorkspace(BaseModel):
    id: str
    display_name: str
    path: str
    allowlist: list[str] | None = None
    origin: Literal["created", "restored"] = "created"
    parent_workspace_id: str | None = None
    snapshot_id: str | None = None
    case_id: str | None = None
    created_at: str


class SnapshotFile(BaseModel):
    path: str
    sha256: str
    size_bytes: int


class SnapshotExclusion(BaseModel):
    path: str
    reason: str


SnapshotKind = Literal["starting", "checkpoint", "final"]
InputOrigin = Literal["starting_snapshot", "capture_time_workspace"]


class SnapshotManifest(BaseModel):
    id: str
    workspace_id: str
    captured_at: str
    kind: SnapshotKind = "final"
    mechanism: Literal["application_directory_snapshot"] = "application_directory_snapshot"
    not_git_commit: Literal[True] = True
    included_files: list[SnapshotFile] = Field(default_factory=list)
    exclusions: list[SnapshotExclusion] = Field(default_factory=list)
    environment_restore: Literal["not_this_milestone"] = "not_this_milestone"
    environment_exclusions: list[str] = Field(default_factory=list)
    external_effect_rollback: Literal["not_supported"] = "not_supported"
    rollback_promise: Literal["none"] = "none"
    unresolved_side_effects: list[str] = Field(default_factory=list)
    allowlist: list[str] | None = None
    tree_path: str


class CaptureRequest(BaseModel):
    workspace_id: str
    run_id: str | None = None
    task: str | None = None
    deployment_id: str | None = None
    profile_id: str | None = None
    presented_tools: list[str] | None = None
    criteria: TaskCriteria | None = None
    allowlist: list[str] | None = None
    memory_version_refs: list[str] | None = None
    skill_version_refs: list[str] | None = None
    protected_instruction_version_refs: list[str] | None = None
    knowledge_version_refs: list[str] | None = None
    embedding_deployment_id: str | None = None
    retrieval_project_paths: list[str] | None = None


class LabCase(BaseModel):
    id: str
    snapshot_id: str
    snapshot_kind: SnapshotKind = "final"
    input_origin: InputOrigin = "capture_time_workspace"
    source_run_id: str | None = None
    source_workspace_id: str
    task: str
    profile_id: str | None = None
    deployment_id: str | None = None
    presented_tools: list[str] = Field(default_factory=list)
    system_prompt: str | None = None
    criteria: TaskCriteria = Field(default_factory=TaskCriteria)
    budgets: AgentBudgets | None = None
    tool_fixtures: list[dict[str, Any]] = Field(default_factory=list)
    acceptance_checks: TaskCriteria = Field(default_factory=TaskCriteria)
    dependency_versions: dict[str, str] = Field(default_factory=dict)
    memory_version_refs: list[str] = Field(default_factory=list)
    skill_version_refs: list[str] = Field(default_factory=list)
    protected_instruction_version_refs: list[str] = Field(default_factory=list)
    exclusions: list[SnapshotExclusion] = Field(default_factory=list)
    environment_restore: Literal["not_this_milestone"] = "not_this_milestone"
    environment_exclusions: list[str] = Field(default_factory=list)
    external_effect_rollback: Literal["not_supported"] = "not_supported"
    rollback_promise: Literal["none"] = "none"
    unresolved_side_effects: list[str] = Field(default_factory=list)
    created_at: str
    snapshot_path: str
    knowledge: KnowledgeBinding = "none"
    embedding_deployment_id: str | None = None
    retrieval_project_paths: list[str] = Field(default_factory=list)


class RestoreResult(BaseModel):
    workspace: LabWorkspace
    case_id: str
    parent_workspace_id: str
    parent_unchanged: bool
    branch: dict[str, str]
    deviations: list[str] = Field(default_factory=list)
    snapshot_id: str
    snapshot_kind: SnapshotKind = "final"
    input_origin: InputOrigin = "capture_time_workspace"
    external_effects_rolled_back: Literal[False] = False
    rollback_promise: Literal["none"] = "none"
    unresolved_side_effects: list[str] = Field(default_factory=list)


class RerunRequest(BaseModel):
    tool_mode: ToolMode
    workspace_id: str
    criteria: TaskCriteria | None = None
    presented_tools: list[str] | None = None


class AppliedConfig(BaseModel):
    deployment_id: str | None = None
    profile_id: str | None = None
    presented_tools: list[str] = Field(default_factory=list)
    tool_mode: ToolMode
    system_prompt: str | None = None
    criteria: TaskCriteria = Field(default_factory=TaskCriteria)
    dependency_versions: dict[str, str] = Field(default_factory=dict)
    workspace_id: str
    memory_version_refs: list[str] = Field(default_factory=list)
    skill_version_refs: list[str] = Field(default_factory=list)
    protected_instruction_version_refs: list[str] = Field(default_factory=list)
    knowledge: KnowledgeBinding = "none"
    embedding_deployment_id: str | None = None
    retrieval_project_paths: list[str] = Field(default_factory=list)
    harness: Literal["deepagents"] = "deepagents"
    adapter: Literal["mod-005"] = "mod-005"
    evaluation_kind: Literal["task_evaluation"] = "task_evaluation"
    building_blocks: Literal["inspect_ai"] = "inspect_ai"
    second_agent_loop: Literal[False] = False


class LabResult(BaseModel):
    id: str
    case_id: str
    workspace_id: str
    source_run_id: str | None = None
    agent_run_id: str
    tool_mode: ToolMode
    tool_mode_label: str
    recorded_is_not_live_proof: bool
    evaluation_kind: Literal["task_evaluation"] = "task_evaluation"
    building_blocks: Literal["inspect_ai"] = "inspect_ai"
    harness: Literal["deepagents"] = "deepagents"
    adapter: Literal["mod-005"] = "mod-005"
    second_agent_loop: Literal[False] = False
    applied_config: AppliedConfig
    evidence: dict[str, Any] = Field(default_factory=dict)
    judgement: dict[str, Any] = Field(default_factory=dict)
    deviations: list[str] = Field(default_factory=list)
    parent_workspace_unchanged: bool = True
    created_at: str


class EngineMeasureRequest(BaseModel):
    deployment_id: str | None = None


class EngineMeasurement(BaseModel):
    id: str
    kind: Literal["engine_measurement"] = "engine_measurement"
    engine: Literal["llama-bench"] = "llama-bench"
    available: bool
    success: bool = False
    reason: str | None = None
    scores: dict[str, Any] | None = None
    raw_output: str | None = None
    command: list[str] | None = None
    deployment_id: str | None = None
    runtime_executable: str | None = None
    created_at: str
    note: str = (
        "Engine measurement is separate from task evaluation. "
        "Scores are never fabricated when llama-bench is unavailable."
    )


class CaseExport(BaseModel):
    case: LabCase
    snapshot: SnapshotManifest
    secret_scan_clean: bool
    export_status: Literal["clean", "sanitized"] = "clean"
    sanitized_fields: list[str] = Field(default_factory=list)
    exported_files: dict[str, str] = Field(default_factory=dict)
    detector_limitations: str = DETECTOR_LIMITATIONS
    note: str = (
        "Shareable export sanitizes or blocks detectable unsafe content. "
        "Filename exclusions are not sufficient. Detector is incomplete."
    )
