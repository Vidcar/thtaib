"""Embedded harness API: AGT-001/002/005/006 plus honour AGT-003/004."""

from __future__ import annotations

import asyncio
import http.server
import os
import socketserver
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

import httpx
from langgraph.checkpoint.base import empty_checkpoint
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService, _graph_checkpoint_snapshot
from workbench_backend.agents.schemas import (
    AgentEvent,
    AgentRun,
    AgentRunStatus,
    GenerationObservation,
    PendingInterrupt,
    PendingInterruptAction,
)
from workbench_backend.app import create_app
from workbench_backend.errors import HarnessError, InteractionPersistenceError
from workbench_backend.inference.capabilities import setup_fingerprint
from workbench_backend.inference.adapter import RecordingTransport
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.lab.snapshot import capture_project_snapshot
from workbench_backend.inference.schemas import ServerProperties
from workbench_backend.state.checkpointer import open_sqlite_checkpointer

from tests.scripted_model import ScriptedChatModel, set_generate_hold, wait_for_generate_hold
from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run, wait_for_status


class _ThreadingHttpServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _RecordingModel(ScriptedChatModel):
    """Records the tool names bound for each model call, including copies."""

    offered: ClassVar[list[list[str]]] = []

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        names: list[str] = []
        for tool in tools:
            name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)
            if isinstance(name, str):
                names.append(name)
        type(self).offered.append(names)
        return super().bind_tools(tools, **kwargs)


