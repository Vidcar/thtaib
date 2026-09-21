"""Durable Chat state helpers stored in application.sqlite."""

from __future__ import annotations
from pathlib import Path

from workbench_backend.chat.schemas import ChatConversation, ChatMessage
from workbench_backend.inference.ids import utc_now

CHAT_STATE_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_conversations_updated
ON conversations(updated_at);

CREATE TABLE IF NOT EXISTS chat_submission_cancellations (
    conversation_id TEXT NOT NULL,
    input_message_id TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    run_id TEXT,
    resolved_at TEXT,
    PRIMARY KEY (conversation_id, input_message_id)
);
"""


def migrate_chat_identity_payload(payload: dict) -> dict:
    if not payload.get("area_id"):
        project = payload.get("project_path")
        workspace = payload.get("workspace_id")
        payload.update(area_kind="project" if project or workspace else "general",
            area_id=workspace or project or "general", area_project_path=project,
            area_workspace_id=workspace, area_label=Path(project).name if project else workspace or "General")
    return payload


class ChatStateStoreMixin:
    """Conversation records, drafts, archive state and editable queue metadata."""

    def request_chat_submission_cancel(
        self,
        conversation_id: str,
        input_message_id: str,
        *,
        run_id: str | None = None,
    ) -> None:
        now = utc_now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO chat_submission_cancellations(conversation_id, input_message_id, requested_at, run_id, resolved_at)
                VALUES (?, ?, ?, ?, NULL)
                ON CONFLICT(conversation_id, input_message_id) DO UPDATE SET
                    run_id=COALESCE(excluded.run_id, chat_submission_cancellations.run_id),
                    resolved_at=NULL
                """,
                (conversation_id, input_message_id, now, run_id),
            )
            self._conn.commit()

    def chat_submission_cancel_requested(self, conversation_id: str, input_message_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT 1 FROM chat_submission_cancellations
                WHERE conversation_id = ? AND input_message_id = ? AND resolved_at IS NULL
                """,
                (conversation_id, input_message_id),
            ).fetchone()
        return row is not None

    def chat_submission_cancel_known(self, conversation_id: str, input_message_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT 1 FROM chat_submission_cancellations
                WHERE conversation_id = ? AND input_message_id = ?
                """,
                (conversation_id, input_message_id),
            ).fetchone()
        return row is not None

    def pending_chat_submission_cancels(self, conversation_id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT input_message_id FROM chat_submission_cancellations
                WHERE conversation_id = ? AND resolved_at IS NULL
                ORDER BY requested_at
                """,
                (conversation_id,),
            ).fetchall()
        return [str(row["input_message_id"]) for row in rows]

    def pause_chat_submission_queue_item(
        self,
        conversation_id: str,
        input_message_id: str,
    ) -> ChatConversation | None:
        now = utc_now()
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                return None
            conversation = ChatConversation.model_validate_json(row["payload"])
            changed = False
            for item in conversation.queue:
                if item.input_message_id == input_message_id and item.status in {"queued", "dispatching"}:
                    item.status = "paused"
                    item.pause_reason = "cancelled"
                    item.pause_error_code = "cancel_requested"
                    item.pause_error = "Queued turn stopped before it could dispatch."
                    item.updated_at = now
                    changed = True
            if not changed:
                return conversation
            conversation.updated_at = now
            self._conn.execute(
                """
                UPDATE conversations
                SET payload = ?, updated_at = ?
                WHERE id = ?
                """,
                (conversation.model_dump_json(), conversation.updated_at, conversation.id),
            )
            self._conn.commit()
            return conversation

    def accept_chat_dispatched_run(
        self,
        conversation_id: str,
        run_id: str,
        input_message_id: str | None,
    ) -> ChatConversation | None:
        now = utc_now()
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                return None
            conversation = ChatConversation.model_validate_json(row["payload"])
            if run_id not in conversation.run_ids:
                conversation.run_ids.append(run_id)
            conversation.current_run_id = run_id
            for message in reversed(conversation.transcript):
                if message.role == "user" and message.id == input_message_id:
                    message.run_id = run_id
                    break
            for item in conversation.queue:
                if item.input_message_id == input_message_id and item.status in {"dispatching", "paused"}:
                    item.run_id = run_id
                    item.updated_at = now
                    break
            conversation.updated_at = now
            conversation = self._reconcile_conversation_current_run_locked(conversation)
            self._conn.execute(
                """
                UPDATE conversations
                SET payload = ?, updated_at = ?
                WHERE id = ?
                """,
                (conversation.model_dump_json(), conversation.updated_at, conversation.id),
            )
            self._conn.commit()
            return conversation

    def resolve_chat_submission_cancel(
        self,
        conversation_id: str,
        input_message_id: str,
        *,
        run_id: str | None = None,
    ) -> None:
        now = utc_now()
        with self._lock:
            self._conn.execute(
                """
                UPDATE chat_submission_cancellations
                SET resolved_at = ?, run_id = COALESCE(?, run_id)
                WHERE conversation_id = ? AND input_message_id = ? AND resolved_at IS NULL
                """,
                (now, run_id, conversation_id, input_message_id),
            )
            self._conn.commit()

    def put_conversation(self, conversation: ChatConversation) -> ChatConversation:
        with self._lock:
            conversation = self._reconcile_conversation_current_run_locked(conversation)
            self._conn.execute(
                """
                INSERT INTO conversations(id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    conversation.id,
                    conversation.model_dump_json(),
                    conversation.created_at,
                    conversation.updated_at,
                ),
            )
            self._conn.commit()
        return conversation

    def get_conversation(self, conversation_id: str) -> ChatConversation | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        return ChatConversation.model_validate_json(row["payload"])

    def list_conversations(self, *, include_archived: bool = False) -> list[ChatConversation]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM conversations ORDER BY created_at"
            ).fetchall()
        conversations = [ChatConversation.model_validate_json(row["payload"]) for row in rows]
        if include_archived:
            return conversations
        return [item for item in conversations if not item.archived]

    def search_conversations(
        self,
        query: str,
        *,
        include_archived: bool = False,
    ) -> list[tuple[ChatConversation, list[ChatMessage]]]:
        needle = query.strip().casefold()
        if not needle:
            return []
        results: list[tuple[ChatConversation, list[ChatMessage]]] = []
        for conversation in self.list_conversations(include_archived=include_archived):
            title_matches = needle in (conversation.title or "").casefold()
            message_matches = [
                message
                for message in conversation.transcript
                if needle in message.content.casefold()
            ]
            if title_matches or message_matches:
                results.append((conversation, message_matches))
        return results

    def update_conversation(self, conversation: ChatConversation) -> ChatConversation:
        conversation.updated_at = utc_now()
        return self.put_conversation(conversation)

    def append_conversation_message_once(
        self,
        conversation_id: str,
        message: ChatMessage,
        *,
        run_id: str,
    ) -> ChatConversation | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                return None
            conversation = ChatConversation.model_validate_json(row["payload"])
            if conversation.history_replaced:
                return conversation
            if run_id not in conversation.run_ids:
                return conversation
            if run_id != conversation.current_run_id:
                return conversation
            if any(item.run_id == run_id and item.role == message.role for item in conversation.transcript):
                return conversation
            conversation.transcript.insert(
                _assistant_insert_index(conversation, run_id),
                message,
            )
            conversation.updated_at = utc_now()
            self._conn.execute(
                """
                UPDATE conversations
                SET payload = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    conversation.model_dump_json(),
                    conversation.updated_at,
                    conversation.id,
                ),
            )
            self._conn.commit()
            return conversation


def _assistant_insert_index(conversation: ChatConversation, run_id: str) -> int:
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
