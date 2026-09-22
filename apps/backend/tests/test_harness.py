"""Embedded harness API: AGT-001/002/005/006 plus honour AGT-003/004."""

from __future__ import annotations

import http.server
import os
import socketserver
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
from langgraph.checkpoint.base import empty_checkpoint
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService, _graph_checkpoint_snapshot
from workbench_backend.agents.schemas import (
    AgentRun,
    AgentRunStatus,
    GenerationObservation,
    PendingInterrupt,
    PendingInterruptAction,
)
from workbench_backend.app import create_app
from workbench_backend.inference.capabilities import setup_fingerprint
from workbench_backend.inference.adapter import RecordingTransport
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import ServerProperties
from workbench_backend.state.checkpointer import open_sqlite_checkpointer

from tests.scripted_model import ScriptedChatModel, set_generate_hold, wait_for_generate_hold
from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run, wait_for_status


class _ThreadingHttpServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


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
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.scripted = ScriptedChatModel(echo_then_reply())
        self.extra_harnesses: list[HarnessService] = []

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
        )
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "harness-fixture"},
        ).json()["id"]

    def tearDown(self) -> None:
        for harness in self.extra_harnesses:
            harness.close(timeout=1.0)
            if harness._app_store is not None:
                harness._app_store.close()
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _restart_harness(self) -> HarnessService:
        restarted = HarnessService(
            lambda: self.manager,
            model_factory=lambda _run, _sink: self.scripted,
            knowledge_provider=lambda: self.app.state.knowledge,
        )
        self.extra_harnesses.append(restarted)
        return restarted

    def _put_checkpoint(self, thread_id: str) -> str:
        saver = open_sqlite_checkpointer(self.manager.paths.checkpoints_db)
        saved = saver.put(
            {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
            empty_checkpoint(),
            {"source": "test", "step": 0, "writes": {}, "parents": {}},
            {},
        )
        checkpoint_id = saved["configurable"]["checkpoint_id"]
        self.assertIsInstance(checkpoint_id, str)
        return checkpoint_id

    def _put_pending_interrupt_checkpoint(self, thread_id: str) -> str:
        saver = open_sqlite_checkpointer(self.manager.paths.checkpoints_db)
        saved = saver.put(
            {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
            empty_checkpoint(),
            {"source": "test", "step": 0, "writes": {}, "parents": {}},
            {},
        )
        saver.put_writes(
            saved,
            [("__interrupt__", [{"id": f"{thread_id}:interrupt", "value": {"action_requests": [{"name": "execute", "args": {}}]}}])],
            "test_interrupt_task",
        )
        checkpoint_id = saved["configurable"]["checkpoint_id"]
        self.assertIsInstance(checkpoint_id, str)
        return checkpoint_id

    def _start(self, **extra: Any) -> dict[str, Any]:
        payload = {
            "deployment_id": self.deployment_id,
            "task": "Echo the text harness-ok using the echo tool.",
            **extra,
        }
        response = self.client.post("/v1/agent-runs", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _wait_for_pending_interrupt(self, run_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + 10
        body: dict[str, Any] = {}
        while time.monotonic() < deadline:
            response = self.client.get(f"/v1/agent-runs/{run_id}")
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            if body.get("pending_interrupt") and body.get("checkpoint_ids"):
                return body
            time.sleep(0.05)
        raise AssertionError(f"pending interrupt not observed: {body}")

    def _record_capability(self, capability: str, status: str = "passed") -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        self.manager.store.put_capability_evidence(
            {
                "schema_version": 1,
                "id": f"probe_{capability}_{status}",
                "deployment_id": deployment.id,
                "capability": capability,
                "status": status,
                "fingerprint": setup_fingerprint(deployment),
                "setup": {"deployment_id": deployment.id},
                "tested_at": utc_now(),
                "inputs": {},
                "observations": {},
            }
        )

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

    def test_native_driver_observer_and_audit_details(self) -> None:
        observed: list[tuple[str, str | None]] = []

        def observer(run: AgentRun, event: dict[str, Any] | None) -> None:
            method = event.get("method") if isinstance(event, dict) else None
            observed.append((run.id, method))

        self.app.state.harness.close(timeout=1.0)
        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=lambda _run, _sink: ScriptedChatModel(echo_then_reply()),
            knowledge_provider=lambda: self.app.state.knowledge,
            interaction_observer=observer,
        )
        self.extra_harnesses.append(self.app.state.harness)

        started = self._start()
        body = wait_for_run(self.client, started["id"])

        self.assertEqual(body["status"], "completed")
        self.assertIn("values", [method for _run_id, method in observed])
        self.assertIn("messages", [method for _run_id, method in observed])
        self.assertIn(None, [method for _run_id, method in observed])
        kinds = [event["kind"] for event in body["events"]]
        self.assertEqual(kinds.count("tool_call"), 1)
        self.assertEqual(kinds.count("tool_result"), 1)
        assistant = [event for event in body["events"] if event["kind"] == "assistant_message"][-1]
        self.assertEqual(assistant["detail"]["content"], "The echo tool returned harness-ok. Looks correct.")
        self.assertTrue(assistant["detail"]["message_id"])
        self.assertEqual(
            assistant["detail"]["content_blocks"],
            [{"type": "text", "text": "The echo tool returned harness-ok. Looks correct."}],
        )

    def test_native_values_do_not_reingest_prior_thread_messages(self) -> None:
        thread_id = "thread-native-values-dedupe"
        self.app.state.harness.close(timeout=1.0)
        scripted = ScriptedChatModel([
            AIMessage(content="first assistant"),
            AIMessage(content="second assistant"),
        ])
        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=lambda _run, _sink: scripted,
            knowledge_provider=lambda: self.app.state.knowledge,
        )
        self.extra_harnesses.append(self.app.state.harness)

        first = self._start(thread_id=thread_id, presented_tools=[])
        first_body = wait_for_run(self.client, first["id"])
        self.assertEqual(first_body["status"], "completed")

        second = self._start(thread_id=thread_id, task="Continue.", presented_tools=[])
        second_body = wait_for_run(self.client, second["id"])

        assistant_events = [
            event["detail"]["content"]
            for event in second_body["events"]
            if event["kind"] == "assistant_message"
        ]
        self.assertEqual(assistant_events, ["second assistant"])

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
        self.assertIn("context_observation", capture)
        self.assertEqual(capture["context_observation"]["summarization_path"], "deepagents-upstream")

    def test_rejects_arbitrary_history_injection_fields(self) -> None:
        response = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "hello",
                "messages": [{"role": "system", "content": "replace policy"}],
            },
        )

        self.assertEqual(response.status_code, 422, response.text)

    def test_context_preflight_blocks_before_dispatch(self) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        self.manager.store.put_deployment(
            deployment.model_copy(
                update={
                    "server_props": ServerProperties(
                        fetched=utc_now(),
                        source_url="http://127.0.0.1:9/props",
                        n_ctx=64,
                    )
                }
            )
        )

        response = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "x" * 2000,
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["code"], "context_capacity_exceeded")

    def test_structured_output_requires_passed_setup_specific_probe(self) -> None:
        schema = {
            "schema_version": 1,
            "name": "AnswerShape",
            "schema": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
        }

        failed = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "answer briefly",
                "output_schema": schema,
            },
        )
        self.assertEqual(failed.status_code, 409, failed.text)
        self.assertEqual(failed.json()["code"], "structured_tools_unavailable")

        self._record_capability("tools")
        self._record_capability("structured_tools")
        self._record_capability("structured_tools_with_tools")
        started = self._start(task="answer briefly", output_schema=schema)
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["structured_output"]["strategy"], "tool")
        self.assertIn(
            body["structured_output"]["validation_status"],
            {"valid", "missing", "invalid"},
        )

    def test_upstream_planning_tool_round_trip_without_project(self) -> None:
        self.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"name": "write_todos", "args": {"todos": [{"content": "Check integration", "status": "in_progress"}]}, "id": "plan-1"}]),
            AIMessage(content="Planning recorded."),
        ])
        started = self._start()
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertIn("write_todos", body["model_requests"][0]["presented_tools"])
        self.assertTrue(any(event["kind"] == "tool_result" and event["detail"].get("name") == "write_todos" for event in body["events"]))

    def test_enabled_tools_are_not_silently_removed(self) -> None:
        catalogue = self.client.get("/v1/agent-tools").json()["enabled"]
        self.assertEqual(
            catalogue,
            [
                "echo",
                "time_now",
                "ls",
                "read_file",
                "write_file",
                "edit_file",
                "glob",
                "grep",
                "rename_file",
                "delete_file",
                "execute",
                "write_todos",
                "ask_user",
                "propose_memory",
                "read_attachment",
            ],
        )
        started = self._start(presented_tools=["echo"])
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["enabled_tools"], ["echo", "time_now", "write_todos", "ask_user", "propose_memory", "read_file"])
        self.assertEqual(body["presented_tools"], ["echo"])
        self.assertEqual(body["model_requests"][0]["available_tools"], ["echo", "time_now", "write_todos", "ask_user", "propose_memory", "read_file"])
        self.assertCountEqual(body["model_requests"][0]["presented_tools"], ["echo", "read_file"])
        self.assertEqual(body["framework_read_paths"], ["/large_tool_results/", "/conversation_history/"])
        project = self.root / "agt-005-project"
        project.mkdir()
        bound = self._start(presented_tools=["echo"], project_path=str(project))
        bound_body = wait_for_run(self.client, bound["id"])
        self.assertEqual(bound_body["enabled_tools"], [name for name in catalogue if name != "read_attachment"])
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
        from workbench_backend.agents.tools import resolve_presented_tools
        presented, denied, _filesystem, _shell = resolve_presented_tools(
            ["echo", "read_attachment"],
            project_bound=True,
            attachment_available=False,
        )
        self.assertIn("echo", presented)
        self.assertNotIn("read_attachment", presented)
        self.assertNotIn("read_attachment", denied)
        with_file, still_denied, _filesystem, _shell = resolve_presented_tools(
            ["read_attachment"],
            project_bound=True,
            attachment_available=True,
        )
        self.assertEqual(with_file, ["read_attachment"])
        self.assertEqual(still_denied, [])

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

    def test_second_run_starts_while_another_uses_the_same_project(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        self.addCleanup(set_generate_hold, None)
        self.addCleanup(hold.set)
        project = self.root / "shared-project"
        project.mkdir()
        workspace = self.client.post(
            "/v1/lab/workspaces",
            json={"display_name": "shared-folder", "files": {"notes.md": "original\n"}},
        )
        self.assertEqual(workspace.status_code, 200, workspace.text)
        workspace_id = workspace.json()["id"]

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel(echo_then_reply(), hold=hold)

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
        )
        self.app.state.lab._harness_provider = lambda: self.app.state.harness
        first = self._start(project_path=str(project), presented_tools=["echo"])
        wait_for_status(self.client, first["id"], "running")
        second = self._start(
            project_path=str(project),
            presented_tools=["echo"],
            task="A second chat may write in the same folder.",
        )
        self.assertNotEqual(second["id"], first["id"])
        held_workspace = self._start(workspace_id=workspace_id, presented_tools=["echo"], task="Hold the workspace.")
        wait_for_status(self.client, held_workspace["id"], "running")
        another_workspace = self._start(
            workspace_id=workspace_id,
            presented_tools=["echo"],
            task="Another chat in the same workspace.",
        )
        self.assertNotEqual(another_workspace["id"], held_workspace["id"])
        blocked = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace_id, "run_id": held_workspace["id"]},
        )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["code"], "not_quiescent")
        hold.set()
        for run_id in (first["id"], second["id"], held_workspace["id"], another_workspace["id"]):
            self.assertEqual(wait_for_run(self.client, run_id)["status"], "completed")

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

    def test_cancel_closes_run_owned_model_client_without_confirming_stop(self) -> None:
        run = AgentRun(
            id="agent_cancel_closes_client",
            status=AgentRunStatus.running,
            deployment_id=self.deployment_id,
            task="held model call",
            enabled_tools=["echo"],
            presented_tools=["echo"],
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        harness = self.app.state.harness
        client = httpx.Client(timeout=60.0)
        self.addCleanup(client.close)
        with harness._lock:  # Product boundary: cancel closes only this run's transport.
            harness._runs[run.id] = run
            harness._cancels[run.id] = threading.Event()
            harness._decision_ready[run.id] = threading.Event()
            harness._model_clients[run.id] = client

        cancelled = harness.cancel(run.id)

        self.assertTrue(client.is_closed)
        self.assertEqual(cancelled.status, AgentRunStatus.cancel_requested)
        self.assertIsNone(cancelled.finished_at)
        self.assertEqual(
            [event.kind for event in cancelled.events],
            ["cancel_requested"],
        )

    def test_httpx_client_close_interrupts_blocked_model_transport(self) -> None:
        if os.name != "nt":
            self.skipTest("httpcore 1.0.9 closes sockets without shutdown; cross-thread recv unblock was validated for the Windows product runtime only.")
        entered = threading.Event()
        release = threading.Event()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                entered.set()
                release.wait()

            def log_message(self, *_args: object) -> None:
                return

        server = _ThreadingHttpServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        serve = threading.Thread(target=server.serve_forever, daemon=True)
        serve.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(release.set)
        capture_sink: list[dict[str, Any]] = []
        client = httpx.Client(
            transport=RecordingTransport(capture_sink),
            timeout=60.0,
        )
        self.addCleanup(client.close)
        result: dict[str, str] = {}

        def request() -> None:
            try:
                client.post(
                    f"http://127.0.0.1:{server.server_address[1]}/v1/chat/completions",
                    json={"messages": [{"role": "user", "content": "wait"}]},
                )
                result["status"] = "returned"
            except Exception as exc:  # noqa: BLE001 - transport error is the expected cancellation signal.
                result["status"] = type(exc).__name__

        worker = threading.Thread(target=request)
        worker.start()
        self.assertTrue(entered.wait(timeout=5.0))
        try:
            client.close()
            worker.join(timeout=5.0)

            self.assertFalse(worker.is_alive(), result)
            self.assertIn(result.get("status"), {"ReadError", "WriteError", "ConnectError"})
            self.assertEqual(len(capture_sink), 1)
            self.assertTrue(capture_sink[0]["url"].endswith("/v1/chat/completions"))
        finally:
            release.set()

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
        with harness._lock:
            harness._runs[run.id] = run
            harness._cancels[run.id] = threading.Event()
        self.assertEqual(harness.active_workspace_run_ids("ws_cancel_live"), [run.id])
        run.status = AgentRunStatus.cancelled
        harness.store.put_run(run)
        self.assertEqual(harness.active_workspace_run_ids("ws_cancel_live"), [])

    def test_restart_reconciles_orphan_running_run_as_failed(self) -> None:
        now = utc_now()
        run = AgentRun(
            id="agent_orphan_running",
            status=AgentRunStatus.running,
            deployment_id=self.deployment_id,
            task="lost worker",
            enabled_tools=["echo"],
            presented_tools=["echo"],
            created_at=now,
            updated_at=now,
            workspace_id="ws_orphan",
            generation_observation=GenerationObservation(request_id="lost-request", phase="generating",
                input_tokens=100, output_tokens=7, context_used_tokens=107, elapsed_seconds=.5,
                tokens_per_second=12, measured_at=now, basis="llama_cpp_timings", interval="current_model_call_generation"),
        )
        self.app.state.harness.store.put_run(run)

        restarted = self._restart_harness()

        observed = restarted.get_run(run.id)
        self.assertEqual(observed.status, AgentRunStatus.failed)
        self.assertEqual(observed.stop_reason, "orphaned")
        self.assertIn("restarted", observed.error or "")
        self.assertEqual(restarted.active_workspace_run_ids("ws_orphan"), [])
        self.assertEqual(observed.generation_observation.phase, "interrupted")
        self.assertEqual(observed.generation_observation.output_tokens, 7)
        self.assertEqual(observed.generation_observation.interval, "last_model_call_generation")
        self.assertEqual(restarted.store.get_run(run.id).generation_observation, observed.generation_observation)

    def test_restart_reconciles_orphan_queued_and_running_runs_as_failed(self) -> None:
        for status in (AgentRunStatus.queued, AgentRunStatus.running):
            with self.subTest(status=status.value):
                now = utc_now()
                run = AgentRun(
                    id=f"agent_orphan_{status.value}",
                    status=status,
                    deployment_id=self.deployment_id,
                    task="lost worker",
                    enabled_tools=["echo"],
                    presented_tools=["echo"],
                    created_at=now,
                    updated_at=now,
                    workspace_id=f"ws_orphan_{status.value}",
                )
                self.app.state.harness.store.put_run(run)

                restarted = self._restart_harness()

                observed = restarted.get_run(run.id)
                self.assertEqual(observed.status, AgentRunStatus.failed)
                self.assertEqual(observed.stop_reason, "orphaned")
                self.assertEqual(
                    observed.events[-1].detail["code"],
                    "run_orphaned_after_restart",
                )
                self.assertEqual(restarted.active_workspace_run_ids(run.workspace_id), [])

    def test_restart_preserves_pending_interrupt_for_resume(self) -> None:
        now = utc_now()
        pending = PendingInterrupt(
            interrupt_id="thread_pending_interrupt:interrupt",
            action_requests=[
                PendingInterruptAction(
                    name="execute",
                    args={"command": "Remove-Item disposable.txt"},
                    allowed_decisions=["approve", "reject"],
                )
            ]
        )
        run = AgentRun(
            id="agent_pending_interrupt",
            status=AgentRunStatus.running,
            deployment_id=self.deployment_id,
            task="approval paused",
            enabled_tools=["execute"],
            presented_tools=["execute"],
            created_at=now,
            updated_at=now,
            pending_interrupt=pending,
            thread_id="thread_pending_interrupt",
            checkpoint_ids=[self._put_pending_interrupt_checkpoint("thread_pending_interrupt")],
        )
        self.app.state.harness.store.put_run(run)

        restarted = self._restart_harness()

        observed = restarted.get_run(run.id)
        self.assertEqual(observed.status, AgentRunStatus.running)
        self.assertIsNotNone(observed.pending_interrupt)
        self.assertEqual(observed.pending_interrupt.action_requests[0].name, "execute")

    def test_checkpoint_reader_matches_execution_graph_for_pending_interrupt_without_runtime_effects(self) -> None:
        self._record_capability("tools")
        self._record_capability("structured_tools")
        self._record_capability("structured_tools_with_tools")
        project = self.root / "checkpoint-reader-project"
        project.mkdir()
        (project / "disposable.txt").write_text("keep", encoding="utf-8")
        self.scripted = ScriptedChatModel([
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "execute",
                        "args": {"command": "Remove-Item disposable.txt"},
                        "id": "exec_checkpoint_reader",
                    }
                ],
            )
        ])
        started = self._start(
            task="run a shell command",
            presented_tools=["execute"],
            project_path=str(project),
            output_schema={
                "schema_version": 1, "name": "AnswerShape",
                "schema": {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]},
            },
        )
        body = self._wait_for_pending_interrupt(started["id"])
        run = self.app.state.harness.get_run(started["id"])
        checkpoint_id = body["checkpoint_ids"][-1]

        execution_agent = self.app.state.harness._create_compiled_agent(run, [], None)
        execution_snapshot = _graph_checkpoint_snapshot(execution_agent, run.thread_id, checkpoint_id)

        def fail_model_factory(_run, _sink):
            raise AssertionError("checkpoint read must not construct a runtime model")

        self.app.state.harness._model_factory = fail_model_factory
        original_run = run.model_dump(mode="json")
        with patch.object(
            self.app.state.manager,
            "ensure_deployment_ready",
            side_effect=AssertionError("checkpoint read must not start deployment"),
        ):
            with patch(
                "workbench_backend.agents.harness_backend.harness_scratch_root",
                # Backend construction may resolve paths, but may not create
                # or populate storage while inspecting saved state.
                wraps=lambda *_args: self.root / "inspection-must-not-create",
            ):
                with patch(
                    "workbench_backend.agents.harness.materialize_onto_backend",
                    side_effect=AssertionError("checkpoint read must not materialize knowledge"),
                ):
                    inspected = self.app.state.harness.checkpoint_state_for_run(run, checkpoint_id)
                    inspection_agent = self.app.state.harness._create_compiled_agent(
                        run.model_copy(deep=True), [], None, inspection_only=True,
                    )

        self.assertEqual(inspected["next"], tuple(execution_snapshot.next))
        self.assertEqual(inspected["values"], dict(execution_snapshot.values))
        self.assertEqual(set(inspection_agent.nodes), set(execution_agent.nodes))
        self.assertEqual(set(inspection_agent.channels), set(execution_agent.channels))
        self.assertEqual(run.model_dump(mode="json"), original_run)
        self.assertFalse((self.root / "inspection-must-not-create").exists())

    def test_restart_fails_pending_interrupt_with_historical_only_checkpoint(self) -> None:
        now = utc_now()
        pending = PendingInterrupt(
            interrupt_id="historical-only:interrupt",
            action_requests=[
                PendingInterruptAction(
                    name="execute",
                    args={"command": "Remove-Item disposable.txt"},
                    allowed_decisions=["approve", "reject"],
                )
            ]
        )
        run = AgentRun(
            id="agent_historical_only_interrupt",
            status=AgentRunStatus.running,
            deployment_id=self.deployment_id,
            task="approval paused",
            enabled_tools=["execute"],
            presented_tools=["execute"],
            created_at=now,
            updated_at=now,
            pending_interrupt=pending,
            thread_id="thread_historical_only_interrupt",
            checkpoint_ids=[self._put_checkpoint("thread_historical_only_interrupt")],
        )
        # A later non-interrupted checkpoint makes the saved interrupt checkpoint
        # historical. Restart must not resume from the old approval boundary.
        self._put_checkpoint("thread_historical_only_interrupt")
        self.app.state.harness.store.put_run(run)

        restarted = self._restart_harness()

        observed = restarted.get_run(run.id)
        self.assertEqual(observed.status, AgentRunStatus.failed)
        self.assertEqual(observed.stop_reason, "orphaned")
        self.assertEqual(
            observed.events[-1].detail["code"],
            "pending_interrupt_checkpoint_missing",
        )

    def test_restart_fails_pending_interrupt_without_checkpoint_linkage(self) -> None:
        now = utc_now()
        pending = PendingInterrupt(
            interrupt_id="thread_resume_reserved:interrupt",
            action_requests=[
                PendingInterruptAction(
                    name="execute",
                    args={"command": "Remove-Item disposable.txt"},
                    allowed_decisions=["approve", "reject"],
                )
            ]
        )
        run = AgentRun(
            id="agent_pending_without_checkpoint",
            status=AgentRunStatus.running,
            deployment_id=self.deployment_id,
            task="approval paused without checkpoint",
            enabled_tools=["execute"],
            presented_tools=["execute"],
            created_at=now,
            updated_at=now,
            pending_interrupt=pending,
            thread_id="thread_pending_without_checkpoint",
        )
        self.app.state.harness.store.put_run(run)

        restarted = self._restart_harness()

        observed = restarted.get_run(run.id)
        self.assertEqual(observed.status, AgentRunStatus.failed)
        self.assertEqual(observed.stop_reason, "orphaned")
        self.assertIn("no recorded checkpoint linkage", observed.error or "")
        self.assertEqual(
            observed.events[-1].detail["code"],
            "pending_interrupt_checkpoint_missing",
        )

    def test_restart_marks_cancel_requested_orphan_terminal(self) -> None:
        now = utc_now()
        run = AgentRun(
            id="agent_persisted_cancel",
            status=AgentRunStatus.cancel_requested,
            deployment_id=self.deployment_id,
            task="cancel before restart",
            enabled_tools=["echo"],
            presented_tools=["echo"],
            created_at=now,
            updated_at=now,
            workspace_id="ws_cancel_restart",
        )
        self.app.state.harness.store.put_run(run)

        restarted = self._restart_harness()

        observed = restarted.get_run(run.id)
        self.assertEqual(observed.status, AgentRunStatus.failed)
        self.assertEqual(observed.stop_reason, "orphaned")
        self.assertIsNotNone(observed.finished_at)
        self.assertIn("unknown external effects", observed.error or "")
        self.assertEqual(
            observed.events[-1].detail["code"],
            "cancel_requested_orphaned_after_restart",
        )
        self.assertEqual(restarted.active_workspace_run_ids("ws_cancel_restart"), [])

    def test_restart_cancel_requested_pending_checkpoint_is_terminal_no_worker(self) -> None:
        now = utc_now()
        pending = PendingInterrupt(
            interrupt_id="thread_resume_reserved:interrupt",
            action_requests=[
                PendingInterruptAction(
                    name="execute",
                    args={"command": "Remove-Item disposable.txt"},
                    allowed_decisions=["approve", "reject"],
                )
            ]
        )
        run = AgentRun(
            id="agent_cancel_pending_checkpoint",
            status=AgentRunStatus.cancel_requested,
            deployment_id=self.deployment_id,
            task="cancelled approval pause",
            enabled_tools=["execute"],
            presented_tools=["execute"],
            created_at=now,
            updated_at=now,
            pending_interrupt=pending,
            thread_id="thread_cancel_pending_checkpoint",
            checkpoint_ids=[self._put_checkpoint("thread_cancel_pending_checkpoint")],
            workspace_id="ws_cancel_pending_checkpoint",
        )
        self.app.state.harness.store.put_run(run)

        restarted = self._restart_harness()

        observed = restarted.get_run(run.id)
        self.assertEqual(observed.status, AgentRunStatus.failed)
        self.assertEqual(observed.stop_reason, "orphaned")
        self.assertIsNotNone(observed.pending_interrupt)
        self.assertEqual(
            observed.events[-1].detail["code"],
            "cancel_requested_orphaned_after_restart",
        )
        self.assertEqual(restarted.active_workspace_run_ids("ws_cancel_pending_checkpoint"), [])
        self.assertEqual(restarted._threads, {})

        cancelled = restarted.cancel(run.id)

        self.assertEqual(cancelled.status, AgentRunStatus.failed)
        self.assertEqual(cancelled.stop_reason, "orphaned")
        self.assertEqual(restarted._threads, {})

    def test_resume_after_restart_reserves_once_before_worker_runs(self) -> None:
        now = utc_now()
        pending = PendingInterrupt(
            interrupt_id="thread_resume_reserved:interrupt",
            action_requests=[
                PendingInterruptAction(
                    name="execute",
                    args={"command": "Remove-Item disposable.txt"},
                    allowed_decisions=["approve", "reject"],
                )
            ]
        )
        run = AgentRun(
            id="agent_resume_reserved",
            status=AgentRunStatus.running,
            deployment_id=self.deployment_id,
            task="approval paused",
            enabled_tools=["execute"],
            presented_tools=["execute"],
            created_at=now,
            updated_at=now,
            pending_interrupt=pending,
            thread_id="thread_resume_reserved",
            checkpoint_ids=[self._put_pending_interrupt_checkpoint("thread_resume_reserved")],
        )
        harness = self.app.state.harness
        harness.store.put_run(run)

        request = {"interrupt_id": pending.interrupt_id, "namespace": [], "decisions": [{"type": "reject"}]}
        entered = threading.Event()
        release = threading.Event()

        def fail_compilation(*_args: Any, **_kwargs: Any) -> None:
            entered.set()
            if not release.wait(timeout=10):
                raise TimeoutError("resume worker was not released")
            raise RuntimeError("scripted resume setup failure")

        with patch.object(harness, "_create_compiled_agent", side_effect=fail_compilation):
            try:
                first = self.client.post(f"/v1/agent-runs/{run.id}/interrupt-decision", json=request)
                self.assertTrue(entered.wait(timeout=10))
                owner = harness._threads[run.id]
                second = self.client.post(f"/v1/agent-runs/{run.id}/interrupt-decision", json=request)
                self.assertEqual(first.status_code, 200, first.text)
                self.assertEqual(second.status_code, 409, second.text)
                self.assertEqual(second.json()["code"], "interrupt_decision_pending")
                self.assertIs(harness._threads[run.id], owner)
            finally:
                release.set()
                worker = harness._threads.get(run.id)
                if worker is not None:
                    worker.join(timeout=10)
            self.assertFalse(worker.is_alive())
        self.assertEqual(harness.get_run(run.id).status, AgentRunStatus.failed)
        self.assertIsNone(harness._pending_decisions[run.id])

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
