"""Chat transcripts in application.sqlite. Never the working project."""

from __future__ import annotations

import threading

from workbench_backend.chat.schemas import ChatConversation, ChatMessage
from workbench_backend.state.store import ApplicationStore


class ChatStore:
    def __init__(self, app_store: ApplicationStore) -> None:
        self.app_store = app_store

    def list_conversations(self) -> list[ChatConversation]:
        return self.app_store.list_conversations()

    def get(self, conversation_id: str) -> ChatConversation | None:
        return self.app_store.get_conversation(conversation_id)

    def put(self, conversation: ChatConversation) -> ChatConversation:
        return self.app_store.put_conversation(conversation)

    def conversation_lock(self, conversation_id: str) -> threading.RLock:
        return self.app_store.conversation_lock(conversation_id)

    def append_message_once(
        self,
        conversation_id: str,
        message: ChatMessage,
        *,
        run_id: str,
    ) -> ChatConversation | None:
        return self.app_store.append_conversation_message_once(
            conversation_id,
            message,
            run_id=run_id,
        )
