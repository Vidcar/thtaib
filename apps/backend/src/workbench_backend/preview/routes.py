"""Status and explicit stop control for project preview processes."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/v1/previews")


@router.get("/{thread_id}")
def preview_status(request: Request, thread_id: str):
    return request.app.state.preview.status(thread_id)


@router.delete("/{thread_id}")
def stop_preview(request: Request, thread_id: str):
    stopped = request.app.state.preview.stop(thread_id)
    return {"stopped": stopped, **request.app.state.preview.status(thread_id)}


@router.post("/{thread_id}/reset")
def reset_lost_preview(request: Request, thread_id: str):
    return request.app.state.preview.reset_lost(thread_id)
