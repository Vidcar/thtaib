"""HTTP routes for MOD-006 compatibility records. Loopback smoke only."""

from __future__ import annotations

from fastapi import APIRouter, Request

from workbench_backend.inference.compatibility import (
    CompatibilityAssessRequest,
    CompatibilityService,
    UserOverrideRequest,
)
from workbench_backend.inference.service import ModelManager

router = APIRouter(prefix="/v1/compatibility")


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
