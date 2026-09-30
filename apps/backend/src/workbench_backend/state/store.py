"""Application SQLite system of record for runs and chat linkage."""

from __future__ import annotations

import sqlite3
import json
import threading
from pathlib import Path

from workbench_backend.agents.schemas import AgentRun, ModelRequestCapture
from workbench_backend.chat.schemas import ChatConversation, ChatMessage
from workbench_backend.inference.ids import utc_now
from workbench_backend.knowledge.diagnostics import (
    apply_capture_policy,
    apply_run_diagnostic_policy,
    capture_settings_for_paths,
)
from workbench_backend.paths import APPLICATION_DB_NAME, WorkbenchPaths
from workbench_backend.state.schemas import ExternalEffect, RelatedFile, RunLinkage
from workbench_backend.state.assistant_text import assistant_insert_index, assistant_text
from workbench_backend.state.chat_state import CHAT_STATE_SCHEMA, ChatStateStoreMixin, migrate_chat_identity_payload
from workbench_backend.state.interaction import INTERACTION_SCHEMA, InteractionStoreMixin
from workbench_backend.state.packet03_schema import ASSET_SCHEMA, PREFERENCE_SCHEMA
from workbench_backend.state.setup_records import SETUP_SCHEMA, SetupStoreMixin
from workbench_backend.state.lab_state import LAB_SCHEMA, LabStateStoreMixin
from workbench_backend.state.run_views import (
    AgentRunOperational,
    BrowserRunProjection,
    RunAttentionProjection,
    RunLifecycleProjection,
)

SCHEMA_VERSION = "3"

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

CREATE INDEX IF NOT EXISTS idx_runs_status_created ON runs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_thread_created ON runs(thread_id, created_at);

CREATE TABLE IF NOT EXISTS run_diagnostic_captures (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK(position >= 0),
    payload TEXT NOT NULL,
    PRIMARY KEY (run_id, position)
) WITHOUT ROWID;

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


