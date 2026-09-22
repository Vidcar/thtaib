"""Lifecycle/export routes for retained assets and conversations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

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
    if chat is not None and manager is not None:
        with manager.lifecycle.mutate("chat_delete"), chat.store.conversation_lock(conversation_id):
            return get_lifecycle(request).delete_conversation(
                conversation_id,
                include_diagnostics=body.include_diagnostics,
            )
    return get_lifecycle(request).delete_conversation(
        conversation_id,
        include_diagnostics=body.include_diagnostics,
    )
