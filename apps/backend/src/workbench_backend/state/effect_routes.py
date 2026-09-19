"""HTTP routes for STATE-004 unknown-effect safety. Loopback smoke only."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from workbench_backend.errors import StateError
from workbench_backend.state.effects import (
    AcknowledgeEffectRequest,
    DispatchEffectRequest,
    EffectService,
    ReconcileEffectRequest,
    RecoverEffectRequest,
)

router = APIRouter(prefix="/v1/effects")


def get_effects(request: Request) -> EffectService:
    return request.app.state.effects


@router.get("")
def list_effects(
    request: Request,
    run_id: str | None = Query(default=None),
    unresolved_only: bool = Query(default=False),
) -> object:
    return get_effects(request).list_effects(run_id=run_id, unresolved_only=unresolved_only)


@router.post("")
def dispatch_effect(request: Request, body: DispatchEffectRequest) -> object:
    return get_effects(request).dispatch(body)


@router.get("/{effect_id}")
def get_effect(request: Request, effect_id: str) -> object:
    return get_effects(request).get_effect(effect_id)


@router.post("/{effect_id}/acknowledge")
def acknowledge_effect(
    request: Request,
    effect_id: str,
    body: AcknowledgeEffectRequest | None = None,
) -> object:
    return get_effects(request).acknowledge(effect_id, body)


@router.post("/{effect_id}/recover")
def recover_effect(
    request: Request,
    effect_id: str,
    body: RecoverEffectRequest | None = None,
) -> object:
    return get_effects(request).recover(effect_id, body)


@router.post("/{effect_id}/reconcile")
def reconcile_effect(request: Request, effect_id: str, body: ReconcileEffectRequest) -> object:
    return get_effects(request).reconcile(effect_id, body)


@router.post("/{effect_id}/rollback")
def refuse_rollback(request: Request, effect_id: str) -> object:
    refusal = get_effects(request).refuse_rollback(effect_id)
    raise StateError(
        refusal.note,
        code=refusal.code,
        status_code=409,
        details=refusal.model_dump(mode="json"),
    )
