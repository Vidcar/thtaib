"""MOD-004 deployments and OQ-007 partial lifecycle rules."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from workbench_backend.errors import ManagerError
from workbench_backend.inference.deployments import managed_argv
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.process import HttpProbe, ProcessIdentity, ProcessSupervisor
from workbench_backend.inference.runtime import RuntimeInstaller
from workbench_backend.inference.schemas import (
    ConnectedDeploymentRequest,
    Deployment,
    DeploymentStatus,
    HuggingFaceImportRequest,
    LocalImportRequest,
    ManagedDeploymentRequest,
    ManagementScope,
    PinRuntimeRequest,
    SettingsBags,
)
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from support import write_tiny_gguf
from test_app import FakeHF


class RecordingSupervisor(ProcessSupervisor):
    """Real supervisor that also keeps the argv it launched."""

    def __init__(self) -> None:
        super().__init__()
        self.launched: list[list[str]] = []

    def start(
        self,
        argv: list[str],
        *,
        cwd: Path | None = None,
        log_path: Path | None = None,
    ) -> ProcessIdentity:
        self.launched.append(list(argv))
        return super().start(argv, cwd=cwd, log_path=log_path)


class FakeWindowsInstaller(RuntimeInstaller):
    verify_release_digest = False

    def __init__(self) -> None:
        self.urls: list[str] = []

    def download(self, url: str, dest: Path) -> None:
        self.urls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zipped:
            if "cudart" in dest.name:
                zipped.writestr("cudart64_134.dll", b"fake-cudart")
            else:
                zipped.writestr("llama-server.exe", b"not-a-real-binary")
        dest.write_bytes(buffer.getvalue())


class FailingInstaller(RuntimeInstaller):
    def download(self, url: str, dest: Path) -> None:
        raise InterruptedError("runtime download interrupted")


class PropsVariantHandler(BaseHTTPRequestHandler):
    """Healthy OpenAI-compatible stub whose ``/props`` is broken in a configurable way."""

    props_mode = "missing"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, b'{"status":"ok"}', "application/json")
            return
        if self.path == "/props":
            if self.props_mode == "missing":
                self._send(404, b'{"error":"not found"}', "application/json")
            elif self.props_mode == "html":
                self._send(200, b"<html><body>not json</body></html>", "text/html")
            else:
                self._send(200, json.dumps(["not", "a", "dict"]).encode("utf-8"), "application/json")
            return
        self._send(404, b'{"error":"not found"}', "application/json")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BrokenPropsEndpointTests(unittest.TestCase):
    """A healthy endpoint without usable ``/props`` stays running with nothing recorded."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.manager = ModelManager(WorkbenchPaths(Path(self.tmp.name)).ensure())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), PropsVariantHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_props_404_non_json_or_list_leave_deployment_running(self) -> None:
        for mode in ("missing", "html", "list"):
            with self.subTest(mode=mode):
                PropsVariantHandler.props_mode = mode
                self.assertIsNone(HttpProbe().props(self.endpoint))
                deployment = self.manager.attach_connected(
                    ConnectedDeploymentRequest(endpoint=self.endpoint)
                )
                self.assertEqual(deployment.status.value, "running")
                self.assertTrue(deployment.health and deployment.health.healthy)
                self.assertIsNone(deployment.server_props)
                refreshed = self.manager.deployment_health(deployment.id)
                self.assertEqual(refreshed.status.value, "running")
                self.assertTrue(refreshed.health and refreshed.health.healthy)
                self.assertIsNone(refreshed.server_props)
                self.manager.detach_deployment(deployment.id)


class DeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.gguf = write_tiny_gguf(self.root / "incoming" / "tiny.gguf")
        self.supervisor = RecordingSupervisor()
        self.manager = ModelManager(
            self.paths,
            hf=FakeHF(error=RuntimeError("boom")),
            processes=self.supervisor,
        )
        job = self.manager.import_local(LocalImportRequest(source_path=str(self.gguf)))
        self.bundle_id = job.bundle_id or ""
        self.manager.pin_runtime(
            PinRuntimeRequest(local_executable=self._fake_server_script())
        )

    def tearDown(self) -> None:
        for deployment in list(self.manager.list_deployments()):
            if deployment.scope.value == "managed" and deployment.pid:
                try:
                    self.manager.stop_deployment(deployment.id)
                except ManagerError:
                    pass
        self.tmp.cleanup()

    def _fake_server_script(self) -> str:
        runtime_dir = self.root / "fake-runtime"
        runtime_dir.mkdir(exist_ok=True)
        script = runtime_dir / "fake-llama-server"
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

    def test_managed_start_health_stop(self) -> None:
        deployment = self.manager.create_managed(
            ManagedDeploymentRequest(bundle_id=self.bundle_id, startup={"port": 18080})
        )
        self.assertEqual(deployment.scope.value, "managed")
        self.assertIn(deployment.status.value, {"running", "unhealthy"})
        self.assertIsNotNone(deployment.endpoint)
        self.assertIn("port", deployment.applied_startup)
        self.assertIsNotNone(deployment.resource_usage)
        self.assertIsNotNone(deployment.process_identity)
        self.assertEqual(deployment.pid, deployment.process_identity.pid)
        refreshed = self.manager.deployment_health(deployment.id)
        self.assertTrue(refreshed.health and refreshed.health.healthy)
        stopped = self.manager.stop_deployment(deployment.id)
        self.assertEqual(stopped.status.value, "stopped")
        self.assertIsNone(stopped.pid)

    def test_invalid_managed_startup_fails_closed_on_create(self) -> None:
        cases = (
            ({"port": 18081, "ctx_size": -1}, ["ctx_size"]),
            ({"port": "not-a-port"}, ["port"]),
            ({"port": 18081, "unknown_flag": True}, ["unknown_flag"]),
            ({"port": 18081, "mlock": True, "no_mmap": True}, ["mlock", "no_mmap"]),
        )
        for startup, keys in cases:
            with self.subTest(startup=startup):
                with self.assertRaises(ManagerError) as caught:
                    self.manager.create_managed(
                        ManagedDeploymentRequest(bundle_id=self.bundle_id, startup=startup)
                    )
                self.assertEqual(caught.exception.code, "managed_startup_invalid")
                for key in keys:
                    self.assertIn(key, caught.exception.message)
                self.assertEqual(self.supervisor.launched, [])

    def test_valid_load_mode_replaces_retired_flags(self) -> None:
        deployment = self.manager.create_managed(
            ManagedDeploymentRequest(
                bundle_id=self.bundle_id,
                startup={"port": 18081, "load_mode": "mlock"},
            )
        )
        self.assertIn(deployment.status.value, {"running", "unhealthy"})
        self.assertEqual(deployment.applied_startup["load_mode"], "mlock")
        self.assertEqual(len(self.supervisor.launched), 1)
        argv = self.supervisor.launched[0]
        self.assertEqual(argv[argv.index("--load-mode") + 1], "mlock")
        self.assertNotIn("--mlock", argv)
        self.assertNotIn("--no-mmap", argv)
        self.manager.stop_deployment(deployment.id)

    def test_invalid_saved_managed_startup_fails_closed_on_start(self) -> None:
        now = utc_now()
        legacy = Deployment(
            id="deploy_legacy_invalid_startup",
            display_name="managed:legacy-invalid",
            scope=ManagementScope.managed,
            status=DeploymentStatus.stopped,
            bundle_id=self.bundle_id,
            endpoint="http://127.0.0.1:18085/v1",
            requested_startup={"port": 18085, "ctx_size": -1},
            applied_startup={"host": "127.0.0.1", "port": 18085},
            settings=SettingsBags(),
            created_at=now,
            updated_at=now,
        )
        self.manager.store.put_deployment(legacy)
        with self.assertRaises(ManagerError) as caught:
            self.manager.start_deployment(legacy.id)
        self.assertEqual(caught.exception.code, "managed_startup_invalid")
        self.assertIn("ctx_size", caught.exception.message)
        self.assertEqual(self.supervisor.launched, [])

    def test_mmproj_companion_is_passed_on_managed_start(self) -> None:
        source = self.root / "incoming" / "vision"
        write_tiny_gguf(source / "vision-model-Q4_K_M.gguf", name="vision")
        write_tiny_gguf(source / "mmproj-vision-F16.gguf", name="projector")
        job = self.manager.import_local(LocalImportRequest(source_path=str(source)))
        bundle = self.manager.get_bundle(job.bundle_id or "")
        self.assertEqual([item.name for item in bundle.companions], ["mmproj-vision-F16.gguf"])
        self.assertTrue(bundle.primary_path and bundle.primary_path.endswith("vision-model-Q4_K_M.gguf"))

        argv = managed_argv("llama-server", bundle, {"ctx_size": 4096})
        self.assertEqual(argv[:3], ["llama-server", "-m", bundle.primary_path])
        self.assertEqual(argv[argv.index("--mmproj") + 1], bundle.companions[0].path)
        self.assertEqual(argv[argv.index("--ctx-size") + 1], "4096")

        deployment = self.manager.create_managed(
            ManagedDeploymentRequest(bundle_id=bundle.id, startup={"port": 18082})
        )
        self.assertIn(deployment.status.value, {"running", "unhealthy"})
        launched = self.supervisor.launched[-1]
        self.assertEqual(launched[launched.index("--mmproj") + 1], bundle.companions[0].path)
        self.assertIsNotNone(deployment.server_props)
        assert deployment.server_props is not None
        self.assertTrue(deployment.server_props.modalities.get("vision"))
        self.manager.stop_deployment(deployment.id)

    def test_missing_mmproj_file_is_a_clear_failure(self) -> None:
        source = self.root / "incoming" / "broken"
        write_tiny_gguf(source / "model.gguf")
        write_tiny_gguf(source / "mmproj-model.gguf", name="projector")
        job = self.manager.import_local(LocalImportRequest(source_path=str(source)))
        bundle = self.manager.get_bundle(job.bundle_id or "")
        Path(bundle.companions[0].path).unlink()
        with self.assertRaises(ManagerError) as caught:
            managed_argv("llama-server", bundle, {})
        self.assertEqual(caught.exception.code, "bundle_file_missing")
        self.assertIn("mmproj", caught.exception.message)

    def test_server_props_recorded_when_healthy_and_cleared_on_stop(self) -> None:
        deployment = self.manager.create_managed(
            ManagedDeploymentRequest(bundle_id=self.bundle_id, startup={"port": 18083, "alias": "tiny"})
        )
        self.assertEqual(deployment.status.value, "running")
        props = deployment.server_props
        self.assertIsNotNone(props)
        assert props is not None
        self.assertTrue(props.source_url.endswith("/props"))
        self.assertEqual(props.model_alias, "tiny")
        self.assertEqual(props.build_info, "fake-llama-server")
        self.assertEqual(props.modalities, {"vision": False, "video": False, "audio": False})
        self.assertTrue(props.chat_template_caps.get("supports_tools"))
        self.assertEqual(props.chat_template, "{{ fake }}")
        self.assertEqual(props.n_ctx, 4096)
        stopped = self.manager.stop_deployment(deployment.id)
        self.assertIsNone(stopped.server_props)

    def test_connected_attach_records_props_and_tolerates_missing_endpoint(self) -> None:
        managed = self.manager.create_managed(
            ManagedDeploymentRequest(bundle_id=self.bundle_id, startup={"port": 18084})
        )
        self.assertEqual(managed.status.value, "running")
        connected = self.manager.attach_connected(
            ConnectedDeploymentRequest(endpoint="http://127.0.0.1:18084/v1")
        )
        self.assertIsNotNone(connected.server_props)
        assert connected.server_props is not None
        self.assertEqual(connected.server_props.source_url, "http://127.0.0.1:18084/props")
        self.manager.detach_deployment(connected.id)
        self.manager.stop_deployment(managed.id)
        unreachable = self.manager.attach_connected(
            ConnectedDeploymentRequest(endpoint="http://127.0.0.1:9")
        )
        self.assertIsNone(unreachable.server_props)
        self.manager.detach_deployment(unreachable.id)

    def test_failed_import_cannot_become_deployment(self) -> None:
        job = self.manager.import_huggingface(
            HuggingFaceImportRequest(repo_id="org/x", revision="1")
        )
        self.assertEqual(job.status.value, "failed")
        with self.assertRaises(ManagerError) as caught:
            self.manager.create_managed(
                ManagedDeploymentRequest(bundle_id="missing", auto_start=False)
            )
        self.assertEqual(caught.exception.code, "bundle_not_deployable")

    def test_connected_has_no_destructive_lifecycle(self) -> None:
        deployment = self.manager.attach_connected(
            ConnectedDeploymentRequest(endpoint="http://127.0.0.1:9")
        )
        self.assertEqual(deployment.scope.value, "connected")
        self.assertIsNotNone(deployment.resource_usage)
        self.assertFalse(deployment.resource_usage.available)
        with self.assertRaises(ManagerError) as stop_error:
            self.manager.stop_deployment(deployment.id)
        self.assertEqual(stop_error.exception.code, "connected_no_lifecycle")
        with self.assertRaises(ManagerError) as start_error:
            self.manager.start_deployment(deployment.id)
        self.assertEqual(start_error.exception.code, "connected_no_lifecycle")
        detached = self.manager.detach_deployment(deployment.id)
        self.assertEqual(detached.id, deployment.id)
        with self.assertRaises(ManagerError):
            self.manager.get_deployment(deployment.id)

    def test_connected_embedder_records_declared_startup_without_gpu_defaults(self) -> None:
        deployment = self.manager.attach_connected(
            ConnectedDeploymentRequest(
                endpoint="http://127.0.0.1:9",
                startup={"embedding": "on", "pooling": "last"},
            )
        )
        self.assertEqual(deployment.applied_startup.get("embedding"), "on")
        self.assertEqual(deployment.applied_startup.get("pooling"), "last")
        self.assertNotIn("ctx_size", deployment.applied_startup)
        self.assertNotIn("n_gpu_layers", deployment.applied_startup)
        self.manager.detach_deployment(deployment.id)

    def test_windows_pin_writes_manifest_and_rejects_unpinned_start(self) -> None:
        installer = FakeWindowsInstaller()
        other = ModelManager(
            WorkbenchPaths(self.root / "other"),
            installer=installer,
            nvidia_present=lambda: True,
        )
        manifest = other.pin_runtime()
        self.assertEqual(manifest.status, "ready")
        self.assertEqual(manifest.platform, "win-x64")
        self.assertEqual(manifest.flavor, "cuda-13.4")
        self.assertEqual(manifest.release_tag, "b11045")
        self.assertEqual(manifest.asset_name, "llama-b11045-bin-win-cuda-13.4-x64.zip")
        self.assertEqual(manifest.companion_asset_name, "cudart-llama-bin-win-cuda-13.4-x64.zip")
        self.assertEqual(manifest.path_fallback, "unsupported")
        self.assertTrue(Path(manifest.executable).name.endswith("llama-server.exe"))
        self.assertTrue((Path(manifest.install_dir) / "cudart64_134.dll").is_file())
        self.assertEqual(len(installer.urls), 2)
        self.assertTrue(any("cuda-13.4" in url and "cudart" not in url for url in installer.urls))
        self.assertTrue(any("cudart-llama-bin-win-cuda-13.4" in url for url in installer.urls))
        empty = ModelManager(WorkbenchPaths(self.root / "empty"))
        job = empty.import_local(LocalImportRequest(source_path=str(self.gguf)))
        with self.assertRaises(ManagerError) as caught:
            empty.create_managed(
                ManagedDeploymentRequest(bundle_id=job.bundle_id or "", auto_start=True)
            )
        self.assertEqual(caught.exception.code, "runtime_unpinned")

    def test_interrupted_runtime_pin_is_not_ready(self) -> None:
        manager = ModelManager(
            WorkbenchPaths(self.root / "failpin"),
            installer=FailingInstaller(),
            nvidia_present=lambda: True,
        )
        manifest = manager.pin_runtime()
        self.assertEqual(manifest.status, "interrupted")
        self.assertNotEqual(manifest.status, "ready")


if __name__ == "__main__":
    unittest.main()
