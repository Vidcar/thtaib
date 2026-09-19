"""Embedded harness API: AGT-001/002/005/006 plus honour AGT-003/004."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.app import create_app
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel, set_generate_hold, wait_for_generate_hold
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


def wait_for_status(
    client: TestClient,
    run_id: str,
    status: str,
    *,
    timeout: float = 10.0,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/agent-runs/{run_id}")
        body = response.json()
        if body.get("status") == status:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not reach {status}: {body}")


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
        self.assertEqual(body["enabled_tools"], ["echo", "time_now"])
        self.assertEqual(body["presented_tools"], ["echo"])
        self.assertEqual(body["model_requests"][0]["available_tools"], ["echo", "time_now"])
        self.assertEqual(body["model_requests"][0]["presented_tools"], ["echo"])
        project = self.root / "agt-005-project"
        project.mkdir()
        bound = self._start(presented_tools=["echo"], project_path=str(project))
        bound_body = wait_for_run(self.client, bound["id"])
        self.assertEqual(bound_body["enabled_tools"], catalogue)
        self.assertEqual(bound_body["presented_tools"], ["echo"])
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
        blocked = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "nope",
                "presented_tools": ["write_file"],
            },
        )
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.json()["code"], "filesystem_requires_project")
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

    def test_cancel_request_is_not_immediately_confirmed(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        self.addCleanup(set_generate_hold, None)
        self.addCleanup(hold.set)
        held = ScriptedChatModel(echo_then_reply(), hold=hold)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return held

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
        )
        started = self._start()
        try:
            wait_for_status(self.client, started["id"], "running")
            wait_for_generate_hold()
            requested = self.client.post(f"/v1/agent-runs/{started['id']}/cancel")
            self.assertEqual(requested.status_code, 200, requested.text)
            body = requested.json()
            self.assertEqual(body["status"], "cancel_requested")
            self.assertIsNone(body["stop_reason"])
            self.assertIsNone(body["finished_at"])
            kinds = [event["kind"] for event in body["events"]]
            self.assertIn("cancel_requested", kinds)
            self.assertNotIn("cancelled", kinds)
            observed = self.client.get(f"/v1/agent-runs/{started['id']}")
            self.assertEqual(observed.json()["status"], "cancel_requested")
        finally:
            hold.set()
        confirmed = wait_for_run(self.client, started["id"])
        self.assertEqual(confirmed["status"], "cancelled")
        self.assertEqual(confirmed["stop_reason"], "cancelled")
        self.assertIsNotNone(confirmed["finished_at"])
        confirmed_kinds = [event["kind"] for event in confirmed["events"]]
        self.assertIn("cancel_requested", confirmed_kinds)
        self.assertIn("cancelled", confirmed_kinds)

    def test_cancel_requested_is_still_live_for_quiescence(self) -> None:
        now = utc_now()
        run = AgentRun(
            id="agent_cancel_live_ws",
            status=AgentRunStatus.cancel_requested,
            deployment_id=self.deployment_id,
            task="held for quiescence",
            enabled_tools=["echo"],
            presented_tools=["echo"],
            created_at=now,
            updated_at=now,
            workspace_id="ws_cancel_live",
        )
        harness = self.app.state.harness
        harness.store.put_run(run)
        self.assertEqual(harness.active_workspace_run_ids("ws_cancel_live"), [run.id])
        run.status = AgentRunStatus.cancelled
        harness.store.put_run(run)
        self.assertEqual(harness.active_workspace_run_ids("ws_cancel_live"), [])

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
