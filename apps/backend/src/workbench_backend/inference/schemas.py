"""Pydantic records for the model manager. These are application records, not weights."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class FileRole(str, Enum):
    primary_weights = "primary_weights"
    shard = "shard"
    companion = "companion"


class BundleSourceKind(str, Enum):
    huggingface = "huggingface"
    local = "local"


class ImportStatus(str, Enum):
    running = "running"
    complete = "complete"
    failed = "failed"
    interrupted = "interrupted"


class ManagementScope(str, Enum):
    managed = "managed"
    connected = "connected"


class DeploymentStatus(str, Enum):
    starting = "starting"
    running = "running"
    unhealthy = "unhealthy"
    stopped = "stopped"
    failed = "failed"


class BundleSource(BaseModel):
    kind: BundleSourceKind
    repo_id: str | None = None
    requested_revision: str | None = None
    resolved_revision: str | None = None
    original_path: str | None = None


class BundleFile(BaseModel):
    role: FileRole
    name: str
    path: str
    sha256: str
    size_bytes: int


class ModelBundle(BaseModel):
    id: str
    display_name: str
    format: Literal["gguf"] = "gguf"
    quantization: str | None = None
    source: BundleSource
    files: list[BundleFile]
    shards: list[BundleFile] = Field(default_factory=list)
    companions: list[BundleFile] = Field(default_factory=list)
    primary_path: str | None = None
    created_at: str
    status: ImportStatus = ImportStatus.complete
    disk_matches: bool = True


class ImportJob(BaseModel):
    id: str
    kind: BundleSourceKind
    status: ImportStatus
    display_name: str | None = None
    bundle_id: str | None = None
    error: str | None = None
    created_at: str
    finished_at: str | None = None


class HuggingFaceImportRequest(BaseModel):
    repo_id: str
    revision: str
    allow_patterns: list[str] | None = None
    display_name: str | None = None


class LocalImportRequest(BaseModel):
    source_path: str
    display_name: str | None = None


class SettingNote(BaseModel):
    key: str
    requested: Any = None
    applied: Any = None
    reason: str


class SettingsBag(BaseModel):
    requested: dict[str, Any] = Field(default_factory=dict)
    applied: dict[str, Any] = Field(default_factory=dict)
    unsupported: list[str] = Field(default_factory=list)
    overridden: list[SettingNote] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)


class SettingsBags(BaseModel):
    startup: SettingsBag = Field(default_factory=SettingsBag)
    per_request: SettingsBag = Field(default_factory=SettingsBag)
    agent: SettingsBag = Field(default_factory=SettingsBag)


class ProfileWriteRequest(BaseModel):
    display_name: str
    bundle_id: str | None = None
    startup: dict[str, Any] = Field(default_factory=dict)
    per_request: dict[str, Any] = Field(default_factory=dict)
    agent: dict[str, Any] = Field(default_factory=dict)


class SettingsPreviewRequest(BaseModel):
    startup: dict[str, Any] = Field(default_factory=dict)
    per_request: dict[str, Any] = Field(default_factory=dict)
    agent: dict[str, Any] = Field(default_factory=dict)


class RunProfile(BaseModel):
    id: str
    display_name: str
    bundle_id: str | None = None
    bags: SettingsBags
    created_at: str
    updated_at: str


class ResourceUsage(BaseModel):
    available: bool
    cpu_percent: float | None = None
    rss_bytes: int | None = None
    reason: str | None = None


class HealthReport(BaseModel):
    healthy: bool
    endpoint: str | None = None
    checked: str
    detail: str | None = None
    resource_usage: ResourceUsage | None = None


class RuntimeManifest(BaseModel):
    schema_version: int = 1
    product: str = "Local AI Workbench"
    engine: str = "llama.cpp"
    component: str = "llama-server"
    platform: str
    flavor: str
    release_tag: str
    source_url: str | None = None
    asset_name: str | None = None
    sha256: str | None = None
    install_dir: str
    executable: str
    path_fallback: Literal["unsupported"] = "unsupported"
    status: Literal["ready", "failed", "interrupted"] = "ready"
    error: str | None = None


class PinRuntimeRequest(BaseModel):
    """Production pin downloads the Windows llama-server asset.

    ``local_executable`` is only for an already-managed binary or a test
    fixture. It still writes a runtime-manifest and never uses PATH.
    """

    local_executable: str | None = None


class ManagedDeploymentRequest(BaseModel):
    bundle_id: str
    profile_id: str | None = None
    startup: dict[str, Any] = Field(default_factory=dict)
    auto_start: bool = True


class ConnectedDeploymentRequest(BaseModel):
    endpoint: str
    display_name: str | None = None


class Deployment(BaseModel):
    id: str
    display_name: str
    scope: ManagementScope
    status: DeploymentStatus
    bundle_id: str | None = None
    profile_id: str | None = None
    endpoint: str | None = None
    requested_startup: dict[str, Any] = Field(default_factory=dict)
    applied_startup: dict[str, Any] = Field(default_factory=dict)
    settings: SettingsBags = Field(default_factory=SettingsBags)
    pid: int | None = None
    health: HealthReport | None = None
    resource_usage: ResourceUsage | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class InspectTensor(BaseModel):
    name: str
    shape: list[int]
    n_elements: int
    n_bytes: int
    tensor_type: str


class InspectReport(BaseModel):
    bundle_id: str
    file_path: str
    sha256: str
    reader: str = "gguf.GGUFReader"
    reader_mode: Literal["r"] = "r"
    metadata_edited: Literal[False] = False
    architecture: str | None = None
    name: str | None = None
    quantization_version: int | None = None
    file_type: int | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    omitted_fields: list[str] = Field(default_factory=list)
    tensors: list[InspectTensor] = Field(default_factory=list)


class SmokeResult(BaseModel):
    ok: bool
    endpoint: str
    detail: str | None = None
    adapter: Literal["openai-compatible-smoke"] = "openai-compatible-smoke"
    note: str = "Thin OpenAI-compatible smoke only. Not a Deep Agents / LangChain adapter."
