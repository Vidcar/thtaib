"""Chat HTTP API. Thin surface over the embedded harness."""

from __future__ import annotations

from fastapi import APIRouter, Request

from workbench_backend.chat.schemas import (
    ChatConversationCreateRequest,
    ChatInterruptDecisionRequest,
    ChatStartRequest,
    ChatTranscriptReplaceRequest,
)
from workbench_backend.chat.service import ChatService

router = APIRouter(prefix="/v1/chat")


def get_chat(request: Request) -> ChatService:
    return request.app.state.chat


@router.post("/conversations")
def create_conversation(request: Request, body: ChatConversationCreateRequest) -> object:
    return get_chat(request).create(body)


@router.get("/conversations")
def list_conversations(request: Request) -> object:
    return get_chat(request).list_conversations()


@router.get("/conversations/{conversation_id}")
def get_conversation(request: Request, conversation_id: str) -> object:
    return get_chat(request).get(conversation_id)


@router.post("/conversations/{conversation_id}/start")
def start_conversation(request: Request, conversation_id: str, body: ChatStartRequest) -> object:
    return get_chat(request).start(conversation_id, body)


@router.post("/conversations/{conversation_id}/cancel")
def cancel_conversation(request: Request, conversation_id: str) -> object:
    return get_chat(request).cancel(conversation_id)


@router.post("/conversations/{conversation_id}/interrupt-decision")
def decide_conversation_interrupt(
    request: Request,
    conversation_id: str,
    body: ChatInterruptDecisionRequest,
) -> object:
    return get_chat(request).resume_interrupt(conversation_id, body)


@router.put("/conversations/{conversation_id}/transcript")
def replace_transcript(
    request: Request,
    conversation_id: str,
    body: ChatTranscriptReplaceRequest,
) -> object:
    return get_chat(request).replace_transcript(conversation_id, body)
