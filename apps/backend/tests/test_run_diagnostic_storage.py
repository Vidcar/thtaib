"""Capture storage migration and writes keep substantial history off hot paths."""

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

    def test_large_legacy_history_migrates_once_without_python_inspection(self) -> None:
        legacy, _payload = self._legacy_store()
        with patch("workbench_backend.state.store.apply_capture_policy", side_effect=AssertionError("Migration redacted diagnostic content")), \
             patch("workbench_backend.state.store.apply_run_diagnostic_policy", side_effect=AssertionError("Migration normalized a full run")), \
             patch.object(ModelRequestCapture, "model_validate_json", side_effect=AssertionError("Migration decoded diagnostic history")):
            store = ApplicationStore(self.paths)
            self.addCleanup(close_workbench_sqlite, store)
            with store._lock:
                payload = store._conn.execute("SELECT payload FROM runs WHERE id = ?", (legacy.id,)).fetchone()[0]
                saved = store._diagnostic_rows_locked(legacy.id)
                version = store._conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()[0]
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertNotIn("model_requests", json.loads(payload))
            self.assertLess(len(payload.encode()), 20 * 1024)
            self.assertEqual([position for position, _ in saved], list(range(50)))
            self.assertEqual([json.loads(value) for _, value in saved], [capture.model_dump(mode="json") for capture in legacy.model_requests])
            self.assertNotIn("model_requests", store.get_run_operational(legacy.id).model_dump())
        close_workbench_sqlite(store)
        with patch.object(ApplicationStore, "_migrate_run_diagnostics", side_effect=AssertionError("Capture migration repeated")):
            reopened = ApplicationStore(self.paths)
            self.addCleanup(close_workbench_sqlite, reopened)
        execution = reopened.get_execution_run(legacy.id)
        self.assertEqual(len(execution.model_requests), 50)
        self.assertIn("wb_synthetic_legacy_credential_1234", execution.model_requests[7].instructions)
        diagnostic = reopened.get_run(legacy.id)
        self.assertNotIn("wb_synthetic_legacy_credential_1234", diagnostic.model_requests[7].instructions)
        with reopened._lock:
            # Run deletion cascades all diagnostic rows in this same database.
            reopened._conn.execute("DELETE FROM runs WHERE id = ?", (legacy.id,))
            reopened._conn.commit()
            self.assertEqual(reopened._diagnostic_rows_locked(legacy.id), [])

    def test_failed_legacy_migration_rolls_back_captures_payload_and_version(self) -> None:
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
        self.assertEqual(len(migrated.get_execution_run(legacy.id).model_requests), 50)

    def test_operational_updates_never_read_copy_or_write_saved_capture_bodies(self) -> None:
        store = ApplicationStore(self.paths)
        self.addCleanup(close_workbench_sqlite, store)
        run = store.put_run(synthetic_large_run())
        with store._lock:
            diagnostics = store._diagnostic_rows_locked(run.id)
            self.assertGreater(sum(len(payload.encode()) for _, payload in diagnostics), 10 * 1024 * 1024)
        statements = []
        store._conn.set_trace_callback(statements.append)
        try:
            with patch.object(ModelRequestCapture, "model_dump_json", side_effect=AssertionError("Operational update serialized saved diagnostics")), \
                 patch("workbench_backend.state.store.apply_capture_policy", side_effect=AssertionError("Operational update inspected saved diagnostics")):
                run.model_requests = []  # A shortened execution cache cannot erase saved history.
                for index in range(5):
                    run.task = f"Small operational update {index}"
                    store.put_execution_run(run)
                    store.get_run_browser(run.id)
                    store.list_run_attention({"running"})
                    store.get_run_lifecycle(run.id, details=False)
                    store.get_run_operational(run.id)
        finally:
            store._conn.set_trace_callback(None)
        capture_statements = [sql for sql in statements if "run_diagnostic_captures" in sql]
        self.assertEqual(len(capture_statements), 5)
        self.assertTrue(all("SELECT COALESCE(MAX(position) + 1, 0)" in sql for sql in capture_statements))
        with store._lock:
            payload = store._conn.execute("SELECT payload FROM runs WHERE id = ?", (run.id,)).fetchone()[0]
            self.assertEqual(store._diagnostic_rows_locked(run.id), diagnostics)
        self.assertLess(len(payload.encode()), 20 * 1024)
        self.assertNotIn("model_requests", json.loads(payload))
        self.assertEqual(len(store.get_run(run.id).model_requests), 50)


if __name__ == "__main__":
    unittest.main()
