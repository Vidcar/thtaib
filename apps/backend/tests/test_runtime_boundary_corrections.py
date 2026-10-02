"""Observable host approval, interrupted-job and preview-deletion boundaries."""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from langchain_core.messages import AIMessage
from langchain_core.tools import ToolException

from tests import test_harness as harness_fixture
from tests import test_permission_boundary as permission_fixture
from tests import test_asset_lifecycle as asset_fixture
from tests.scripted_model import RECEIVED_PROMPTS, ScriptedChatModel, reset_received_prompts
from tests.support import wait_for_run
from workbench_backend.agents.harness import HarnessService, _with_shell_folder
from workbench_backend.agents.host_shell import recheck_saved_authorization
from workbench_backend.agents.schemas import PendingInterrupt, PendingInterruptAction
from workbench_backend.assets.lifecycle_routes import delete_conversation
from workbench_backend.errors import HarnessError
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.preview.service import PreviewService
from workbench_backend.process_tree import WindowsJob
from workbench_backend.state.preferences import PreferenceStore
from workbench_backend.state.store import ApplicationStore


class HostActionConfirmationTests(unittest.TestCase):
    def test_first_card_and_exact_saved_grant_cover_every_host_execution_path(self):
        cases = [
            ("execute", {"command": "echo host-confirmation"}),
            ("start_command", {"command": [sys.executable, "-c", "print('job')"], "timeout_seconds": 30}),
            ("execute_skill_script", {"entry_id": "skill", "version_id": "version", "resource_path": "scripts/check.py", "arguments": ["literal"]}),
        ]
        with tempfile.TemporaryDirectory() as area:
            store = ApplicationStore(WorkbenchPaths(Path(area) / "state"))
            parked = permission_fixture._Parked()
            harness = HarnessService(lambda: SimpleNamespace(paths=store.paths), app_store=store)
            try:
                prefs = PreferenceStore(store)
                names = [name for name, _ in cases]
                for name, args in cases:
                    with self.subTest(action=name):
                        other = permission_fixture._run(id="other-" + name, thread_id="other-" + name,
                            source_surface="chat", project_path=area, presented_tools=names, enabled_tools=names)
                        saved = prefs.allow(other, PendingInterruptAction(name=name, args={**args, "starting_folder": "C:/forged"}), "always")
                        prefs.confirm_host_shell(other.thread_id)
                        self.assertEqual(saved.starting_folder, str(Path(area).resolve()))
                        self.assertNotIn("starting_folder", saved.arguments)
                        run = other.model_copy(update={"id": "new-" + name, "thread_id": "new-" + name})
                        full = run.model_copy(update={"approval_mode": "full_access"})
                        self.assertFalse(prefs.matches(run, name, args))
                        self.assertTrue(permission_fixture._pauses(run, prefs, name, args))
                        self.assertTrue(permission_fixture._pauses(full, prefs, name, args))
                        shown = _with_shell_folder(run, PendingInterrupt(action_requests=[PendingInterruptAction(name=name, args=args)]))
                        self.assertEqual(shown.action_requests[0].args["starting_folder"], str(Path(area).resolve()))
                        self.assertIn(str(Path(area).resolve()), shown.action_requests[0].description)
                        parked.resume(harness, run, shown.action_requests, [{"type": "reject"}])
                        self.assertFalse(prefs.host_shell_confirmed(run.thread_id))
                        self.assertTrue(permission_fixture._pauses(full, prefs, name, args))
                        accepted = run.model_copy(update={"id": "accepted-" + name})
                        parked.resume(harness, accepted, shown.action_requests, [{"type": "approve", "scope": "once"}])
                        self.assertTrue(prefs.host_shell_confirmed(run.thread_id))
                        for later_name, later_args in cases:
                            self.assertFalse(permission_fixture._pauses(full, prefs, later_name, later_args))
                        self.assertFalse(permission_fixture._pauses(run, prefs, name, args))
                        self.assertTrue(permission_fixture._pauses(run.model_copy(update={"project_path": str(Path(area) / "elsewhere")}), prefs, name, args))
                        changed = {**args, "command": "echo different"} if name == "execute" else {**args, "arguments": ["changed"]} if name == "execute_skill_script" else {**args, "command": [sys.executable, "-c", "print('different')"]}
                        self.assertTrue(permission_fixture._pauses(run, prefs, name, changed))
                        permission_fixture._pauses(run, prefs, name, args)
                        prefs.revoke(saved.id)
                        with self.assertRaises(ToolException):
                            recheck_saved_authorization(run, name, args, "call-1", prefs)
            finally:
                parked.close()
                store.close()


