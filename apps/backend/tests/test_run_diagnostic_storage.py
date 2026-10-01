"""Stored model-request copies are discarded. Runs and chats stay."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from workbench_backend.agents.schemas import ModelRequestCapture
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
        finally:
            close_workbench_sqlite(store)
        conn = sqlite3.connect(self.paths.application_db)
        try:
            conn.execute("DROP TABLE run_diagnostic_captures")
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
                saved = store._conn.execute("SELECT payload FROM run_diagnostic_captures WHERE run_id = ?", (legacy.id,)).fetchall()
                version = store._conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()[0]
                conversations = store._conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertNotIn("model_requests", json.loads(payload))
            self.assertNotIn("wb_synthetic_legacy_credential_1234", payload)
            self.assertEqual(saved, [])
            self.assertEqual(conversations, 0)
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
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name = 'run_diagnostic_captures'").fetchone())
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
            saved = migrated._conn.execute("SELECT COUNT(*) FROM run_diagnostic_captures").fetchone()[0]
        self.assertEqual(saved, 0)

    def test_run_writes_do_not_store_request_bodies(self) -> None:
        store = ApplicationStore(self.paths)
        self.addCleanup(close_workbench_sqlite, store)
        run = store.put_run(synthetic_large_run())
        self.assertGreaterEqual(len(run.model_requests), 50)
        with store._lock:
            saved = store._conn.execute("SELECT COUNT(*) FROM run_diagnostic_captures").fetchone()[0]
            payload = store._conn.execute("SELECT payload FROM runs WHERE id = ?", (run.id,)).fetchone()[0]
        self.assertEqual(saved, 0)
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
        inserted = [sql for sql in statements if "INSERT INTO run_diagnostic_captures" in sql]
        self.assertEqual(inserted, [])
        self.assertEqual(store.get_run(run.id).model_requests, [])
        self.assertEqual(store.get_execution_run(run.id).model_requests, [])
        self.assertEqual(len(run.model_requests), 50)


if __name__ == "__main__":
    unittest.main()
