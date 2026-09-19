"""Issue #62 managed-deployment ownership: duplicate start and PID identity.

Unsafe PID reuse is exercised with fixtures/mocks only. Tests never
terminate an unrelated user process.
"""

from __future__ import annotations

import socket
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from workbench_backend.errors import ManagerError
from workbench_backend.inference.deployments import DeploymentService
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.process import (
    PROCESS_IDENTITY_MISMATCH,
    PROCESS_IDENTITY_UNPROVEN,
    ProcessInspector,
    ProcessSupervisor,
)
from workbench_backend.inference.runtime import RuntimeService
from workbench_backend.inference.schemas import (
    ConnectedDeploymentRequest,
    Deployment,
    DeploymentStatus,
    HealthReport,
    LocalImportRequest,
    ManagedDeploymentRequest,
    ManagementScope,
    PinRuntimeRequest,
    ProcessIdentity,
    ResourceUsage,
)
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from support import write_tiny_gguf
from test_app import FakeHF


class ScriptedInspector(ProcessInspector):
    """In-memory identity map. Does not inspect or kill the host process table."""

    def __init__(self) -> None:
        self.by_pid: dict[int, ProcessIdentity | None] = {}
        self.ports: dict[int, list[int] | None] = {}

    def identity_of(self, pid: int) -> ProcessIdentity | None:
        return self.by_pid.get(int(pid))

    def listen_ports(self, pid: int) -> list[int] | None:
        return self.ports.get(int(pid))


