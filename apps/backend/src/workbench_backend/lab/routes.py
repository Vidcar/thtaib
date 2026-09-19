"""Minimal Lab HTTP API. Not Chat or Builder."""

from __future__ import annotations

from fastapi import APIRouter, Request

from workbench_backend.lab.schemas import (
    CaptureRequest,
    EngineMeasureRequest,
    RerunRequest,
    WorkspaceCreateRequest,
    WorkspaceWriteRequest,
)
from workbench_backend.lab.service import LabService

router = APIRouter(prefix="/v1/lab")


def get_lab(request: Request) -> LabService:
    return request.app.state.lab


@router.post("/workspaces")
def create_workspace(request: Request, body: WorkspaceCreateRequest) -> object:
    return get_lab(request).create_workspace(body)


@router.get("/workspaces")
def list_workspaces(request: Request) -> object:
    return get_lab(request).list_workspaces()


@router.get("/workspaces/{workspace_id}")
def get_workspace(request: Request, workspace_id: str) -> object:
    return get_lab(request).get_workspace(workspace_id)


@router.get("/workspaces/{workspace_id}/files")
def read_workspace_files(request: Request, workspace_id: str) -> object:
    return {"files": get_lab(request).read_workspace_files(workspace_id)}


@router.put("/workspaces/{workspace_id}/files")
def write_workspace_files(request: Request, workspace_id: str, body: WorkspaceWriteRequest) -> object:
    workspace = get_lab(request).write_workspace_files(workspace_id, body.files)
    return {"workspace": workspace, "files": get_lab(request).read_workspace_files(workspace_id)}


@router.post("/cases/capture")
def capture_case(request: Request, body: CaptureRequest) -> object:
    return get_lab(request).capture(body)


@router.get("/cases")
def list_cases(request: Request) -> object:
    return get_lab(request).list_cases()


@router.get("/cases/{case_id}")
def get_case(request: Request, case_id: str) -> object:
    return get_lab(request).get_case(case_id)


@router.get("/cases/{case_id}/export")
def export_case(request: Request, case_id: str) -> object:
    return get_lab(request).export_case(case_id)


@router.post("/cases/{case_id}/restore")
def restore_case(request: Request, case_id: str) -> object:
    return get_lab(request).restore(case_id)


@router.post("/cases/{case_id}/rerun")
def rerun_case(request: Request, case_id: str, body: RerunRequest) -> object:
    return get_lab(request).rerun(case_id, body)


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(request: Request, snapshot_id: str) -> object:
    return get_lab(request).get_snapshot(snapshot_id)


@router.get("/results")
def list_results(request: Request) -> object:
    return get_lab(request).list_results()


@router.get("/results/{result_id}")
def get_result(request: Request, result_id: str) -> object:
    return get_lab(request).get_result(result_id)


@router.post("/engine-measurements")
def measure_engine(request: Request, body: EngineMeasureRequest) -> object:
    return get_lab(request).measure_engine(body)


@router.get("/engine-measurements")
def list_engine_measurements(request: Request) -> object:
    return get_lab(request).list_measurements()
