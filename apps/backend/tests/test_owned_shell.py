"""Windows shell completion means the entire owned process tree settled."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import psutil

from workbench_backend.agents.owned_shell import OwnedLocalShellBackend
from workbench_backend.errors import HarnessError
from workbench_backend.process_tree import WindowsJob


@unittest.skipUnless(os.name == "nt", "Windows process-tree ownership")
class OwnedShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.script = self.root / "fixture.py"
        self.script.write_text(
            "import os,sys,subprocess,time,threading\nfrom pathlib import Path\n"
            "if sys.argv[1]=='child':\n"
            " with Path('held.txt').open('w') as held:\n"
            "  held.write('held'); held.flush(); Path('ready').write_text('ready')\n"
            "  threading.Event().wait(20)\n"
            "else:\n"
            " child=subprocess.Popen([sys.executable,__file__,'child'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True,creationflags=subprocess.CREATE_NO_WINDOW)\n"
            " Path('child.pid').write_text(str(child.pid))\n"
            " deadline=time.monotonic()+5\n"
            " while not Path('ready').exists() and time.monotonic()<deadline: threading.Event().wait(.01)\n"
            " if sys.argv[1]=='wait': threading.Event().wait(20)\n",
            encoding="utf-8")
        self.backend = OwnedLocalShellBackend(root_dir=self.root, inherit_env=True)

    def tearDown(self):
        pid_file = self.root / "child.pid"
        if pid_file.exists():
            try:
                child = psutil.Process(int(pid_file.read_text()))
                if str(self.script).lower() in " ".join(child.cmdline()).lower():
                    child.kill()
                    child.wait(5)
            except psutil.NoSuchProcess:
                pass
        self.temp.cleanup()

    def command(self, mode):
        return f'"{sys._base_executable}" "{self.script}" {mode}'

    def assert_child_stopped(self):
        self.assertTrue((self.root / "ready").exists(), "The grandchild ran before termination")
        child_pid = int((self.root / "child.pid").read_text())
        self.assertFalse(psutil.pid_exists(child_pid), "No live descendant after tool result")
        (self.root / "held.txt").unlink()  # Its inherited/native file handles have also closed.

    def test_timeout_reaps_detached_grandchild_before_returning(self):
        result = self.backend.execute(self.command("wait"), timeout=2)
        self.assertEqual(result.exit_code, 124)
        self.assertIn("owned process tree has stopped", result.output)
        self.assert_child_stopped()

    def test_normal_shell_exit_cannot_leave_background_work(self):
        result = self.backend.execute(self.command("exit"), timeout=10)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assert_child_stopped()

    def test_cancellation_reaps_tree_before_the_waiter_settles(self):
        cancel = threading.Event()
        self.backend._cancel_requested = cancel.is_set
        result = []
        worker = threading.Thread(target=lambda: result.append(self.backend.execute(self.command("wait"), timeout=20)))
        worker.start()
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "ready").exists() and time.monotonic() < deadline:
                threading.Event().wait(.01)
            self.assertTrue((self.root / "ready").exists())
        finally:
            cancel.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result[0].exit_code, 130)
        self.assert_child_stopped()

    def test_unconfirmed_stop_is_not_a_correctable_command_result(self):
        real_stop = WindowsJob.stop
        def unconfirmed(job):
            real_stop(job)
            return False
        with patch.object(WindowsJob, "stop", unconfirmed):
            with self.assertRaises(HarnessError) as caught:
                self.backend.execute("echo stopped", timeout=5)
        self.assertEqual(caught.exception.code, "shell_stop_unconfirmed")

    def test_native_nonzero_exit_and_output_contract(self):
        result = self.backend.execute("echo expected & echo problem 1>&2 & exit /b 7", timeout=5)
        self.assertEqual(result.exit_code, 7)
        self.assertIn("expected", result.output)
        self.assertIn("[stderr] problem", result.output)
        self.assertIn("Exit code: 7", result.output)


if __name__ == "__main__":
    unittest.main()
