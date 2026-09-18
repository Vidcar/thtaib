"""HTTP routes for the model manager. Loopback smoke only; OQ-002 stays open."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from workbench_backend.errors import ManagerError
from workbench_backend.inference.schemas import (
    ConnectedDeploymentRequest,
    HuggingFaceImportRequest,
    LocalImportRequest,
    ManagedDeploymentRequest,
    PinRuntimeRequest,
    ProfileWriteRequest,
    SettingsPreviewRequest,
)
from workbench_backend.inference.service import ModelManager

router = APIRouter(prefix="/v1")


def get_manager(request: Request) -> ModelManager:
    return request.app.state.manager


@router.get("/paths")
def paths(request: Request) -> dict[str, str]:
    return get_manager(request).describe_paths()


@router.post("/imports/huggingface")
def import_huggingface(request: Request, body: HuggingFaceImportRequest) -> object:
    return get_manager(request).import_huggingface(body)


@router.post("/imports/local")
def import_local(request: Request, body: LocalImportRequest) -> object:
    return get_manager(request).import_local(body)


@router.get("/imports")
def list_imports(request: Request) -> object:
    return get_manager(request).list_jobs()


@router.get("/imports/{job_id}")
def get_import(request: Request, job_id: str) -> object:
    return get_manager(request).get_job(job_id)


@router.get("/bundles")
def list_bundles(request: Request) -> object:
    return get_manager(request).list_bundles()


@router.get("/bundles/{bundle_id}")
def get_bundle(request: Request, bundle_id: str) -> object:
    return get_manager(request).get_bundle(bundle_id)


@router.get("/bundles/{bundle_id}/inspect")
def inspect_bundle(request: Request, bundle_id: str) -> object:
    return get_manager(request).inspect_bundle(bundle_id)


@router.get("/profiles")
def list_profiles(request: Request) -> object:
    return get_manager(request).list_profiles()


@router.post("/profiles")
def create_profile(request: Request, body: ProfileWriteRequest) -> object:
    return get_manager(request).create_profile(body)


@router.get("/profiles/{profile_id}")
def get_profile(request: Request, profile_id: str) -> object:
    return get_manager(request).get_profile(profile_id)


@router.put("/profiles/{profile_id}")
def update_profile(request: Request, profile_id: str, body: ProfileWriteRequest) -> object:
    return get_manager(request).update_profile(profile_id, body)


@router.post("/settings/preview")
def preview_settings(request: Request, body: SettingsPreviewRequest) -> object:
    return get_manager(request).resolve_preview(
        startup=body.startup,
        per_request=body.per_request,
        agent=body.agent,
    )


@router.get("/runtime")
def get_runtime(request: Request) -> object:
    return get_manager(request).current_runtime()


@router.post("/runtime/pin")
def pin_runtime(request: Request, body: PinRuntimeRequest | None = None) -> object:
    return get_manager(request).pin_runtime(body or PinRuntimeRequest())


@router.get("/deployments")
def list_deployments(request: Request) -> object:
    return get_manager(request).list_deployments()


@router.post("/deployments/managed")
def create_managed(request: Request, body: ManagedDeploymentRequest) -> object:
    return get_manager(request).create_managed(body)


@router.post("/deployments/connected")
def attach_connected(request: Request, body: ConnectedDeploymentRequest) -> object:
    return get_manager(request).attach_connected(body)


@router.get("/deployments/{deployment_id}")
def get_deployment(request: Request, deployment_id: str) -> object:
    return get_manager(request).get_deployment(deployment_id)


@router.post("/deployments/{deployment_id}/start")
def start_deployment(request: Request, deployment_id: str) -> object:
    return get_manager(request).start_deployment(deployment_id)


@router.post("/deployments/{deployment_id}/stop")
def stop_deployment(request: Request, deployment_id: str) -> object:
    return get_manager(request).stop_deployment(deployment_id)


@router.post("/deployments/{deployment_id}/detach")
def detach_deployment(request: Request, deployment_id: str) -> object:
    return get_manager(request).detach_deployment(deployment_id)


@router.get("/deployments/{deployment_id}/health")
def deployment_health(request: Request, deployment_id: str) -> object:
    return get_manager(request).deployment_health(deployment_id)


@router.post("/deployments/{deployment_id}/smoke")
def deployment_smoke(request: Request, deployment_id: str) -> object:
    return get_manager(request).deployment_smoke(deployment_id)


def manager_error_handler(_request: Request, exc: ManagerError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "code": exc.code},
    )
