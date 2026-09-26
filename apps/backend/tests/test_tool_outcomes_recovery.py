"""Native sibling settlement and inspection-based recovery without repeating effects."""

import asyncio
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool, ToolException
from langgraph.types import Command

import tests.test_harness as harness_fixture
from tests.scripted_model import RECEIVED_PROMPTS, ScriptedChatModel, reset_received_prompts
from tests.support import wait_for_run
from workbench_backend.agents.execution_policy import ExecutionControl
from workbench_backend.agents.harness import _invoke_config
from workbench_backend.agents.harness_backend import FilesystemBackend
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, ToolMode, ToolOutcome
from workbench_backend.agents.tool_outcomes import file_evidence, failure_for_run, reconcile_effects, result_outcome
from workbench_backend.inference.ids import utc_now
from workbench_backend.state.checkpointer import conversation_state, run_checkpoint_task


class ToolOutcomeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = harness_fixture.HarnessApiTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.project = self.fixture.root / "effects-project"
        self.project.mkdir()

    def run_record(self, names, *, ident="recovery-fixture"):
        now = utc_now()
        return AgentRun(id=ident, deployment_id=self.fixture.deployment_id, status="running",
            task="Exercise native recovery", enabled_tools=names, presented_tools=names,
            approval_mode="full_access", project_path=str(self.project), thread_id=f"thread-{ident}",
            created_at=now, updated_at=now)

    def test_cancelled_run_keeps_a_durable_continuation_action(self):
        run = self.run_record([])
        run.status = AgentRunStatus.cancelled
        run.stop_reason = "cancelled"
        failure = failure_for_run(run)
        self.assertIsNotNone(failure)
        self.assertEqual(failure.category, "cancelled")
        self.assertEqual(failure.recovery_action, "continue")

    def test_six_native_writes_keep_two_successes_and_four_individual_failures(self):
        (self.project / "src").mkdir()
        (self.project / "blocked").write_text("existing file", encoding="utf-8")
        paths = ["/src/a.txt", "/src/b.txt", "../escape.txt", "/../escape2.txt", "/blocked/child.txt", "/src"]
        self.fixture.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"id": f"write-{index}", "name": "write_file",
                "args": {"file_path": path, "content": f"content-{index}"}} for index, path in enumerate(paths)]),
            AIMessage(content="Two files written; four requests need correction."),
        ])
        started = self.fixture._start(project_path=str(self.project), presented_tools=["write_file"], approval_mode="full_access")
        finished = wait_for_run(self.fixture.client, started["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual([finished["tool_outcomes"][f"write-{index}"]["outcome"] for index in range(6)],
                         ["succeeded", "succeeded", "failed", "failed", "failed", "failed"])
        self.assertEqual((self.project / "src/a.txt").read_text(), "content-0")
        self.assertEqual((self.project / "src/b.txt").read_text(), "content-1")
        self.assertEqual((self.project / "blocked").read_text(), "existing file")
        self.assertFalse((self.project.parent / "escape.txt").exists())
        state = conversation_state(self.fixture.manager.paths.checkpoints_db, finished["thread_id"])
        results = {message.tool_call_id: message for message in state["messages"] if isinstance(message, ToolMessage)}
        self.assertEqual(len(results), 6)
        self.assertEqual(sum(message.status == "error" for message in results.values()), 4)
        for index in range(2, 6):
            self.assertTrue(results[f"write-{index}"].content)

    def test_declared_browser_error_survives_a_successful_native_sibling(self):
        async def unavailable():
            raise ToolException("Browser page refused the read: 403")
        browser = StructuredTool.from_function(coroutine=unavailable, name="browser_snapshot", description="Read a page")
        self.fixture.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"id": "browser", "name": "browser_snapshot", "args": {}},
                {"id": "write", "name": "write_file", "args": {"file_path": "/kept.txt", "content": "kept"}}]),
            AIMessage(content="The page was unavailable; the file was written."),
        ])
        run = self.run_record(["browser_snapshot", "write_file"])
        harness = self.fixture.app.state.harness
        agent = harness._create_compiled_agent(run, [], None, external_tools=[browser])
        state = run_checkpoint_task(self.fixture.manager.paths.checkpoints_db,
            agent.ainvoke({"messages": [HumanMessage(content="Read and write")]}, _invoke_config(run)))
        results = {message.tool_call_id: message for message in state["messages"] if isinstance(message, ToolMessage)}
        self.assertEqual(results["browser"].status, "error")
        self.assertIn("403", results["browser"].content)
        self.assertEqual(results["write"].status, "success")
        self.assertEqual(run.tool_outcomes["browser"].outcome, "failed")
        self.assertEqual((self.project / "kept.txt").read_text(), "kept")
        self.assertEqual(state["messages"][-1].content, "The page was unavailable; the file was written.")

    def test_native_shell_failure_uses_exit_evidence_and_can_continue(self):
        self.fixture.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"id": "shell-failure", "name": "execute",
                "args": {"command": "exit /b 7" if os.name == "nt" else "exit 7"}}]),
            AIMessage(content="The command failed; its result is available."),
        ])
        started = self.fixture._start(project_path=str(self.project), presented_tools=["execute"], approval_mode="full_access")
        finished = wait_for_run(self.fixture.client, started["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        outcome = finished["tool_outcomes"]["shell-failure"]
        self.assertEqual(outcome["outcome"], "failed")
        self.assertEqual(outcome["evidence"]["exit_code"], 7)
        self.assertEqual(outcome["recovery_action"], "continue")

        misleading_text = ToolMessage(content="[Command failed with exit code 99]", name="execute",
            tool_call_id="actually-successful", artifact={"exit_code": 0}, status="success")
        self.assertEqual(result_outcome("actually-successful", "execute", misleading_text).outcome, "succeeded")

    def test_interrupted_command_results_require_inspection_without_invented_stop_evidence(self):
        for exit_code in (124, 130):
            with self.subTest(exit_code=exit_code):
                message = ToolMessage(content="Processes stopped; some changes may have happened", name="execute",
                    tool_call_id="interrupted", artifact={"exit_code": exit_code}, status="success")
                outcome = result_outcome("interrupted", "execute", message)
                self.assertEqual(outcome.outcome, "uncertain")
                self.assertEqual(outcome.recovery_action, "inspect_effects")
                self.assertNotIn("process_stopped", outcome.evidence)
                run = self.run_record(["execute"])
                run.tool_outcomes[outcome.call_id] = outcome
                reconcile_effects(run)
                self.assertEqual(run.tool_outcomes[outcome.call_id].outcome, "uncertain")
                self.assertEqual(failure_for_run(run).category, "uncertain_effects")

    @unittest.skipUnless(os.name == "nt", "Windows native process ownership")
    def test_native_timeout_stops_retry_until_explicit_inspection_acknowledgement(self):
        script = self.project / "partial.py"
        script.write_text("import threading\nfrom pathlib import Path\n"
            "with Path('marker.txt').open('a') as marker: marker.write('once\\n')\n"
            "threading.Event().wait(120)\n", encoding="utf-8")
        command = subprocess.list2cmdline([sys._base_executable, str(script)])
        self.fixture.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"id": "partial-shell", "name": "execute",
                "args": {"command": command, "timeout": 2}}]),
            AIMessage(content="Retrying the command", tool_calls=[{"id": "must-not-repeat", "name": "execute",
                "args": {"command": command, "timeout": 2}}]),
            AIMessage(content="Incorrectly continued."),
        ])
        reset_received_prompts()
        started = self.fixture._start(project_path=str(self.project), presented_tools=["execute"], approval_mode="full_access")
        finished = wait_for_run(self.fixture.client, started["id"])
        self.assertEqual(finished["status"], "failed", finished.get("error"))
        self.assertEqual(finished["failure"]["category"], "uncertain_effects")
        self.assertEqual(finished["failure"]["recovery_action"], "inspect_effects")
        outcome = finished["tool_outcomes"]["partial-shell"]
        self.assertEqual(outcome["outcome"], "uncertain")
        self.assertEqual(outcome["evidence"], {"exit_code": 124, "process_stopped": True})
        self.assertEqual(len(RECEIVED_PROMPTS), 1, "No further model request may propose an automatic retry")
        self.assertEqual(finished["dispatched_tool_calls"], 1)
        self.assertEqual((self.project / "marker.txt").read_text().splitlines(), ["once"])
        blocked = self.fixture.client.post("/v1/agent-runs", json={"deployment_id": self.fixture.deployment_id,
            "project_path": str(self.project), "task": "Continue"})
        self.assertEqual(blocked.status_code, 409, blocked.text)
        acknowledged = self.fixture.app.state.harness.acknowledge_project_effects(started["id"])
        self.assertEqual(acknowledged.tool_outcomes["partial-shell"].outcome, "uncertain")
        self.assertTrue(acknowledged.tool_outcomes["partial-shell"].evidence["acknowledged_at"])
        self.fixture.scripted = ScriptedChatModel([AIMessage(content="Continuing after inspection, without repeating the command.")])
        continued = self.fixture._start(thread_id=started["thread_id"], project_path=str(self.project),
            presented_tools=["execute"], approval_mode="full_access", task="I inspected the file; continue without repeating it.")
        self.assertEqual(wait_for_run(self.fixture.client, continued["id"])["status"], "completed")
        self.assertEqual((self.project / "marker.txt").read_text().splitlines(), ["once"])

    @unittest.skipUnless(os.name == "nt", "Windows native process ownership")
    def test_cancel_after_partial_effect_preserves_stopped_process_evidence_and_project_hold(self):
        script = self.project / "cancel.py"
        script.write_text("import threading\nfrom pathlib import Path\n"
            "Path('marker.txt').write_text('once')\nthreading.Event().wait(120)\n", encoding="utf-8")
        self.fixture.scripted = ScriptedChatModel([
            AIMessage(content="", tool_calls=[{"id": "cancel-shell", "name": "execute", "args": {
                "command": subprocess.list2cmdline([sys._base_executable, str(script)]), "timeout": 120}}]),
            AIMessage(content="Must not continue after stop."),
        ])
        reset_received_prompts()
        started = self.fixture._start(project_path=str(self.project), presented_tools=["execute"], approval_mode="full_access")
        try:
            deadline = time.monotonic() + 10
            while not (self.project / "marker.txt").exists() and time.monotonic() < deadline:
                threading.Event().wait(.01)
            self.assertTrue((self.project / "marker.txt").exists(), "The command must have an actual partial effect before cancellation")
        finally:
            self.fixture.app.state.harness.cancel(started["id"])
        finished = wait_for_run(self.fixture.client, started["id"])
        self.assertEqual(finished["status"], "cancelled", finished.get("error"))
        outcome = finished["tool_outcomes"]["cancel-shell"]
        self.assertEqual(outcome["outcome"], "uncertain")
        self.assertEqual(outcome["evidence"], {"exit_code": 130, "process_stopped": True})
        self.assertEqual(finished["failure"]["category"], "uncertain_effects")
        self.assertEqual(len(RECEIVED_PROMPTS), 1)
        self.assertEqual((self.project / "marker.txt").read_text(), "once")
        blocked = self.fixture.client.post("/v1/agent-runs", json={"deployment_id": self.fixture.deployment_id,
            "project_path": str(self.project), "task": "Continue"})
        self.assertEqual(blocked.status_code, 409, blocked.text)

    def test_aborted_batch_restores_durable_sibling_and_next_turn_does_not_replay(self):
        harness = self.fixture.app.state.harness
        run = self.run_record(["browser_snapshot", "write_file"], ident="aborted-batch")
        written = threading.Event()

        def publish():
            harness.store.put_run(run.model_copy(deep=True))
            if run.tool_outcomes.get("write") and run.tool_outcomes["write"].outcome == "succeeded":
                written.set()

        async def interrupted_read():
            if not await asyncio.to_thread(written.wait, 5):
                raise AssertionError("native write did not settle")
            raise RuntimeError("browser worker terminated unexpectedly")

        browser = StructuredTool.from_function(coroutine=interrupted_read, name="browser_snapshot", description="Read a page")
        self.fixture.scripted = ScriptedChatModel([AIMessage(content="", tool_calls=[
            {"id": "write", "name": "write_file", "args": {"file_path": "/once.txt", "content": "written once"}},
            {"id": "browser", "name": "browser_snapshot", "args": {}},
        ])])
        control = ExecutionControl(run, publish)
        agent = harness._create_compiled_agent(run, [], None, external_tools=[browser], execution_control=control)
        writes = []
        original_write = FilesystemBackend.write

        def counted_write(backend, path, content):
            if path == "/once.txt":
                writes.append(path)
            return original_write(backend, path, content)

        async def fail_then_link():
            with self.assertRaisesRegex(RuntimeError, "browser worker"):
                await agent.ainvoke({"messages": [HumanMessage(content="Do both")]}, _invoke_config(run))
            # The known result must already exist independently of batch commit.
            self.assertEqual(harness.store.get_run(run.id).tool_outcomes["write"].outcome, "succeeded")
            run.error = "browser worker terminated unexpectedly"
            run.status = AgentRunStatus.failed
            await harness._alink_run(run, agent)
            harness.store.put_run(run)

        with patch.object(FilesystemBackend, "write", counted_write):
            run_checkpoint_task(self.fixture.manager.paths.checkpoints_db, fail_then_link())
            state = conversation_state(self.fixture.manager.paths.checkpoints_db, run.thread_id)
            results = {message.tool_call_id: message for message in state["messages"] if isinstance(message, ToolMessage)}
            self.assertEqual(results["write"].status, "success")
            self.assertEqual(results["browser"].status, "error")
            self.fixture.scripted = ScriptedChatModel([AIMessage(content="Continuing with the saved successful write.")])
            next_run = self.fixture._start(thread_id=run.thread_id, project_path=str(self.project),
                presented_tools=["write_file"], approval_mode="full_access", task="Continue")
            finished = wait_for_run(self.fixture.client, next_run["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual(writes, ["/once.txt"])
        self.assertEqual((self.project / "once.txt").read_text(), "written once")

    def test_edit_evidence_matches_native_newlines_and_inspects_without_replay(self):
        path = self.project / "edit.txt"
        path.write_bytes(b"one\rtwo\r\nthree\n")
        run = self.run_record(["edit_file"])
        args = {"file_path": "/edit.txt", "old_string": "one\rtwo\r\n", "new_string": "first\r\nsecond\r"}
        evidence = file_evidence(run, "edit_file", args)
        run.tool_outcomes["edit"] = ToolOutcome(call_id="edit", name="edit_file", outcome="running", evidence=evidence, updated_at=utc_now())
        self.assertIsNone(FilesystemBackend(root_dir=self.project).edit(**args).error)
        before = path.read_bytes()
        reconcile_effects(run)
        self.assertEqual(run.tool_outcomes["edit"].outcome, "succeeded")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(before, b"first\nsecond\nthree\n")

    def test_write_evidence_matches_exact_native_lf_crlf_and_mixed_bytes(self):
        for content in ("one\ntwo\n", "one\r\ntwo\r\n", "one\rtwo\r\nthree\n"):
            with self.subTest(content=repr(content)):
                path = self.project / "newlines.txt"
                if path.exists():
                    path.unlink()
                run = self.run_record(["write_file"])
                evidence = file_evidence(run, "write_file", {"file_path": "/newlines.txt", "content": content})
                run.tool_outcomes["write"] = ToolOutcome(call_id="write", name="write_file", outcome="running",
                    evidence=evidence, updated_at=utc_now())
                self.assertIsNone(FilesystemBackend(root_dir=self.project).write("/newlines.txt", content).error)
                self.assertEqual(path.read_bytes(), content.encode("utf-8"))
                reconcile_effects(run)
                self.assertEqual(run.tool_outcomes["write"].outcome, "succeeded")

    def test_unchanged_native_write_and_edit_require_exact_before_bytes(self):
        path = self.project / "unchanged.txt"
        before = b"old\rmiddle\r\nlast\n"
        for name, args in (("write_file", {"content": "replacement\n"}),
                           ("edit_file", {"old_string": "old\r", "new_string": "replacement\r\n"})):
            with self.subTest(tool=name):
                path.write_bytes(before)
                run = self.run_record([name])
                evidence = file_evidence(run, name, {"file_path": "/unchanged.txt", **args})
                pending = ToolOutcome(call_id="pending", name=name, outcome="running", evidence=evidence, updated_at=utc_now())
                run.tool_outcomes["pending"] = pending
                reconcile_effects(run)
                self.assertEqual(run.tool_outcomes["pending"].outcome, "failed")
                self.assertEqual(path.read_bytes(), before)
                # A third-party newline conversion is a real change. It proves
                # neither our replacement nor an unchanged target.
                path.write_bytes(before.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
                run.tool_outcomes["pending"] = pending
                reconcile_effects(run)
                self.assertEqual(run.tool_outcomes["pending"].outcome, "uncertain")

    def test_recorded_outcomes_never_inspect_live_files_for_evidence(self):
        run = self.run_record(["write_file"])
        run.tool_mode = ToolMode.recorded_tool
        run.tool_outcomes["write"] = ToolOutcome(call_id="write", name="write_file", outcome="running",
            evidence={"path": "/target.txt", "before_exists": False}, updated_at=utc_now())
        with patch("workbench_backend.agents.harness_backend.resolve_project_tool_path",
                   side_effect=AssertionError("Replay must not inspect host files")) as resolve:
            self.assertEqual(file_evidence(run, "write_file", {"file_path": "/target.txt", "content": "fixture"}), {})
            reconcile_effects(run)
            resolve.assert_not_called()
        self.assertEqual(run.tool_outcomes["write"].outcome, "uncertain")

    def test_changed_unconfirmed_target_stays_gated_and_unchanged_target_is_retryable(self):
        path = self.project / "target.txt"
        path.write_text("before", encoding="utf-8")
        run = self.run_record(["write_file"])
        evidence = file_evidence(run, "write_file", {"file_path": "/target.txt", "content": "wanted"})
        run.tool_outcomes["write"] = ToolOutcome(call_id="write", name="write_file", outcome="running", evidence=evidence, updated_at=utc_now())
        path.write_text("third-party content", encoding="utf-8")
        reconcile_effects(run)
        self.assertEqual(run.tool_outcomes["write"].outcome, "uncertain")
        self.assertEqual(failure_for_run(run).recovery_action, "inspect_effects")
        self.assertEqual(path.read_text(), "third-party content")
        path.write_text("before", encoding="utf-8")
        reconcile_effects(run)
        self.assertEqual(run.tool_outcomes["write"].outcome, "failed")
        self.assertEqual(run.tool_outcomes["write"].recovery_action, "continue")

    def test_command_result_preserves_only_its_matching_native_tool_message(self):
        command = Command(update={"todos": [{"content": "verify", "status": "pending"}], "messages": [
            ToolMessage(content="other result", tool_call_id="other"),
            ToolMessage(content="Plan saved", tool_call_id="todo", status="success"),
        ]})
        outcome = result_outcome("todo", "write_todos", command)
        self.assertEqual(outcome.result, "Plan saved")
        self.assertEqual(outcome.outcome, "succeeded")
        failed = result_outcome("todo", "write_todos", Command(update={"messages": [
            ToolMessage(content="Rejected checklist", tool_call_id="todo", status="error")]}))
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(failed.result, "Rejected checklist")
