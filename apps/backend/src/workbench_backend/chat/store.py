"""Chat transcripts under application state. Never the working project."""

from __future__ import annotations

import json
from pathlib import Path

from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.paths import WorkbenchPaths


class ChatStore:
    def __init__(self, paths: WorkbenchPaths) -> None:
        self.paths = paths.ensure()
        self.root = self.paths.state / "chat"
        self.root.mkdir(parents=True, exist_ok=True)

    def list_conversations(self) -> list[ChatConversation]:
        items = [
            ChatConversation.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.root.glob("chat_*.json"))
        ]
        return items

    def get(self, conversation_id: str) -> ChatConversation | None:
        path = self._path(conversation_id)
        if not path.is_file():
            return None
        return ChatConversation.model_validate_json(path.read_text(encoding="utf-8"))

    def put(self, conversation: ChatConversation) -> ChatConversation:
        path = self._path(conversation.id)
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_text(json.dumps(conversation.model_dump(mode="json"), indent=2), encoding="utf-8")
        tmp.replace(path)
        return conversation

    def _path(self, conversation_id: str) -> Path:
        return self.root / f"{conversation_id}.json"
