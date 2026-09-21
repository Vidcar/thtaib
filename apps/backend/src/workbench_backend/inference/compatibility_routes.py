"""HTTP routes for MOD-006 compatibility records. Loopback smoke only."""

from __future__ import annotations

from fastapi import APIRouter, Request

from workbench_backend.inference.compatibility import (
    CompatibilityAssessRequest,
    CompatibilityService,
    UserOverrideRequest,
)
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.capabilities import CapabilityEvidence, CapabilityProbeRequest, capability_support
from workbench_backend.inference.probes import run_capability_probe

router = APIRouter(prefix="/v1/compatibility")


@router.post("/deployments/{deployment_id}/probes", response_model=CapabilityEvidence)
def probe(request: Request, deployment_id: str, body: CapabilityProbeRequest) -> CapabilityEvidence:
    return run_capability_probe(get_manager(request), deployment_id, body)


@router.get("/deployments/{deployment_id}/probes")
def probe_evidence(request: Request, deployment_id: str) -> object:
    deployment = get_manager(request).get_deployment(deployment_id)
    return {
        "evidence": deployment.capability_evidence,
        "current_support": {name: capability_support(deployment, name) for name in (
            "text_stream", "tools", "structured_native", "structured_tools", "structured_with_tools", "structured_tools_with_tools", "reasoning", "reasoning_replay", "image"
        )},
    }


def get_compatibility(request: Request) -> CompatibilityService:
    return request.app.state.compatibility


def get_manager(request: Request) -> ModelManager:
    return request.app.state.manager


@router.get("/records")
def list_records(request: Request) -> object:
    return get_compatibility(request).list_records()


@router.get("/records/{record_id}")
def get_record(request: Request, record_id: str) -> object:
    return get_compatibility(request).get_record(record_id)


@router.post("/records/{record_id}/overrides")
def add_override(request: Request, record_id: str, body: UserOverrideRequest) -> object:
    return get_compatibility(request).add_user_override(record_id, body)


@router.post("/assess")
def assess(request: Request, body: CompatibilityAssessRequest) -> object:
    service = get_compatibility(request)
    if body.bundle_id:
        bundle = get_manager(request).get_bundle(body.bundle_id)
        return service.assess_bundle(bundle)
    if not body.selector and not body.display_name:
        return service.assess(selector="unfamiliar")
    return service.assess(selector=body.selector, display_name=body.display_name)