class ManagedJobRecoveryTests(unittest.TestCase):
    def test_timeout_during_final_response_cannot_be_reported_as_completed(self):
        fixture = harness_fixture.HarnessApiTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        fixture.app.state.harness.managed_commands = fixture.app.state.managed_commands
        project = fixture.root / "job-final-response"
        project.mkdir()
        script = project / "partial.py"
        script.write_text("from pathlib import Path\nimport threading\nPath('partial.txt').write_text('partial')\nthreading.Event().wait(60)\n", encoding="utf-8")
        class LateFinalModel(ScriptedChatModel):
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                if self._index == 1:
                    command = next(iter(fixture.app.state.managed_commands._commands.values()))
                    if not command.settled.wait(5):
                        raise AssertionError("The real job must time out while the response is being generated")
                return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        fixture.scripted = LateFinalModel([
            AIMessage(content="", tool_calls=[{"id": "job", "name": "start_command", "args": {"command": [sys._base_executable, str(script)], "timeout_seconds": 1}}]),
            AIMessage(content="Finished"),
        ])
        started = fixture._start(project_path=str(project), presented_tools=["start_command"], approval_mode="full_access")
        finished = wait_for_run(fixture.client, started["id"])
        self.assertTrue((project / "partial.txt").is_file())
        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["failure"]["category"], "uncertain_effects")

    def test_partial_job_timeout_blocks_retry_until_inspected_acknowledgement(self):
        fixture = harness_fixture.HarnessApiTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        fixture.app.state.harness.managed_commands = fixture.app.state.managed_commands
        project = fixture.root / "partial-job"
        project.mkdir()
        script = project / "partial.py"
        script.write_text("from pathlib import Path\nimport threading\nwith Path('marker.txt').open('a') as f: f.write('once\\n')\nthreading.Event().wait(60)\n", encoding="utf-8")
        # The job ID is returned at runtime. The deterministic model extracts
        # it exactly as a real continuation would, then asks for status.
        class JobModel(ScriptedChatModel):
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                import json
                if self._index == 1:
                    result = next(message for message in reversed(messages) if getattr(message, "name", None) == "start_command")
                    self._script[1] = AIMessage(content="", tool_calls=[{"id": "job-status", "name": "command_status", "args": {"command_id": json.loads(result.content)["command_id"], "wait_seconds": 5}}])
                return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        argv = [sys._base_executable, str(script)]
        fixture.scripted = JobModel([
            AIMessage(content="", tool_calls=[{"id": "partial-job", "name": "start_command", "args": {"command": argv, "timeout_seconds": 1}}]),
            AIMessage(content="placeholder"),
            AIMessage(content="Retrying", tool_calls=[{"id": "must-not-repeat", "name": "start_command", "args": {"command": argv, "timeout_seconds": 1}}]),
            AIMessage(content="Incorrectly continued"),
        ])
        reset_received_prompts()
        started = fixture._start(project_path=str(project), presented_tools=["start_command", "command_status"], approval_mode="full_access")
        finished = wait_for_run(fixture.client, started["id"])
        self.assertEqual(finished["status"], "failed", finished.get("error"))
        self.assertEqual(finished["failure"]["category"], "uncertain_effects")
        uncertain = [row for row in finished["tool_outcomes"].values() if row["outcome"] == "uncertain"]
        self.assertEqual(len(uncertain), 1)
        self.assertEqual(uncertain[0]["evidence"]["exit_code"], 124)
        self.assertTrue(uncertain[0]["evidence"]["process_stopped"])
        self.assertEqual(len(RECEIVED_PROMPTS), 2, "Timeout must prevent the model proposing a retry")
        self.assertEqual((project / "marker.txt").read_text().splitlines(), ["once"])
        blocked = fixture.client.post("/v1/agent-runs", json={"deployment_id": fixture.deployment_id, "thread_id": started["thread_id"], "project_path": str(project), "task": "Continue"})
        self.assertEqual(blocked.status_code, 409, blocked.text)
        acknowledged = fixture.app.state.harness.acknowledge_project_effects(started["id"])
        self.assertTrue(any(row.evidence.get("acknowledged_at") for row in acknowledged.tool_outcomes.values() if row.outcome == "uncertain"))
        fixture.scripted = ScriptedChatModel([AIMessage(content="Continue after inspection without repeating the job.")])
        continued = fixture._start(thread_id=started["thread_id"], project_path=str(project), presented_tools=["start_command", "command_status"], approval_mode="full_access")
        self.assertEqual(wait_for_run(fixture.client, continued["id"])["status"], "completed")
        self.assertEqual((project / "marker.txt").read_text().splitlines(), ["once"])


