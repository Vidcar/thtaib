"""Real native Unicode searches and narrowly scoped read-error recovery."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
import psutil

from workbench_backend import __main__ as entrypoint
from workbench_backend.agents.tool_errors import recoverable_tool_error
from workbench_backend.errors import HarnessError, InteractionPersistenceError


class TextDecodingTests(unittest.TestCase):
    def test_windows_bootstrap_forwards_arguments_streams_environment_and_exit(self):
        arguments = ["--host", "127.0.0.1", "--port", "8123"]
        before = dict(os.environ)
        with patch.object(entrypoint.sys, "platform", "win32"), \
                patch.object(entrypoint.sys, "flags", SimpleNamespace(utf8_mode=0)), \
                patch.object(entrypoint.subprocess, "call", return_value=7) as launch:
            with self.assertRaises(SystemExit) as stopped:
                entrypoint.main(arguments)
        self.assertEqual(stopped.exception.code, 7)
        launch.assert_called_once_with([sys.executable, "-X", "utf8", "-m", "workbench_backend", *arguments])
        self.assertEqual(dict(os.environ), before)

    def test_already_utf8_entrypoint_does_not_relaunch(self):
        app = SimpleNamespace(state=SimpleNamespace())
        module = SimpleNamespace(app=app, create_app=lambda: app)
        with patch.object(entrypoint.sys, "platform", "win32"), \
                patch.object(entrypoint.sys, "flags", SimpleNamespace(utf8_mode=1)), \
                patch.object(entrypoint.subprocess, "call") as launch, \
                patch.dict(sys.modules, {"workbench_backend.app": module}), \
                patch.object(entrypoint.uvicorn, "Config"), \
                patch.object(entrypoint.uvicorn, "Server") as server:
            entrypoint.main([])
        launch.assert_not_called()
        server.return_value.run.assert_called_once()

    def test_only_read_and_search_decode_errors_are_recoverable(self):
        decode = UnicodeDecodeError("cp1252", b"\x9d", 0, 1, "character maps to <undefined>")
        for name in ("grep", "read_file"):
            result = recoverable_tool_error(decode, name=name, call_id="same-call")
            self.assertEqual((result.name, result.tool_call_id, result.status), (name, "same-call", "error"))
            self.assertIn("No complete result", result.content)
            self.assertIn("cp1252", result.content)
        for name in ("write_file", "edit_file", "execute", "browser_snapshot", "other"):
            self.assertIsNone(recoverable_tool_error(decode, name=name, call_id="same-call"))
        for error in (asyncio.CancelledError(), InteractionPersistenceError(),
                      HarnessError("unknown effect", code="unknown"), OSError("storage failed"),
                      UnicodeEncodeError("cp1252", "\u275a", 0, 1, "unencodable")):
            for name in ("grep", "read_file"):
                self.assertIsNone(recoverable_tool_error(error, name=name, call_id="same-call"))

    @unittest.skipUnless(shutil.which("rg"), "actual ripgrep required")
    def test_real_utf8_search_all_native_routes_sync_and_async(self):
        # Child startup, rather than a locale mock, exercises Python's real
        # TextIOWrapper used by the installed upstream ripgrep implementation.
        program = r'''
import asyncio, json, tempfile
from pathlib import Path
from deepagents.backends import CompositeBackend
from workbench_backend.agents.harness_backend import FilesystemBackend, BoundedImageLocalShellBackend
content = 'paint \u25b6\u275a\u275a\u2014\npaint caf\u00e9\npaint \u65e5\u672c\u8a9e\n'
with tempfile.TemporaryDirectory() as directory:
 root = Path(directory)
 name = 'caf\u00e9-\u65e5.js'
 (root / name).write_text(content, encoding='utf-8', newline='')
 scratch = root / 'scratch'
 scratch.mkdir()
 (scratch / name).write_text(content, encoding='utf-8', newline='')
 routes = {'/conversation_history/': FilesystemBackend(root_dir=scratch, virtual_mode=True)}
 backends = [FilesystemBackend(root_dir=root, virtual_mode=True),
             BoundedImageLocalShellBackend(root_dir=root, virtual_mode=True),
             CompositeBackend(default=FilesystemBackend(root_dir=root, virtual_mode=True), routes=routes)]
 checked = 0
 for index, backend in enumerate(backends):
  path = ('/conversation_history/' if index == 2 else '/') + name
  for cap in [2, 3]:
   for result in [backend.grep('paint', path, max_count=cap), asyncio.run(backend.agrep('paint', path, max_count=cap))]:
    assert result.error is None, result.error
    assert len(result.matches) == cap, result
    assert result.truncated == (cap == 2), result
    assert [m['text'] for m in result.matches] == content.splitlines()[:cap], result
    assert all(m['path'] == path for m in result.matches), result
    checked += 1
  result = backend.grep('absent', path)
  assert result.error is None and not result.matches and not result.truncated, result
 print(json.dumps({'checked': checked}))
'''
        completed = subprocess.run([sys.executable, "-X", "utf8", "-c", program],
            capture_output=True, encoding="utf-8", timeout=45)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["checked"], 12)

    @unittest.skipUnless(os.name == "nt", "Windows host output")
    def test_host_output_keeps_ansi_locale_under_utf8_mode(self):
        program = r'''
import json, locale, os, subprocess, sys, tempfile
from pathlib import Path
from workbench_backend.process_tree import run_windows_command
assert sys.flags.utf8_mode == 1
encoding = locale.getencoding()
text = 'caf\u00e9'
with tempfile.TemporaryDirectory() as directory:
 root = Path(directory)
 script = root / 'emit.py'
 script.write_text('import sys\nsys.stdout.buffer.write(' + repr(text.encode(encoding)) + ')\n', encoding='utf-8')
 command = subprocess.list2cmdline([sys.executable, str(script)])
 result = run_windows_command(command, cwd=root, env=dict(os.environ), timeout=10)
 assert result.returncode == 0 and result.stdout == text, repr(result)
 print(json.dumps({'host_encoding': encoding, 'text': result.stdout}))
'''
        completed = subprocess.run([sys.executable, "-X", "utf8", "-c", program],
            capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["text"], "caf\u00e9")


@unittest.skipUnless(os.name == "nt", "Windows backend entrypoints")
class WindowsUtf8EntrypointTests(unittest.TestCase):
    def test_real_console_and_module_bootstrap_keep_lifecycle_and_unicode_root(self):
        console = Path(sys.executable).with_name("workbench-backend.exe")
        self.assertTrue(console.is_file())
        for argv in ([sys.executable, "-X", "utf8=0", "-m", "workbench_backend"], [str(console)]):
            with self.subTest(entrypoint=argv), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "isolated data caf\u00e9"
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", 0))
                    port = listener.getsockname()[1]
                log_path = Path(directory) / "backend.log"
                with log_path.open("wb") as log:
                    process = subprocess.Popen([*argv, "--host", "127.0.0.1", "--port", str(port)],
                        env={**os.environ, "PYTHONUTF8": "0", "WORKBENCH_DATA_ROOT": str(root)},
                        stdout=log, stderr=log)
                    try:
                        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=3) as client:
                            deadline = time.monotonic() + 30
                            while time.monotonic() < deadline:
                                self.assertIsNone(process.poll(), log_path.read_text(encoding="utf-8", errors="replace"))
                                try:
                                    if client.get("/health").status_code == 200:
                                        break
                                except httpx.TransportError:
                                    pass
                                time.sleep(.05)
                            else:
                                self.fail("Backend startup timed out")
                            descendants = psutil.Process(process.pid).children(recursive=True)
                            # Windows venv executables are redirector processes;
                            # the leaf interpreter is the actual backend worker.
                            utf8_children = [child for child in descendants if "utf8" in child.cmdline() and not child.children()]
                            self.assertEqual(len(utf8_children), 1, [child.cmdline() for child in descendants])
                            token = (root / "state/desktop_backend_shared_secret").read_text(encoding="utf-8").strip()
                            client.headers["X-Workbench-Local-Token"] = token
                            self.assertTrue(client.post("/v1/desktop/stop-owned-work", json={}).json()["stopped"])
                            process.wait(timeout=12)
                            self.assertEqual(process.returncode, 0)
                            self.assertTrue((root / "application.sqlite").is_file())
                    finally:
                        if process.poll() is None:
                            children = psutil.Process(process.pid).children(recursive=True)
                            for child in reversed(children):
                                try:
                                    child.kill()
                                except psutil.NoSuchProcess:
                                    pass
                            process.kill()
                            process.wait(timeout=5)
                self.assertEqual(log_path.read_text(encoding="utf-8").count("Started server process"), 1)
