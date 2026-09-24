"""Reusable configuration and folder bindings; execution authority stays separate."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    criteria: str = Field(default="", max_length=16000)
    max_revisions: Literal[2] = 2


class SetupConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None inherits a layer; an empty selection deliberately selects nothing.
    deployment_id: str | None = None
    bundle_id: str | None = None
    model_configuration_id: str | None = None
    startup_overrides: dict[str, Any] | None = None
    profile_id: str | None = None
    inherit_deployment_settings: bool | None = None
    instructions: str | None = None
    presented_tools: list[str] | None = None
    approval_mode: Literal["ask", "full_access"] | None = None
    connection_ids: list[str] | None = None
    memory_version_refs: list[str] | None = None
    skill_version_refs: list[str] | None = None
    protected_instruction_version_refs: list[str] | None = None
    embedding_deployment_id: str | None = None
    per_request_overrides: dict[str, Any] | None = None
    requires_project: bool | None = None
    requires_host_shell: bool | None = None
    work_mode: Literal["work", "plan"] | None = None
    helper_agent_ids: list[str] | None = None
    review: ReviewConfiguration | None = None


class SetupDependencyIssue(BaseModel):
    kind: str
    id: str
    reason: str


class InstructionLayer(BaseModel):
    name: str
    content: str
    source_id: str | None = None


class FrozenHelperSelection(BaseModel):
    agent_id: str
    version_id: str
    name: str
    role: str | None = None
    configuration: SetupConfiguration
    instruction_layers: list[InstructionLayer] = Field(default_factory=list)
    settings_snapshot: dict[str, Any] | None = None


class ResolvedSetting(BaseModel):
    value: Any = None
    source: str
    source_id: str | None = None
    inherited: bool = False
    known: bool = True
    requires_reload: bool = False
    unavailable_reason: str | None = None
    requested_override: Any = None
    default_value: Any = None
    default_source: str | None = None
    supported: bool | None = None
    inherited_value: Any = None
    inherited_source: str | None = None


class ProjectRecord(BaseModel):
    id: str
    name: str
    path: str
    canonical_path: str
    active: bool = True
    defaults: SetupConfiguration = Field(default_factory=SetupConfiguration)
    created_at: str
    updated_at: str
    missing: bool = False


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    path: str = Field(min_length=1)
    defaults: SetupConfiguration = Field(default_factory=SetupConfiguration)


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    defaults: SetupConfiguration | None = None


class ProjectFile(BaseModel):
    name: str
    path: str
    kind: Literal["file", "directory"]
    size_bytes: int | None = None


class ProjectFiles(BaseModel):
    project_id: str
    path: str
    entries: list[ProjectFile]


class ProjectFileContent(BaseModel):
    """Read-only captured text for one project file. Not a model call."""

    project_id: str
    path: str
    size_bytes: int
    text: str | None = None
    text_unavailable_reason: str | None = None
    image_data_url: str | None = None


class AgentSetupVersion(BaseModel):
    id: str
    setup_id: str
    previous_version_id: str | None = None
    name: str
    role: str | None = None
    configuration: SetupConfiguration = Field(default_factory=SetupConfiguration)
    created_at: str


class AgentSetupRecord(BaseModel):
    id: str
    current_version_id: str
    active: bool = True
    created_at: str
    updated_at: str


class AgentSetupView(AgentSetupRecord):
    name: str
    role: str | None = None
    configuration: SetupConfiguration
    missing_dependencies: list[SetupDependencyIssue] = Field(default_factory=list)


class AgentSetupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    role: str | None = None
    configuration: SetupConfiguration = Field(default_factory=SetupConfiguration)


class AgentSetupUpdateRequest(AgentSetupCreateRequest):
    base_version: str


class AgentSetupDuplicateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)


class ResolvedSetupSelection(BaseModel):
    project_id: str | None = None
    agent_setup_id: str | None = None
    agent_setup_version_id: str | None = None
    configuration: SetupConfiguration
    instruction_layers: list[InstructionLayer] = Field(default_factory=list)
    effective_values: dict[str, ResolvedSetting] = Field(default_factory=dict)


class FrozenExecutionSelection(BaseModel):
    """Trusted app-owned queue snapshot; never accepted as start-request input."""

    selection: ResolvedSetupSelection
    settings: dict[str, Any]
    system_prompt: str | None = None


class SetupResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    editing_layer: Literal["application", "project", "agent", "conversation"] = "conversation"
    project_id: str | None = None
    agent_setup_version_id: str | None = None
    overrides: SetupConfiguration = Field(default_factory=SetupConfiguration)
