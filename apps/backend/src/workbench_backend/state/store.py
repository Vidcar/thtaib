"""Application SQLite system of record for runs and chat linkage."""

from __future__ import annotations

import sqlite3
import json
import threading
from pathlib import Path

from workbench_backend.agents.schemas import AgentRun
from workbench_backend.chat.schemas import ChatConversation, ChatMessage
from workbench_backend.inference.ids import utc_now
from workbench_backend.knowledge.diagnostics import (
    apply_run_diagnostic_policy,
    capture_settings_for_paths,
)
from workbench_backend.paths import APPLICATION_DB_NAME, WorkbenchPaths
from workbench_backend.state.schemas import ExternalEffect, RelatedFile, RunLinkage
from workbench_backend.state.chat_state import CHAT_STATE_SCHEMA, ChatStateStoreMixin, migrate_chat_identity_payload
from workbench_backend.state.interaction import INTERACTION_SCHEMA, InteractionStoreMixin
from workbench_backend.state.packet03_schema import ASSET_SCHEMA, PREFERENCE_SCHEMA
from workbench_backend.state.setup_records import SETUP_SCHEMA, SetupStoreMixin

SCHEMA_VERSION = "2"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    thread_id TEXT,
    profile_id TEXT,
    deployment_id TEXT,
    workspace_id TEXT,
    project_path TEXT,
    parent_run_id TEXT,
    source_surface TEXT,
    status TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_checkpoints (
    run_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    thread_id TEXT,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (run_id, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS run_files (
    run_id TEXT NOT NULL,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (run_id, path, kind)
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS migration_log (
    source TEXT PRIMARY KEY,
    destination TEXT NOT NULL,
    status TEXT NOT NULL,
    at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS external_effects (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    payload TEXT NOT NULL,
    outcome TEXT NOT NULL,
    unresolved INTEGER NOT NULL,
    dispatched_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class ApplicationStore(ChatStateStoreMixin, InteractionStoreMixin, SetupStoreMixin):
    """Owns ``application.sqlite`` only. Never opens ``checkpoints.sqlite``."""

    def __init__(self, paths: WorkbenchPaths) -> None:
        self.paths = paths.ensure()
        self.path = self.paths.application_db
        if self.path.name != APPLICATION_DB_NAME:
            raise ValueError("Application store must open application.sqlite.")
        if self.path.resolve() == self.paths.checkpoints_db.resolve():
            raise ValueError("Application store must not share the checkpointer path.")
        self._lock = threading.RLock()
        self._conversation_locks: dict[str, threading.RLock] = {}
        self._conversation_locks_guard = threading.Lock()
        self._conn: sqlite3.Connection | None = sqlite3.connect(
            str(self.path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            try:
                table = self._conn.execute("SELECT 1 FROM sqlite_master WHERE name='schema_meta'").fetchone()
                previous = self._conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone() if table else None
                if previous and previous[0] not in {"1", SCHEMA_VERSION}:
                    raise ValueError("This application database requires a different runtime version.")
                self._conn.executescript("BEGIN IMMEDIATE;\n" + _SCHEMA + CHAT_STATE_SCHEMA + INTERACTION_SCHEMA + ASSET_SCHEMA + PREFERENCE_SCHEMA + SETUP_SCHEMA)
                self._migrate_interaction_replay()
                if previous is None or previous[0] == "1":
                    self._migrate_chat_identity()
                self._conn.execute(
                    "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
                    ("schema_version", SCHEMA_VERSION),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                self._conn.close()
                self._conn = None
                raise

    def _migrate_chat_identity(self) -> None:
        """Preserve legacy bindings even when their external project disappeared."""
        for row in self._conn.execute("SELECT id,payload FROM conversations").fetchall():
            payload = migrate_chat_identity_payload(json.loads(row["payload"]))
            ChatConversation.model_validate(payload)
            self._conn.execute("UPDATE conversations SET payload=? WHERE id=?", (json.dumps(payload), row["id"]))

    def close(self) -> None:
        """Release ``application.sqlite`` so Windows can delete the workroot."""
        with self._lock:
            conn = self._conn
            self._conn = None
        if conn is None:
            return
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        except sqlite3.Error:
            pass
        conn.close()

    def __enter__(self) -> "ApplicationStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def table_names(self) -> set[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        return {str(row["name"]) for row in rows}

    def put_run(self, run: AgentRun) -> AgentRun:
        run = apply_run_diagnostic_policy(run, capture_settings_for_paths(self.paths))
        payload = run.model_dump_json()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO runs(
                    id, payload, thread_id, profile_id, deployment_id, workspace_id,
                    project_path, parent_run_id, source_surface, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload=excluded.payload,
                    thread_id=excluded.thread_id,
                    profile_id=excluded.profile_id,
                    deployment_id=excluded.deployment_id,
                    workspace_id=excluded.workspace_id,
                    project_path=excluded.project_path,
                    parent_run_id=excluded.parent_run_id,
                    source_surface=excluded.source_surface,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    run.id,
                    payload,
                    run.thread_id,
                    run.profile_id,
                    run.deployment_id,
                    run.workspace_id,
                    run.project_path,
                    run.parent_run_id,
                    run.source_surface,
                    run.status.value,
                    run.created_at,
                    run.updated_at,
                ),
            )
            self._replace_checkpoints_locked(run.id, run.thread_id, run.checkpoint_ids)
            self._replace_files_locked(run.id, run.related_files)
            self._reconcile_chat_completion_locked(run)
            self._conn.commit()
        return run

    def get_run(self, run_id: str) -> AgentRun | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        run = AgentRun.model_validate_json(row["payload"])
        linkage = self.get_linkage(run_id)
        run.thread_id = linkage.thread_id or run.thread_id
        run.checkpoint_ids = list(linkage.checkpoint_ids)
        run.related_files = list(linkage.related_files)
        sanitized = apply_run_diagnostic_policy(run, capture_settings_for_paths(self.paths))
        if sanitized.model_requests != run.model_requests:
            return self.put_run(sanitized)
        return sanitized

    def list_runs(self) -> list[AgentRun]:
        with self._lock:
            rows = self._conn.execute("SELECT id FROM runs ORDER BY created_at").fetchall()
        runs: list[AgentRun] = []
        for row in rows:
            loaded = self.get_run(str(row["id"]))
            if loaded is not None:
                runs.append(loaded)
        return runs

    def get_linkage(self, run_id: str) -> RunLinkage:
        with self._lock:
            run_row = self._conn.execute(
                "SELECT thread_id FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            checkpoint_rows = self._conn.execute(
                """
                SELECT checkpoint_id FROM run_checkpoints
                WHERE run_id = ? ORDER BY recorded_at
                """,
                (run_id,),
            ).fetchall()
            file_rows = self._conn.execute(
                """
                SELECT path, kind FROM run_files
                WHERE run_id = ? ORDER BY recorded_at
                """,
                (run_id,),
            ).fetchall()
        return RunLinkage(
            run_id=run_id,
            thread_id=None if run_row is None else run_row["thread_id"],
            checkpoint_ids=[str(row["checkpoint_id"]) for row in checkpoint_rows],
            related_files=[
                RelatedFile(path=str(row["path"]), kind=row["kind"]) for row in file_rows
            ],
        )

    def _reconcile_conversation_current_run_locked(
        self,
        conversation: ChatConversation,
    ) -> ChatConversation:
        if conversation.history_replaced or not conversation.current_run_id:
            return conversation
        if conversation.current_run_id not in conversation.run_ids:
            return conversation
        if not any(
            item.role == "user" and item.run_id == conversation.current_run_id
            for item in conversation.transcript
        ):
            return conversation
        row = self._conn.execute(
            "SELECT payload FROM runs WHERE id = ?",
            (conversation.current_run_id,),
        ).fetchone()
        if row is None:
            return conversation
        run = AgentRun.model_validate_json(row["payload"])
        if run.status.value not in {"completed", "failed", "cancelled"}:
            return conversation
        if any(item.run_id == run.id and item.role == "assistant" for item in conversation.transcript):
            return conversation
        text = _assistant_text(run)
        if not text:
            return conversation
        conversation = conversation.model_copy(deep=True)
        conversation.transcript.insert(
            _assistant_insert_index(conversation, run.id),
            ChatMessage(
                role="assistant",
                content=text,
                at=run.finished_at or utc_now(),
                run_id=run.id,
            ),
        )
        conversation.updated_at = utc_now()
        return conversation

    def conversation_lock(self, conversation_id: str) -> threading.RLock:
        with self._conversation_locks_guard:
            lock = self._conversation_locks.get(conversation_id)
            if lock is None:
                lock = threading.RLock()
                self._conversation_locks[conversation_id] = lock
            return lock

    def _reconcile_chat_completion_locked(self, run: AgentRun) -> None:
        if run.source_surface != "chat":
            return
        if run.status.value not in {"completed", "failed", "cancelled"}:
            return
        text = _assistant_text(run)
        if not text:
            return
        message = ChatMessage(
            role="assistant",
            content=text,
            at=run.finished_at or utc_now(),
            run_id=run.id,
        )
        rows = self._conn.execute("SELECT payload FROM conversations").fetchall()
        for row in rows:
            conversation = ChatConversation.model_validate_json(row["payload"])
            if conversation.history_replaced:
                continue
            if run.id not in conversation.run_ids:
                continue
            if run.id != conversation.current_run_id:
                continue
            if any(item.run_id == run.id and item.role == "assistant" for item in conversation.transcript):
                continue
            conversation.transcript.insert(
                _assistant_insert_index(conversation, run.id),
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

    def migration_done(self, source: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM migration_log WHERE source = ?",
                (source,),
            ).fetchone()
        return row is not None and str(row["status"]) == "done"

    def record_migration(self, source: str, destination: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO migration_log(source, destination, status, at)
                VALUES (?, ?, ?, ?)
                """,
                (source, destination, "done", utc_now()),
            )
            self._conn.commit()

    def _replace_checkpoints_locked(
        self,
        run_id: str,
        thread_id: str | None,
        checkpoint_ids: list[str],
    ) -> None:
        self._conn.execute("DELETE FROM run_checkpoints WHERE run_id = ?", (run_id,))
        now = utc_now()
        for checkpoint_id in checkpoint_ids:
            self._conn.execute(
                """
                INSERT INTO run_checkpoints(run_id, checkpoint_id, thread_id, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, checkpoint_id, thread_id, now),
            )

    def put_effect(self, effect: ExternalEffect) -> ExternalEffect:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO external_effects(
                    id, run_id, payload, outcome, unresolved, dispatched_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    run_id=excluded.run_id,
                    payload=excluded.payload,
                    outcome=excluded.outcome,
                    unresolved=excluded.unresolved,
                    dispatched_at=excluded.dispatched_at,
                    updated_at=excluded.updated_at
                """,
                (
                    effect.id,
                    effect.run_id,
                    effect.model_dump_json(),
                    effect.outcome.value,
                    1 if effect.unresolved else 0,
                    effect.dispatched_at,
                    utc_now(),
                ),
            )
            self._conn.commit()
        return effect

    def get_effect(self, effect_id: str) -> ExternalEffect | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM external_effects WHERE id = ?",
                (effect_id,),
            ).fetchone()
        if row is None:
            return None
        return ExternalEffect.model_validate_json(row["payload"])

    def list_effects(
        self,
        *,
        run_id: str | None = None,
        unresolved_only: bool = False,
    ) -> list[ExternalEffect]:
        sql = "SELECT payload FROM external_effects"
        params: list[object] = []
        clauses: list[str] = []
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if unresolved_only:
            clauses.append("unresolved = 1")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY dispatched_at"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [ExternalEffect.model_validate_json(row["payload"]) for row in rows]

    def _replace_files_locked(self, run_id: str, files: list[RelatedFile]) -> None:
        self._conn.execute("DELETE FROM run_files WHERE run_id = ?", (run_id,))
        now = utc_now()
        seen: set[tuple[str, str]] = set()
        for item in files:
            key = (item.path, item.kind)
            if key in seen:
                continue
            seen.add(key)
            self._conn.execute(
                """
                INSERT INTO run_files(run_id, path, kind, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, item.path, item.kind, now),
            )


def _assistant_text(run: AgentRun) -> str | None:
    for event in reversed(run.events):
        if event.kind != "assistant_message":
            continue
        content = event.detail.get("content")
        if isinstance(content, str) and content.strip():
            return content
    return None


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


def json_chat_root(paths: WorkbenchPaths) -> Path:
    return paths.state / "chat"


def json_runs_root(paths: WorkbenchPaths) -> Path:
    return paths.state / "runs"
