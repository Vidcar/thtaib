"""Reusable configuration and folder bindings; execution authority stays separate."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SetupConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None inherits a layer; an empty selection deliberately selects nothing.
    deployment_id: str | None = None
    bundle_id: str | None = None
    profile_id: str | None = None
    inherit_deployment_settings: bool | None = None
    instructions: str | None = None
    presented_tools: list[str] | None = None
    connection_ids: list[str] | None = None
    memory_version_refs: list[str] | None = None
    skill_version_refs: list[str] | None = None
    protected_instruction_version_refs: list[str] | None = None
    embedding_deployment_id: str | None = None
    per_request_overrides: dict[str, Any] | None = None
    requires_project: bool | None = None
    requires_host_shell: bool | None = None


class SetupDependencyIssue(BaseModel):
    kind: str
    id: str
    reason: str


class InstructionLayer(BaseModel):
    name: str
    content: str
    source_id: str | None = None


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


class SetupResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str | None = None
    agent_setup_version_id: str | None = None
    overrides: SetupConfiguration = Field(default_factory=SetupConfiguration)
