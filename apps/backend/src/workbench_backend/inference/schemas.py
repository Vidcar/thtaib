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
    pending = "pending"
    running = "running"
    stopping = "stopping"
    stopped = "stopped"
    complete = "complete"
    failed = "failed"
    interrupted = "interrupted"
    discarded = "discarded"


class ManagementScope(str, Enum):
    managed = "managed"
    connected = "connected"


class DeploymentStatus(str, Enum):
    starting = "starting"
    running = "running"
    unhealthy = "unhealthy"
    stopped = "stopped"
    failed = "failed"


class ImportStage(str, Enum):
    queued = "queued"
    metadata = "metadata"
    transfer = "transfer"
    verify = "verify"
    install = "install"
    repair = "repair"
    cleanup = "cleanup"
    done = "done"


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
    ownership: Literal["managed", "external"] = "managed"


class HuggingFaceConfiguration(BaseModel):
    source_repo_id: str | None = None
    source_revision: str | None = None
    source_verified: bool = False
    source_note: str | None = None
    template_origin: Literal["gguf", "repository", "publisher", "none"] = "none"
    template_file: str | None = None
    template_differs: bool = False
    template_compatible: bool | None = None
    generation_defaults: dict[str, Any] = Field(default_factory=dict)
    unsupported: dict[str, str] = Field(default_factory=dict)


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
    managed_root: str | None = None
    created_at: str
    status: ImportStatus = ImportStatus.complete
    disk_matches: bool = True
    default_configuration_id: str | None = None
    huggingface_configuration: HuggingFaceConfiguration | None = None


class ProjectorSelectionRequest(BaseModel):
    path: str | None


class ProjectorCandidate(BaseModel):
    path: str
    name: str
    size_bytes: int
    selected: bool = False
    metadata_name: str | None = None
    architecture: str | None = None
    projector_type: str | None = None
    compatibility: Literal["unverified"] = "unverified"
    inspection_error: str | None = None


class BundleProjectors(BaseModel):
    bundle_id: str
    selected_path: str | None = None
    candidates: list[ProjectorCandidate] = Field(default_factory=list)


class ImportProgress(BaseModel):
    stage: ImportStage = ImportStage.queued
    message: str | None = None
    files_done: int = 0
    files_total: int | None = None
    bytes_done: int = 0
    bytes_total: int | None = None


class ImportJob(BaseModel):
    id: str
    kind: BundleSourceKind
    status: ImportStatus
    display_name: str | None = None
    bundle_id: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    progress: ImportProgress = Field(default_factory=ImportProgress)
    source_path: str | None = None
    repo_id: str | None = None
    requested_revision: str | None = None
    resolved_revision: str | None = None
    allow_patterns: list[str] | None = None
    staging_path: str | None = None
    install_root: str | None = None
    owned_install_path: str | None = None
    worker_id: str | None = None
    transfer_pid: int | None = None
    transfer_create_time: float | None = None
    cancel_requested: bool = False
    retry_of: str | None = None
    repair_of_bundle_id: str | None = None


class StorageLocation(BaseModel):
    kind: Literal["managed", "staging", "cache", "metadata"]
    path: str
    bytes: int
    removable: bool = False
    reference_count: int = 0


class StorageSummary(BaseModel):
    install_root: str
    future_install_root: str
    managed_bytes: int = 0
    staging_bytes: int = 0
    cache_bytes: int = 0
    metadata_bytes: int = 0
    reclaimable_bytes: int = 0
    capacity_bytes: int | None = None
    available_bytes: int | None = None
    locations: list[StorageLocation] = Field(default_factory=list)


class HuggingFaceImportRequest(BaseModel):
    repo_id: str
    revision: str = "main"
    allow_patterns: list[str] | None = None
    display_name: str | None = None


class ChatTemplateSelectionRequest(BaseModel):
    origin: Literal["gguf", "repository", "publisher"]


class HuggingFaceInspectRequest(BaseModel):
    repo_id: str
    revision: str = "main"


class HubVariant(BaseModel):
    name: str
    files: list[str]
    size_bytes: int | None = None
    complete: bool = True


