"""Bounded llama-server process logs (David-PC UAT observation 2)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from workbench_backend.errors import ManagerError
from workbench_backend.inference.process import (
    OWNED_HEALTH_ATTEMPTS,
    OWNED_HEALTH_BUDGET_SECONDS,
    OWNED_HEALTH_DELAY_SECONDS,
)
from workbench_backend.inference.process_logs import (
    RotatingLogWriter,
    deployment_log_path,
    prune_logs_dir,
    rotate_log_file,
)
from workbench_backend.inference.schemas import (
    LocalImportRequest,
    ManagedDeploymentRequest,
    PinRuntimeRequest,
)
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from support import write_tiny_gguf
from test_app import FakeHF


class ProcessLogHelperTests(unittest.TestCase):
    def test_rotate_shifts_and_drops_oldest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "llama-server-deploy_x.log"
            path.write_bytes(b"current")
            Path(f"{path}.1").write_bytes(b"one")
            Path(f"{path}.2").write_bytes(b"two")
            rotate_log_file(path, max_bytes=1, backups=2)
            self.assertFalse(path.exists())
            self.assertEqual(Path(f"{path}.1").read_bytes(), b"current")
            self.assertEqual(Path(f"{path}.2").read_bytes(), b"one")
            self.assertFalse(Path(f"{path}.3").exists())

    def test_writer_rotates_when_max_bytes_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "llama-server-deploy_y.log"
            writer = RotatingLogWriter(path, max_bytes=8, backups=2, dir_max_bytes=1024)
            writer.write(b"12345678")
            writer.write(b"more")
            writer.close()
            self.assertTrue(Path(f"{path}.1").is_file())
            self.assertIn(b"more", path.read_bytes())

    def test_prune_logs_dir_deletes_oldest_until_under_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            first = logs / "llama-server-old.log"
            second = logs / "llama-server-new.log"
            first.write_bytes(b"a" * 20)
            second.write_bytes(b"b" * 20)
            older = 1_700_000_000
            os.utime(first, (older, older))
            os.utime(second, (older + 60, older + 60))
            prune_logs_dir(logs, max_bytes=25)
            self.assertFalse(first.exists())
            self.assertTrue(second.exists())

    def test_owned_health_budget_is_tens_of_seconds_not_minutes(self) -> None:
        self.assertEqual(OWNED_HEALTH_ATTEMPTS, 60)
        self.assertEqual(OWNED_HEALTH_DELAY_SECONDS, 0.5)
        self.assertEqual(OWNED_HEALTH_BUDGET_SECONDS, 30.0)
        self.assertGreaterEqual(OWNED_HEALTH_BUDGET_SECONDS, 10)
        self.assertLess(OWNED_HEALTH_BUDGET_SECONDS, 60)


class ManagedStartLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=os.name == "nt")
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.gguf = write_tiny_gguf(self.root / "incoming" / "tiny.gguf")
        self.manager = ModelManager(self.paths, hf=FakeHF(error=RuntimeError("boom")))

    def tearDown(self) -> None:
        for deployment in list(self.manager.list_deployments()):
            if deployment.scope.value != "managed":
                continue
            try:
                self.manager.stop_deployment(deployment.id)
            except ManagerError:
                pass
        self.tmp.cleanup()

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
        return script

    def test_managed_start_writes_rotating_log_under_data_root(self) -> None:
        job = self.manager.import_local(LocalImportRequest(source_path=str(self.gguf)))
        self.manager.pin_runtime(
            PinRuntimeRequest(local_executable=str(self._fake_server(self.root / "rt")))
        )
        deployment = self.manager.create_managed(
            ManagedDeploymentRequest(
                bundle_id=job.bundle_id or "",
                startup={"port": 18300},
                auto_start=True,
            )
        )
        log_path = deployment_log_path(self.paths.logs, deployment.id)
        self.assertTrue(log_path.is_file(), f"expected process log at {log_path}")
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("workbench llama-server start", text)
        self.assertIn("argv:", text)
        self.manager.stop_deployment(deployment.id)


class PathLayoutLogTests(unittest.TestCase):
    def test_ensure_creates_logs_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp)).ensure()
            self.assertEqual(paths.logs, paths.root / "logs")
            self.assertTrue(paths.logs.is_dir())
            public = paths.as_public_dict()
            self.assertEqual(public["logs"], str(paths.logs))
            self.assertIn("logs", public["windows_layout"])


if __name__ == "__main__":
    unittest.main()
