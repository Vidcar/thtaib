"""Shared reading and placement of a finished assistant reply."""

from __future__ import annotations

from workbench_backend.agents.schemas import AgentRun
from workbench_backend.chat.schemas import ChatConversation


def assistant_text(run: AgentRun) -> str | None:
    for event in reversed(run.events):
        if event.kind != "assistant_message":
            continue
        content = event.detail.get("content")
        if isinstance(content, str) and content.strip():
            return content
    return None


def assistant_insert_index(conversation: ChatConversation, run_id: str) -> int:
    for index, item in enumerate(conversation.transcript):
        if item.role == "user" and item.run_id == run_id:
            return index + 1
    try:
        run_index = conversation.run_ids.index(run_id)
    except ValueError:
        return len(conversation.transcript)
    user_seen = 0
    for index, item in enumerate(conversation.transcript):
        if item.role == "user":
            user_seen += 1
            if user_seen == run_index + 1:
                return index + 1
    return len(conversation.transcript)
