"""Manual backup and clean-root restore routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, ConfigDict
from workbench_backend.state.activation import register_restore, prepare_activation

from workbench_backend.state.backup import (
    BackupCreateRequest,
    BackupCreateResult,
    BackupError,
    BackupRestoreRequest,
    BackupRestoreResult,
    BackupService,
)

router = APIRouter(prefix="/v1/backups")


def get_backups(request: Request) -> BackupService:
    return request.app.state.backups


@router.post("", response_model=BackupCreateResult)
def create_backup(request: Request, body: BackupCreateRequest) -> BackupCreateResult:
    try:
        return get_backups(request).create_backup(body)
    except BackupError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc


@router.post("/restore", response_model=BackupRestoreResult)
def restore_backup(request: Request, body: BackupRestoreRequest) -> BackupRestoreResult:
    try:
        with request.app.state.maintenance_gate.mutation():
            result = get_backups(request).restore_backup(body)
            register_restore(request.app.state.app_store, result)
            return result
    except BackupError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc


class RestoreActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination_root: str


@router.post("/activate")
def activate_restore(request: Request, body: RestoreActivationRequest, background_tasks: BackgroundTasks) -> dict:
    state = request.app.state
    restart = getattr(state, "restart_backend", None)
    if not callable(restart):
        raise HTTPException(status_code=409, detail="This backend launcher does not support coordinated restart.")
    gate = state.maintenance_gate
    acquired = False
    try:
        gate.begin("restore_activation")
        acquired = True
        if state.backups.active_work():
            raise BackupError("Stop running work before activating the restore.", code="restore_active_work")
        destination = prepare_activation(state, body.destination_root)
    except BackupError as exc:
        if acquired:
            gate.end()
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    except Exception:
        if acquired:
            gate.end()
        raise
    background_tasks.add_task(restart)
    return {"destination_root": destination, "restarting": True}
