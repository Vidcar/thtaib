"""Lifecycle/export routes for retained assets and conversations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from workbench_backend.state.checkpointer import submit_checkpoint_task

from workbench_backend.assets.lifecycle import (
    AssetLifecycleService,
    ConversationDeletePreview,
    ConversationDeleteRequest,
    ConversationExport,
)

router = APIRouter()


def get_lifecycle(request: Request) -> AssetLifecycleService:
    service = getattr(request.app.state, "asset_lifecycle", None)
    if service is None:
        harness = getattr(request.app.state, "harness", None)
        service = AssetLifecycleService(request.app.state.manager.paths, request.app.state.app_store,
            harness_provider=(lambda: harness) if harness is not None else None)
        request.app.state.asset_lifecycle = service
    return service


@router.get("/v1/chat/conversations/{conversation_id}/export", response_model=ConversationExport)
def export_conversation(request: Request, conversation_id: str) -> ConversationExport:
    return get_lifecycle(request).export_conversation(conversation_id)


@router.post("/v1/chat/conversations/{conversation_id}/delete-preview", response_model=ConversationDeletePreview)
def preview_conversation_delete(request: Request, conversation_id: str) -> ConversationDeletePreview:
    return get_lifecycle(request).preview_conversation_delete(conversation_id)


@router.delete("/v1/chat/conversations/{conversation_id}", response_model=ConversationDeletePreview)
def delete_conversation(
    request: Request,
    conversation_id: str,
    body: ConversationDeleteRequest | None = None,
) -> ConversationDeletePreview:
    body = body or ConversationDeleteRequest()
    if not body.execute:
        raise HTTPException(
            status_code=409,
            detail={"code": "delete_confirmation_required", "message": "Set execute=true after reviewing the deletion preview."},
        )
    chat = getattr(request.app.state, "chat", None)
    manager = getattr(request.app.state, "manager", None)
    thread_id = None
    if chat is not None and manager is not None:
        with manager.lifecycle.mutate("chat_delete"), chat.store.conversation_lock(conversation_id):
            lookup = getattr(chat.store, "get", None)
            conversation = lookup(conversation_id) if callable(lookup) else None
            thread_id = conversation.thread_id if conversation is not None else None
            preview = get_lifecycle(request).preview_conversation_delete(conversation_id)
            if preview.blockers:
                raise HTTPException(status_code=409, detail={"code": "conversation_delete_active_runs", "preview": preview.model_dump(mode="json")})
            browser = getattr(request.app.state, "browser", None)
            if thread_id and browser is not None:
                # A failed stop cannot leave a deleted chat's authenticated
                # browser running without its owner. Confirm before deletion.
                submit_checkpoint_task(manager.paths.checkpoints_db, browser.delete_chat(thread_id)).result(timeout=30)
            preview_owner = getattr(request.app.state, "preview", None)
            if thread_id and preview_owner is not None and not preview_owner.stop(thread_id):
                raise HTTPException(status_code=409, detail={"code": "preview_stop_unconfirmed",
                    "message": "The preview stop is unconfirmed. Retry Stop in this chat before deleting it."})
            result = get_lifecycle(request).delete_conversation(
                conversation_id,
                include_diagnostics=body.include_diagnostics,
            )
    else:
        result = get_lifecycle(request).delete_conversation(
            conversation_id,
            include_diagnostics=body.include_diagnostics,
        )
    if thread_id:
        desktop = getattr(request.app.state, "desktop_automation", None)
        if desktop is not None:
            desktop.clear_scope(thread_id)
    return result