class ApplicationStore(ChatStateStoreMixin, InteractionStoreMixin, SetupStoreMixin, LabStateStoreMixin):
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
                if previous and previous[0] not in {"1", "2", SCHEMA_VERSION}:
                    raise ValueError("This application database requires a different runtime version.")
                self._conn.executescript("BEGIN IMMEDIATE;\n" + _SCHEMA + CHAT_STATE_SCHEMA + INTERACTION_SCHEMA + ASSET_SCHEMA + PREFERENCE_SCHEMA + SETUP_SCHEMA + LAB_SCHEMA)
                self._migrate_interaction_replay()
                if previous is None or previous[0] == "1":
                    self._migrate_chat_identity()
                if previous is None or previous[0] in {"1", "2"}:
                    self._migrate_run_diagnostics()
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

    def _migrate_run_diagnostics(self) -> None:
        """Move legacy capture arrays once, without inspecting their content."""
        self._conn.execute(
            """INSERT OR IGNORE INTO run_diagnostic_captures(run_id, position, payload)
               SELECT runs.id, CAST(capture.key AS INTEGER), capture.value
               FROM runs, json_each(runs.payload, '$.model_requests') AS capture
               WHERE json_type(runs.payload, '$.model_requests') = 'array'"""
        )
        self._conn.execute(
            "UPDATE runs SET payload = json_remove(payload, '$.model_requests') "
            "WHERE json_type(payload, '$.model_requests') IS NOT NULL"
        )

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
        if not isinstance(run, AgentRun):
            raise TypeError("Only complete AgentRun records can be persisted.")
        run = apply_run_diagnostic_policy(run, capture_settings_for_paths(self.paths))
        return self._put_run_record(run, preserve_diagnostics=False)

    def put_execution_run(self, run: AgentRun) -> AgentRun:
        """Persist the execution owner's already-enforced captures.

        Capture creation and diagnostic loading share the privacy policy. This
        path does not inspect all saved diagnostic bodies at every tool event.
        """
        if not isinstance(run, AgentRun):
            raise TypeError("Only complete AgentRun records can be persisted.")
        return self._put_run_record(run, preserve_diagnostics=True)

    def _put_run_record(self, run: AgentRun, *, preserve_diagnostics: bool) -> AgentRun:
        payload = run.model_dump_json(exclude={"model_requests"})
        # All capture batches, linkage and Chat completion belong to one run
        # write. Roll back failures before another store operation can commit
        # a partial update on this shared connection.
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            capture_count = self._conn.execute(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM run_diagnostic_captures WHERE run_id = ?",
                (run.id,),
            ).fetchone()[0] if preserve_diagnostics else 0
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
            if not preserve_diagnostics:
                self._conn.execute("DELETE FROM run_diagnostic_captures WHERE run_id = ?", (run.id,))
            new = run.model_requests[int(capture_count):]
            for offset in range(0, len(new), 25):
                batch = new[offset:offset + 25]
                self._conn.executemany(
                    "INSERT INTO run_diagnostic_captures(run_id, position, payload) VALUES (?, ?, ?)",
                    [(run.id, int(capture_count) + offset + index, capture.model_dump_json())
                     for index, capture in enumerate(batch)],
                )
            self._replace_checkpoints_locked(run.id, run.thread_id, run.checkpoint_ids)
            self._replace_files_locked(run.id, run.related_files)
            self._reconcile_chat_completion_locked(run)
        return run

    def run_status(self, run_id: str | None) -> str | None:
        if not run_id:
            return None
        with self._lock:
            row = self._conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
        return str(row["status"]) if row is not None and row["status"] is not None else None

    def run_ids_with_status(self, statuses: set[str]) -> list[tuple[str, str]]:
        if not statuses:
            return []
        marks = ",".join("?" for _ in statuses)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT id, status FROM runs WHERE status IN ({marks}) ORDER BY created_at",
                tuple(sorted(statuses)),
            ).fetchall()
        return [(str(row["id"]), str(row["status"])) for row in rows]

    def get_run(self, run_id: str) -> AgentRun | None:
        operational = self.get_run_operational(run_id)
        if operational is None:
            return None
        captures = self.normalize_run_diagnostics(run_id)
        if captures is None:
            return None
        return AgentRun.model_validate({**operational.model_dump(mode="python"), "model_requests": captures})

    def get_execution_run(self, run_id: str) -> AgentRun | None:
        """Hydrate a complete record for execution/recovery, without inspection."""
        with self._lock:
            row = self._conn.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
            captures = self._diagnostic_rows_locked(run_id) if row is not None else []
        if row is None:
            return None
        run = AgentRun.model_validate_json(row["payload"])
        run.model_requests = [ModelRequestCapture.model_validate_json(payload) for _, payload in captures]
        linkage = self.get_linkage(run_id)
        run.thread_id = linkage.thread_id or run.thread_id
        run.checkpoint_ids = list(linkage.checkpoint_ids)
        run.related_files = list(linkage.related_files)
        return run

    def _diagnostic_rows_locked(self, run_id: str) -> list[tuple[int, str]]:
        return [(int(row["position"]), str(row["payload"])) for row in self._conn.execute(
            "SELECT position, payload FROM run_diagnostic_captures WHERE run_id = ? ORDER BY position",
            (run_id,),
        ).fetchall()]

    def normalize_run_diagnostics(self, run_id: str) -> list[ModelRequestCapture] | None:
        """Enforce privacy outside locks, updating diagnostics alone by CAS.

        Concurrent lifecycle/tool changes need not retry: the comparison is
        against the capture row snapshot rather than the complete run payload.
        A concurrent capture append/edit retries without overwriting it.
        """
        while True:
            settings = capture_settings_for_paths(self.paths)
            with self._lock:
                row = self._conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
                original = self._diagnostic_rows_locked(run_id) if row is not None else []
            if row is None:
                return None
            captures = [ModelRequestCapture.model_validate_json(payload) for _, payload in original]
            normalized = [apply_capture_policy(value, settings) for value in captures]
            if capture_settings_for_paths(self.paths) != settings:
                continue
            changed = [(original[index][0], after) for index, (before, after) in
                       enumerate(zip(captures, normalized, strict=True)) if before is not after]
            if not changed:
                return normalized
            # Only changed bodies are serialized, and this expensive work is
            # outside the shared store lock. Unchanged saved entries stay put.
            replacements = [(index, capture.model_dump_json()) for index, capture in changed]
            if capture_settings_for_paths(self.paths) != settings:
                continue
            matched = False
            with self._lock, self._conn:
                # Reserve the SQLite writer before comparing the complete
                # history, so another connection cannot append/edit after CAS.
                self._conn.execute("BEGIN IMMEDIATE")
                current = self._diagnostic_rows_locked(run_id)
                if current != original:
                    continue
                if self._conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone() is None:
                    return None
                for offset in range(0, len(replacements), 25):
                    batch = replacements[offset:offset + 25]
                    self._conn.executemany(
                        "UPDATE run_diagnostic_captures SET payload = ? WHERE run_id = ? AND position = ?",
                        [(content, run_id, position) for position, content in batch],
                    )
                matched = True
            if matched:
                return normalized

    def get_run_operational(self, run_id: str) -> AgentRunOperational | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT json_remove(payload, '$.model_requests') AS payload, status, thread_id "
                "FROM runs WHERE id = ?", (run_id,),
            ).fetchone()
        return self._operational_run(row) if row is not None else None

    def _operational_run(self, row: sqlite3.Row) -> AgentRunOperational:
        # json_remove runs before Python decoding; captures are never loaded,
        # copied or sent through privacy normalization by ordinary observation.
        run = AgentRunOperational.model_validate_json(row["payload"])
        linkage = self.get_linkage(run.id)
        return run.model_copy(update={
            "status": type(run.status)(row["status"]),
            "thread_id": linkage.thread_id or run.thread_id,
            "checkpoint_ids": list(linkage.checkpoint_ids),
            "related_files": list(linkage.related_files),
        })

    def list_runs_operational(self) -> list[AgentRunOperational]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT json_remove(payload, '$.model_requests') AS payload, status, thread_id "
                "FROM runs ORDER BY created_at",
            ).fetchall()
        return [self._operational_run(row) for row in rows]

    def get_run_lifecycle(self, run_id: str, *, details: bool = True) -> RunLifecycleProjection | None:
        rows = self._run_lifecycle_rows("id = ?", (run_id,), details=details)
        return self._lifecycle_run(rows[0]) if rows else None

    def _lifecycle_run(self, row: sqlite3.Row) -> RunLifecycleProjection:
        value = dict(row)
        if "child_runs" in value:
            value["child_runs"] = json.loads(value["child_runs"] or "[]")
        if "tool_outcomes" in value:
            value["tool_outcomes"] = json.loads(value["tool_outcomes"] or "{}")
        return RunLifecycleProjection.model_validate(value)

    def list_run_lifecycle(
        self, *, statuses: set[str] | None = None, thread_id: str | None = None,
        roots_only: bool = False, details: bool = True,
    ) -> list[RunLifecycleProjection]:
        clauses: list[str] = []
        params: list[object] = []
        if statuses is not None:
            if not statuses:
                return []
            clauses.append("status IN (" + ",".join("?" for _ in statuses) + ")")
            params.extend(sorted(statuses))
        if thread_id is not None:
            clauses.append("thread_id = ?")
            params.append(thread_id)
        if roots_only:
            clauses.append("parent_run_id IS NULL")
        return [self._lifecycle_run(row) for row in
                self._run_lifecycle_rows(" AND ".join(clauses), tuple(params), details=details)]

    def _run_lifecycle_rows(self, where: str, params: tuple[object, ...], *, details: bool = True) -> list[sqlite3.Row]:
        columns = "id,status,thread_id,workspace_id,project_path,parent_run_id,source_surface,created_at,updated_at"
        if details:
            columns += (
                ", json_extract(payload, '$.finished_at') AS finished_at, "
                "COALESCE(json_extract(payload, '$.task'), '') AS task, "
                "json_extract(payload, '$.child_runs') AS child_runs, "
                "json_extract(payload, '$.finalization_phase') AS finalization_phase, "
                "(SELECT json_group_object(key, json_object('outcome', json_extract(value, '$.outcome'), "
                "'evidence', json_object('acknowledged_at', json_extract(value, '$.evidence.acknowledged_at')))) "
                "FROM json_each(runs.payload, '$.tool_outcomes')) AS tool_outcomes"
            )
        with self._lock:
            return self._conn.execute(
                "SELECT " + columns + " FROM runs "
                + ("WHERE " + where if where else "") + " ORDER BY created_at", params,
            ).fetchall()

    def get_run_browser(self, run_id: str) -> BrowserRunProjection | None:
        with self._lock:
            row = self._conn.execute(
                """SELECT id,thread_id,status,source_surface,project_path,deployment_id,
                json_extract(payload, '$.browser_control') AS browser_control,
                json_extract(payload, '$.retained_asset_ids') AS retained_asset_ids,
                json_extract(payload, '$.presented_tools') AS presented_tools,
                json_extract(payload, '$.work_mode') AS work_mode,
                json_extract(payload, '$.effective_setup.bags.per_request.requested') AS requested,
                json_extract(payload, '$.effective_setup.bags.per_request.applied') AS applied,
                json_type(payload, '$.effective_setup') AS effective_setup_type
                FROM runs WHERE id = ?""", (run_id,),
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        for name in ("retained_asset_ids", "presented_tools"):
            value[name] = json.loads(value[name] or "[]")
        setup_type = value.pop("effective_setup_type")
        requested, applied = value.pop("requested"), value.pop("applied")
        value["effective_setup"] = {"bags": {"per_request": {
            "requested": json.loads(requested or "{}"), "applied": json.loads(applied or "{}"),
        }}} if setup_type == "object" else None
        value["browser_control"] = value["browser_control"] or "agent"
        value["work_mode"] = value["work_mode"] or "work"
        return BrowserRunProjection.model_validate(value)

    def list_run_attention(self, statuses: set[str]) -> list[RunAttentionProjection]:
        if not statuses:
            return []
        marks = ",".join("?" for _ in statuses)
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT id,status,source_surface,
                json_type(payload, '$.pending_interrupt') AS pending_type,
                json_extract(payload, '$.pending_interrupt.interrupt_id') AS interrupt_id,
                (SELECT json_group_array(json_extract(value, '$.name'))
                 FROM json_each(runs.payload, '$.pending_interrupt.action_requests')) AS action_names,
                json_extract(payload, '$.finished_at') AS finished_at
                FROM runs WHERE status IN ({marks}) ORDER BY created_at""", tuple(sorted(statuses)),
            ).fetchall()
            checkpoints = {
                str(row["id"]): tuple(str(item[0]) for item in self._conn.execute(
                    "SELECT checkpoint_id FROM run_checkpoints WHERE run_id = ? ORDER BY recorded_at", (row["id"],),
                ).fetchall()) for row in rows
            }
        result: list[RunAttentionProjection] = []
        for row in rows:
            value = dict(row)
            pending_type = value.pop("pending_type")
            interrupt_id, names = value.pop("interrupt_id"), value.pop("action_names")
            value["pending_interrupt"] = {"interrupt_id": interrupt_id, "action_names": json.loads(names or "[]")} if pending_type == "object" else None
            value["checkpoint_ids"] = checkpoints[str(row["id"])]
            result.append(RunAttentionProjection.model_validate(value))
        return result

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
            "SELECT json_remove(payload, '$.model_requests') AS payload FROM runs WHERE id = ?",
            (conversation.current_run_id,),
        ).fetchone()
        if row is None:
            return conversation
        run = AgentRunOperational.model_validate_json(row["payload"])
        if run.status.value not in {"completed", "failed", "cancelled"}:
            return conversation
        if any(item.run_id == run.id and item.role == "assistant" for item in conversation.transcript):
            return conversation
        text = assistant_text(run)
        if not text:
            return conversation
        conversation = conversation.model_copy(deep=True)
        conversation.transcript.insert(
            assistant_insert_index(conversation, run.id),
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
        text = assistant_text(run)
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
                assistant_insert_index(conversation, run.id),
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


def json_chat_root(paths: WorkbenchPaths) -> Path:
    return paths.state / "chat"


def json_runs_root(paths: WorkbenchPaths) -> Path:
    return paths.state / "runs"