class HubSearchResult(BaseModel):
    repo_id: str
    downloads: int | None = None
    likes: int | None = None


class HubSource(BaseModel):
    repo_id: str
    resolved_revision: str | None = None
    verified: bool = False
    note: str | None = None
    guidance_files: list[str] = Field(default_factory=list)


class HubRepository(BaseModel):
    repo_id: str
    resolved_revision: str
    variants: list[HubVariant]
    projectors: list[HubVariant]
    guidance_files: list[str]
    warnings: list[str]
    file_sha256: dict[str, str | None] = Field(default_factory=dict)
    file_sizes: dict[str, int | None] = Field(default_factory=dict)
    source: HubSource | None = None
    gguf_candidates: list[HubSearchResult] = Field(default_factory=list)


class LocalImportRequest(BaseModel):
    source_path: str
    display_name: str | None = None
    copy_files: bool = True


class SettingNote(BaseModel):
    key: str
    requested: Any = None
    applied: Any = None
    reason: str


class SettingsBag(BaseModel):
    requested: dict[str, Any] = Field(default_factory=dict)
    applied: dict[str, Any] = Field(default_factory=dict)
    unsupported: list[str] = Field(default_factory=list)
    unsupported_notes: list[SettingNote] = Field(default_factory=list)
    overridden: list[SettingNote] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    retired: list[SettingNote] = Field(default_factory=list)
    """Requested keys the pinned runtime no longer accepts; each note says what replaces it."""


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
    expected_revision: int | None = None


class SettingsPreviewRequest(BaseModel):
    startup: dict[str, Any] = Field(default_factory=dict)
    per_request: dict[str, Any] = Field(default_factory=dict)
    agent: dict[str, Any] = Field(default_factory=dict)


class RunProfile(BaseModel):
    id: str
    display_name: str
    bundle_id: str | None = None
    bundle_name: str | None = Field(default=None, json_schema_extra={"readOnly": True})
    equivalent_configuration_ids: list[str] = Field(default_factory=list, json_schema_extra={"readOnly": True})
    merged_into_configuration_id: str | None = Field(default=None, json_schema_extra={"readOnly": True})
    configuration_origin: Literal["legacy", "recovered", "named"] = Field(default="legacy", json_schema_extra={"readOnly": True})
    bags: SettingsBags
    created_at: str
    updated_at: str
    revision: int = 1


class DefaultConfigurationRequest(BaseModel):
    configuration_id: str


class ModelConfigurationWriteRequest(ProfileWriteRequest):
    configuration_id: str | None = None
    make_default: bool = False


class ReconfigureDeploymentRequest(BaseModel):
    startup: dict[str, Any]
    replace_startup: bool = False
    model_configuration_id: str | None = None
    expected_configuration_revision: int | None = None
    expected_updated_at: str | None = None
    conversation_id: str | None = None


class RenameProfileRequest(BaseModel):
    display_name: str


class DuplicateProfileRequest(BaseModel):
    display_name: str | None = None


class LifecycleConsumer(BaseModel):
    kind: Literal["profile", "deployment", "chat", "lab_case", "agent_run", "import_job", "file", "project", "agent_setup_version", "knowledge", "knowledge_version", "setup_defaults", "chat_queue", "memory_proposal", "automatic_save_policy"]
    id: str
    label: str | None = None
    live: bool = False
    retained: bool = True
    future_use: bool = False
    effect: str | None = None


class DeleteFilePlan(BaseModel):
    path: str
    size_bytes: int
    removable: bool
    reason: str | None = None


class DeletePreview(BaseModel):
    target_kind: Literal["profile", "bundle", "project", "agent_setup", "knowledge", "skill_package", "connection", "credential"]
    target_id: str
    target_label: str | None = None
    summary: str | None = None
    blockers: list[LifecycleConsumer] = Field(default_factory=list)
    consumers: list[LifecycleConsumer] = Field(default_factory=list)
    files: list[DeleteFilePlan] = Field(default_factory=list)
    removable_bytes: int = 0
    retained: list[str] = Field(default_factory=list)


