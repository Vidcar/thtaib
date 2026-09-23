"""Chat HTTP API. Thin surface over the embedded harness."""

from __future__ import annotations

from fastapi import APIRouter, Request

from workbench_backend.chat.schemas import (
    ChatConversationArchiveRequest,
    ChatCancelRequest,
    ChatConversationCreateRequest,
    ChatConversationUpdateRequest,
    ChatConversationView,
    ChatDraftUpdateRequest,
    ChatInterruptDecisionRequest,
    ChatQueueItemUpdateRequest,
    ChatQueueResumeRequest,
    ChatSearchResult,
    ChatStartRequest,
    ChatTranscriptReplaceRequest,
)
from workbench_backend.chat.service import ChatService

router = APIRouter(prefix="/v1/chat")


def get_chat(request: Request) -> ChatService:
    return request.app.state.chat


@router.post("/conversations")
def create_conversation(request: Request, body: ChatConversationCreateRequest) -> ChatConversationView:
    return get_chat(request).create(body)


@router.get("/conversations")
def list_conversations(request: Request, include_archived: bool = False) -> list[ChatConversationView]:
    return get_chat(request).list_conversations(include_archived=include_archived)


@router.get("/conversations/search")
def search_conversations(
    request: Request,
    q: str,
    include_archived: bool = False,
) -> list[ChatSearchResult]:
    return get_chat(request).search(q, include_archived=include_archived)


@router.get("/conversations/{conversation_id}")
def get_conversation(request: Request, conversation_id: str) -> ChatConversationView:
    return get_chat(request).get(conversation_id)


@router.patch("/conversations/{conversation_id}")
def rename_conversation(
    request: Request,
    conversation_id: str,
    body: ChatConversationUpdateRequest,
) -> ChatConversationView:
    return get_chat(request).rename(conversation_id, body)


@router.post("/conversations/{conversation_id}/archive")
def archive_conversation(
    request: Request,
    conversation_id: str,
    body: ChatConversationArchiveRequest,
) -> ChatConversationView:
    return get_chat(request).archive(conversation_id, body)


@router.post("/conversations/{conversation_id}/reopen")
def reopen_conversation(request: Request, conversation_id: str) -> ChatConversationView:
    return get_chat(request).archive(conversation_id, ChatConversationArchiveRequest(archived=False))


@router.put("/conversations/{conversation_id}/draft")
def update_conversation_draft(
    request: Request,
    conversation_id: str,
    body: ChatDraftUpdateRequest,
) -> ChatConversationView:
    return get_chat(request).update_draft(conversation_id, body)


@router.post("/conversations/{conversation_id}/queue")
def enqueue_conversation_turn(
    request: Request,
    conversation_id: str,
    body: ChatStartRequest,
) -> ChatConversationView:
    return get_chat(request).enqueue(conversation_id, body)


@router.post("/conversations/{conversation_id}/queue/resume")
def resume_conversation_queue(
    request: Request,
    conversation_id: str,
    body: ChatQueueResumeRequest | None = None,
) -> ChatConversationView:
    return get_chat(request).resume_queue(conversation_id, body or ChatQueueResumeRequest())


@router.patch("/conversations/{conversation_id}/queue/{item_id}")
def update_conversation_queue_item(
    request: Request,
    conversation_id: str,
    item_id: str,
    body: ChatQueueItemUpdateRequest,
) -> ChatConversationView:
    return get_chat(request).update_queue_item(conversation_id, item_id, body)


@router.post("/conversations/{conversation_id}/queue/{item_id}/steer")
def steer_conversation_queue_item(
    request: Request,
    conversation_id: str,
    item_id: str,
) -> ChatConversationView:
    return get_chat(request).steer_queue_item(conversation_id, item_id)


@router.delete("/conversations/{conversation_id}/queue/{item_id}")
def remove_conversation_queue_item(
    request: Request,
    conversation_id: str,
    item_id: str,
) -> ChatConversationView:
    return get_chat(request).remove_queue_item(conversation_id, item_id)


@router.post("/conversations/{conversation_id}/start")
def start_conversation(request: Request, conversation_id: str, body: ChatStartRequest) -> ChatConversationView:
    return get_chat(request).start(conversation_id, body)


@router.post("/conversations/{conversation_id}/cancel")
def cancel_conversation(
    request: Request,
    conversation_id: str,
    body: ChatCancelRequest | None = None,
) -> object:
    return get_chat(request).cancel(conversation_id, body or ChatCancelRequest())


@router.post("/conversations/{conversation_id}/interrupt-decision")
def decide_conversation_interrupt(
    request: Request,
    conversation_id: str,
    body: ChatInterruptDecisionRequest,
) -> object:
    chat = get_chat(request)
    view = chat.get(conversation_id)
    if view.current_run_id is None:
        return chat.resume_interrupt(conversation_id, body)
    chat.harness.resume_interrupt(
        view.current_run_id,
        body,
        require_interrupt_identity=True,
    )
    return chat.get(conversation_id)


@router.put("/conversations/{conversation_id}/transcript")
def replace_transcript(
    request: Request,
    conversation_id: str,
    body: ChatTranscriptReplaceRequest,
) -> object:
    view = get_chat(request).replace_transcript(conversation_id, body)
    request.app.state.interaction.replace_chat_display_archive(view)
    return view
