"""Status and explicit stop control for project preview processes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from workbench_backend.errors import HarnessError

router = APIRouter(prefix="/v1/previews")


class StaticPreviewRequest(BaseModel):
    entry_path: str = Field(min_length=1, max_length=4096)


@router.post("/{thread_id}/start")
def start_static_preview(request: Request, thread_id: str, body: StaticPreviewRequest):
    store = request.app.state.app_store
    # The UI start and chat deletion share one admission boundary. Re-read the
    # chat under it so a queued start cannot resurrect a deleted chat's process.
    with request.app.state.manager.lifecycle.mutate("chat_preview_start"):
        conversation_id = store.conversation_id_for_thread(thread_id)
        if conversation_id is None:
            raise HarnessError("Choose a saved project chat to preview its page.", code="preview_thread_required", status_code=404)
        with request.app.state.chat.store.conversation_lock(conversation_id):
            conversation = store.get_conversation(conversation_id)
            if conversation is None or conversation.archived:
                raise HarnessError("Choose a saved project chat to preview its page.", code="preview_thread_required", status_code=404)
            if not conversation.project_path or conversation.work_mode != "work":
                raise HarnessError("Project previews require Work mode in a project chat.", code="preview_work_required", status_code=409)
            if "start_preview" not in (conversation.presented_tools or []):
                raise HarnessError("Enable project previews for this chat before starting a page.", code="preview_not_selected", status_code=409)
            return request.app.state.preview.start_static(thread_id, conversation.project_path, body.entry_path)


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
