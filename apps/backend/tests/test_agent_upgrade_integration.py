"""Selected upgrades cross the actual compiler and durable dispatch boundary."""
from __future__ import annotations

import json
import sys
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import asyncio
from tempfile import TemporaryDirectory
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage
from workbench_backend.agents.host_shell import interrupt_on_for_run
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, PendingInterruptAction
from tests import test_harness
from tests.scripted_model import ScriptedChatModel


class AgentUpgradeIntegrationTests(unittest.TestCase):
    setUp = test_harness.HarnessApiTests.setUp
    tearDown = test_harness.HarnessApiTests.tearDown
    _start = test_harness.HarnessApiTests._start

    def test_selected_desktop_admission_keeps_typed_policy_and_essential_readiness(self):
        from tests.test_desktop_automation import DesktopAutomationTests
        fixture = DesktopAutomationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.app.state.harness.desktop_automation = fixture.service
        self.scripted = ScriptedChatModel([AIMessage(content="Selected window is ready.")])
        policy = {"tool_loading": "when_needed", "pinned_tools": ["desktop_inspect"]}
        request = {"deployment_id": self.deployment_id, "task": "Inspect the selected window", "source_surface": "chat",
            "thread_id": "thread-one", "presented_tools": ["desktop_inspect"], "desktop_access": "selected", "input_policy": policy}
        started_without_window = self.client.post("/v1/agent-runs", json=request)
        self.assertEqual(started_without_window.status_code, 200, started_without_window.text)
        unfinished = test_harness.wait_for_run(self.client, started_without_window.json()["id"])
        self.assertEqual(unfinished["status"], "completed", unfinished.get("error"))
        self.assertEqual(fixture.commands, [])
        self.assertIsNone(unfinished["desktop_window"])
        fixture.service.set_scope("thread-one", "selected", hwnd=101)
        started = self.client.post("/v1/agent-runs", json=request)
        self.assertEqual(started.status_code, 200, started.text)
        finished = test_harness.wait_for_run(self.client, started.json()["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual(finished["input_policy"]["pinned_tools"], ["desktop_inspect"])
        self.assertEqual(finished["desktop_access"], "selected")
        self.assertEqual(finished["desktop_window"], {"hwnd": 101, "process_id": 10, "process_created_at": 1000.0})
        self.assertTrue(all(command[1] == "list-windows" for command, _ in fixture.commands),
            "Readiness may revalidate live identity, but a prose-only response must not invoke a desktop action")

    def test_compiled_managed_command_stops_before_run_is_terminal(self):
        project = self.root / "command project"
        project.mkdir()
        service = self.app.state.managed_commands
        self.app.state.harness.managed_commands = service
        self.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"name": "start_command", "args": {
                "command": [sys.executable, "-u", "-c", "import time; print('launched'); time.sleep(120)"],
                "timeout_seconds": 60}, "id": "command-launch"}]),
            AIMessage(content="The command was launched."),
        ])
        started = self._start(project_path=str(project), presented_tools=["start_command", "command_status", "stop_command", "read_tool_result"], approval_mode="full_access")
        finished = test_harness.wait_for_run(self.client, started["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        commands = list(service._commands.values())
        self.assertEqual(len(commands), 1)
        command = commands[0]
        self.assertIsNotNone(command.process.poll())
        self.assertTrue(command.settled.is_set())
        effect = service.effects.get_effect(command.effect_id)
        self.assertTrue(effect.evidence["process_stop_confirmed"])
        self.assertFalse(effect.unresolved)

    def test_compiled_skill_script_uses_frozen_resource_and_failed_exit(self):
        project = self.root / "script project"
        project.mkdir()
        package = self.root / "package"
        (package / "scripts").mkdir(parents=True)
        (package / "SKILL.md").write_text("---\nname: exit-test\ndescription: Run this script only for the exit-test request.\n---\nScript is scripts/check.py.\n", encoding="utf-8")
        (package / "scripts" / "check.py").write_text("import sys\nprint('actual frozen script')\nsys.exit(7)\n", encoding="utf-8")
        imported = self.client.post("/v1/knowledge/skills/import", json={"source_path": str(package)})
        self.assertEqual(imported.status_code, 200, imported.text)
        entry = imported.json()
        self.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"name": "execute_skill_script", "args": {
                "entry_id": entry["id"], "version_id": entry["current_version_id"], "resource_path": "scripts/check.py"}, "id": "script-exit"}]),
            AIMessage(content="The script returned exit code 7."),
        ])
        started = self._start(project_path=str(project), presented_tools=["execute", "execute_skill_script", "read_tool_result"],
            skill_version_refs=[entry["current_version_id"]], approval_mode="full_access")
        finished = test_harness.wait_for_run(self.client, started["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        outcome = finished["tool_outcomes"]["script-exit"]
        self.assertEqual(outcome["outcome"], "failed")
        self.assertEqual(outcome["evidence"]["exit_code"], 7)
        self.assertTrue(outcome["evidence"]["process_stopped"])
        self.assertIn("actual frozen script", str(outcome["result"]))
        self.assertFalse((project / "skills").exists())

    def test_revoked_original_grant_is_rechecked_inside_dispatch(self):
        project = self.root / "grant project"
        project.mkdir()
        run = AgentRun(id="revoked-run", thread_id="revoked-thread", deployment_id=self.deployment_id, task="write",
            project_path=str(project), status=AgentRunStatus.running, enabled_tools=["write_file"], presented_tools=["write_file"],
            created_at="2026-10-01T00:00:00Z", updated_at="2026-10-01T00:00:00Z")
        args = {"file_path": "/file.txt", "content": "never"}
        preferences = self.app.state.preferences
        grant = preferences.allow(run, PendingInterruptAction(name="write_file", args=args), "session")
        request = SimpleNamespace(tool_call={"name": "write_file", "args": args, "id": "revoked-call"},
            runtime=SimpleNamespace(state={"messages": []}))
        predicate = interrupt_on_for_run(run, preferences)["write_file"]["when"]
        self.assertFalse(predicate(request))
        self.client.delete(f"/v1/settings/grants/{grant.id}")
        called = []
        def handler(request):
            called.append(True)
            (project / "file.txt").write_text("never")
            return ToolMessage(content="done", tool_call_id="revoked-call", name="write_file")
        result = WorkbenchHarnessMiddleware(run, grants=preferences).wrap_tool_call(request, handler)
        self.assertEqual(result.status, "error")
        self.assertEqual(called, [])
        self.assertFalse((project / "file.txt").exists())
        self.assertEqual(run.tool_outcomes["revoked-call"].outcome, "failed")

    def test_preview_does_not_request_write_approval(self):
        run = AgentRun(id="preview-run", deployment_id=self.deployment_id, task="preview", project_path=str(self.root),
            enabled_tools=["apply_edits"], presented_tools=["apply_edits"], created_at="2026-10-01T00:00:00Z", updated_at="2026-10-01T00:00:00Z")
        predicate = interrupt_on_for_run(run)["apply_edits"]["when"]
        call = {"name": "apply_edits", "args": {"file_path": "/a.txt", "edits": [{"old_string": "a", "new_string": "b"}]}, "id": "preview"}
        self.assertFalse(predicate(SimpleNamespace(tool_call=call)))
        call["args"]["base_sha256"] = "0" * 64
        self.assertTrue(predicate(SimpleNamespace(tool_call=call)))

    def test_unconfirmed_command_cleanup_cannot_report_completed(self):
        stopped = []
        def stop_run(run_id):
            stopped.append(run_id)
            raise RuntimeError("process stop unconfirmed")
        self.app.state.harness.managed_commands = SimpleNamespace(
            tools_for_run=lambda *args, **kwargs: [], stop_run=stop_run, shutdown=lambda: None)
        self.scripted = ScriptedChatModel([AIMessage(content="Answer finished.")])
        started = self._start(presented_tools=[])
        finished = test_harness.wait_for_run(self.client, started["id"])
        self.assertEqual(stopped, [started["id"]])
        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["stop_reason"], "effects_unconfirmed")
        self.assertEqual(finished["tool_outcomes"]["owned-command-cleanup"]["outcome"], "uncertain")
        self.assertEqual(finished["failure"]["recovery_action"], "inspect_effects")

    def test_native_mutation_and_atomic_edit_share_project_lease(self):
        from deepagents.backends import FilesystemBackend
        from workbench_backend.agents.file_operations import apply_edits_tool
        project = self.root / "concurrent project"
        project.mkdir()
        target = project / "file.txt"
        target.write_text("original", encoding="utf-8")
        run = AgentRun(id="native-owner", deployment_id=self.deployment_id, task="write", project_path=str(project),
            status=AgentRunStatus.running, enabled_tools=["write_file", "apply_edits"], presented_tools=["write_file", "apply_edits"],
            created_at="2026-10-01T00:00:00Z", updated_at="2026-10-01T00:00:00Z")
        backend = FilesystemBackend(root_dir=str(project), virtual_mode=True)
        entered, release = threading.Event(), threading.Event()
        request = SimpleNamespace(tool_call={"name": "write_file", "args": {"file_path": "/file.txt", "content": "native"}, "id": "native-write"},
            runtime=SimpleNamespace(state={"messages": []}))
        def native_handler(request):
            entered.set()
            self.assertTrue(release.wait(5))
            backend.edit("/file.txt", "original", "native")
            return ToolMessage(content="Changed", name="write_file", tool_call_id="native-write")
        with ThreadPoolExecutor(max_workers=2) as pool:
            native = pool.submit(WorkbenchHarnessMiddleware(run).wrap_tool_call, request, native_handler)
            try:
                self.assertTrue(entered.wait(5))
                other = run.model_copy(update={"id": "structured-owner"})
                atomic = pool.submit(apply_edits_tool(other).invoke, {"file_path": "/file.txt",
                    "edits": [{"old_string": "original", "new_string": "structured"}], "base_sha256": hashlib.sha256(b"original").hexdigest()})
                # The sync tool fails at once. It does not park a pool thread behind the write.
                refused = atomic.result(timeout=2)
                self.assertIn("already being changed", refused.lower())
                self.assertEqual(target.read_text(encoding="utf-8"), "original")
            finally:
                release.set()
            self.assertEqual(native.result(timeout=5).status, "success")
        self.assertEqual(target.read_text(encoding="utf-8"), "native")

    def test_partial_native_delete_records_remaining_effects_before_retry(self):
        from deepagents.backends import FilesystemBackend
        project = self.root / "partial project"
        folder = project / "target"
        folder.mkdir(parents=True)
        (folder / "first.txt").write_bytes(b"removed")
        (folder / "locked.txt").write_bytes(b"kept")
        run = AgentRun(id="delete-owner", deployment_id=self.deployment_id, task="delete", project_path=str(project),
            status=AgentRunStatus.running, enabled_tools=["delete"], presented_tools=["delete"],
            created_at="2026-10-01T00:00:00Z", updated_at="2026-10-01T00:00:00Z")
        backend = FilesystemBackend(root_dir=str(project), virtual_mode=True)
        request = SimpleNamespace(tool_call={"name": "delete", "args": {"file_path": "/target"}, "id": "partial-delete"},
            runtime=SimpleNamespace(state={"messages": []}))
        def partial_rmtree(path, *args, **kwargs):
            (Path(path) / "first.txt").unlink()
            raise PermissionError("locked target")
        def handler(request):
            result = backend.delete("/target")
            return ToolMessage(content=result.error or "Deleted", name="delete", tool_call_id="partial-delete", status="error" if result.error else "success")
        with patch("shutil.rmtree", side_effect=partial_rmtree):
            result = WorkbenchHarnessMiddleware(run).wrap_tool_call(request, handler)
        outcome = run.tool_outcomes["partial-delete"]
        self.assertEqual(outcome.outcome, "uncertain")
        self.assertEqual(outcome.recovery_action, "inspect_effects")
        self.assertEqual(outcome.evidence["before_files"], 2)
        self.assertEqual(outcome.evidence["after_files"], 1)
        self.assertTrue(outcome.evidence["after_exists"])
        self.assertIn("do not blindly repeat", result.content)
        self.assertFalse((folder / "first.txt").exists())
        self.assertEqual((folder / "locked.txt").read_bytes(), b"kept")


class MutationCancellationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.area = TemporaryDirectory()
        self.addCleanup(self.area.cleanup)
        self.project = Path(self.area.name)
        self.run = AgentRun(id="async-mutation", deployment_id="fixture", task="write", project_path=str(self.project),
            status=AgentRunStatus.running, enabled_tools=["write_file"], presented_tools=["write_file"],
            created_at="2026-10-01T00:00:00Z", updated_at="2026-10-01T00:00:00Z")
        self.request = SimpleNamespace(tool_call={"name": "write_file", "args": {"file_path": "/file.txt", "content": "written"}, "id": "native-async"},
            runtime=SimpleNamespace(state={"messages": []}))

    async def test_queued_cancellation_does_not_steal_or_strand_the_lease(self):
        from workbench_backend.agents.file_operations import file_order_lock, file_order_path
        lock = file_order_lock(file_order_path(self.project, "file.txt"))
        self.assertTrue(lock.acquire())
        called = []
        async def handler(request):
            called.append(True)
            return ToolMessage(content="bad", name="write_file", tool_call_id="native-async")
        task = asyncio.create_task(WorkbenchHarnessMiddleware(self.run).awrap_tool_call(self.request, handler))
        try:
            for _ in range(50):
                if lock.waiting():
                    break
                await asyncio.sleep(0.02)
            self.assertGreaterEqual(lock.waiting(), 1)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2)
            self.assertEqual(called, [])
            self.assertFalse(lock.acquire(), "queued cancellation must leave the holder admitted")
        finally:
            lock.release()
        self.assertTrue(lock.acquire())
        lock.release()

    async def test_repeated_cancellation_keeps_lease_until_native_worker_settles(self):
        from workbench_backend.agents.file_operations import file_order_lock, file_order_path
        lock = file_order_lock(file_order_path(self.project, "file.txt"))
        entered, release = threading.Event(), threading.Event()
        def native_work():
            entered.set()
            if not release.wait(5):
                raise TimeoutError("native worker not released")
            (self.project / "file.txt").write_text("written", encoding="utf-8")
            return ToolMessage(content="Written", name="write_file", tool_call_id="native-async")
        async def handler(request):
            return await asyncio.to_thread(native_work)
        task = asyncio.create_task(WorkbenchHarnessMiddleware(self.run).awrap_tool_call(self.request, handler))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            self.assertFalse(lock.acquire(), "native worker still owns mutation lease")
        finally:
            release.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
        self.assertEqual((self.project / "file.txt").read_text(encoding="utf-8"), "written")
        self.assertEqual(self.run.tool_outcomes["native-async"].outcome, "succeeded")
        self.assertTrue(lock.acquire())
        lock.release()


if __name__ == "__main__":
    unittest.main()