class HealthyProbe:
    def health(self, endpoint: str) -> HealthReport:
        return HealthReport(healthy=True, endpoint=endpoint, checked=utc_now(), detail="fixture")

    def smoke(self, endpoint: str) -> tuple[bool, str]:
        return True, "fixture"


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class ProcessOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.gguf = write_tiny_gguf(self.root / "incoming" / "tiny.gguf")
        self.manager = ModelManager(self.paths, hf=FakeHF(error=RuntimeError("boom")))
        job = self.manager.import_local(LocalImportRequest(source_path=str(self.gguf)))
        self.bundle_id = job.bundle_id or ""
        self.manager.pin_runtime(PinRuntimeRequest(local_executable=self._fake_server_script()))
        self._foreign: ThreadingHTTPServer | None = None

    def tearDown(self) -> None:
        if self._foreign is not None:
            self._foreign.shutdown()
            self._foreign.server_close()
        for deployment in list(self.manager.list_deployments()):
            if deployment.scope.value != "managed":
                continue
            try:
                self.manager.stop_deployment(deployment.id)
            except ManagerError:
                pass
        for child in list(self.manager.deployments.processes._children.values()):
            try:
                child.wait(timeout=2)
            except Exception:
                pass
        self.tmp.cleanup()

    def _fake_server_script(self, name: str = "fake-llama-server") -> str:
        runtime_dir = self.root / "fake-runtime"
        runtime_dir.mkdir(exist_ok=True)
        script = runtime_dir / name
        module = Path(__file__).with_name("fake_llama_server.py")
        script.write_text(
            "#!{}\nimport runpy\nrunpy.run_path({!r}, run_name='__main__')\n".format(
                sys.executable,
                str(module),
            ),
            encoding="utf-8",
        )
        script.chmod(0o755)
        (runtime_dir / "cudart64_134.dll").write_bytes(b"fake-cudart")
        return str(script)

    def _dying_script(self) -> str:
        runtime_dir = self.root / "dying-runtime"
        runtime_dir.mkdir(exist_ok=True)
        script = runtime_dir / "dying-llama-server"
        script.write_text(
            "#!{}\nimport sys\nsys.exit(0)\n".format(sys.executable),
            encoding="utf-8",
        )
        script.chmod(0o755)
        (runtime_dir / "cudart64_134.dll").write_bytes(b"fake-cudart")
        return str(script)

    def _occupy(self, host: str, port: int) -> ThreadingHTTPServer:
        server = ThreadingHTTPServer((host, port), _HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._foreign = server
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, port), timeout=0.1):
                    return server
            except OSError:
                time.sleep(0.05)
        return server

    def test_sequential_duplicate_start_is_idempotent(self) -> None:
        created = self.manager.create_managed(
            ManagedDeploymentRequest(
                bundle_id=self.bundle_id,
                startup={"port": 18200},
                auto_start=False,
            )
        )
        first = self.manager.start_deployment(created.id)
        second = self.manager.start_deployment(created.id)
        self.assertIsNotNone(first.process_identity)
        self.assertEqual(first.process_identity, second.process_identity)
        self.assertEqual(first.pid, second.pid)
        self.assertIn(first.status.value, {"running", "unhealthy"})
        self.assertIn(second.status.value, {"running", "unhealthy"})

    def test_concurrent_duplicate_start_owns_one_process(self) -> None:
        created = self.manager.create_managed(
            ManagedDeploymentRequest(
                bundle_id=self.bundle_id,
                startup={"port": 18210},
                auto_start=False,
            )
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.manager.start_deployment, created.id),
                pool.submit(self.manager.start_deployment, created.id),
            ]
            results = [item.result(timeout=20) for item in futures]
        identities = {
            (
                item.process_identity.pid,
                item.process_identity.create_time,
                item.process_identity.executable,
            )
            for item in results
            if item.process_identity is not None
        }
        self.assertEqual(len(identities), 1)
        pids = {item.pid for item in results}
        self.assertEqual(len(pids), 1)
        self.assertIsNotNone(results[0].pid)

    def test_dead_launch_with_foreign_health_is_not_owned(self) -> None:
        created = self.manager.create_managed(
            ManagedDeploymentRequest(
                bundle_id=self.bundle_id,
                startup={"port": 18220},
                auto_start=False,
            )
        )
        port = int(created.applied_startup["port"])
        self._occupy("127.0.0.1", port)
        self.manager.pin_runtime(PinRuntimeRequest(local_executable=self._dying_script()))
        started = self.manager.start_deployment(created.id)
        self.assertEqual(started.status, DeploymentStatus.failed)
        self.assertIsNone(started.pid)
        self.assertIsNone(started.process_identity)
        self.assertIn("not recorded as a healthy owned", (started.error or "").lower())

    def test_restart_reconcile_readopts_matching_process(self) -> None:
        started = self.manager.create_managed(
            ManagedDeploymentRequest(bundle_id=self.bundle_id, startup={"port": 18230})
        )
        self.assertIsNotNone(started.process_identity)
        identity = started.process_identity
        restarted = ModelManager(self.paths, hf=FakeHF(error=RuntimeError("boom")))
        adopted = restarted.get_deployment(started.id)
        self.assertEqual(adopted.process_identity, identity)
        self.assertEqual(adopted.pid, identity.pid if identity else None)
        self.assertIn(adopted.status.value, {"running", "unhealthy", "starting"})
        stopped = restarted.stop_deployment(started.id)
        self.assertEqual(stopped.status, DeploymentStatus.stopped)
        self.assertIsNone(stopped.pid)
        self.assertIsNone(stopped.process_identity)

    def test_connected_lifecycle_stays_non_destructive(self) -> None:
        deployment = self.manager.attach_connected(
            ConnectedDeploymentRequest(endpoint="http://127.0.0.1:9")
        )
        self.assertEqual(deployment.scope.value, "connected")
        with self.assertRaises(ManagerError) as stop_error:
            self.manager.stop_deployment(deployment.id)
        self.assertEqual(stop_error.exception.code, "connected_no_lifecycle")
        with self.assertRaises(ManagerError) as start_error:
            self.manager.start_deployment(deployment.id)
        self.assertEqual(start_error.exception.code, "connected_no_lifecycle")
        detached = self.manager.detach_deployment(deployment.id)
        self.assertEqual(detached.id, deployment.id)


