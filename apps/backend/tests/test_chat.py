"""Chat → embedded harness wiring, STATE-002, and project filesystem tools."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.agents.tools import ENABLED_TOOL_NAMES
from workbench_backend.app import create_app
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel

FILESYSTEM_CATALOGUE = list(ENABLED_TOOL_NAMES)


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


def wait_for_chat(client: TestClient, conversation_id: str, *, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/chat/conversations/{conversation_id}")
        body = response.json()
        run = body.get("current_run") or {}
        if run.get("status") in {"completed", "cancelled", "failed"}:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"chat {conversation_id} did not finish: {body}")


def write_then_reply(path: str = "/edited.md", content: str = "chat-file-edit") -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "write_file",
                    "args": {"file_path": path, "content": content},
                    "id": "call_write",
                }
            ],
        ),
        AIMessage(content="Wrote edited.md in the project workspace."),
    ]


class ChatHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project-workspace"
        self.project.mkdir()
        (self.project / "keep.md").write_text("retain-me", encoding="utf-8")
        self.manager = ModelManager(WorkbenchPaths(self.root).ensure())
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        self.scripted = ScriptedChatModel(write_then_reply())

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        self.client = TestClient(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "chat-fixture"},
        ).json()["id"]
        self.profile_id = self.client.post(
            "/v1/profiles",
            json={
                "display_name": "chat-profile",
                "startup": {},
                "per_request": {},
                "agent": {},
            },
        ).json()["id"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create(self, **extra: Any) -> dict[str, Any]:
        payload = {
            "deployment_id": self.deployment_id,
            "profile_id": self.profile_id,
            "project_path": str(self.project),
            **extra,
        }
        response = self.client.post("/v1/chat/conversations", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _start(self, conversation_id: str, task: str = "Edit edited.md in the project.") -> dict[str, Any]:
        response = self.client.post(
            f"/v1/chat/conversations/{conversation_id}/start",
            json={"task": task},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_chat_calls_the_same_embedded_harness(self) -> None:
        conversation = self._create()
        self.assertEqual(conversation["harness"], "deepagents")
        self.assertFalse(conversation["second_agent_loop"])
        self.assertEqual(conversation["profile_id"], self.profile_id)
        started = self._start(conversation["id"])
        self.assertEqual(started["harness"], "deepagents")
        self.assertFalse(started["second_agent_loop"])
        run = started["current_run"]
        self.assertIsNotNone(run)
        self.assertEqual(run["harness"], "deepagents")
        self.assertEqual(run["source_surface"], "chat")
        self.assertEqual(run["project_path"], str(self.project.resolve()))
        self.assertEqual(run["profile_id"], self.profile_id)
        listed = self.client.get("/v1/agent-runs").json()
        self.assertTrue(any(item["id"] == run["id"] for item in listed))
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "completed")
        kinds = [event["kind"] for event in body["events"]]
        self.assertIn("started", kinds)
        self.assertIn("tool_call", kinds)
        self.assertIn("tool_result", kinds)
        self.assertIn("completed", kinds)
        self.assertEqual(body["current_run"]["harness"], "deepagents")

    def test_filesystem_tools_write_project_storage(self) -> None:
        catalogue = self.client.get("/v1/agent-tools").json()["enabled"]
        self.assertEqual(catalogue, FILESYSTEM_CATALOGUE)
        conversation = self._create()
        started = self._start(conversation["id"])
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "completed", body["current_run"].get("error"))
        names = [item["name"] for item in body["current_run"]["tool_invocations"]]
        self.assertIn("write_file", names)
        written = self.project / "edited.md"
        self.assertTrue(written.is_file())
        self.assertEqual(written.read_text(encoding="utf-8"), "chat-file-edit")
        self.assertEqual((self.project / "keep.md").read_text(encoding="utf-8"), "retain-me")
        paths = WorkbenchPaths(self.root)
        edited_hits = [path for path in self.root.rglob("edited.md") if path.is_file()]
        self.assertEqual(edited_hits, [written])
        self.assertTrue(paths.application_db.is_file())
        self.assertTrue(paths.checkpoints_db.is_file())
        self.assertNotEqual(paths.application_db, paths.checkpoints_db)
        self.assertFalse((paths.state / "chat" / "edited.md").exists())

    def test_transcript_is_not_the_working_project(self) -> None:
        conversation = self._create()
        self._start(conversation["id"])
        wait_for_chat(self.client, conversation["id"])
        self.assertEqual((self.project / "edited.md").read_text(encoding="utf-8"), "chat-file-edit")
        fingerprints_before = {
            path.relative_to(self.project).as_posix(): path.read_text(encoding="utf-8")
            for path in self.project.rglob("*")
            if path.is_file()
        }
        replaced = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/transcript",
            json={"messages": [{"role": "user", "content": "rewritten history only", "at": "2026-01-01T00:00:00+00:00"}]},
        )
        self.assertEqual(replaced.status_code, 200, replaced.text)
        self.assertTrue(replaced.json()["history_replaced"])
        self.assertEqual(len(replaced.json()["transcript"]), 1)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["transcript"][0]["content"], "rewritten history only")
        fingerprints_after = {
            path.relative_to(self.project).as_posix(): path.read_text(encoding="utf-8")
            for path in self.project.rglob("*")
            if path.is_file()
        }
        self.assertEqual(fingerprints_after, fingerprints_before)
        self.assertEqual((self.project / "keep.md").read_text(encoding="utf-8"), "retain-me")
        self.assertEqual((self.project / "edited.md").read_text(encoding="utf-8"), "chat-file-edit")

        fresh = self._create()
        self.assertNotEqual(fresh["id"], conversation["id"])
        self.assertEqual(fresh["transcript"], [])
        self.assertEqual((self.project / "keep.md").read_text(encoding="utf-8"), "retain-me")
        self.assertEqual((self.project / "edited.md").read_text(encoding="utf-8"), "chat-file-edit")

        cleared = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/transcript",
            json={"messages": []},
        )
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertEqual(cleared.json()["transcript"], [])
        self.assertEqual((self.project / "keep.md").read_text(encoding="utf-8"), "retain-me")
        self.assertEqual((self.project / "edited.md").read_text(encoding="utf-8"), "chat-file-edit")

    def test_workspace_id_resolves_project_path(self) -> None:
        workspace = self.client.post(
            "/v1/lab/workspaces",
            json={"display_name": "chat-ws", "files": {"from-lab.md": "lab-seed"}},
        ).json()
        conversation = self._create(workspace_id=workspace["id"], project_path=workspace["path"])
        self.assertEqual(Path(conversation["project_path"]), Path(workspace["path"]).resolve())
        started = self._start(conversation["id"])
        wait_for_chat(self.client, conversation["id"])
        self.assertTrue((Path(workspace["path"]) / "edited.md").is_file())
        self.assertEqual((Path(workspace["path"]) / "from-lab.md").read_text(encoding="utf-8"), "lab-seed")
        self.assertEqual(started["current_run"]["workspace_id"], workspace["id"])

    def test_missing_project_path_is_rejected(self) -> None:
        response = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "project_required")

    def test_unknown_profile_is_rejected(self) -> None:
        response = self.client.post(
            "/v1/chat/conversations",
            json={
                "deployment_id": self.deployment_id,
                "profile_id": "profile_missing",
                "project_path": str(self.project),
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "profile_missing")

    def test_cancel_uses_the_harness_cancel_path(self) -> None:
        slow = ScriptedChatModel(write_then_reply(), delay_s=0.4)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return slow

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        conversation = self._create()
        started = self._start(conversation["id"])
        cancelled = self.client.post(f"/v1/chat/conversations/{conversation['id']}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "cancelled")
        self.assertEqual(body["current_run"]["id"], started["current_run"]["id"])


class HarnessProjectFilesystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "direct-project"
        self.project.mkdir()
        self.manager = ModelManager(WorkbenchPaths(self.root).ensure())
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        self.scripted = ScriptedChatModel(write_then_reply("/direct.md", "via-harness"))

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            app_store=self.app.state.app_store,
        )
        self.client = TestClient(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "fs-fixture"},
        ).json()["id"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_agent_run_write_file_targets_project_path(self) -> None:
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Write direct.md",
                "project_path": str(self.project),
                "presented_tools": ["write_file"],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertEqual((self.project / "direct.md").read_text(encoding="utf-8"), "via-harness")


if __name__ == "__main__":
    unittest.main()
