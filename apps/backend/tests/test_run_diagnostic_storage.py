"""Stored model-request copies are discarded. Runs and chats stay."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from workbench_backend.agents.schemas import ModelRequestCapture
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore, SCHEMA_VERSION

from tests.large_run_history import synthetic_large_run
from tests.support import close_workbench_sqlite


class DiagnosticStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.paths = WorkbenchPaths(Path(temporary.name))

    def _legacy_store(self):
        run = synthetic_large_run()
        run.model_requests[7].instructions += " API_KEY=wb_synthetic_legacy_credential_1234"
        payload = run.model_dump_json()
        self.assertGreater(len(payload.encode()), 10 * 1024 * 1024)
        store = ApplicationStore(self.paths)
        try:
            store.put_execution_run(run)
            store.put_conversation(ChatConversation(
                id="scratch-chat",
                deployment_id=run.deployment_id,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            ))
            with store._lock:
                self.kept_tables = {
                    str(row[0])
                    for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
        finally:
            close_workbench_sqlite(store)
        conn = sqlite3.connect(self.paths.application_db)
        try:
            conn.execute(
                """
                CREATE TABLE run_diagnostic_captures (
                    run_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, position)
                )
                """
            )
            conn.execute(
                "INSERT INTO run_diagnostic_captures (run_id, position, payload) VALUES (?, 0, ?)",
                (run.id, json.dumps({"instructions": "API_KEY=wb_synthetic_legacy_credential_1234"})),
            )
            conn.execute("UPDATE runs SET payload = ? WHERE id = ?", (payload, run.id))
            conn.execute("UPDATE schema_meta SET value = '2' WHERE key = 'schema_version'")
            conn.commit()
        finally:
            conn.close()
        return run, payload

    def test_legacy_request_bodies_are_discarded_without_being_read(self) -> None:
        legacy, _payload = self._legacy_store()
        with patch.object(ModelRequestCapture, "model_validate_json", side_effect=AssertionError("Migration decoded diagnostic history")):
            store = ApplicationStore(self.paths)
            self.addCleanup(close_workbench_sqlite, store)
            with store._lock:
                payload = store._conn.execute("SELECT payload FROM runs WHERE id = ?", (legacy.id,)).fetchone()[0]
                table = store._conn.execute("SELECT name FROM sqlite_master WHERE name = 'run_diagnostic_captures'").fetchone()
                version = store._conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()[0]
                chat = store._conn.execute("SELECT payload FROM conversations WHERE id = 'scratch-chat'").fetchone()[0]
                names = {str(row[0]) for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertNotIn("model_requests", json.loads(payload))
            self.assertNotIn("wb_synthetic_legacy_credential_1234", payload)
            self.assertIsNone(table)
            self.assertIn("scratch-chat", chat)
            self.assertEqual(names, self.kept_tables)
            self.assertIsNotNone(store.get_run_operational(legacy.id))
            self.assertNotIn("model_requests", store.get_run_operational(legacy.id).model_dump())
        execution = store.get_execution_run(legacy.id)
        self.assertEqual(execution.model_requests, [])
        self.assertEqual(store.get_run(legacy.id).model_requests, [])
        self.assertEqual(execution.id, legacy.id)

    def test_failed_legacy_cutover_rolls_back_without_a_readable_copy(self) -> None:
        legacy, payload = self._legacy_store()
        conn = sqlite3.connect(self.paths.application_db)
        try:
            conn.execute(
                """CREATE TRIGGER reject_capture_cutover BEFORE UPDATE OF payload ON runs
                   WHEN json_type(NEW.payload, '$.model_requests') IS NULL
                   BEGIN SELECT RAISE(ABORT, 'Synthetic capture migration failure'); END"""
            )
            conn.commit()
            with self.assertRaisesRegex(sqlite3.IntegrityError, "Synthetic capture migration failure"):
                ApplicationStore(self.paths)
            self.assertEqual(conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()[0], "2")
            self.assertEqual(conn.execute("SELECT payload FROM runs WHERE id = ?", (legacy.id,)).fetchone()[0], payload)
            self.assertIsNotNone(conn.execute("SELECT name FROM sqlite_master WHERE name = 'run_diagnostic_captures'").fetchone())
            self.assertIn("scratch-chat", conn.execute("SELECT payload FROM conversations WHERE id = 'scratch-chat'").fetchone()[0])
            conn.execute("DROP TRIGGER reject_capture_cutover")
            conn.commit()
        finally:
            conn.close()
        migrated = ApplicationStore(self.paths)
        self.addCleanup(close_workbench_sqlite, migrated)
        restored = migrated.get_execution_run(legacy.id)
        self.assertEqual(restored.model_requests, [])
        self.assertEqual(restored.id, legacy.id)
        with migrated._lock:
            table = migrated._conn.execute("SELECT name FROM sqlite_master WHERE name = 'run_diagnostic_captures'").fetchone()
            chat = migrated._conn.execute("SELECT payload FROM conversations WHERE id = 'scratch-chat'").fetchone()[0]
            names = {str(row[0]) for row in migrated._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        self.assertIsNone(table)
        self.assertIn("scratch-chat", chat)
        self.assertEqual(names, self.kept_tables)

    def test_run_writes_do_not_store_request_bodies(self) -> None:
        store = ApplicationStore(self.paths)
        self.addCleanup(close_workbench_sqlite, store)
        run = store.put_run(synthetic_large_run())
        self.assertGreaterEqual(len(run.model_requests), 50)
        with store._lock:
            table = store._conn.execute("SELECT name FROM sqlite_master WHERE name = 'run_diagnostic_captures'").fetchone()
            payload = store._conn.execute("SELECT payload FROM runs WHERE id = ?", (run.id,)).fetchone()[0]
        self.assertIsNone(table)
        self.assertNotIn("model_requests", json.loads(payload))
        self.assertLess(len(payload.encode()), 20 * 1024)
        statements = []
        store._conn.set_trace_callback(statements.append)
        try:
            for index in range(5):
                run.task = f"Small operational update {index}"
                store.put_execution_run(run)
                store.get_run_browser(run.id)
                store.list_run_attention({"running"})
                store.get_run_lifecycle(run.id, details=False)
                store.get_run_operational(run.id)
        finally:
            store._conn.set_trace_callback(None)
        touched = [sql for sql in statements if "run_diagnostic_captures" in sql]
        self.assertEqual(touched, [])
        self.assertEqual(store.get_run(run.id).model_requests, [])
        self.assertEqual(store.get_execution_run(run.id).model_requests, [])
        self.assertEqual(len(run.model_requests), 50)


if __name__ == "__main__":
    unittest.main()