class ProcessIdentityFixtureTests(unittest.TestCase):
    """PID reuse / mismatch — fixtures only; no host-process termination."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.gguf = write_tiny_gguf(self.root / "incoming" / "tiny.gguf")
        self.terminations: list[int] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _service(self, *, inspector: ScriptedInspector) -> DeploymentService:
        store_manager = ModelManager(self.paths, hf=FakeHF(error=RuntimeError("boom")))
        supervisor = ProcessSupervisor(inspector=inspector)

        def refuse_tree(pid: int, *, timeout: float, force: bool = False) -> None:
            self.terminations.append(int(pid))
            raise AssertionError(f"refused fixture tried to terminate pid={pid}")

        supervisor._stop_process_tree = refuse_tree  # type: ignore[method-assign]
        return DeploymentService(
            store_manager.store,
            store_manager.runtime,
            processes=supervisor,
            probe=HealthyProbe(),  # type: ignore[arg-type]
            reconcile_on_init=False,
        )

    def _record(
        self,
        service: DeploymentService,
        *,
        identity: ProcessIdentity | None,
        pid: int | None,
        status: DeploymentStatus = DeploymentStatus.running,
    ) -> Deployment:
        now = "2026-09-19T00:00:00+00:00"
        deployment = Deployment(
            id="deploy_fixture",
            display_name="fixture",
            scope=ManagementScope.managed,
            status=status,
            endpoint="http://127.0.0.1:9/v1",
            pid=pid,
            process_identity=identity,
            resource_usage=ResourceUsage(available=False, reason="fixture"),
            created_at=now,
            updated_at=now,
        )
        return service.store.put_deployment(deployment)

    def test_mismatch_identity_is_refused_before_termination(self) -> None:
        inspector = ScriptedInspector()
        owned = ProcessIdentity(pid=42424242, create_time=100.0, executable="/owned/llama-server")
        reused = ProcessIdentity(pid=42424242, create_time=999.0, executable="/unrelated/python")
        inspector.by_pid[42424242] = reused
        service = self._service(inspector=inspector)
        self._record(service, identity=owned, pid=owned.pid)
        with self.assertRaises(ManagerError) as caught:
            service.stop("deploy_fixture")
        self.assertEqual(caught.exception.code, PROCESS_IDENTITY_MISMATCH)
        self.assertEqual(self.terminations, [])
        stored = service.store.get_deployment("deploy_fixture")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertIsNone(stored.pid)
        self.assertIsNone(stored.process_identity)
        self.assertEqual(stored.status, DeploymentStatus.stopped)

    def test_unproven_pid_is_refused_before_termination(self) -> None:
        inspector = ScriptedInspector()
        service = self._service(inspector=inspector)
        self._record(service, identity=None, pid=42424243)
        with self.assertRaises(ManagerError) as caught:
            service.stop("deploy_fixture")
        self.assertEqual(caught.exception.code, PROCESS_IDENTITY_UNPROVEN)
        self.assertEqual(self.terminations, [])
        stored = service.store.get_deployment("deploy_fixture")
        assert stored is not None
        self.assertIsNone(stored.pid)

    def test_reconcile_clears_reused_pid_without_kill(self) -> None:
        inspector = ScriptedInspector()
        owned = ProcessIdentity(pid=42424244, create_time=100.0, executable="/owned/llama-server")
        inspector.by_pid[42424244] = ProcessIdentity(
            pid=42424244,
            create_time=500.0,
            executable="/someone-else/app",
        )
        service = self._service(inspector=inspector)
        self._record(service, identity=owned, pid=owned.pid)
        reconciled = service.reconcile()
        self.assertEqual(self.terminations, [])
        self.assertEqual(len(reconciled), 1)
        self.assertIsNone(reconciled[0].pid)
        self.assertIsNone(reconciled[0].process_identity)
        self.assertEqual(reconciled[0].status, DeploymentStatus.stopped)
        self.assertIn("cleared without termination", reconciled[0].error or "")

    def test_supervisor_stop_mismatch_does_not_touch_psutil_tree(self) -> None:
        inspector = ScriptedInspector()
        owned = ProcessIdentity(pid=42424245, create_time=1.0, executable="/owned/llama")
        inspector.by_pid[42424245] = ProcessIdentity(
            pid=42424245,
            create_time=2.0,
            executable="/other/bin",
        )
        supervisor = ProcessSupervisor(inspector=inspector)
        supervisor._stop_process_tree = (  # type: ignore[method-assign]
            lambda *args, **kwargs: self.terminations.append(args[0] if args else -1)
        )
        with self.assertRaises(ManagerError) as caught:
            supervisor.stop(owned)
        self.assertEqual(caught.exception.code, PROCESS_IDENTITY_MISMATCH)
        self.assertEqual(self.terminations, [])


class RuntimeOwnedLiveTests(unittest.TestCase):
    def test_stale_running_status_without_match_does_not_block_pin(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        try:
            paths = WorkbenchPaths(Path(tmp.name)).ensure()
            store_manager = ModelManager(paths, hf=FakeHF(error=RuntimeError("boom")))
            now = "2026-09-19T00:00:00+00:00"
            store_manager.store.put_deployment(
                Deployment(
                    id="deploy_stale",
                    display_name="stale",
                    scope=ManagementScope.managed,
                    status=DeploymentStatus.running,
                    endpoint="http://127.0.0.1:9/v1",
                    pid=42424246,
                    process_identity=ProcessIdentity(
                        pid=42424246,
                        create_time=1.0,
                        executable="/gone/llama",
                    ),
                    created_at=now,
                    updated_at=now,
                )
            )
            runtime = RuntimeService(paths, store_manager.store)
            self.assertEqual(runtime.running_managed_deployments(), [])
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
