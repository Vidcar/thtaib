"""MOD-004 deployments and OQ-007 partial lifecycle rules."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from workbench_backend.errors import ManagerError
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
        self.manager = ModelManager(self.paths, hf=FakeHF(error=RuntimeError("boom")))
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
