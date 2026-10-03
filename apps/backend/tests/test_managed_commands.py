"""Real managed-command ownership, retained output and truthful recovery."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import psutil
from langchain_core.tools import ToolException

from workbench_backend.agents.managed_commands import ManagedCommandService
from workbench_backend.agents.tool_results import OwnedToolResults
from workbench_backend.errors import HarnessError
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore


class ManagedCommandsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.paths = WorkbenchPaths(self.root / "data").ensure()
        self.store = ApplicationStore(self.paths)
        self.service = ManagedCommandService(self.paths, app_store=self.store)
        self.run = SimpleNamespace(id="run_command", thread_id="thread_command", parent_run_id=None,
            project_path=str(self.project), status="running", work_mode="work", tool_mode="live-tool", presented_tools=["start_command", "command_status", "stop_command"])
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.addCleanup(self.service.shutdown)

    def script(self, text):
        path = self.project / "fixture.py"
        path.write_text(text, encoding="utf-8")
        return [sys._base_executable, str(path)]

    def test_late_failure_output_owner_and_known_recovery(self):
        launch = self.service.start(self.run, self.script("import sys\nprint('earlier '+ 'x'*30000)\nprint('late error',flush=True)\nsys.exit(7)"), 10)
        status = self.service.status(self.run, launch["command_id"], wait_seconds=10)
        self.assertEqual(status["state"], "completed")
        self.assertEqual(status["exit_code"], 7)
        self.assertTrue(status["process_stop_confirmed"])
        self.assertIn("late error", status["preview"])
        found = OwnedToolResults(self.paths, self.run).read(status["retained_result"]["path"], query="earlier")
        self.assertEqual(found["match_count"], 1)
        other = SimpleNamespace(id="other", thread_id="other", parent_run_id=None)
        with self.assertRaises(ToolException):
            self.service.status(other, launch["command_id"])
        recovered = ManagedCommandService(self.paths, app_store=self.store)
        self.assertEqual(recovered.status(self.run, launch["command_id"])["exit_code"], 7)

    def test_run_cleanup_stops_tree_and_never_claims_lost_identity(self):
        launch = self.service.start(self.run, self.script("import time\nprint('ready',flush=True)\ntime.sleep(30)"), 60)
        restarted = ManagedCommandService(self.paths, app_store=self.store)
        unknown = restarted.status(self.run, launch["command_id"])
        self.assertEqual(unknown["state"], "lost")
        self.assertFalse(unknown["process_stop_confirmed"])
        with self.assertRaises(HarnessError):
            restarted.stop(self.run, launch["command_id"])
        self.assertTrue(psutil.pid_exists(launch["pid"]))
        self.service.stop_run(self.run.id)
        self.assertFalse(psutil.pid_exists(launch["pid"]))
        self.assertEqual(self.service.stop(self.run, launch["command_id"])["state"], "stopped")

    def test_timeout_and_cancel_are_distinct_confirmed_outcomes(self):
        outcomes = []
        argv = self.script("import time\ntime.sleep(30)")
        timeout = self.service.start(self.run, argv, 1, record_outcome=outcomes.append)
        self.assertEqual(self.service.status(self.run, timeout["command_id"], wait_seconds=10)["state"], "timed_out")
        self.assertEqual([row.outcome for row in outcomes], ["running", "uncertain"])
        self.assertEqual((outcomes[-1].recovery_action, outcomes[-1].evidence["exit_code"]), ("inspect_effects", 124))
        record = self.service.effects.get_effect(self.service._commands[timeout["command_id"]].effect_id)
        self.assertFalse(record.unresolved, "the process lifecycle is confirmed separately from its partial effects")
        self.assertEqual(record.evidence["effect_scope"], "process_lifecycle")
        self.assertTrue(record.evidence["partial_effects_unconfirmed"])
        cancel = threading.Event()
        created = self.service.start(self.run, argv, 30, cancel_requested=cancel.is_set, record_outcome=outcomes.append)
        cancel.set()
        self.service.stop_run(self.run.id)  # Cleanup racing the watcher must preserve cancellation evidence.
        status = self.service.status(self.run, created["command_id"], wait_seconds=10)
        self.assertEqual((status["state"], status["exit_code"]), ("cancelled", 130))
        self.assertFalse(psutil.pid_exists(created["pid"]))
        self.assertEqual([row.outcome for row in outcomes], ["running", "uncertain", "running", "uncertain"])
        self.assertEqual((outcomes[-1].failure_category, outcomes[-1].evidence["exit_code"]), ("cancelled", 130))

    def test_explicit_stop_and_known_completion_do_not_create_partial_effect_warning(self):
        outcomes = []
        argv = self.script("import time\ntime.sleep(30)")
        stopped = self.service.start(self.run, argv, 30, record_outcome=outcomes.append)
        self.assertEqual(self.service.stop(self.run, stopped["command_id"])["state"], "stopped")
        completed = self.service.start(self.run, self.script("import sys\nsys.exit(7)"), 30, record_outcome=outcomes.append)
        self.assertEqual(self.service.status(self.run, completed["command_id"], wait_seconds=10)["exit_code"], 7)
        self.assertEqual([row.outcome for row in outcomes], ["running", "succeeded", "running", "failed"])
        self.assertTrue(all(row.outcome != "uncertain" for row in outcomes))

    def test_cancellation_during_launch_waits_for_that_command_cleanup(self):
        entered, release = threading.Event(), threading.Event()
        real_start = self.service.start
        def blocked(*args, **kwargs):
            entered.set()
            release.wait(5)
            return real_start(*args, **kwargs)
        async def interrupted():
            with patch.object(self.service, "start", side_effect=blocked):
                start = self.service.tools_for_run(self.run)[0]
                task = asyncio.create_task(start.coroutine(command=self.script("import time\ntime.sleep(30)")))
                await asyncio.to_thread(entered.wait, 5)
                task.cancel()
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        asyncio.run(interrupted())
        self.assertTrue(self.service._commands)
        self.assertTrue(all(command.settled.is_set() for command in self.service._commands.values()))

    @unittest.skipUnless(os.name == "nt", "Windows job descendant ownership")
    def test_launcher_exit_cannot_orphan_detached_descendant(self):
        argv = self.script("import sys,subprocess,time\nfrom pathlib import Path\nif len(sys.argv)>1:\n Path('child-ready').write_text('ready')\n time.sleep(30)\nelse:\n p=subprocess.Popen([sys.executable,__file__,'child'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True,creationflags=subprocess.CREATE_NO_WINDOW)\n Path('child.pid').write_text(str(p.pid))\n end=time.monotonic()+5\n while not Path('child-ready').exists() and time.monotonic()<end:time.sleep(.01)\n")
        launched = self.service.start(self.run, argv, 10)
        self.assertEqual(self.service.status(self.run, launched["command_id"], wait_seconds=10)["state"], "completed")
        self.assertTrue((self.project / "child-ready").is_file())
        self.assertFalse(psutil.pid_exists(int((self.project / "child.pid").read_text())))

    def test_unconfirmed_stop_is_an_error_and_not_replayed(self):
        outcomes = []
        launch = self.service.start(self.run, self.script("import time\ntime.sleep(30)"), 60, record_outcome=outcomes.append)
        from workbench_backend.agents import managed_commands
        real_stop = managed_commands.stop_process_tree
        def unconfirmed(*args):
            real_stop(*args)
            return False
        with patch.object(managed_commands, "stop_process_tree", side_effect=unconfirmed):
            with self.assertRaisesRegex(HarnessError, "uncertain"):
                self.service.stop(self.run, launch["command_id"])
        self.assertEqual(self.service.status(self.run, launch["command_id"])["state"], "uncertain")
        self.assertEqual([row.outcome for row in outcomes], ["running", "uncertain"])
        self.assertFalse(outcomes[-1].evidence["process_stopped"])

    def test_cleanup_attempts_every_command_before_reporting_failure(self):
        argv = self.script("import time\ntime.sleep(30)")
        first = self.service.start(self.run, argv, 60)
        second = self.service.start(self.run, argv, 60)
        real_stop = self.service.stop
        attempted = []
        def failed_first(run, ident):
            attempted.append(ident)
            result = real_stop(run, ident)
            if ident == first["command_id"]:
                raise HarnessError("fixture uncertainty", code="command_stop_unconfirmed")
            return result
        with patch.object(self.service, "stop", side_effect=failed_first):
            with self.assertRaisesRegex(HarnessError, "every owned command"):
                self.service.stop_run(self.run.id)
        self.assertEqual(attempted, [first["command_id"], second["command_id"]])
        self.assertFalse(psutil.pid_exists(second["pid"]))
