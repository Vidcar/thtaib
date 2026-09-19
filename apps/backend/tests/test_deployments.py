"""MOD-004 deployments and OQ-007 partial lifecycle rules."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from workbench_backend.errors import ManagerError
from workbench_backend.inference.deployments import managed_argv
from workbench_backend.inference.process import ProcessIdentity, ProcessSupervisor
from workbench_backend.inference.runtime import RuntimeInstaller
from workbench_backend.inference.schemas import (
    ConnectedDeploymentRequest,
    HuggingFaceImportRequest,
    LocalImportRequest,
    ManagedDeploymentRequest,
    PinRuntimeRequest,
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

    def start(self, argv: list[str], *, cwd: Path | None = None) -> ProcessIdentity:
        self.launched.append(list(argv))
        return super().start(argv, cwd=cwd)


class FakeWindowsInstaller(RuntimeInstaller):
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

    def test_managed_argv_uses_load_mode_and_omits_retired_flags(self) -> None:
        deployment = self.manager.create_managed(
            ManagedDeploymentRequest(
                bundle_id=self.bundle_id,
                startup={"port": 18081, "load_mode": "mlock", "mlock": True, "no_mmap": True},
            )
        )
        self.assertIn(deployment.status.value, {"running", "unhealthy"})
        self.assertEqual(deployment.applied_startup["load_mode"], "mlock")
        self.assertNotIn("mlock", deployment.applied_startup)
        self.assertEqual({note.key for note in deployment.settings.startup.retired}, {"mlock", "no_mmap"})
        self.assertEqual(len(self.supervisor.launched), 1)
        argv = self.supervisor.launched[0]
        self.assertEqual(argv[argv.index("--load-mode") + 1], "mlock")
        self.assertNotIn("--mlock", argv)
        self.assertNotIn("--no-mmap", argv)
        self.assertNotIn("--mmproj", argv)
        self.manager.stop_deployment(deployment.id)

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
