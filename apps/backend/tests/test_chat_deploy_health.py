"""Issue #78: Chat/API reports deploy-health failures; #56 continuity stays."""

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
from workbench_backend.app import create_app
from workbench_backend.inference.connection_errors import (
    DEPLOY_UNHEALTHY_MESSAGE,
    DEPLOY_UNREACHABLE_MESSAGE,
    classify_connection_failure,
    clarify_connection_error,
)
from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, workbench_client


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


class ConnectionErrorClassificationTests(unittest.TestCase):
    def test_opaque_adapter_connection_error_is_classified(self) -> None:
        self.assertEqual(classify_connection_failure("Connection error."), "deploy_unreachable")
        self.assertEqual(clarify_connection_error("Connection error."), DEPLOY_UNREACHABLE_MESSAGE)
        self.assertNotEqual(clarify_connection_error("Connection error."), "Connection error.")

    def test_unrelated_errors_are_not_rewritten(self) -> None:
        self.assertIsNone(classify_connection_failure("tool write_file failed"))
        self.assertEqual(clarify_connection_error("tool write_file failed"), "tool write_file failed")


class ChatDeployHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project-workspace"
        self.project.mkdir()
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.client = workbench_client(self.app)
        attached = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "unreachable-llama"},
        )
        self.assertEqual(attached.status_code, 200, attached.text)
        self.deployment = attached.json()
        self.assertEqual(self.deployment["status"], "unhealthy")

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _create(self) -> dict[str, Any]:
        response = self.client.post(
            "/v1/chat/conversations",
            json={
                "deployment_id": self.deployment["id"],
                "project_path": str(self.project),
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_unhealthy_connected_deploy_is_reported_on_chat_create(self) -> None:
        conversation = self._create()
        health = conversation["deploy_health"]
        self.assertEqual(health["deployment_id"], self.deployment["id"])
        self.assertEqual(health["deployment_status"], "unhealthy")
        self.assertFalse(health["healthy"])
        self.assertEqual(health["code"], "deploy_unhealthy")
        self.assertEqual(health["message"], DEPLOY_UNHEALTHY_MESSAGE)
        self.assertIn("continuity only", health["note"])
        self.assertEqual(conversation["continuity"]["thread_id"], conversation["thread_id"])
        self.assertTrue(conversation["thread_id"])

    def test_live_adapter_unreachable_is_failed_not_empty_success(self) -> None:
        conversation = self._create()
        thread_id = conversation["thread_id"]
        started = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Say hello if the deployment is live."},
        )
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["thread_id"], thread_id)
        self.assertEqual(started.json()["continuity"]["thread_id"], thread_id)
        self.assertTrue(started.json()["current_run_id"])
        body = wait_for_chat(self.client, conversation["id"])
        run = body["current_run"]
        self.assertIsNotNone(run)
        self.assertEqual(run["status"], "failed", run)
        self.assertNotEqual(run["status"], "completed")
        self.assertEqual(body["thread_id"], thread_id)
        self.assertEqual(body["continuity"]["thread_id"], thread_id)
        self.assertEqual(body["continuity"]["run_ids"], [run["id"]])
        health = body["deploy_health"]
        self.assertEqual(health["code"], "deploy_unreachable")
        self.assertEqual(health["message"], DEPLOY_UNREACHABLE_MESSAGE)
        self.assertFalse(health["healthy"])
        self.assertEqual(run["error"], DEPLOY_UNREACHABLE_MESSAGE)
        self.assertNotEqual(run["error"], "Connection error.")
        assistant = [item for item in body["transcript"] if item["role"] == "assistant"]
        self.assertEqual(assistant, [])
        failed_events = [event for event in body["events"] if event["kind"] == "failed"]
        self.assertTrue(failed_events)
        self.assertEqual(failed_events[-1]["detail"].get("code"), "deploy_unreachable")

    def test_scripted_continuity_still_completes_on_unhealthy_fixture(self) -> None:
        scripted = ScriptedChatModel([AIMessage(content="scripted-continuity-ok")])

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        conversation = self._create()
        thread_id = conversation["thread_id"]
        started = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Remember TOKEN-78-CONTINUITY."},
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "completed", body["current_run"].get("error"))
        self.assertEqual(body["thread_id"], thread_id)
        self.assertEqual(body["continuity"]["thread_id"], thread_id)
        self.assertEqual(body["deploy_health"]["code"], "deploy_unhealthy")
        follow = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Second turn on the same thread."},
        )
        self.assertEqual(follow.status_code, 200, follow.text)
        self.assertEqual(follow.json()["thread_id"], thread_id)
        self.assertEqual(follow.json()["continuity"]["thread_id"], thread_id)
        second = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(second["current_run"]["status"], "completed")
        self.assertEqual(second["thread_id"], thread_id)
        self.assertNotEqual(second["current_run"]["id"], body["current_run"]["id"])
        self.assertEqual(second["continuity"]["run_ids"], [body["current_run"]["id"], second["current_run"]["id"]])


if __name__ == "__main__":
    unittest.main()