class _UnprofiledModel(ScriptedChatModel):
    offered: ClassVar[list[list[str]]] = []

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        names: list[str] = []
        for tool in tools:
            name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)
            if isinstance(name, str):
                names.append(name)
        type(self).offered.append(names)
        return super().bind_tools(tools, **kwargs)

    def _get_ls_params(self, stop=None, **kwargs):  # type: ignore[override]
        params = super()._get_ls_params(stop=stop, **kwargs)
        params["ls_provider"] = "workbench-unprofiled"
        return params


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
        from workbench_backend.agents.tools import ENABLED_TOOLS, project_mutation_tools
        self.assertFalse(set(ENABLED_TOOLS) & {"ls", "read_file", "write_file", "edit_file", "glob", "grep", "delete", "task"})
        mutations = [tool.name for tool in project_mutation_tools(str(project))]
        self.assertEqual(mutations, ["rename_file", "delete_file"])

    def test_ordinary_chat_does_not_offer_task_or_recursive_delete(self) -> None:
        from deepagents import create_deep_agent
        from deepagents.backends import FilesystemBackend
        from workbench_backend.agents.harness_profile import ensure_ordinary_chat_profile
        from workbench_backend.agents.tools import project_mutation_tools

        project = self.root / "offered-tools"
        project.mkdir()
        (project / "note.txt").write_text("hello\n", encoding="utf-8")
        _RecordingModel.offered.clear()
        model = _RecordingModel([
            AIMessage(content="", tool_calls=[{"name": "task", "args": {"description": "Read note.txt", "subagent_type": "helper"}, "id": "task-1"}]),
            AIMessage(content="helper finished"),
            AIMessage(content="parent finished"),
        ])
        unprofiled = _UnprofiledModel([AIMessage(content="defaults")])
        _UnprofiledModel.offered.clear()
        defaults = create_deep_agent(model=unprofiled, system_prompt="defaults")
        defaults.invoke({"messages": [{"role": "user", "content": "hi"}]})
        default_names = set().union(*_UnprofiledModel.offered)
        self.assertIn("task", default_names)
        self.assertIn("delete", default_names)

        ensure_ordinary_chat_profile(model)
        child_agent = create_deep_agent(
            model=model,
            tools=project_mutation_tools(str(project)),
            system_prompt="parent",
            backend=FilesystemBackend(root_dir=str(project), virtual_mode=True),
            subagents=[{
                "name": "helper",
                "description": "Reads one project file.",
                "system_prompt": "Report the file.",
                "model": model,
            }],
        )
        child_agent.invoke({"messages": [{"role": "user", "content": "look"}]})
        self.assertTrue(_RecordingModel.offered, "the model should be offered a tool list")
        child_offers = [names for names in _RecordingModel.offered if "task" not in names]
        self.assertTrue(child_offers, "a compiled child should be offered tools without the task tool")
        for names in child_offers:
            self.assertNotIn("delete", names)
            self.assertNotIn("task", names)
            self.assertIn("read_file", names)
        self.assertIn("delete_file", set().union(*_RecordingModel.offered))

        _RecordingModel.offered.clear()
        self.scripted = _RecordingModel([AIMessage(content="ordinary chat")])
        started = self._start(project_path=str(project), task="Say hello.")
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertTrue(_RecordingModel.offered)
        for names in _RecordingModel.offered:
            self.assertNotIn("task", names)
            self.assertNotIn("delete", names)
        offered = set().union(*_RecordingModel.offered)
        self.assertIn("read_file", offered)
        self.assertIn("delete_file", offered)
        self.assertNotIn("task", [item["name"] for item in body["tool_invocations"]])

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
        self.assertIsNone(judgement["model_review"])
        self.assertEqual(judgement["source"], "not_requested")
        self.assertNotEqual(evidence, judgement)
        self.assertIn("no independent review", judgement["note"].lower())

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

    def test_final_snapshot_does_not_hold_harness_lock_and_stop_is_too_late(self) -> None:
        harness = self.app.state.harness
        harness._reconcile_startup_once()
        project = self.root / "finalizing-project"
        project.mkdir()
        now = utc_now()
        run = AgentRun(id="agent_finalizing_lock", status=AgentRunStatus.running,
            deployment_id=self.deployment_id, task="finished graph", enabled_tools=[], presented_tools=[],
            created_at=now, updated_at=now, project_path=str(project))
        with harness._lock:
            harness._runs[run.id] = run
            harness._cancels[run.id] = threading.Event()
            harness.store.put_run(run)

        entered = threading.Event()
        release = threading.Event()
        read_done = threading.Event()
        read_result: dict[str, object] = {}

        def capture(*args, **kwargs):
            entered.set()
            if not release.wait(timeout=5):
                raise TimeoutError("snapshot gate was not released")
            return type("Captured", (), {"id": "snap_finalizing_test"})()

        worker = threading.Thread(target=harness._finish, args=(run, AgentRunStatus.completed, "completed"))
        reader = threading.Thread(target=lambda: (read_result.update(harness.projection_run(run.id)), read_done.set()))
        with patch("workbench_backend.agents.harness.capture_project_snapshot", side_effect=capture):
            worker.start()
            try:
                self.assertTrue(entered.wait(timeout=5))
                reader.start()
                self.assertTrue(read_done.wait(timeout=1), "A snapshot held the harness lock")
                self.assertEqual(read_result["finalization_phase"], "saving_changes")
                self.assertEqual(read_result["status"], "running")
                with self.assertRaises(HarnessError) as ctx:
                    harness.cancel(run.id)
                self.assertEqual(ctx.exception.code, "run_finalizing")
            finally:
                release.set()
                worker.join(timeout=5)
                if reader.is_alive():
                    reader.join(timeout=5)
        self.assertFalse(worker.is_alive())
        finished = harness.get_run(run.id)
        self.assertEqual(finished.status, AgentRunStatus.completed)
        self.assertEqual(finished.final_snapshot_id, "snap_finalizing_test")
        self.assertIsNone(finished.finalization_phase)
        self.assertEqual([event.kind for event in finished.events].count("completed"), 1)

    def test_restart_finishes_settled_snapshot_without_replaying_graph(self) -> None:
        project = self.root / "recovered-finalizing-project"
        project.mkdir()
        (project / "created.txt").write_text("retained", encoding="utf-8")
        now = utc_now()
        outcomes = [
            ("completed", AgentRunStatus.running),
            ("cancelled", AgentRunStatus.cancel_requested),
            ("failed", AgentRunStatus.running),
        ]
        for outcome, live_status in outcomes:
            snapshot_id = new_id("snap")
            capture_project_snapshot(self.manager.paths, workspace_id="unbound",
                project_root=project, kind="final", snapshot_id=snapshot_id)
            run = AgentRun(id=f"agent_recover_finalizing_{outcome}", status=live_status,
                deployment_id=self.deployment_id, task="graph already settled", enabled_tools=[], presented_tools=[],
                created_at=now, updated_at=now, project_path=str(project), finalization_phase="saving_changes",
                settled_status=outcome, settled_stop_reason=outcome,
                events=[AgentEvent(at=now, kind="finalizing",
                    detail={"phase": "saving_changes", "execution_settled": True, "snapshot_id": snapshot_id})],
                error="original execution failure" if outcome == "failed" else None)
            self.app.state.harness.store.put_run(run)

        (project / "created.txt").write_text("later edit", encoding="utf-8")

        restarted = self._restart_harness()
        for outcome, _live_status in outcomes:
            with self.subTest(outcome=outcome):
                recovered = restarted.get_run(f"agent_recover_finalizing_{outcome}")
                self.assertEqual(recovered.status.value, outcome)
                self.assertEqual(recovered.stop_reason, outcome)
                self.assertEqual(recovered.error, "original execution failure" if outcome == "failed" else None)
                self.assertIsNone(recovered.finalization_phase)
                self.assertTrue(recovered.final_snapshot_id)
                self.assertEqual((self.manager.paths.snapshots / recovered.final_snapshot_id / "tree" / "created.txt").read_text(encoding="utf-8"), "retained")
                self.assertEqual([event.kind for event in recovered.events].count(outcome), 1)

    def test_restart_does_not_recapture_project_after_interrupted_snapshot(self) -> None:
        project = self.root / "interrupted-finalizing-project"
        project.mkdir()
        (project / "created.txt").write_text("later edit", encoding="utf-8")
        now = utc_now()
        snapshot_id = new_id("snap")
        staging = self.manager.paths.snapshots / f".{snapshot_id}.staging"
        staging.mkdir(parents=True)
        (staging / "incomplete.txt").write_text("partial", encoding="utf-8")
        run = AgentRun(id="agent_interrupted_finalizing", status=AgentRunStatus.running,
            deployment_id=self.deployment_id, task="graph already settled", enabled_tools=[], presented_tools=[],
            created_at=now, updated_at=now, project_path=str(project), finalization_phase="saving_changes",
            settled_status="completed", settled_stop_reason="completed",
            events=[AgentEvent(at=now, kind="finalizing",
                detail={"phase": "saving_changes", "execution_settled": True, "snapshot_id": snapshot_id})])
        self.app.state.harness.store.put_run(run)

        restarted = self._restart_harness()
        recovered = restarted.get_run(run.id)
        self.assertEqual(recovered.status, AgentRunStatus.completed)
        self.assertIsNone(recovered.final_snapshot_id)
        self.assertEqual([event.kind for event in recovered.events],
            ["finalizing", "branch_snapshot_unavailable", "completed"])
        self.assertFalse(staging.exists())

    def test_failed_terminal_persistence_retries_saved_settlement_once(self) -> None:
        harness = self.app.state.harness
        harness._reconcile_startup_once()
        project = self.root / "retry-finalizing-project"
        project.mkdir()
        (project / "created.txt").write_text("retained", encoding="utf-8")
        now = utc_now()
        run = AgentRun(id="agent_retry_finalizing", status=AgentRunStatus.running,
            deployment_id=self.deployment_id, task="graph already settled", enabled_tools=[], presented_tools=[],
            created_at=now, updated_at=now, project_path=str(project))
        with harness._lock:
            harness._runs[run.id] = run
            harness.store.put_run(run)
        original_put = harness.store.put_run
        failed = False

        def fail_terminal_once(record):
            nonlocal failed
            if record.id == run.id and record.status == AgentRunStatus.completed and not failed:
                failed = True
                raise OSError("temporary terminal persistence failure")
            return original_put(record)

        with patch.object(harness.store, "put_run", side_effect=fail_terminal_once):
            with self.assertRaisesRegex(OSError, "temporary terminal persistence failure"):
                harness._finish(run, AgentRunStatus.completed, "completed")
        saved = harness.store.get_run(run.id)
        self.assertEqual(saved.finalization_phase, "saving_changes")
        self.assertEqual(saved.settled_status, "completed")
        recovered = harness.get_run(run.id)
        self.assertEqual(recovered.status, AgentRunStatus.completed)
        self.assertIsNone(recovered.finalization_phase)
        self.assertTrue(recovered.final_snapshot_id)
        self.assertEqual([event.kind for event in recovered.events].count("completed"), 1)

    def test_restart_rejects_changed_published_final_snapshot(self) -> None:
        project = self.root / "changed-final-snapshot-project"
        project.mkdir()
        (project / "saved.txt").write_text("original", encoding="utf-8")
        snapshot_id = new_id("snap")
        capture_project_snapshot(self.manager.paths, workspace_id="unbound",
            project_root=project, kind="final", snapshot_id=snapshot_id)
        (self.manager.paths.snapshots / snapshot_id / "tree" / "saved.txt").write_text("changed", encoding="utf-8")
        now = utc_now()
        run = AgentRun(id="agent_corrupt_final_snapshot", status=AgentRunStatus.running,
            deployment_id=self.deployment_id, task="graph already settled", enabled_tools=[], presented_tools=[],
            created_at=now, updated_at=now, project_path=str(project), finalization_phase="saving_changes",
            settled_status="completed", settled_stop_reason="completed",
            events=[AgentEvent(at=now, kind="finalizing",
                detail={"phase": "saving_changes", "execution_settled": True, "snapshot_id": snapshot_id})])
        self.app.state.harness.store.put_run(run)

        recovered = self._restart_harness().get_run(run.id)
        self.assertEqual(recovered.status, AgentRunStatus.completed)
        self.assertIsNone(recovered.final_snapshot_id)
        self.assertEqual([event.kind for event in recovered.events],
            ["finalizing", "branch_snapshot_unavailable", "completed"])

    def test_snapshot_failure_keeps_settled_execution_outcome_and_blocks_branch(self) -> None:
        harness = self.app.state.harness
        harness._reconcile_startup_once()
        project = self.root / "failed-snapshot-project"
        project.mkdir()
        now = utc_now()
        run = AgentRun(id="agent_snapshot_failure", status=AgentRunStatus.running,
            deployment_id=self.deployment_id, task="completed graph", enabled_tools=[], presented_tools=[],
            created_at=now, updated_at=now, project_path=str(project))
        with harness._lock:
            harness._runs[run.id] = run
            harness.store.put_run(run)
        with patch("workbench_backend.agents.harness.capture_project_snapshot", side_effect=OSError("source changed")):
            harness._finish(run, AgentRunStatus.completed, "completed")
        observed = harness.get_run(run.id)
        self.assertEqual(observed.status, AgentRunStatus.completed)
        self.assertIsNone(observed.final_snapshot_id)
        self.assertIsNone(observed.finalization_phase)
        self.assertEqual([event.kind for event in observed.events], ["finalizing", "branch_snapshot_unavailable", "completed"])
        self.assertEqual(harness.store.get_run(run.id).status, AgentRunStatus.completed)

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

    def test_follow_up_links_only_checkpoints_created_after_pre_run_head(self) -> None:
        thread_id = "conversation_checkpoint_boundary"
        prior = self._put_checkpoint(thread_id)
        self.scripted = ScriptedChatModel([AIMessage(content="A new reply.")])

        started = self._start(thread_id=thread_id, task="Reply briefly.", presented_tools=[])
        finished = wait_for_run(self.client, started["id"])

        self.assertEqual(finished["status"], "completed")
        self.assertEqual(finished["pre_run_checkpoint_id"], prior)
        self.assertTrue(finished["checkpoint_ids"])
        self.assertNotIn(prior, finished["checkpoint_ids"])

    def test_missing_checkpoint_anchor_fails_linkage_explicitly(self) -> None:
        harness = self.app.state.harness
        now = utc_now()
        run = AgentRun(id="agent_missing_checkpoint_anchor", status=AgentRunStatus.running,
            deployment_id=self.deployment_id, task="link new checkpoints", enabled_tools=[], presented_tools=[],
            created_at=now, updated_at=now, thread_id="missing_anchor_thread",
            pre_run_checkpoint_id="checkpoint_that_disappeared")

        class Graph:
            async def aget_state_history(self, _config, *, before=None, limit=None):
                if False:
                    yield None

        with self.assertRaises(HarnessError) as raised:
            asyncio.run(harness._alink_new_checkpoints(run, Graph()))
        self.assertEqual(raised.exception.code, "checkpoint_linkage_failed")
        self.assertEqual(run.checkpoint_ids, [])
        self.assertEqual(run.events[-1].kind, "checkpoint_linkage_failed")

    def test_native_interaction_failure_stops_consumption_and_keeps_model_errors_distinct(self) -> None:
        harness = self.app.state.harness
        now = utc_now()
        consumed: list[int] = []

        class Graph:
            async def astream_events(self, _payload, **_kwargs):
                async def events():
                    for number in (1, 2):
                        consumed.append(number)
                        yield {"method": "messages", "params": {"namespace": [], "data": {"event": "message-start"}}}
                return events()

        run = AgentRun(id="agent_interaction_failed", status=AgentRunStatus.running,
            deployment_id=self.deployment_id, task="observe", enabled_tools=[], presented_tools=[],
            created_at=now, updated_at=now, thread_id="agent_interaction_failed")
        harness._interaction_observer = lambda _run, _event: (_ for _ in ()).throw(InteractionPersistenceError())
        with self.assertRaises(HarnessError) as raised:
            asyncio.run(harness._stream_until_pause(Graph(), run, {}, threading.Event(),
                {"configurable": {"thread_id": run.thread_id}}, set(), {}))
        self.assertEqual(raised.exception.code, "interaction_persistence_failed")
        self.assertEqual(consumed, [1])
        self.assertEqual(run.events[-1].kind, "interaction_persistence_failed")

        class BrokenModel:
            async def astream_events(self, _payload, **_kwargs):
                async def events():
                    raise ValueError("model stream failed")
                    yield None
                return events()

        harness._interaction_observer = None
        with self.assertRaisesRegex(ValueError, "model stream failed"):
            asyncio.run(harness._stream_until_pause(BrokenModel(), run, {}, threading.Event(),
                {"configurable": {"thread_id": run.thread_id}}, set(), {}))

    def test_essential_interaction_failure_finishes_run_with_distinct_reason(self) -> None:
        harness = self.app.state.harness

        def fail_native(_run, event):
            if event is not None:
                raise InteractionPersistenceError()

        harness._interaction_observer = fail_native
        started = self._start(presented_tools=[])
        finished = wait_for_run(self.client, started["id"])
        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["stop_reason"], "interaction_persistence_failed")
        self.assertEqual([event["kind"] for event in finished["events"]].count("failed"), 1)
        self.assertEqual(finished["events"][-1]["detail"]["code"], "interaction_persistence_failed")

    def test_native_audit_persistence_failure_stops_before_next_event(self) -> None:
        harness = self.app.state.harness
        now = utc_now()
        consumed: list[int] = []
        run = AgentRun(id="agent_audit_failed", status=AgentRunStatus.running,
            deployment_id=self.deployment_id, task="audit", enabled_tools=[], presented_tools=[],
            created_at=now, updated_at=now, thread_id="agent_audit_failed")

        class Graph:
            async def astream_events(self, _payload, **_kwargs):
                async def events():
                    for number in (1, 2):
                        consumed.append(number)
                        yield {"method": "values", "params": {"namespace": [],
                            "data": {"messages": [AIMessage(id=f"message_{number}", content="reply")]}}}
                return events()

        with patch.object(harness, "_persist_and_notify", side_effect=OSError("audit SQLite unavailable")):
            with self.assertRaises(HarnessError) as raised:
                asyncio.run(harness._stream_until_pause(Graph(), run, {}, threading.Event(),
                    {"configurable": {"thread_id": run.thread_id}}, set(), {}))
        self.assertEqual(raised.exception.code, "interaction_persistence_failed")
        self.assertEqual(consumed, [1])
        self.assertEqual(run.events[-1].kind, "interaction_persistence_failed")

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
