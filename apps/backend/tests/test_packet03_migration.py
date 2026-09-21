"""Packet 03 application.sqlite migration safety coverage."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from workbench_backend.agents.schemas import AgentRun
from workbench_backend.chat.schemas import ChatMessage
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.migrate import open_application_store
from workbench_backend.state.store import ApplicationStore, json_chat_root

from tests.support import close_workbench_sqlite


AREA_KEYS = {
    "area_kind",
    "area_id",
    "area_label",
    "area_project_path",
    "area_workspace_id",
}


def _create_v1_db(path: Path, *, conversations: list[dict], runs: list[AgentRun] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE conversations(id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE runs(
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, thread_id TEXT, profile_id TEXT,
                deployment_id TEXT, workspace_id TEXT, project_path TEXT, parent_run_id TEXT,
                source_surface TEXT, status TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE run_checkpoints(
                run_id TEXT NOT NULL, checkpoint_id TEXT NOT NULL, thread_id TEXT,
                recorded_at TEXT NOT NULL, PRIMARY KEY(run_id, checkpoint_id)
            );
            CREATE TABLE run_files(
                run_id TEXT NOT NULL, path TEXT NOT NULL, kind TEXT NOT NULL,
                recorded_at TEXT NOT NULL, PRIMARY KEY(run_id, path, kind)
            );
            CREATE TABLE migration_log(source TEXT PRIMARY KEY, destination TEXT NOT NULL, status TEXT NOT NULL, at TEXT NOT NULL);
            INSERT INTO schema_meta(key, value) VALUES ('schema_version', '1');
            """
        )
        for payload in conversations:
            conn.execute(
                "INSERT INTO conversations(id, payload, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (payload["id"], json.dumps(payload), payload["created_at"], payload["updated_at"]),
            )
        for run in runs or []:
            conn.execute(
                """
                INSERT INTO runs(
                    id, payload, thread_id, profile_id, deployment_id, workspace_id,
                    project_path, parent_run_id, source_surface, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.model_dump_json(),
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
            for checkpoint_id in run.checkpoint_ids:
                conn.execute(
                    "INSERT INTO run_checkpoints(run_id, checkpoint_id, thread_id, recorded_at) VALUES (?, ?, ?, ?)",
                    (run.id, checkpoint_id, run.thread_id, utc_now()),
                )
        conn.commit()
    finally:
        conn.close()


def _schema_version(path: Path) -> str | None:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
        return None if row is None else str(row[0])
    finally:
        conn.close()


def _conversation_payload(path: Path, conversation_id: str) -> str:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("SELECT payload FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        assert row is not None
        return str(row[0])
    finally:
        conn.close()


class Packet03ApplicationMigrationTests(unittest.TestCase):
    def test_v1_sqlite_chat_identity_migrates_without_touching_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as original_tmp, tempfile.TemporaryDirectory() as copied_tmp:
            original_root = Path(original_tmp)
            original_paths = WorkbenchPaths(original_root).ensure()
            original_project = original_root / "removed-project"
            original_project.mkdir()
            now = utc_now()
            run = AgentRun(
                id="agent_v1_linked",
                deployment_id="dep_v1",
                task="legacy turn",
                input_message_id="legacy-input",
                enabled_tools=["echo"],
                presented_tools=["echo"],
                created_at=now,
                updated_at=now,
                thread_id="thread_v1",
                checkpoint_ids=["checkpoint_v1"],
                source_surface="chat",
                project_path=str(original_project),
            )
            conversation = {
                "id": "chat_v1_sqlite",
                "deployment_id": "dep_v1",
                "project_path": str(original_project),
                "thread_id": "thread_v1",
                "current_run_id": run.id,
                "transcript": [
                    ChatMessage(role="user", content="legacy", at=now, run_id=run.id).model_dump(mode="json")
                ],
                "run_ids": [run.id],
                "created_at": now,
                "updated_at": now,
            }
            for key in AREA_KEYS:
                conversation.pop(key, None)
            _create_v1_db(original_paths.application_db, conversations=[conversation], runs=[run])
            original_paths.checkpoints_db.write_bytes(b"checkpoint-bytes-v1")

            copied_root = Path(copied_tmp) / "copy"
            shutil.copytree(original_root, copied_root)
            shutil.rmtree(copied_root / "removed-project")
            copied_paths = WorkbenchPaths(copied_root).ensure()
            checkpoint_before = copied_paths.checkpoints_db.read_bytes()

            store = ApplicationStore(copied_paths)
            try:
                loaded = store.get_conversation("chat_v1_sqlite")
                self.assertIsNotNone(loaded)
                assert loaded is not None
                self.assertEqual(loaded.area_kind, "project")
                self.assertEqual(loaded.area_id, str(original_project))
                self.assertEqual(loaded.area_project_path, str(original_project))
                self.assertEqual(loaded.area_label, "removed-project")
                self.assertEqual(loaded.thread_id, "thread_v1")
                self.assertEqual(loaded.run_ids, [run.id])
                self.assertEqual(loaded.current_run_id, run.id)
                self.assertEqual(loaded.transcript[0].run_id, run.id)
                loaded_run = store.get_run(run.id)
                self.assertIsNotNone(loaded_run)
                assert loaded_run is not None
                self.assertEqual(loaded_run.thread_id, "thread_v1")
                self.assertEqual(loaded_run.checkpoint_ids, ["checkpoint_v1"])
                self.assertEqual(_schema_version(copied_paths.application_db), "2")
                self.assertEqual(copied_paths.checkpoints_db.read_bytes(), checkpoint_before)
            finally:
                close_workbench_sqlite(store)

    def test_v1_invalid_conversation_rolls_back_version_and_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp)).ensure()
            now = utc_now()
            invalid = {
                "id": "chat_invalid_v1",
                "deployment_id": "dep_v1",
                "transcript": [{"role": "user", "content": "missing timestamp"}],
                "created_at": now,
                "updated_at": now,
            }
            _create_v1_db(paths.application_db, conversations=[invalid])
            before = _conversation_payload(paths.application_db, "chat_invalid_v1")

            with self.assertRaises(Exception):
                ApplicationStore(paths)

            self.assertEqual(_schema_version(paths.application_db), "1")
            self.assertEqual(_conversation_payload(paths.application_db, "chat_invalid_v1"), before)

    def test_future_schema_version_refuses_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp)).ensure()
            _create_v1_db(paths.application_db, conversations=[])
            conn = sqlite3.connect(str(paths.application_db))
            try:
                conn.execute("UPDATE schema_meta SET value='99' WHERE key='schema_version'")
                conn.commit()
            finally:
                conn.close()

            with self.assertRaisesRegex(ValueError, "different runtime version"):
                ApplicationStore(paths)
            self.assertEqual(_schema_version(paths.application_db), "99")

    def test_legacy_json_chat_migration_derives_area_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = WorkbenchPaths(root).ensure()
            project = root / "legacy-json-project"
            project.mkdir()
            chat_dir = json_chat_root(paths)
            chat_dir.mkdir(parents=True, exist_ok=True)
            now = utc_now()
            payload = {
                "id": "chat_legacy_area",
                "deployment_id": "dep_legacy",
                "project_path": str(project),
                "thread_id": "thread_json",
                "transcript": [ChatMessage(role="user", content="json", at=now).model_dump(mode="json")],
                "run_ids": [],
                "created_at": now,
                "updated_at": now,
            }
            for key in AREA_KEYS:
                payload.pop(key, None)
            json_path = chat_dir / "chat_legacy_area.json"
            json_path.write_text(json.dumps(payload), encoding="utf-8")

            store = open_application_store(paths)
            try:
                loaded = store.get_conversation("chat_legacy_area")
                self.assertIsNotNone(loaded)
                assert loaded is not None
                self.assertEqual(loaded.area_kind, "project")
                self.assertEqual(loaded.area_id, str(project))
                self.assertEqual(loaded.area_project_path, str(project))
                self.assertEqual(loaded.area_label, "legacy-json-project")
                self.assertTrue((chat_dir / "migrated" / json_path.name).is_file())
            finally:
                close_workbench_sqlite(store)


if __name__ == "__main__":
    unittest.main()