class DeploymentProfileChanges(BaseModel):
    deployment_id: str
    profile_id: str | None = None
    has_pending_startup_changes: bool = False
    pending_startup: dict[str, dict[str, Any]] = Field(default_factory=dict)
    has_pending_per_request_changes: bool = False
    has_pending_agent_changes: bool = False


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


class ProcessIdentity(BaseModel):
    """Owned managed-process identity. PID alone is not sufficient."""

    pid: int
    create_time: float
    executable: str


class ServerProperties(BaseModel):
    """What llama-server's ``GET /props`` reported once the deployment was healthy.

    Recorded as reported, not interpreted. This is not a compatibility
    record and not a capability claim (MOD-006 / OQ-007 stay open).
    """

    fetched: str
    source_url: str
    build_info: str | None = None
    model_alias: str | None = None
    model_path: str | None = None
    default_generation_settings: dict[str, Any] = Field(default_factory=dict)
    n_ctx: int | None = None
    total_slots: int | None = None
    modalities: dict[str, bool] = Field(default_factory=dict)
    chat_template_caps: dict[str, bool] = Field(default_factory=dict)
    chat_template: str | None = None
    bos_token: str | None = None
    eos_token: str | None = None


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
    companion_asset_name: str | None = None
    companion_sha256: str | None = None


class PinRuntimeRequest(BaseModel):
    """Production pin downloads the Windows CUDA 13.4 llama-server pair.

    ``local_executable`` pins an already-managed runtime directory (the
    executable plus sibling CUDA DLLs) or a test fixture. It still writes
    a runtime-manifest and never uses PATH.

    Pinning while a managed server is running is rejected unless
    ``stop_first`` is true.
    """

    local_executable: str | None = None
    stop_first: bool = False


class ManagedDeploymentRequest(BaseModel):
    bundle_id: str
    profile_id: str | None = None
    startup: dict[str, Any] = Field(default_factory=dict)
    auto_start: bool = True


class RuntimeControlOption(BaseModel):
    value: Any
    label: str
    description: str | None = None


class RuntimeControlDescriptor(BaseModel):
    key: str
    flag: str | None = None
    label: str
    description: str
    source: str
    applied: Any = None
    recommended: Any = None
    observed: Any = None
    default_value: Any = None
    default_source: str | None = None
    maximum: int | None = None
    supported: bool | None = None
    accepted_values: list[str] | None = None
    options: list[RuntimeControlOption] = Field(default_factory=list)


class GgufRuntimeMetadata(BaseModel):
    architecture: str | None = None
    name: str | None = None
    context_length: int | None = None
    block_count: int | None = None
    chat_template: str | None = None
    nextn_predict_layers: int | None = None
    has_mtp_tensors: bool = False


class BundleConfigurationOptions(BaseModel):
    bundle_id: str | None
    deployment_id: str | None = None
    context_size: RuntimeControlDescriptor
    gpu_layers: RuntimeControlDescriptor
    startup_defaults: dict[str, RuntimeControlDescriptor]
    per_request_defaults: dict[str, RuntimeControlDescriptor] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectedDeploymentRequest(BaseModel):
    endpoint: str
    display_name: str | None = None
    startup: dict[str, Any] = Field(default_factory=dict)


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
    startup_overrides: dict[str, Any] = Field(default_factory=dict)
    profile_snapshot: SettingsBags | None = None
    publisher_request_defaults: dict[str, Any] = Field(default_factory=dict)
    loaded_chat_template_origin: Literal["repository", "publisher"] | None = None
    settings: SettingsBags = Field(default_factory=SettingsBags)
    pid: int | None = None
    process_identity: ProcessIdentity | None = None
    health: HealthReport | None = None
    resource_usage: ResourceUsage | None = None
    server_props: ServerProperties | None = None
    capability_evidence: list[dict[str, Any]] = Field(default_factory=list)
    inference_identity: dict[str, Any] = Field(default_factory=dict)
    configuration_revision: int | None = None
    reconfiguration: dict[str, Any] | None = None
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
