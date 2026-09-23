"""Real loopback process restart/authorization and deliberate quit."""
from contextlib import closing
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import httpx


class DesktopLifecycleTests(unittest.TestCase):
    def test_quit_closes_connected_observer_without_waiting_for_client_disconnect(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "data"
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            log_path = Path(temporary) / "backend.log"
            with log_path.open("wb") as log:
                process = subprocess.Popen([sys.executable, "-m", "workbench_backend", "--port", str(port)],
                    env=dict(os.environ, WORKBENCH_DATA_ROOT=str(root)), stdout=log, stderr=log)
                try:
                    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=3) as client:
                        deadline = time.monotonic() + 30
                        while time.monotonic() < deadline:
                            self.assertIsNone(process.poll(), log_path.read_text(errors="replace"))
                            try:
                                if client.get("/health").status_code == 200:
                                    break
                            except httpx.TransportError:
                                pass
                            time.sleep(.05)
                        else:
                            self.fail("Backend startup timed out: " + log_path.read_text(errors="replace"))
                        token = (root / "state/desktop_backend_shared_secret").read_text().strip()
                        client.headers["X-Workbench-Local-Token"] = token
                        registered = client.post("/v1/agent-interaction/threads", json={"source_surface": "agent"})
                        registered.raise_for_status()
                        thread_id = registered.json()["thread_id"]
                        work = client.get("/v1/desktop/work").json()
                        self.assertEqual(work["active_run_ids"], [])
                        # Retain the real HTTP response through process exit: a
                        # view must not keep a quiescent application's Quit open.
                        with client.stream("POST", f"/v1/agent-interaction/threads/{thread_id}/stream/events",
                            json={"channels": ["values", "lifecycle"]}) as observer:
                            observer.raise_for_status()
                            self.assertIn("text/event-stream", observer.headers["content-type"])
                            lines = observer.iter_lines()
                            stopped = client.post("/v1/desktop/stop-owned-work", json={})
                            stopped.raise_for_status()
                            self.assertTrue(stopped.json()["stopped"])
                            process.wait(timeout=8)
                            self.assertEqual(process.returncode, 0, log_path.read_text(errors="replace"))
                            self.assertEqual(list(lines), [])
                    self.assertNotIn("timeout graceful shutdown exceeded", log_path.read_text(errors="replace").lower())
                    with closing(sqlite3.connect(root / "application.sqlite")) as connection:
                        self.assertEqual(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)
                        self.assertEqual(connection.execute("SELECT id FROM interaction_threads").fetchone()[0], thread_id)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)

    def test_rejected_quit_does_not_signal_observers(self):
        from workbench_backend.app import create_app
        from tests.support import offline_workbench_client
        with tempfile.TemporaryDirectory() as temporary:
            application = create_app(data_root=Path(temporary))
            callbacks = []
            def stop_service():
                callbacks.append(True)
                application.state.shutdown_requested.set()
            application.state.shutdown_backend = stop_service
            with offline_workbench_client(application) as client:
                application.state.maintenance_gate.begin("backup")
                try:
                    response = client.post("/v1/desktop/stop-owned-work", json={})
                    self.assertEqual(response.status_code, 409, response.text)
                    self.assertFalse(callbacks)
                    self.assertFalse(application.state.shutdown_requested.is_set())
                    self.assertEqual(application.state.maintenance_gate.active_reason, "backup")
                finally:
                    application.state.maintenance_gate.end()

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
