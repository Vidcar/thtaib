"""ENV-001/002: Windows host-shell policy and Deep Agents interrupt_on."""

from __future__ import annotations

import tempfile
import time
import unittest
import os
import subprocess
import threading
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
from workbench_backend.chat.schemas import ChatMessage
from workbench_backend.inference.ids import utc_now

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client
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


def wait_for_interrupt_command(
    client: TestClient,
    run_id: str,
    command: str,
    *,
    timeout: float = 20.0,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/agent-runs/{run_id}")
        body = response.json()
        pending = body.get("pending_interrupt") or {}
        action_requests = pending.get("action_requests") or []
        if action_requests and action_requests[0].get("args", {}).get("command") == command:
            return body
        if body.get("status") in {"completed", "cancelled", "failed"}:
            raise TimeoutError(f"run finished before interrupt {command}: {body}")
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not reach interrupt {command}: {body}")


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


def direct_interrupt_decision(pending: dict[str, Any], decision: str) -> dict[str, Any]:
    return {
        "interrupt_id": pending["interrupt_id"],
        "namespace": pending.get("namespace", []),
        "decisions": [{"type": decision}],
    }


def run_direct_interrupt_decision(paused_run: dict[str, Any], decision: str) -> dict[str, Any]:
    return direct_interrupt_decision(paused_run["pending_interrupt"], decision)


def chat_direct_interrupt_decision(paused_view: dict[str, Any], decision: str) -> dict[str, Any]:
    return direct_interrupt_decision(paused_view["current_run"]["pending_interrupt"], decision)


def execute_then_reply(command: str) -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "execute", "args": {"command": command}, "id": "call_exec"}],
        ),
        AIMessage(content="Host shell command finished."),
    ]


def execute_two_then_reply(first: str, second: str) -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "execute", "args": {"command": first}, "id": "call_exec_a"}],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "execute", "args": {"command": second}, "id": "call_exec_b"}],
        ),
        AIMessage(content="Both host shell commands were considered."),
    ]


def write_marker_command(filename: str) -> str:
    """Use a platform-native write so approval tests prove execution, not PATH."""

    if os.name != "nt":
        return f"touch {filename}"
    return f"cmd /c type nul > {filename}"


def append_marker_command(filename: str) -> str:
    """Append one line so restart approval tests can assert exact execution count."""

    if os.name != "nt":
        return f"sh -c 'echo hit >> {filename}'"
    return f"cmd /c echo hit>> {filename}"


