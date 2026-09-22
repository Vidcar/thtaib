"""HTTP routes for the model manager. Privileged /v1; Issue #40 partial OQ-002."""

from __future__ import annotations

from fastapi import APIRouter, Request, Query

from workbench_backend.errors import manager_error_handler
from workbench_backend.inference.schemas import (
    ConnectedDeploymentRequest,
    HuggingFaceImportRequest,
    HuggingFaceInspectRequest,
    HubRepository,
    HubSearchResult,
    LocalImportRequest,
    ManagedDeploymentRequest,
    PinRuntimeRequest,
    ProfileWriteRequest,
    SettingsPreviewRequest,
    RenameProfileRequest,
    DeletePreview,
    DeploymentProfileChanges,
    ImportJob,
    StorageSummary,
    ModelBundle,
    RunProfile,
    Deployment,
    InspectReport,
    BundleConfigurationOptions,
    SettingsBags,
    RuntimeManifest,
    SmokeResult,
)
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.process_logs import deployment_log_path
from pydantic import BaseModel


class DeploymentLogResponse(BaseModel):
    available: bool
    text: str


class StorageLocationRequest(BaseModel):
    path: str


class StorageCleanupResponse(BaseModel):
    removed: list[str]

router = APIRouter(prefix="/v1")


def get_manager(request: Request) -> ModelManager:
    return request.app.state.manager


@router.get("/paths")
def paths(request: Request) -> dict[str, str]:
    return get_manager(request).describe_paths()


@router.post("/imports/huggingface", response_model=ImportJob, status_code=202)
def import_huggingface(request: Request, body: HuggingFaceImportRequest) -> ImportJob:
    return get_manager(request).imports.start_huggingface(body)


@router.post("/models/huggingface/inspect", response_model=HubRepository)
def inspect_huggingface(request: Request, body: HuggingFaceInspectRequest) -> HubRepository:
    return get_manager(request).bundles.hf.inspect(repo_id=body.repo_id, revision=body.revision)


@router.get("/models/huggingface/search", response_model=list[HubSearchResult])
def search_huggingface(request: Request, q: str = Query(min_length=1, max_length=200), limit: int = Query(default=20, ge=1, le=50)) -> list[HubSearchResult]:
    return get_manager(request).bundles.hf.search(q, limit=limit)


@router.post("/imports/local", response_model=ImportJob, status_code=202)
def import_local(request: Request, body: LocalImportRequest) -> ImportJob:
    return get_manager(request).imports.start_local(body)


@router.get("/imports", response_model=list[ImportJob])
def list_imports(request: Request) -> object:
    return get_manager(request).list_jobs()


@router.get("/imports/{job_id}", response_model=ImportJob)
def get_import(request: Request, job_id: str) -> object:
    return get_manager(request).get_job(job_id)


@router.post("/imports/{job_id}/cancel", response_model=ImportJob)
def cancel_import(request: Request, job_id: str) -> ImportJob:
    return get_manager(request).imports.cancel_job(job_id)


@router.post("/imports/{job_id}/retry", response_model=ImportJob, status_code=202)
def retry_import(request: Request, job_id: str) -> ImportJob:
    return get_manager(request).imports.retry_job(job_id)


@router.post("/imports/{job_id}/discard", response_model=ImportJob)
def discard_import(request: Request, job_id: str) -> ImportJob:
    return get_manager(request).imports.discard_job(job_id)


@router.post("/bundles/{bundle_id}/repair", response_model=ImportJob, status_code=202)
def repair_bundle(request: Request, bundle_id: str) -> ImportJob:
    return get_manager(request).imports.start_repair(bundle_id)


@router.get("/models/storage", response_model=StorageSummary)
def model_storage(request: Request) -> StorageSummary:
    return get_manager(request).imports.storage_summary()


@router.put("/models/storage", response_model=StorageSummary)
def set_model_storage(request: Request, body: StorageLocationRequest) -> StorageSummary:
    return get_manager(request).imports.set_install_location(body.path)


@router.post("/models/storage/cleanup", response_model=StorageCleanupResponse)
def clean_model_storage(request: Request) -> StorageCleanupResponse:
    imports = get_manager(request).imports
    return StorageCleanupResponse(removed=[*imports.cleanup_unreferenced_staging(), *imports.cleanup_cache()])


@router.get("/bundles", response_model=list[ModelBundle])
def list_bundles(request: Request) -> object:
    return get_manager(request).list_bundles()


@router.get("/bundles/{bundle_id}", response_model=ModelBundle)
def get_bundle(request: Request, bundle_id: str) -> object:
    return get_manager(request).get_bundle(bundle_id)


@router.get("/bundles/{bundle_id}/inspect", response_model=InspectReport)
def inspect_bundle(request: Request, bundle_id: str, refresh: bool = False) -> object:
    return get_manager(request).inspect_bundle(bundle_id, refresh=refresh)


@router.get("/bundles/{bundle_id}/configuration-options", response_model=BundleConfigurationOptions)
def bundle_configuration_options(
    request: Request,
    bundle_id: str,
    deployment_id: str | None = None,
    refresh: bool = False,
) -> object:
    return get_manager(request).get_bundle_configuration_options(
        bundle_id,
        deployment_id=deployment_id,
        refresh=refresh,
    )


@router.get("/bundles/{bundle_id}/compatibility")
def bundle_compatibility(request: Request, bundle_id: str) -> object:
    bundle = get_manager(request).get_bundle(bundle_id)
    return request.app.state.compatibility.assess_bundle(bundle)


