"""Real loopback process restart/authorization and deliberate quit."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class DesktopLifecycleTests(unittest.TestCase):
    def test_restore_activation_restarts_with_fresh_auth_then_quit_exits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "original"
            root.mkdir()
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            environment = dict(os.environ, WORKBENCH_DATA_ROOT=str(root))
            log_path = Path(temporary) / "backend.log"
            with log_path.open("wb") as log:
                process = subprocess.Popen([sys.executable, "-m", "workbench_backend", "--port", str(port)],
                    env=environment, stdout=log, stderr=log)
                def request(route, token=None, body=None):
                    headers = {"Content-Type": "application/json"}
                    if token:
                        headers["X-Workbench-Local-Token"] = token
                    data = json.dumps(body).encode() if body is not None else None
                    req = urllib.request.Request(f"http://127.0.0.1:{port}{route}", data=data, headers=headers)
                    with urllib.request.urlopen(req, timeout=3) as response:
                        return json.load(response)
                def ready(token=None):
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            self.fail("Backend exited: " + log_path.read_text(errors="replace"))
                        try:
                            request("/v1/desktop/work" if token else "/health", token)
                            return
                        except (OSError, urllib.error.URLError):
                            time.sleep(.05)
                    self.fail("Backend startup timed out: " + log_path.read_text(errors="replace"))
                try:
                    ready()
                    original_token = (root / "state/desktop_backend_shared_secret").read_text().strip()
                    archive = request("/v1/backups", original_token, {"destination": str(Path(temporary) / "backup.zip")})
                    destination = Path(temporary) / "restored"
                    restored = request("/v1/backups/restore", original_token,
                        {"archive_path": archive["archive_path"], "destination_root": str(destination)})
                    self.assertFalse(restored["activated"])
                    activated = request("/v1/backups/activate", original_token, {"destination_root": str(destination)})
                    self.assertTrue(activated["restarting"])
                    fresh_token = (destination / "state/desktop_backend_shared_secret").read_text().strip()
                    self.assertNotEqual(fresh_token, original_token)
                    ready(fresh_token)
                    with self.assertRaises(urllib.error.HTTPError) as forbidden:
                        request("/v1/desktop/work", original_token)
                    self.assertEqual(forbidden.exception.code, 403)
                    self.assertTrue(request("/v1/desktop/stop-owned-work", fresh_token, {})["stopped"])
                    process.wait(timeout=15)
                    self.assertEqual(process.returncode, 0)
                    self.assertTrue((root / "application.sqlite").is_file())
                    self.assertTrue(Path(archive["archive_path"]).is_file())
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