class PreviewDeletionRecoveryTests(unittest.TestCase):
    def test_unconfirmed_preview_stop_preserves_chat_and_retryable_owner(self):
        fixture = asset_fixture.AssetLifecycleTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        project = fixture.root / "project"
        project.mkdir()
        (project / "index.html").write_text("<h1>Ready</h1>", encoding="utf-8")
        fixture.put_conversation("preview-chat", thread_id="preview-thread", project_path=str(project))
        preview = PreviewService(fixture.paths, idle_seconds=60)
        self.addCleanup(preview.shutdown)
        preview.start_static("preview-thread", str(project), "index.html")
        owner = preview._owned["preview-thread"]
        def cleanup_owner():
            from workbench_backend.preview.service import _kill_tree
            _kill_tree(owner.process, owner.job)
            owner.log_file.close()
        self.addCleanup(cleanup_owner)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            asset_lifecycle=fixture.lifecycle, preview=preview,
            chat=SimpleNamespace(store=SimpleNamespace(get=fixture.store.get_conversation, conversation_lock=lambda _: nullcontext())),
            manager=SimpleNamespace(lifecycle=SimpleNamespace(mutate=lambda _: nullcontext())),
        )))
        body = SimpleNamespace(execute=True, include_diagnostics=False)
        with patch("workbench_backend.preview.service._kill_tree", return_value=False):
            with self.assertRaises(HTTPException) as blocked:
                delete_conversation(request, "preview-chat", body)
            self.assertEqual(blocked.exception.status_code, 409)
            self.assertIsNotNone(fixture.store.get_conversation("preview-chat"))
            self.assertIs(preview._owned.get("preview-thread"), owner)
            self.assertTrue(preview.status("preview-thread")["stop_pending"])
            self.assertFalse(owner.log_file.closed)
            with self.assertRaises(HarnessError):
                preview.reset_lost("preview-thread")
            with self.assertRaises(HarnessError):
                preview.start_static("preview-thread", str(project), "index.html")
        deleted = delete_conversation(request, "preview-chat", body)
        self.assertEqual(deleted.conversation_id, "preview-chat")
        self.assertIsNone(fixture.store.get_conversation("preview-chat"))
        self.assertNotIn("preview-thread", preview._owned)
        self.assertTrue(owner.log_file.closed)
        self.assertEqual(preview.status("preview-thread")["state"], "closed")


class WindowsStopIdentityTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows job identity")
    def test_final_owners_still_release_job_handle_on_unconfirmed_stop(self):
        closed = []
        def query(handle, kind, pointer, size, returned):
            if kind == 3:
                pointer._obj.count = 0
            return kind == 3
        def close(handle):
            closed.append(handle)
            return True
        kernel = SimpleNamespace(QueryInformationJobObject=query, CloseHandle=close,
            TerminateJobObject=lambda *args: True, OpenProcess=lambda *args: 0,
            WaitForSingleObject=lambda *args: 0)
        job = WindowsJob(1234)
        with patch("workbench_backend.process_tree.ctypes.WinDLL", return_value=kernel):
            self.assertFalse(job.stop())
        self.assertEqual(closed, [1234])
        self.assertEqual(job.handle, 0)

    @unittest.skipUnless(sys.platform == "win32", "Windows job identity")
    def test_unconfirmed_query_retains_exact_job_handle_for_retry(self):
        closed = []
        attempts = []
        def query(handle, kind, pointer, size, returned):
            if kind == 3:
                pointer._obj.count = 0
                return True
            attempts.append(handle)
            pointer._obj.active_processes = 0
            return len(attempts) > 1
        def close(handle):
            closed.append(handle)
            return True
        kernel = SimpleNamespace(QueryInformationJobObject=query, CloseHandle=close,
            TerminateJobObject=lambda *args: True, OpenProcess=lambda *args: 0,
            WaitForSingleObject=lambda *args: 0)
        job = WindowsJob(1234)
        with patch("workbench_backend.process_tree.ctypes.WinDLL", return_value=kernel):
            self.assertFalse(job.stop(retain_on_failure=True))
            self.assertEqual(job.handle, 1234)
            self.assertEqual(closed, [])
            self.assertTrue(job.stop(retain_on_failure=True))
        self.assertEqual(attempts, [1234, 1234])
        self.assertEqual(closed, [1234])
        self.assertEqual(job.handle, 0)