@router.get("/profiles", response_model=list[RunProfile])
def list_profiles(request: Request) -> object:
    return get_manager(request).list_profiles()


@router.post("/profiles", response_model=RunProfile)
def create_profile(request: Request, body: ProfileWriteRequest) -> object:
    return get_manager(request).create_profile(body)


@router.get("/profiles/{profile_id}", response_model=RunProfile)
def get_profile(request: Request, profile_id: str) -> object:
    return get_manager(request).get_profile(profile_id)


@router.put("/profiles/{profile_id}", response_model=RunProfile)
def update_profile(request: Request, profile_id: str, body: ProfileWriteRequest) -> object:
    return get_manager(request).update_profile(profile_id, body)


@router.post("/profiles/{profile_id}/rename", response_model=RunProfile)
def rename_profile(request: Request, profile_id: str, body: RenameProfileRequest) -> object:
    return get_manager(request).rename_profile(profile_id, body.display_name)


@router.post("/profiles/{profile_id}/duplicate", response_model=RunProfile)
def duplicate_profile(request: Request, profile_id: str) -> object:
    return get_manager(request).duplicate_profile(profile_id)


@router.get("/profiles/{profile_id}/delete-preview", response_model=DeletePreview)
def profile_delete_preview(request: Request, profile_id: str) -> DeletePreview:
    return get_manager(request).profile_delete_preview(profile_id)


@router.delete("/profiles/{profile_id}", response_model=DeletePreview)
def delete_profile(request: Request, profile_id: str) -> DeletePreview:
    return get_manager(request).delete_profile(profile_id)


@router.get("/bundles/{bundle_id}/delete-preview", response_model=DeletePreview)
def bundle_delete_preview(request: Request, bundle_id: str) -> DeletePreview:
    return get_manager(request).bundle_delete_preview(bundle_id)


@router.delete("/bundles/{bundle_id}", response_model=DeletePreview)
def delete_bundle(request: Request, bundle_id: str) -> DeletePreview:
    return get_manager(request).delete_bundle(bundle_id)


@router.post("/settings/preview", response_model=SettingsBags)
def preview_settings(request: Request, body: SettingsPreviewRequest) -> object:
    return get_manager(request).resolve_preview(
        startup=body.startup,
        per_request=body.per_request,
        agent=body.agent,
    )


@router.get("/runtime", response_model=RuntimeManifest | None)
def get_runtime(request: Request) -> object:
    return get_manager(request).current_runtime()


@router.post("/runtime/pin", response_model=RuntimeManifest)
def pin_runtime(request: Request, body: PinRuntimeRequest | None = None) -> object:
    return get_manager(request).pin_runtime(body or PinRuntimeRequest())


@router.get("/deployments", response_model=list[Deployment])
def list_deployments(request: Request) -> object:
    return get_manager(request).list_deployments()


@router.post("/deployments/managed", response_model=Deployment)
def create_managed(request: Request, body: ManagedDeploymentRequest) -> object:
    return get_manager(request).create_managed(body)


@router.post("/deployments/connected", response_model=Deployment)
def attach_connected(request: Request, body: ConnectedDeploymentRequest) -> object:
    return get_manager(request).attach_connected(body)


@router.get("/deployments/{deployment_id}", response_model=Deployment)
def get_deployment(request: Request, deployment_id: str) -> object:
    return get_manager(request).get_deployment(deployment_id)


@router.post("/deployments/{deployment_id}/start", response_model=Deployment)
def start_deployment(request: Request, deployment_id: str) -> object:
    return get_manager(request).start_deployment(deployment_id)


@router.post("/deployments/{deployment_id}/stop", response_model=Deployment)
def stop_deployment(request: Request, deployment_id: str) -> object:
    return get_manager(request).stop_deployment(deployment_id)


@router.post("/deployments/{deployment_id}/reload", response_model=Deployment)
def reload_deployment(request: Request, deployment_id: str) -> object:
    return get_manager(request).reload_deployment(deployment_id)


@router.get("/deployments/{deployment_id}/profile-changes", response_model=DeploymentProfileChanges)
def deployment_profile_changes(request: Request, deployment_id: str) -> DeploymentProfileChanges:
    return get_manager(request).deployment_profile_changes(deployment_id)


@router.get("/deployments/{deployment_id}/logs", response_model=DeploymentLogResponse)
def deployment_logs(request: Request, deployment_id: str) -> DeploymentLogResponse:
    manager = get_manager(request)
    deployment = manager.get_deployment(deployment_id)
    log = deployment_log_path(manager.paths.logs, deployment.id).resolve()
    if not log.is_relative_to(manager.paths.logs.resolve()) or not log.is_file():
        return DeploymentLogResponse(available=False, text="No local engine log is available.")
    with log.open("rb") as handle:
        handle.seek(0, 2)
        handle.seek(max(0, handle.tell() - 32_768))
        text = handle.read(32_768).decode("utf-8", errors="replace")
    return DeploymentLogResponse(available=True, text=text)


@router.post("/deployments/{deployment_id}/detach", response_model=Deployment)
def detach_deployment(request: Request, deployment_id: str) -> object:
    return get_manager(request).detach_deployment(deployment_id)


@router.get("/deployments/{deployment_id}/health", response_model=Deployment)
def deployment_health(request: Request, deployment_id: str) -> object:
    return get_manager(request).deployment_health(deployment_id)


@router.post("/deployments/{deployment_id}/smoke", response_model=SmokeResult)
def deployment_smoke(request: Request, deployment_id: str) -> object:
    return get_manager(request).deployment_smoke(deployment_id)


__all__ = ["get_manager", "manager_error_handler", "router"]