def tool_result_text(body: dict[str, Any]) -> str:
    results = [event for event in body["events"] if event["kind"] == "tool_result"]
    if not results:
        return ""
    return str(results[-1]["detail"].get("content") or "")


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
        cases = {
            "": True,
            "rm -rf /tmp/x": True,
            "echo hi && rm -rf /": True,
            "git commit": True,
            r"C:\Windows\System32\cmd.exe": True,
            "touch file": True,
            "git branch -D doomed": True,
            "git branch -m old new": True,
            "git diff --output=out.patch": True,
            "git diff --output out.patch": True,
            'git diff --no-ext-diff --no-textconv "--output=out.patch"': True,
            "git diff --no-ext-diff --no-textconv '--output=out.patch'": True,
            "git diff --no-ext-diff --no-textconv *": True,
            "git DIFF --no-ext-diff --no-textconv": True,
            "Git status": True,
            "git diff --ext-diff": True,
            "git diff -- README.md": True,
            "git show --stat": True,
            "echo %USERNAME%": True,
            "echo !USERNAME!": True,
            "echo ^& whoami": True,
            "echo (hello)": True,
            "echo hello\rwhoami": True,
            "echo /?": True,
            "dir /s": True,
            "dir --all": True,
            "ls --all": True,
            "Get-ChildItem -Recurse": True,
            "type /?": True,
            "type ..\\secret.txt": True,
            "Get-Content -Raw file.txt": True,
            "where /r . cmd.exe": True,
            "which --all python": True,
            "whoami /priv": True,
            "pwd extra": True,
            "Get-Help -Full": True,
            "git status --short": False,
            "git log --oneline -n 3": False,
            "git branch --show-current": False,
            "git diff --no-ext-diff --no-textconv -- README.md": False,
            "git show --no-ext-diff --no-textconv --stat": False,
            "git rev-parse --show-toplevel": False,
            "echo host-shell-ok": False,
            "echo off": False,
            "dir": False,
            "dir README.md": False,
            "ls README.md": False,
            "type README.md": False,
            "where python": False,
            "which python": False,
            "Get-Help Get-ChildItem": True,
            "Get-ChildItem": True,
        }
        for command, dangerous in cases.items():
            with self.subTest(command=command):
                self.assertEqual(is_dangerous_shell_command(command), dangerous)

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
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.scripted = ScriptedChatModel(
            execute_then_reply(write_marker_command("host-shell-approved.txt"))
        )

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

    def _restart_from_interrupt(self, command: str) -> tuple[dict[str, Any], HarnessService]:
        self._install(execute_then_reply(command))
        return self._restart_from_script()

    def _restart_from_script(
        self,
        *,
        stop_original_worker: bool = False,
    ) -> tuple[dict[str, Any], HarnessService]:
        started = self._start()
        paused = wait_for_interrupt(self.client, started["id"])
        self.assertTrue(paused["checkpoint_ids"], paused)
        old_harness = self.app.state.harness
        if stop_original_worker:
            self._stop_old_waiting_harness_without_store_write(old_harness, started["id"])

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        restarted = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        self.app.state.harness = restarted
        observed = self.client.get(f"/v1/agent-runs/{started['id']}").json()
        self.assertEqual(observed["status"], "running", observed)
        self.assertIsNotNone(observed["pending_interrupt"])
        return started, old_harness

    def _retire_old_waiting_harness(self, old_harness: HarnessService, run_id: str) -> None:
        with old_harness._lock:
            old_run = old_harness._runs.get(run_id)
            if old_run is not None:
                old_run.status = AgentRunStatus.completed
                old_run.pending_interrupt = None
                old_run.finished_at = old_run.finished_at or utc_now()
            ready = old_harness._decision_ready.get(run_id)
            cancel = old_harness._cancels.get(run_id)
            if cancel is not None:
                cancel.set()
            if ready is not None:
                ready.set()
        thread = old_harness._threads.get(run_id)
        if thread is not None:
            thread.join(timeout=5.0)

    def _stop_old_waiting_harness_without_store_write(
        self,
        old_harness: HarnessService,
        run_id: str,
    ) -> None:
        def skip_persist(_run: AgentRun) -> None:
            return None

        def skip_resume_reject(*_args: Any, **_kwargs: Any) -> None:
            return None

        old_harness._persist_and_notify = skip_persist  # type: ignore[method-assign]
        old_harness._resume_reject_then_stop = skip_resume_reject  # type: ignore[method-assign]
        self._retire_old_waiting_harness(old_harness, run_id)
        thread = old_harness._threads.get(run_id)
        self.assertTrue(thread is None or not thread.is_alive())

    def _marker_lines(self, marker: Path) -> list[str]:
        if not marker.exists():
            return []
        return marker.read_text(encoding="utf-8").splitlines()

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
        self._install(execute_then_reply(write_marker_command("bypass-no-hitl.txt")))
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
        stale = self.client.post(
            f"/v1/agent-runs/{started['id']}/interrupt-decision",
            json={
                "interrupt_id": f"{pending['interrupt_id']}-old",
                "namespace": pending.get("namespace", []),
                "decisions": [{"type": "approve"}],
            },
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["code"], "stale_interrupt")
        decided = self.client.post(
            f"/v1/agent-runs/{started['id']}/interrupt-decision",
            json=run_direct_interrupt_decision(paused, "approve"),
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertIsNone(body["pending_interrupt"])
        self.assertTrue((self.project / "host-shell-approved.txt").is_file())
        content = tool_result_text(body).lower()
        self.assertNotIn("not recognized", content)
        self.assertNotIn("error", content)
        resolved = [event["kind"] for event in body["events"]]
        self.assertIn("interrupt_resolved", resolved)

    def test_dangerous_execute_deny_does_not_run(self) -> None:
        self._install(execute_then_reply(write_marker_command("host-shell-denied.txt")))
        started = self._start()
        paused = wait_for_interrupt(self.client, started["id"])
        decided = self.client.post(
            f"/v1/agent-runs/{started['id']}/interrupt-decision",
            json=run_direct_interrupt_decision(paused, "reject"),
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertFalse((self.project / "host-shell-denied.txt").exists())

    def test_disposable_git_mutation_pauses_rejects_then_approves_once(self) -> None:
        subprocess.run(["git", "init"], cwd=self.project, check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=self.project,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Workbench Test"],
            cwd=self.project,
            check=True,
            capture_output=True,
            text=True,
        )
        (self.project / "tracked.txt").write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.project, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=self.project, check=True, capture_output=True, text=True)
        subprocess.run(["git", "branch", "doomed"], cwd=self.project, check=True, capture_output=True, text=True)

        self._install(execute_then_reply("git branch -D doomed"))
        rejected = self._start()
        rejected_pause = wait_for_interrupt(self.client, rejected["id"])
        response = self.client.post(
            f"/v1/agent-runs/{rejected['id']}/interrupt-decision",
            json=run_direct_interrupt_decision(rejected_pause, "reject"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        rejected_body = wait_for_run(self.client, rejected["id"])
        self.assertEqual(rejected_body["status"], "completed", rejected_body.get("error"))
        branches_after_reject = subprocess.run(
            ["git", "branch", "--list", "doomed"],
            cwd=self.project,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("doomed", branches_after_reject.stdout)

        self._install(execute_then_reply("git branch -D doomed"))
        approved = self._start()
        approved_pause = wait_for_interrupt(self.client, approved["id"])
        results: list[int] = []

        def approve() -> None:
            result = self.client.post(
                f"/v1/agent-runs/{approved['id']}/interrupt-decision",
                json=run_direct_interrupt_decision(approved_pause, "approve"),
            )
            results.append(result.status_code)

        threads = [threading.Thread(target=approve), threading.Thread(target=approve)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [200, 409])
        approved_body = wait_for_run(self.client, approved["id"])
        self.assertEqual(approved_body["status"], "completed", approved_body.get("error"))
        branches_after_approve = subprocess.run(
            ["git", "branch", "--list", "doomed"],
            cwd=self.project,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertNotIn("doomed", branches_after_approve.stdout)

    def test_restart_pending_approval_can_reject_without_running_command(self) -> None:
        marker = self.project / "restart-reject.txt"
        started, old_harness = self._restart_from_interrupt(
            write_marker_command("restart-reject.txt")
        )
        try:
            paused = self.client.get(f"/v1/agent-runs/{started['id']}").json()
            response = self.client.post(
                f"/v1/agent-runs/{started['id']}/interrupt-decision",
                json=run_direct_interrupt_decision(paused, "reject"),
            )
            self.assertEqual(response.status_code, 200, response.text)
            body = wait_for_run(self.client, started["id"])
            self.assertEqual(body["status"], "completed", body.get("error"))
            self.assertFalse(marker.exists())
        finally:
            self._retire_old_waiting_harness(old_harness, started["id"])

    def test_restart_pending_approval_can_approve_once(self) -> None:
        marker = self.project / "restart-approve.txt"
        started, old_harness = self._restart_from_interrupt(
            write_marker_command("restart-approve.txt")
        )
        try:
            paused = self.client.get(f"/v1/agent-runs/{started['id']}").json()
            response = self.client.post(
                f"/v1/agent-runs/{started['id']}/interrupt-decision",
                json=run_direct_interrupt_decision(paused, "approve"),
            )
            self.assertEqual(response.status_code, 200, response.text)
            body = wait_for_run(self.client, started["id"])
            self.assertEqual(body["status"], "completed", body.get("error"))
            self.assertTrue(marker.exists())
        finally:
            self._retire_old_waiting_harness(old_harness, started["id"])

    def test_restart_resume_releases_reservation_for_next_interrupt_decision(self) -> None:
        for second_action in ("approve", "reject", "cancel", "race"):
            with self.subTest(second_action=second_action):
                first_marker = self.project / f"restart-a-{second_action}.txt"
                second_marker = self.project / f"restart-b-{second_action}.txt"
                second_command = append_marker_command(second_marker.name)
                self._install(
                    execute_two_then_reply(
                        append_marker_command(first_marker.name),
                        second_command,
                    )
                )
                started, old_harness = self._restart_from_script(stop_original_worker=True)

                first_pause = self.client.get(f"/v1/agent-runs/{started['id']}").json()
                first_response = self.client.post(
                    f"/v1/agent-runs/{started['id']}/interrupt-decision",
                    json=run_direct_interrupt_decision(first_pause, "approve"),
                )
                self.assertEqual(first_response.status_code, 200, first_response.text)
                second_pause = wait_for_interrupt_command(
                    self.client,
                    started["id"],
                    second_command,
                )
                self.assertEqual(second_pause["status"], "running", second_pause)
                self.assertEqual(
                    second_pause["pending_interrupt"]["action_requests"][0]["args"]["command"],
                    second_command,
                )

                if second_action == "cancel":
                    cancelled = self.client.post(f"/v1/agent-runs/{started['id']}/cancel")
                    self.assertEqual(cancelled.status_code, 200, cancelled.text)
                    body = wait_for_run(self.client, started["id"])
                    self.assertEqual(body["status"], "cancelled", body.get("error"))
                elif second_action == "race":
                    barrier = threading.Barrier(2)
                    results: list[int] = []

                    def approve() -> None:
                        barrier.wait(timeout=5.0)
                        response = self.client.post(
                            f"/v1/agent-runs/{started['id']}/interrupt-decision",
                            json=run_direct_interrupt_decision(second_pause, "approve"),
                        )
                        results.append(response.status_code)

                    threads = [threading.Thread(target=approve), threading.Thread(target=approve)]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join(timeout=10)
                        self.assertFalse(thread.is_alive())
                    self.assertEqual(sorted(results), [200, 409])
                    body = wait_for_run(self.client, started["id"])
                    self.assertEqual(body["status"], "completed", body.get("error"))
                else:
                    second_response = self.client.post(
                        f"/v1/agent-runs/{started['id']}/interrupt-decision",
                        json=run_direct_interrupt_decision(second_pause, second_action),
                    )
                    self.assertEqual(second_response.status_code, 200, second_response.text)
                    body = wait_for_run(self.client, started["id"])
                    self.assertEqual(body["status"], "completed", body.get("error"))

                self.assertEqual(self._marker_lines(first_marker), ["hit"])
                if second_action in {"approve", "race"}:
                    self.assertEqual(self._marker_lines(second_marker), ["hit"])
                else:
                    self.assertEqual(self._marker_lines(second_marker), [])
                resolved = [event for event in body["events"] if event["kind"] == "interrupt_resolved"]
                self.assertEqual(len(resolved), 2)
                self.assertIsNone(self.app.state.harness._pending_decisions[started["id"]])

    def test_restart_pending_approval_cancel_rejects_without_running_command(self) -> None:
        marker = self.project / "restart-cancel.txt"
        started, old_harness = self._restart_from_interrupt(
            write_marker_command("restart-cancel.txt")
        )
        try:
            response = self.client.post(f"/v1/agent-runs/{started['id']}/cancel")
            self.assertEqual(response.status_code, 200, response.text)
            body = wait_for_run(self.client, started["id"])
            self.assertEqual(body["status"], "cancelled", body.get("error"))
            self.assertFalse(marker.exists())
        finally:
            self._retire_old_waiting_harness(old_harness, started["id"])

    def test_restart_two_resume_decisions_at_barrier_have_one_side_effect(self) -> None:
        marker = self.project / "restart-race.txt"
        command = (
            "cmd /c echo hit>> restart-race.txt"
            if os.name == "nt"
            else "sh -c 'echo hit >> restart-race.txt'"
        )
        started, old_harness = self._restart_from_interrupt(command)
        paused = self.client.get(f"/v1/agent-runs/{started['id']}").json()
        barrier = threading.Barrier(2)
        results: list[int] = []

        def approve() -> None:
            barrier.wait(timeout=5.0)
            result = self.client.post(
                f"/v1/agent-runs/{started['id']}/interrupt-decision",
                json=run_direct_interrupt_decision(paused, "approve"),
            )
            results.append(result.status_code)

        try:
            threads = [threading.Thread(target=approve), threading.Thread(target=approve)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(sorted(results), [200, 409])
            body = wait_for_run(self.client, started["id"])
            self.assertEqual(body["status"], "completed", body.get("error"))
            self.assertTrue(marker.exists())
            self.assertEqual(marker.read_text(encoding="utf-8").splitlines(), ["hit"])
        finally:
            self._retire_old_waiting_harness(old_harness, started["id"])

    def test_cancel_while_interrupted_rejects_command(self) -> None:
        self._install(execute_then_reply(write_marker_command("host-shell-cancelled.txt")))
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
        paused = wait_for_interrupt(self.client, started["id"])
        bad = self.client.post(
            f"/v1/agent-runs/{started['id']}/interrupt-decision",
            json={
                "interrupt_id": paused["pending_interrupt"]["interrupt_id"],
                "namespace": paused["pending_interrupt"].get("namespace", []),
                "decisions": [],
            },
        )
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertEqual(bad.json()["code"], "interrupt_decision_count")
        self.client.post(
            f"/v1/agent-runs/{started['id']}/interrupt-decision",
            json=run_direct_interrupt_decision(paused, "reject"),
        )
        wait_for_run(self.client, started["id"])

    def test_chat_interrupt_and_shell_flag(self) -> None:
        self._install(execute_then_reply(write_marker_command("chat-host-shell.txt")))
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
            json=chat_direct_interrupt_decision(paused, "approve"),
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
        content = tool_result_text(body["current_run"]).lower()
        self.assertNotIn("not recognized", content)
        self.assertNotIn("error", content)

    def test_chat_interrupt_resume_does_not_overwrite_concurrent_conversation_update(self) -> None:
        self._install(execute_then_reply(write_marker_command("chat-resume-marker.txt")))
        created = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id, "project_path": str(self.project)},
        )
        self.assertEqual(created.status_code, 200, created.text)
        started = self.client.post(
            f"/v1/chat/conversations/{created.json()['id']}/start",
            json={"task": "Run a host-shell command.", "presented_tools": ["execute"]},
        )
        self.assertEqual(started.status_code, 200, started.text)
        paused = wait_for_chat_interrupt(self.client, created.json()["id"])
        stored = self.app.state.app_store.get_conversation(created.json()["id"])
        self.assertIsNotNone(stored)
        assert stored is not None
        stored.transcript.append(
            ChatMessage(
                role="system",
                content="resume concurrent marker",
                at=utc_now(),
            )
        )
        stored.updated_at = utc_now()
        self.app.state.app_store.put_conversation(stored)
        decided = self.client.post(
            f"/v1/chat/conversations/{created.json()['id']}/interrupt-decision",
            json=chat_direct_interrupt_decision(paused, "approve"),
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        self.assertIn(
            "resume concurrent marker",
            [item["content"] for item in decided.json()["transcript"]],
        )
        body = wait_for_run(self.client, started.json()["current_run"]["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))

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
