"""STATE-001 dual SQLite + JSON migration, and STATE-002 history ≠ project."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.chat.schemas import ChatConversation, ChatMessage
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import APPLICATION_DB_NAME, CHECKPOINTS_DB_NAME, WorkbenchPaths
from workbench_backend.state.migrate import open_application_store
from workbench_backend.state.store import ApplicationStore
from workbench_backend.state.checkpointer import open_sqlite_checkpointer
from workbench_backend.state.store import json_chat_root

from tests.scripted_model import ScriptedChatModel

LANGGRAPH_PRIVATE_TABLES = {"checkpoints", "writes"}


def wait_for_run(client: TestClient, run_id: str, *, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/agent-runs/{run_id}")
        body = response.json()
        if body.get("status") in {"completed", "cancelled", "failed"}:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not finish: {body}")


def write_then_reply() -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "write_file",
                    "args": {"file_path": "/edited.md", "content": "chat-file-edit"},
                    "id": "call_write",
                }
            ],
        ),
        AIMessage(content="Wrote edited.md in the project workspace."),
    ]


def sqlite_tables(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        conn.close()
    return {str(row[0]) for row in rows}


class DualDatabasePathTests(unittest.TestCase):
    def test_application_and_checkpoint_paths_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp)).ensure()
            self.assertEqual(paths.application_db.name, APPLICATION_DB_NAME)
            self.assertEqual(paths.checkpoints_db.name, CHECKPOINTS_DB_NAME)
            self.assertNotEqual(paths.application_db, paths.checkpoints_db)
            self.assertEqual(paths.application_db.parent, paths.root)
            self.assertEqual(paths.checkpoints_db.parent, paths.root)
            store = open_application_store(paths)
            self.assertTrue(paths.application_db.is_file())
            self.assertFalse(paths.checkpoints_db.is_file())
            self.assertNotIn("checkpoints", store.table_names())
            self.assertNotIn("writes", store.table_names())
            open_sqlite_checkpointer(paths.checkpoints_db)
            self.assertTrue(paths.checkpoints_db.is_file())
            self.assertTrue(LANGGRAPH_PRIVATE_TABLES.issubset(sqlite_tables(paths.checkpoints_db)))
            self.assertFalse(LANGGRAPH_PRIVATE_TABLES & store.table_names())


class JsonLinkageMigrationTests(unittest.TestCase):
    def test_chat_json_migrates_to_application_db_as_sor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = WorkbenchPaths(root).ensure()
            chat_dir = json_chat_root(paths)
            chat_dir.mkdir(parents=True, exist_ok=True)
            now = utc_now()
            conversation = ChatConversation(
                id="chat_legacy001",
                deployment_id="dep_legacy",
                project_path=str(root / "project"),
                transcript=[ChatMessage(role="user", content="old json", at=now)],
                run_ids=["agent_legacy"],
                created_at=now,
                updated_at=now,
            )
            json_path = chat_dir / f"{conversation.id}.json"
            json_path.write_text(json.dumps(conversation.model_dump(mode="json"), indent=2), encoding="utf-8")

            store = open_application_store(paths)
            loaded = store.get_conversation(conversation.id)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.transcript[0].content, "old json")
            self.assertTrue(store.migration_done("state/chat"))
            self.assertFalse(json_path.exists())
            self.assertTrue((chat_dir / "migrated" / json_path.name).is_file())

            loaded.transcript = [ChatMessage(role="user", content="app db only", at=utc_now())]
            loaded.updated_at = utc_now()
            store.put_conversation(loaded)
            archived = json.loads((chat_dir / "migrated" / json_path.name).read_text(encoding="utf-8"))
            self.assertEqual(archived["transcript"][0]["content"], "old json")
            self.assertEqual(store.get_conversation(conversation.id).transcript[0].content, "app db only")
            self.assertFalse(any(chat_dir.glob("chat_*.json")))

    def test_second_open_does_not_rewrite_archived_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = WorkbenchPaths(root).ensure()
            chat_dir = json_chat_root(paths)
            chat_dir.mkdir(parents=True, exist_ok=True)
            now = utc_now()
            conversation = ChatConversation(
                id="chat_legacy002",
                deployment_id="dep_legacy",
                project_path=str(root / "project"),
                created_at=now,
                updated_at=now,
            )
            json_path = chat_dir / f"{conversation.id}.json"
            json_path.write_text(json.dumps(conversation.model_dump(mode="json"), indent=2), encoding="utf-8")
            open_application_store(paths)
            open_application_store(paths)
            self.assertTrue((chat_dir / "migrated" / json_path.name).is_file())
            self.assertFalse(json_path.exists())


class RunLinkageRestartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project-workspace"
        self.project.mkdir()
        (self.project / "keep.md").write_text("retain-me", encoding="utf-8")
        self.manager = ModelManager(WorkbenchPaths(self.root).ensure())
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel(write_then_reply())

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        self.client = TestClient(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "state-fixture"},
        ).json()["id"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_restart_follows_run_to_checkpoint_and_files_via_app_records(self) -> None:
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Edit edited.md in the project.",
                "project_path": str(self.project),
                "presented_tools": ["write_file"],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        run_id = started.json()["id"]
        self.assertEqual(started.json()["thread_id"], run_id)
        body = wait_for_run(self.client, run_id)
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertTrue(body["checkpoint_ids"], body)
        self.assertTrue((self.project / "edited.md").is_file())

        paths = WorkbenchPaths(self.root)
        self.assertTrue(paths.application_db.is_file())
        self.assertTrue(paths.checkpoints_db.is_file())
        self.assertNotEqual(paths.application_db, paths.checkpoints_db)
        app_tables = sqlite_tables(paths.application_db)
        ckpt_tables = sqlite_tables(paths.checkpoints_db)
        self.assertIn("runs", app_tables)
        self.assertIn("run_checkpoints", app_tables)
        self.assertIn("run_files", app_tables)
        self.assertFalse(LANGGRAPH_PRIVATE_TABLES & app_tables)
        self.assertTrue(LANGGRAPH_PRIVATE_TABLES.issubset(ckpt_tables))

        restarted = create_app(data_root=self.root)
        client = TestClient(restarted)
        restored = client.get(f"/v1/agent-runs/{run_id}")
        self.assertEqual(restored.status_code, 200, restored.text)
        payload = restored.json()
        self.assertEqual(payload["id"], run_id)
        self.assertEqual(payload["thread_id"], run_id)
        self.assertTrue(payload["checkpoint_ids"])
        kinds = {item["kind"] for item in payload["related_files"]}
        self.assertIn("project_root", kinds)
        self.assertIn("written_file", kinds)
        written_paths = [item["path"] for item in payload["related_files"] if item["kind"] == "written_file"]
        self.assertTrue(any(Path(item).name == "edited.md" for item in written_paths))
        store = restarted.state.app_store
        linkage = store.get_linkage(run_id)
        self.assertEqual(linkage.checkpoint_ids, payload["checkpoint_ids"])
        self.assertEqual(store.get_run(run_id).project_path, str(self.project.resolve()))

        checkpoint_bytes = paths.checkpoints_db.read_bytes()
        conversation = client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id, "project_path": str(self.project)},
        ).json()
        replaced = client.put(
            f"/v1/chat/conversations/{conversation['id']}/transcript",
            json={"messages": []},
        )
        self.assertEqual(replaced.status_code, 200, replaced.text)
        self.assertEqual(replaced.json()["transcript"], [])
        self.assertEqual(paths.checkpoints_db.read_bytes(), checkpoint_bytes)
        self.assertEqual((self.project / "edited.md").read_text(encoding="utf-8"), "chat-file-edit")
        self.assertEqual((self.project / "keep.md").read_text(encoding="utf-8"), "retain-me")

    def test_application_store_refuses_checkpointer_path(self) -> None:
        paths = WorkbenchPaths(self.root)
        with self.assertRaises(ValueError):
            open_sqlite_checkpointer(paths.application_db)


class ApplicationStoreIsolationTests(unittest.TestCase):
    def test_store_constructor_rejects_renamed_application_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp)).ensure()
            paths.application_db = paths.root / "not-application.sqlite"
            with self.assertRaises(ValueError):
                ApplicationStore(paths)


if __name__ == "__main__":
    unittest.main()
