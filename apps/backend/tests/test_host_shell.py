"""ENV-001/002: Windows host-shell policy and Deep Agents interrupt_on."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.harness_backend import host_shell_requested
from workbench_backend.agents.host_shell import (
    PERMISSION_DENY_PATHS,
    execute_requires_approval,
    filesystem_permissions_for_run,
    interrupt_on_for_run,
    is_dangerous_shell_command,
    pending_interrupt_from_raw,
    reject_decisions_for,
    validated_decision_payloads,
)
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, InterruptDecision, ToolMode
from workbench_backend.app import create_app
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, workbench_client
from tests.test_harness import wait_for_run


def wait_for_interrupt(client: TestClient, run_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/agent-runs/{run_id}")
        body = response.json()
        if body.get("pending_interrupt"):
            return body
        if body.get("status") in {"completed", "cancelled", "failed"}:
            raise TimeoutError(f"run finished without interrupt: {body}")
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not interrupt: {body}")


def wait_for_chat_interrupt(
    client: TestClient,
    conversation_id: str,
    *,
    timeout: float = 20.0,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/chat/conversations/{conversation_id}")
        body = response.json()
        run = body.get("current_run") or {}
        if run.get("pending_interrupt"):
            return body
        if run.get("status") in {"completed", "cancelled", "failed"}:
            raise TimeoutError(f"chat finished without interrupt: {body}")
        time.sleep(0.05)
    raise TimeoutError(f"chat {conversation_id} did not interrupt: {body}")


def execute_then_reply(command: str) -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "execute", "args": {"command": command}, "id": "call_exec"}],
        ),
        AIMessage(content="Host shell command finished."),
    ]


def _run(*, project_path: str | None, presented: list[str] | None = None) -> AgentRun:
    now = utc_now()
    return AgentRun(
        id="agent_host_shell",
        status=AgentRunStatus.queued,
        deployment_id="deploy_test",
        task="shell unit",
        enabled_tools=["echo"],
        presented_tools=presented or ["execute"],
        created_at=now,
        updated_at=now,
        project_path=project_path,
    )


class HostShellPolicyTests(unittest.TestCase):
    def test_dangerous_command_rules(self) -> None:
        self.assertTrue(is_dangerous_shell_command(""))
        self.assertTrue(is_dangerous_shell_command("rm -rf /tmp/x"))
        self.assertTrue(is_dangerous_shell_command("echo hi && rm -rf /"))
        self.assertTrue(is_dangerous_shell_command("git commit"))
        self.assertTrue(is_dangerous_shell_command(r"C:\Windows\System32\cmd.exe"))
        self.assertTrue(is_dangerous_shell_command("touch file"))
        self.assertFalse(is_dangerous_shell_command("echo host-shell-ok"))
        self.assertFalse(is_dangerous_shell_command("dir"))
        self.assertFalse(is_dangerous_shell_command("git status"))
        self.assertFalse(is_dangerous_shell_command("Get-ChildItem"))

    def test_execute_predicate_reads_command_arg(self) -> None:
        class _Req:
            tool_call = {"name": "execute", "args": {"command": "echo ok"}}

        self.assertFalse(execute_requires_approval(_Req()))  # type: ignore[arg-type]
        _Req.tool_call = {"name": "execute", "args": {"command": "rm -rf x"}}
        self.assertTrue(execute_requires_approval(_Req()))  # type: ignore[arg-type]

    def test_permissions_are_route_scoped_deny_only(self) -> None:
        live = filesystem_permissions_for_run(_run(project_path="/tmp/project"))
        self.assertIsNotNone(live)
        assert live is not None
        self.assertEqual(live[0].mode, "deny")
        self.assertEqual(list(live[0].paths), list(PERMISSION_DENY_PATHS))
        self.assertTrue(
            all(
                path.startswith("/large_tool_results/")
                or path.startswith("/conversation_history/")
                or path.startswith("/retrieved/")
                for path in live[0].paths
            )
        )
        recorded_run = _run(project_path="/tmp/project")
        recorded_run.tool_mode = ToolMode.recorded_tool
        self.assertIsNone(filesystem_permissions_for_run(recorded_run))
        self.assertIsNone(filesystem_permissions_for_run(_run(project_path=None)))
        echo_only = _run(project_path="/tmp/project", presented=["echo"])
        self.assertFalse(host_shell_requested(echo_only))
        self.assertIsNone(interrupt_on_for_run(echo_only))
        presented = _run(project_path="/tmp/project", presented=["execute"])
        self.assertTrue(host_shell_requested(presented))
        self.assertIsNotNone(interrupt_on_for_run(presented))

    def test_pending_interrupt_and_decisions(self) -> None:
        pending = pending_interrupt_from_raw(
            {
                "action_requests": [{"name": "execute", "args": {"command": "rm -rf x"}}],
                "review_configs": [
                    {"action_name": "execute", "allowed_decisions": ["approve", "reject"]}
                ],
            }
        )
        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertEqual(pending.action_requests[0].name, "execute")
        payloads = validated_decision_payloads(pending, [InterruptDecision(type="reject")])
        self.assertEqual(payloads[0]["type"], "reject")
        self.assertIn("rejected", payloads[0]["message"].lower())
        with self.assertRaises(ValueError):
            validated_decision_payloads(pending, [])
        rejects = reject_decisions_for(pending)
        self.assertEqual(len(rejects), 1)
        self.assertEqual(rejects[0]["type"], "reject")


class HostShellHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.manager = ModelManager(WorkbenchPaths(self.root).ensure())
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        self.scripted = ScriptedChatModel(execute_then_reply("touch host-shell-approved.txt"))

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
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "host-shell-fixture"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _install(self, script: list[AIMessage]) -> None:
        self.scripted = ScriptedChatModel(script)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )

    def _start(self, **extra: Any) -> dict[str, Any]:
        payload = {
            "deployment_id": self.deployment_id,
            "task": "Run a host-shell command.",
            "project_path": str(self.project),
            "presented_tools": ["execute"],
            **extra,
        }
        response = self.client.post("/v1/agent-runs", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_catalogue_and_project_gate(self) -> None:
        catalogue = self.client.get("/v1/agent-tools").json()["enabled"]
        self.assertIn("execute", catalogue)
        blocked = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "nope",
                "presented_tools": ["execute"],
            },
        )
        self.assertEqual(blocked.status_code, 400, blocked.text)
        self.assertEqual(blocked.json()["code"], "shell_requires_project")
        self.assertEqual(blocked.json()["tools"], ["execute"])

    def test_unpresented_execute_does_not_run_without_hitl(self) -> None:
        """Reviewer scenario: project + echo-only must not run a scripted touch."""

        marker = self.project / "bypass-no-hitl.txt"
        self._install(execute_then_reply("touch bypass-no-hitl.txt"))
        started = self._start(presented_tools=["echo"])
        self.assertFalse(started["host_shell"]["available"])
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertIsNone(body["pending_interrupt"])
        self.assertFalse(marker.exists())
        kinds = [event["kind"] for event in body["events"]]
        self.assertNotIn("interrupt", kinds)
        results = [event for event in body["events"] if event["kind"] == "tool_result"]
        self.assertTrue(results)
        content = str(results[0]["detail"].get("content") or "").lower()
        self.assertTrue("not presented" in content or "not executed" in content or "error" in content)

    def test_safe_execute_does_not_interrupt(self) -> None:
        self._install(execute_then_reply("echo host-shell-ok"))
        started = self._start()
        self.assertTrue(started["host_shell"]["available"])
        self.assertEqual(started["host_shell"]["cwd"], str(self.project.resolve()))
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertIsNone(body["pending_interrupt"])
        kinds = [event["kind"] for event in body["events"]]
        self.assertNotIn("interrupt", kinds)
        self.assertIn("tool_call", kinds)
        self.assertIn("tool_result", kinds)

    def test_dangerous_execute_approve_runs_command(self) -> None:
        started = self._start()
        paused = wait_for_interrupt(self.client, started["id"])
        self.assertEqual(paused["status"], "running")
        pending = paused["pending_interrupt"]
        self.assertEqual(pending["kind"], "deepagents_interrupt_on")
        self.assertEqual(pending["isolation"], "none")
        self.assertEqual(pending["action_requests"][0]["name"], "execute")
        kinds = [event["kind"] for event in paused["events"]]
        self.assertIn("interrupt", kinds)
        decided = self.client.post(
            f"/v1/agent-runs/{started['id']}/interrupt-decision",
            json={"decisions": [{"type": "approve"}]},
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertIsNone(body["pending_interrupt"])
        self.assertTrue((self.project / "host-shell-approved.txt").is_file())
        resolved = [event["kind"] for event in body["events"]]
        self.assertIn("interrupt_resolved", resolved)

    def test_dangerous_execute_deny_does_not_run(self) -> None:
        self._install(execute_then_reply("touch host-shell-denied.txt"))
        started = self._start()
        wait_for_interrupt(self.client, started["id"])
        decided = self.client.post(
            f"/v1/agent-runs/{started['id']}/interrupt-decision",
            json={"decisions": [{"type": "reject"}]},
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertFalse((self.project / "host-shell-denied.txt").exists())

    def test_cancel_while_interrupted_rejects_command(self) -> None:
        self._install(execute_then_reply("touch host-shell-cancelled.txt"))
        started = self._start()
        wait_for_interrupt(self.client, started["id"])
        cancelled = self.client.post(f"/v1/agent-runs/{started['id']}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "cancelled")
        self.assertFalse((self.project / "host-shell-cancelled.txt").exists())
        self.assertIsNone(body["pending_interrupt"])

    def test_decision_count_must_match(self) -> None:
        started = self._start()
        wait_for_interrupt(self.client, started["id"])
        bad = self.client.post(
            f"/v1/agent-runs/{started['id']}/interrupt-decision",
            json={"decisions": []},
        )
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertEqual(bad.json()["code"], "interrupt_decision_count")
        self.client.post(
            f"/v1/agent-runs/{started['id']}/interrupt-decision",
            json={"decisions": [{"type": "reject"}]},
        )
        wait_for_run(self.client, started["id"])

    def test_chat_interrupt_and_shell_flag(self) -> None:
        self._install(execute_then_reply("touch chat-host-shell.txt"))
        created = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id, "project_path": str(self.project)},
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertTrue(created.json()["shell_tools_available"])
        started = self.client.post(
            f"/v1/chat/conversations/{created.json()['id']}/start",
            json={"task": "Run a host-shell command.", "presented_tools": ["execute"]},
        )
        self.assertEqual(started.status_code, 200, started.text)
        self.assertTrue(started.json()["current_run"]["host_shell"]["available"])
        paused = wait_for_chat_interrupt(self.client, created.json()["id"])
        decided = self.client.post(
            f"/v1/chat/conversations/{created.json()['id']}/interrupt-decision",
            json={"decisions": [{"type": "approve"}]},
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        deadline = time.time() + 20
        body = paused
        while time.time() < deadline:
            body = self.client.get(f"/v1/chat/conversations/{created.json()['id']}").json()
            if (body.get("current_run") or {}).get("status") in {"completed", "cancelled", "failed"}:
                break
            time.sleep(0.05)
        self.assertEqual(body["current_run"]["status"], "completed", body["current_run"].get("error"))
        self.assertTrue((self.project / "chat-host-shell.txt").is_file())

    def test_chat_shell_without_project_is_rejected(self) -> None:
        created = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id},
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertFalse(created.json()["shell_tools_available"])
        response = self.client.post(
            f"/v1/chat/conversations/{created.json()['id']}/start",
            json={"task": "Run a command.", "presented_tools": ["execute"]},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["code"], "shell_requires_project")


if __name__ == "__main__":
    unittest.main()
