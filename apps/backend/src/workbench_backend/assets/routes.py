"""Retained files HTTP API, ready for app inclusion."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from workbench_backend.assets.schemas import (
    RetainedAsset,
    RetainedAssetContent,
    RetainedAssetDeletionPreview,
    RetainedAssetDeletionRequest,
    RetainedAssetListFilters,
    RetainedAssetOrigin,
    RetainedAssetPreview,
    RetainedAssetReuseRequest,
    RetainedUploadRequest,
)
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.assets.sources import SourceRange, SourceRangeRequest, read_source
from workbench_backend.inference.user_content import UserContentBlock

router = APIRouter(prefix="/v1/assets")


def get_assets(request: Request) -> RetainedAssetService:
    service = getattr(request.app.state, "assets", None)
    if service is None:
        service = RetainedAssetService(request.app.state.app_store)
        request.app.state.assets = service
    return service


def _require_explicit_asset_delete(body: RetainedAssetDeletionRequest) -> None:
    if body.session_ids or body.run_ids or body.project_paths or body.branch_ids or body.case_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "Asset delete endpoints accept explicit asset_ids only. "
                "Delete conversations, runs, branches or cases through their owning endpoint."
            ),
        )


@router.post("/uploads", response_model=RetainedAsset)
def retain_upload(request: Request, body: RetainedUploadRequest) -> RetainedAsset:
    return get_assets(request).retain_upload(body)


@router.get("", response_model=list[RetainedAsset])
def list_assets(
    request: Request,
    session_id: str | None = None,
    project_path: str | None = None,
    origin: RetainedAssetOrigin | None = None,
    include_deleted: bool = False,
) -> list[RetainedAsset]:
    return get_assets(request).list_assets(
        RetainedAssetListFilters(
            session_id=session_id,
            project_path=project_path,
            origin=origin,
            include_deleted=include_deleted,
        )
    )


@router.get("/{asset_id}/preview", response_model=RetainedAssetPreview)
def preview_asset(
    request: Request,
    asset_id: str,
    session_id: str | None = None,
    project_path: str | None = None,
) -> RetainedAssetPreview:
    return get_assets(request).preview(asset_id, session_id=session_id, project_path=project_path)


@router.get("/{asset_id}/content", response_model=RetainedAssetContent)
def asset_content(
    request: Request,
    asset_id: str,
    session_id: str | None = None,
    project_path: str | None = None,
) -> RetainedAssetContent:
    return get_assets(request).content(asset_id, session_id=session_id, project_path=project_path)


@router.post("/reuse", response_model=list[UserContentBlock])
def reuse_assets(request: Request, body: RetainedAssetReuseRequest) -> list[UserContentBlock]:
    return get_assets(request).current_user_content(body)


@router.post("/{asset_id}/source", response_model=SourceRange)
def asset_source(request: Request, asset_id: str, body: SourceRangeRequest) -> SourceRange:
    return read_source(get_assets(request), asset_id, body)


@router.post("/delete-preview", response_model=RetainedAssetDeletionPreview)
def delete_preview(
    request: Request,
    body: RetainedAssetDeletionRequest,
) -> RetainedAssetDeletionPreview:
    _require_explicit_asset_delete(body)
    return get_assets(request).deletion_preview(body)


@router.post("/delete", response_model=RetainedAssetDeletionPreview)
def delete_assets(
    request: Request,
    body: RetainedAssetDeletionRequest,
) -> RetainedAssetDeletionPreview:
    _require_explicit_asset_delete(body)
    return get_assets(request).mark_deletable_assets_deleted(body)
