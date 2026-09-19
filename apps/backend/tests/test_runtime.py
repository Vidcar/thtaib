"""Managed Windows CUDA pin, local-pin directory, and pin-while-running (Issue #21)."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from workbench_backend.errors import ManagerError
from workbench_backend.inference.process import argv_for_host
from workbench_backend.inference.runtime import (
    NVIDIA_ABSENT_MESSAGE,
    WINDOWS_CUDA_ASSET,
    WINDOWS_CUDART_ASSET,
    RuntimeInstaller,
)
from workbench_backend.inference.schemas import (
    LocalImportRequest,
    ManagedDeploymentRequest,
    PinRuntimeRequest,
)
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.settings import startup_cli_args
from workbench_backend.paths import WorkbenchPaths

from support import write_tiny_gguf
from test_app import FakeHF


class FakeCudaInstaller(RuntimeInstaller):
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


class TrackingCudaInstaller(FakeCudaInstaller):
    def __init__(self) -> None:
        super().__init__()
        self.started = False

    def download(self, url: str, dest: Path) -> None:
        self.started = True
        super().download(url, dest)


class RuntimePinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.gguf = write_tiny_gguf(self.root / "incoming" / "tiny.gguf")
        self._active_manager: ModelManager | None = None

    def tearDown(self) -> None:
        manager = getattr(self, "_active_manager", None)
        if manager is not None:
            for deployment in list(manager.list_deployments()):
                if deployment.scope.value == "managed" and deployment.pid:
                    try:
                        manager.stop_deployment(deployment.id)
                    except ManagerError:
                        pass
        self.tmp.cleanup()

    def _manager(
        self,
        *,
        installer: RuntimeInstaller | None = None,
        nvidia_present=None,
    ) -> ModelManager:
        manager = ModelManager(
            self.paths,
            hf=FakeHF(error=RuntimeError("boom")),
            installer=installer,
            nvidia_present=nvidia_present,
        )
        self._active_manager = manager
        return manager

    def _fake_server(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        script = directory / "llama-server"
        module = Path(__file__).with_name("fake_llama_server.py")
        script.write_text(
            "#!{}\nimport runpy\nrunpy.run_path({!r}, run_name='__main__')\n".format(
                sys.executable,
                str(module),
            ),
            encoding="utf-8",
        )
        script.chmod(0o755)
        (directory / "cudart64_134.dll").write_bytes(b"fake-cudart")
        return script

    def test_nvidia_absent_is_clear_error_not_silent_gpu(self) -> None:
        installer = TrackingCudaInstaller()
        manager = self._manager(installer=installer, nvidia_present=lambda: False)
        manifest = manager.pin_runtime()
        self.assertEqual(manifest.status, "failed")
        self.assertNotEqual(manifest.status, "ready")
        self.assertEqual(manifest.flavor, "cuda-13.4")
        self.assertIn("NVIDIA", manifest.error or "")
        self.assertIn("silent GPU", NVIDIA_ABSENT_MESSAGE)
        self.assertFalse(installer.started)
        self.assertEqual(installer.urls, [])

    def test_cuda_pin_downloads_b11045_and_cudart_when_nvidia_present(self) -> None:
        installer = FakeCudaInstaller()
        manager = self._manager(installer=installer, nvidia_present=lambda: True)
        manifest = manager.pin_runtime()
        self.assertEqual(manifest.status, "ready")
        self.assertEqual(manifest.release_tag, "b11045")
        self.assertEqual(manifest.flavor, "cuda-13.4")
        self.assertEqual(manifest.asset_name, WINDOWS_CUDA_ASSET)
        self.assertEqual(manifest.companion_asset_name, WINDOWS_CUDART_ASSET)
        self.assertTrue((Path(manifest.install_dir) / "llama-server.exe").is_file())
        self.assertTrue((Path(manifest.install_dir) / "cudart64_134.dll").is_file())
        self.assertTrue((self.paths.runtimes / WINDOWS_CUDA_ASSET).is_file())
        self.assertTrue((self.paths.runtimes / WINDOWS_CUDART_ASSET).is_file())

    def test_local_pin_copies_full_runtime_directory(self) -> None:
        source = self.root / "cuda-tree"
        exe = self._fake_server(source)
        manager = self._manager(nvidia_present=lambda: False)
        manifest = manager.pin_runtime(PinRuntimeRequest(local_executable=str(exe)))
        self.assertEqual(manifest.status, "ready")
        install = Path(manifest.install_dir)
        self.assertEqual(install, self.paths.runtimes / "local-pin")
        self.assertTrue(Path(manifest.executable).is_file())
        self.assertTrue((install / "cudart64_134.dll").is_file())
        self.assertTrue((install / exe.name).is_file())

    def test_default_gpu_profile_is_bound_on_managed_create(self) -> None:
        manager = self._manager(nvidia_present=lambda: False)
        job = manager.import_local(LocalImportRequest(source_path=str(self.gguf)))
        manager.pin_runtime(
            PinRuntimeRequest(local_executable=str(self._fake_server(self.root / "rt")))
        )
        deployment = manager.create_managed(
            ManagedDeploymentRequest(bundle_id=job.bundle_id or "", auto_start=False)
        )
        self.assertGreaterEqual(deployment.applied_startup["ctx_size"], 65536)
        self.assertEqual(deployment.applied_startup["n_gpu_layers"], -1)
        self.assertEqual(deployment.applied_startup["flash_attn"], "on")
        args = startup_cli_args(deployment.applied_startup)
        flash_at = args.index("--flash-attn")
        self.assertEqual(args[flash_at + 1], "on")
        self.assertNotEqual(deployment.requested_startup, {"startup": {}})

    def test_pin_while_running_is_rejected_without_half_pin(self) -> None:
        manager = self._manager(nvidia_present=lambda: True)
        job = manager.import_local(LocalImportRequest(source_path=str(self.gguf)))
        first = self._fake_server(self.root / "first-runtime")
        original = manager.pin_runtime(PinRuntimeRequest(local_executable=str(first)))
        deployment = manager.create_managed(
            ManagedDeploymentRequest(
                bundle_id=job.bundle_id or "",
                startup={"port": 18180},
            )
        )
        self.assertIn(deployment.status.value, {"running", "unhealthy", "starting"})
        installer = TrackingCudaInstaller()
        manager.runtime.installer = installer
        second = self._fake_server(self.root / "second-runtime")
        with self.assertRaises(ManagerError) as caught:
            manager.pin_runtime(PinRuntimeRequest(local_executable=str(second)))
        self.assertEqual(caught.exception.code, "runtime_pin_busy")
        self.assertFalse(installer.started)
        current = manager.current_runtime()
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.status, "ready")
        self.assertEqual(current.executable, original.executable)
        self.assertTrue(Path(original.executable).is_file())
        manager.stop_deployment(deployment.id)

    def test_pin_while_running_stop_first_then_pins(self) -> None:
        manager = self._manager(nvidia_present=lambda: False)
        job = manager.import_local(LocalImportRequest(source_path=str(self.gguf)))
        manager.pin_runtime(
            PinRuntimeRequest(local_executable=str(self._fake_server(self.root / "a")))
        )
        deployment = manager.create_managed(
            ManagedDeploymentRequest(
                bundle_id=job.bundle_id or "",
                startup={"port": 18190},
            )
        )
        replacement = self._fake_server(self.root / "b")
        (replacement.parent / "extra.dll").write_bytes(b"more")
        pinned = manager.pin_runtime(
            PinRuntimeRequest(local_executable=str(replacement), stop_first=True)
        )
        self.assertEqual(pinned.status, "ready")
        self.assertTrue((Path(pinned.install_dir) / "extra.dll").is_file())
        stopped = manager.get_deployment(deployment.id)
        self.assertEqual(stopped.status.value, "stopped")
        self.assertIsNone(stopped.pid)

    def test_argv_for_host_prefixes_python_only_for_windows_shebang(self) -> None:
        script = self.root / "llama-server"
        script.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
        argv = [str(script), "-m", "tiny.gguf"]
        result = argv_for_host(argv)
        if os.name == "nt":
            self.assertEqual(result[0], sys.executable)
            self.assertEqual(result[1:], argv)
        else:
            self.assertEqual(result, argv)
        native = [str(self.root / "llama-server.exe"), "-m", "tiny.gguf"]
        self.assertEqual(argv_for_host(native), native)


if __name__ == "__main__":
    unittest.main()
