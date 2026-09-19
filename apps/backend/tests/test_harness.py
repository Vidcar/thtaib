"""Embedded harness API: AGT-001/002/005/006 plus honour AGT-003/004."""

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
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, workbench_client


def wait_for_run(client: TestClient, run_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/agent-runs/{run_id}")
        body = response.json()
        if body.get("status") in {"completed", "cancelled", "failed"}:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not finish: {body}")


def echo_then_reply() -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "echo", "args": {"text": "harness-ok"}, "id": "call_echo"}],
        ),
        AIMessage(content="The echo tool returned harness-ok. Looks correct."),
    ]


class HarnessApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manager = ModelManager(WorkbenchPaths(self.root).ensure())
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        self.scripted = ScriptedChatModel(echo_then_reply())

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
        )
        self.client = workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "harness-fixture"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _start(self, **extra: Any) -> dict[str, Any]:
        payload = {
            "deployment_id": self.deployment_id,
            "task": "Echo the text harness-ok using the echo tool.",
            **extra,
        }
        response = self.client.post("/v1/agent-runs", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_start_observe_complete_via_deep_agents(self) -> None:
        started = self._start()
        self.assertEqual(started["harness"], "deepagents")
        self.assertIsNone(started["budgets"])
        self.assertEqual(started["knowledge"], "none")
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["stop_reason"], "completed")
        self.assertEqual(body["harness"], "deepagents")
        kinds = [event["kind"] for event in body["events"]]
        self.assertIn("started", kinds)
        self.assertIn("tool_call", kinds)
        self.assertIn("tool_result", kinds)
        self.assertIn("completed", kinds)
        names = [item["name"] for item in body["tool_invocations"]]
        self.assertIn("echo", names)

    def test_actual_model_request_is_captured(self) -> None:
        started = self._start()
        body = wait_for_run(self.client, started["id"])
        self.assertTrue(body["model_requests"])
        capture = body["model_requests"][0]
        self.assertIn("echo", capture["available_tools"])
        self.assertIn("echo", capture["presented_tools"])
        self.assertEqual(capture["memory_versions"], [])
        self.assertEqual(capture["retrieved_material"], [])
        gaps = " ".join(capture["capture_gaps"])
        self.assertIn("no retrieval", gaps)
        self.assertIn("no durable memory", gaps)

    def test_enabled_tools_are_not_silently_removed(self) -> None:
        catalogue = self.client.get("/v1/agent-tools").json()["enabled"]
        self.assertEqual(
            catalogue,
            ["echo", "time_now", "ls", "read_file", "write_file", "edit_file", "glob", "grep"],
        )
        started = self._start(presented_tools=["echo"])
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(
            body["enabled_tools"],
            ["echo", "time_now", "ls", "read_file", "write_file", "edit_file", "glob", "grep"],
        )
        self.assertEqual(body["presented_tools"], ["echo"])
        self.assertIn("echo", body["model_requests"][0]["available_tools"])
        self.assertEqual(body["model_requests"][0]["presented_tools"], ["echo"])
        denied = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "nope",
                "presented_tools": ["shell"],
            },
        )
        self.assertEqual(denied.status_code, 400)
        self.assertEqual(denied.json()["code"], "tool_denied")
        self.assertEqual(self.client.get("/v1/agent-tools").json()["enabled"], catalogue)

    def test_completion_evidence_is_not_judgement(self) -> None:
        started = self._start(
            criteria={
                "checks": ["enabled_tool_invoked", "tool:echo"],
                "expected_artifacts": ["assistant_reply"],
            }
        )
        body = wait_for_run(self.client, started["id"])
        evidence = body["completion"]["evidence"]
        judgement = body["completion"]["judgement"]
        self.assertTrue(evidence["executable_checks"][0]["passed"])
        self.assertTrue(evidence["executable_checks"][1]["passed"])
        self.assertTrue(evidence["expected_artifacts"][0]["present"])
        self.assertIn("echo", judgement["model_review"].lower())
        self.assertNotEqual(evidence, judgement)
        self.assertIn("not an executable check", judgement["note"].lower())

    def test_cancel_stops_a_running_task(self) -> None:
        slow = ScriptedChatModel(echo_then_reply(), delay_s=0.4)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return slow

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
        )
        started = self._start()
        cancelled = self.client.post(f"/v1/agent-runs/{started['id']}/cancel")
        self.assertEqual(cancelled.status_code, 200)
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "cancelled")
        self.assertEqual(body["stop_reason"], "cancelled")

    def test_default_run_has_no_product_budget_or_rag(self) -> None:
        started = self._start()
        body = wait_for_run(self.client, started["id"])
        self.assertIsNone(body["budgets"])
        self.assertEqual(body["knowledge"], "none")
        self.assertFalse(any(self.root.rglob("rag-index*")))
        self.assertFalse(any(self.root.rglob("knowledge-store*")))
        self.assertTrue((self.root / "knowledge").is_dir())
        capture = body["model_requests"][0]
        self.assertEqual(capture["retrieved_material"], [])

    def test_missing_deployment_endpoint_is_rejected(self) -> None:
        response = self.client.post(
            "/v1/agent-runs",
            json={"deployment_id": "deploy_missing", "task": "hello"},
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
