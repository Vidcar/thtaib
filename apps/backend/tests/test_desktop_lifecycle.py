"""Real loopback process restart/authorization and deliberate quit."""
from contextlib import closing, contextmanager, ExitStack
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx


class QueuedDesktopQuitTests(unittest.TestCase):
    @contextmanager
    def owned_router(self):
        """Real route, records and guards; only native router I/O is scripted."""
        from workbench_backend.app import create_app
        from workbench_backend.inference.schemas import Deployment, HealthReport, ProcessIdentity, ResourceUsage, ServerProperties
        from tests.support import close_workbench_sqlite, offline_workbench_client
        with tempfile.TemporaryDirectory() as temporary:
            application = create_app(data_root=Path(temporary))
            client = offline_workbench_client(application)
            manager = application.state.manager
            deployment = manager.store.put_deployment(Deployment(id="owned", display_name="Owned model",
                scope="managed", status="running", bundle_id="bundle", profile_id="profile",
                requested_startup={"ctx_size": 4096}, created_at="now", updated_at="now"))
            connected = manager.store.put_deployment(Deployment(id="connected", display_name="External model",
                scope="connected", status="running", endpoint="http://127.0.0.1:9/v1", created_at="now", updated_at="now"))
            router = manager.deployments.router
            identity = ProcessIdentity(pid=123, create_time=1.0, executable="fixture-owned-router")
            record = {"endpoint": "http://127.0.0.1:18080/v1", "identity": identity}
            resident = {"owned": True, "loaded": True}
            stopped = []
            application.state.shutdown_backend = lambda: stopped.append(True)

            def post(endpoint, route, payload):
                self.assertEqual((endpoint, route, payload), (record["endpoint"], "/models/unload", {"model": deployment.id}))
                resident["loaded"] = False

            def stop_process(actual):
                self.assertEqual(actual, identity)
                resident["owned"] = False

            try:
                with ExitStack() as patches:
                    patches.enter_context(patch.object(manager.deployments, "_router_enabled", return_value=True))
                    patches.enter_context(patch.object(router, "_owned_record", side_effect=lambda: record if resident["owned"] else None))
                    patches.enter_context(patch.object(router, "_inventory", side_effect=lambda *_args, **_kwargs: {
                        deployment.id: {"id": deployment.id, "status": {"value": "loaded" if resident["loaded"] else "unloaded"}}}))
                    unload = patches.enter_context(patch.object(router, "_post", side_effect=post))
                    stop = patches.enter_context(patch.object(router.processes, "stop", side_effect=stop_process))
                    patches.enter_context(patch.object(router.processes, "classify", side_effect=lambda _identity: "match" if resident["owned"] else "gone"))
                    patches.enter_context(patch.object(router.processes, "resource_usage", return_value=ResourceUsage(available=True)))
                    patches.enter_context(patch.object(router.probe, "props", return_value=ServerProperties(fetched="now", source_url="fixture")))
                    patches.enter_context(patch.object(router.probe, "health", return_value=HealthReport(healthy=True, endpoint=record["endpoint"], checked="now", detail="fixture")))
                    yield application, client, deployment, connected, unload, stop, stopped
            finally:
                close_workbench_sqlite(application, client)

    def queued_chat(self, application, *, status="paused", reason="cancelled", run_id=None):
        from workbench_backend.chat.schemas import ChatConversation, ChatQueueItem
        return application.state.chat.store.put(ChatConversation(id="quit-chat", title="Queued cancellation",
            deployment_id="owned", profile_id="profile", current_run_id=run_id, run_ids=[run_id] if run_id else [],
            created_at="now", updated_at="now", queue=[ChatQueueItem(id="queued", task="Retain this input",
                input_message_id="exact-input", status=status, pause_reason=reason, run_id=run_id,
                frozen_config={"deployment_id": "owned", "profile_id": "profile", "per_request": {"temperature": 0.35}},
                created_at="now", updated_at="now")]))

    def test_quit_after_queued_cancel_stops_owned_engine_and_retains_frozen_input(self):
        with self.owned_router() as (app, client, deployment, connected, unload, stop, stopped):
            before = self.queued_chat(app)
            app.state.app_store.request_chat_submission_cancel(before.id, "exact-input")
            app.state.app_store.resolve_chat_submission_cancel(before.id, "exact-input")
            self.assertEqual(client.get("/v1/desktop/work").json(), {"active_run_ids": [], "active_import_ids": []})
            response = client.post("/v1/desktop/stop-owned-work", json={})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["stopped"])
            unload.assert_called_once()
            stop.assert_called_once()
            self.assertEqual(stopped, [True])
            self.assertEqual(app.state.manager.get_deployment(deployment.id).status, "stopped")
            self.assertEqual(app.state.manager.get_deployment(connected.id), connected)
            self.assertEqual(app.state.chat.store.get(before.id).queue, before.queue)
            self.assertTrue(app.state.app_store.chat_submission_cancel_known(before.id, "exact-input"))
            self.assertEqual(app.state.app_store.list_runs_operational(), [])

    def test_quit_retains_paused_uncertainty_and_never_dispatches_queued_work(self):
        for status, reason in (("queued", None), ("paused", "dispatch_uncertain"), ("dispatching", None)):
            with self.subTest(status=status), self.owned_router() as (app, client, _, _, unload, stop, stopped):
                before = self.queued_chat(app, status=status, reason=reason)
                with patch.object(app.state.harness, "start") as start:
                    response = client.post("/v1/desktop/stop-owned-work", json={})
                self.assertEqual(response.status_code, 200, response.text)
                start.assert_not_called()
                saved = app.state.chat.store.get(before.id).queue[0]
                self.assertEqual(saved.status, "paused")
                self.assertEqual(saved.pause_reason, "dispatch_uncertain" if status != "queued" else "cancelled")
                self.assertEqual(saved.input_message_id, before.queue[0].input_message_id)
                self.assertEqual(saved.frozen_config, before.queue[0].frozen_config)
                self.assertEqual(saved.task, before.queue[0].task)
                self.assertEqual(app.state.app_store.list_runs_operational(), [])
                unload.assert_called_once()
                stop.assert_called_once()
                self.assertEqual(stopped, [True])

    def terminal_run(self, app, *, status="cancelled", finalization_phase=None):
        from workbench_backend.agents.schemas import AgentRun
        run = AgentRun(id="terminal", status=status, deployment_id="owned", task="Retain this input",
            input_message_id="exact-input", source_surface="chat", thread_id="thread", enabled_tools=[],
            presented_tools=[], finalization_phase=finalization_phase, created_at="now", updated_at="now")
        app.state.harness.store.put_run(run)
        app.state.harness._runs[run.id] = run
        return run

    def test_quit_retains_unresolved_external_outcomes_without_replaying_input(self):
        from workbench_backend.agents.schemas import ToolOutcome
        with self.owned_router() as (app, client, _, _, _, stop, _):
            run = self.terminal_run(app)
            run.input_message_id = "prior-input"
            run.tool_outcomes = {"call": ToolOutcome(call_id="call", name="execute", outcome="uncertain",
                recovery_action="inspect_effects", detail="External completion was not confirmed", updated_at="now")}
            app.state.harness.store.put_run(run)
            before = self.queued_chat(app, reason="failed")
            app.state.chat.store.put(before.model_copy(update={"current_run_id": run.id, "run_ids": [run.id]}))
            with patch.object(app.state.harness, "start") as start:
                response = client.post("/v1/desktop/stop-owned-work", json={})
            self.assertEqual(response.status_code, 200, response.text)
            start.assert_not_called()
            stop.assert_called_once()
            self.assertEqual(app.state.chat.store.get(before.id).queue, before.queue)
            self.assertEqual(app.state.harness.store.get_execution_run(run.id).tool_outcomes, run.tool_outcomes)

    def test_quit_joins_terminal_worker_before_queue_reconciliation_and_unload(self):
        with self.owned_router() as (app, client, _, _, unload, stop, stopped):
            run = self.terminal_run(app)
            self.queued_chat(app, status="dispatching", reason=None, run_id=run.id)
            release, joining = threading.Event(), threading.Event()
            worker = threading.Thread(target=lambda: release.wait(8))
            worker.start()
            app.state.harness._threads[run.id] = worker
            original_close = app.state.harness.close
            responses = []

            def close(**kwargs):
                joining.set()
                return original_close(**kwargs)

            request = threading.Thread(target=lambda: responses.append(client.post("/v1/desktop/stop-owned-work", json={})))
            try:
                with patch.object(app.state.harness, "close", side_effect=close), patch.object(app.state.harness, "start") as start:
                    request.start()
                    self.assertTrue(joining.wait(5))
                    self.assertTrue(worker.is_alive())
                    unload.assert_not_called()
                    stop.assert_not_called()
                    self.assertEqual(app.state.chat.store.get("quit-chat").queue[0].status, "dispatching")
                    release.set()
                    request.join(8)
                    self.assertFalse(request.is_alive())
                    start.assert_not_called()
            finally:
                release.set()
                worker.join(8)
                request.join(8)
            self.assertEqual(responses[0].status_code, 200, responses[0].text)
            self.assertEqual(app.state.chat.store.get("quit-chat").queue, [])
            self.assertEqual(app.state.chat.store.get("quit-chat").current_run_id, run.id)
            self.assertEqual(app.state.harness.get_run_operational(run.id).status, "cancelled")
            unload.assert_called_once()
            stop.assert_called_once()
            self.assertEqual(stopped, [True])

    def test_unjoined_terminal_worker_blocks_quit_and_harness_remains_usable(self):
        from langchain_core.messages import AIMessage
        from tests.scripted_model import ScriptedChatModel
        from tests.support import wait_for_run
        with self.owned_router() as (app, client, _, connected, unload, stop, stopped):
            run = self.terminal_run(app)
            self.queued_chat(app)
            release = threading.Event()
            worker = threading.Thread(target=lambda: release.wait(8))
            worker.start()
            app.state.harness._threads[run.id] = worker
            original_close = app.state.harness.close
            try:
                # Accelerate only the timeout; exercise the real join and its
                # refusal to release resources while the worker remains alive.
                with patch.object(app.state.harness, "close", side_effect=lambda **_kwargs: original_close(timeout=0)):
                    response = client.post("/v1/desktop/stop-owned-work", json={})
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()["code"], "shutdown_pending")
                unload.assert_not_called()
                stop.assert_not_called()
                self.assertEqual(stopped, [])
                self.assertIsNone(app.state.maintenance_gate.active_reason)
            finally:
                release.set()
                worker.join(8)
            app.state.harness._model_factory = lambda *_args: ScriptedChatModel([AIMessage(content="Still available")])
            created = client.post("/v1/chat/conversations", json={"deployment_id": connected.id, "presented_tools": []})
            self.assertEqual(created.status_code, 200, created.text)
            accepted = client.post(f"/v1/chat/conversations/{created.json()['id']}/start", json={"task": "Continue after refused quit"})
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(wait_for_run(client, accepted.json()["current_run_id"])["status"], "completed")

    def test_quit_keeps_live_and_finalizing_guards_before_engine_stop(self):
        for phase in (None, "saving_changes"):
            with self.subTest(phase=phase), self.owned_router() as (app, client, _, _, unload, stop, stopped):
                run = self.terminal_run(app, status="running", finalization_phase=phase)
                app.state.harness._startup_reconciled = True
                self.queued_chat(app, status="dispatching", reason=None, run_id=run.id)
                # A finalizing owner refuses cancellation itself. An ordinary
                # stuck live owner reaches the existing shutdown deadline.
                clock = SimpleNamespace(monotonic=iter([0, 16]).__next__, sleep=lambda _seconds: None)
                with patch("workbench_backend.state.desktop_routes.time", clock):
                    response = client.post("/v1/desktop/stop-owned-work", json={})
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()["code"], "run_finalizing" if phase else "shutdown_pending")
                unload.assert_not_called()
                stop.assert_not_called()
                self.assertEqual(stopped, [])
                self.assertIsNone(app.state.maintenance_gate.active_reason)

    def test_quit_reservation_failure_does_not_relax_ordinary_paused_guards(self):
        from workbench_backend.errors import ManagerError
        with self.owned_router() as (app, client, deployment, _, unload, stop, stopped):
            self.queued_chat(app)
            with app.state.manager.lifecycle.reserve(deployment):
                response = client.post("/v1/desktop/stop-owned-work", json={})
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(response.json()["code"], "model_lifecycle_active")
            self.assertIsNone(app.state.maintenance_gate.active_reason)
            self.assertFalse(app.state.manager.lifecycle.owns_mutation("desktop_quit"))
            for ordinary_stop in (app.state.manager.stop_deployment, app.state.manager.deployments.stop,
                                  app.state.manager.deployments.router.stop):
                with self.assertRaises(ManagerError) as caught:
                    ordinary_stop(deployment.id)
                self.assertEqual(caught.exception.code, "deployment_active")
            consumers = app.state.manager._chat_consumers(deployment_ids={deployment.id})
            self.assertTrue(next(item for item in consumers if item.kind == "chat_queue").live)
            unload.assert_not_called()
            stop.assert_not_called()
            self.assertEqual(stopped, [])


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
