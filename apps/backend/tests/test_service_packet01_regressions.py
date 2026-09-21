"""Packet01 service regressions for readiness and deletion accounting."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import (
    Deployment,
    DeploymentStatus,
    HealthReport,
    LocalImportRequest,
    ManagementScope,
    ProcessIdentity,
    SettingsBags,
)
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference import bundles
from workbench_backend.errors import ManagerError
from workbench_backend.paths import WorkbenchPaths

from support import write_tiny_gguf


class Packet01ServiceRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manager = ModelManager(WorkbenchPaths(self.root))
        self.source = self.root / "incoming"
        self.primary = write_tiny_gguf(self.source / "demo-Q4_K_M.gguf", name="demo")
        self.import_job = self.manager.import_local(LocalImportRequest(source_path=str(self.source)))
        self.bundle = self.manager.store.get_bundle(self.import_job.bundle_id or "")
        self.assertIsNotNone(self.bundle)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_ready_running_managed_deployment_does_not_rehash_bundle_each_turn(self) -> None:
        now = utc_now()
        deployment = Deployment(
            id="deploy_ready",
            display_name="ready",
            scope=ManagementScope.managed,
            status=DeploymentStatus.running,
            bundle_id=self.bundle.id,
            endpoint="http://127.0.0.1:18181/v1",
            settings=SettingsBags(),
            pid=424242,
            process_identity=ProcessIdentity(
                pid=424242,
                create_time=1.0,
                executable="llama-server",
            ),
            health=HealthReport(
                healthy=True,
                endpoint="http://127.0.0.1:18181/v1",
                checked=now,
                detail="fixture",
            ),
            created_at=now,
            updated_at=now,
        )
        self.manager.store.put_deployment(deployment)

        with (
            patch.object(bundles, "sha256_file", wraps=bundles.sha256_file) as full_hash,
            patch.object(self.manager.deployments, "start", wraps=self.manager.deployments.start) as start,
        ):
            ready = self.manager.ensure_deployment_ready(deployment.id)
            self.manager.ensure_deployment_ready(deployment.id)

        self.assertEqual(ready.id, deployment.id)
        self.assertEqual(full_hash.call_count, 0)
        start.assert_not_called()

    def test_failed_stop_blocks_model_deletion_and_runtime_repin(self):
        now = utc_now()
        owned = ProcessIdentity(pid=424242, create_time=1.0, executable='llama-server')
        deployment = Deployment(id='failed_stop', display_name='failed stop', scope=ManagementScope.managed,
            status=DeploymentStatus.running, bundle_id=self.bundle.id, pid=owned.pid,
            process_identity=owned, created_at=now, updated_at=now)
        self.manager.store.put_deployment(deployment)
        with patch.object(self.manager.deployments.processes, 'stop', side_effect=ManagerError('exit unconfirmed', code='process_stop_failed')):
            with self.assertRaises(ManagerError):
                self.manager.stop_deployment(deployment.id)
        stored = self.manager.get_deployment(deployment.id)
        self.assertEqual(stored.process_identity, owned)
        self.assertEqual(stored.status, DeploymentStatus.failed)
        with self.assertRaises(ManagerError) as deletion:
            self.manager.delete_bundle(self.bundle.id)
        self.assertEqual(deletion.exception.code, 'bundle_delete_blocked')
        self.assertTrue(Path(self.bundle.primary_path).exists())
        with self.assertRaises(ManagerError) as pin:
            self.manager.pin_runtime()
        self.assertEqual(pin.exception.code, 'runtime_pin_busy')

    def test_stopped_managed_deployment_rejects_corrupt_bundle_before_start(self) -> None:
        now = utc_now()
        deployment = Deployment(
            id="deploy_stopped_corrupt",
            display_name="stopped corrupt",
            scope=ManagementScope.managed,
            status=DeploymentStatus.stopped,
            bundle_id=self.bundle.id,
            endpoint="http://127.0.0.1:18182/v1",
            settings=SettingsBags(),
            created_at=now,
            updated_at=now,
        )
        self.manager.store.put_deployment(deployment)
        primary_path = Path(self.bundle.primary_path or "")
        primary_path.write_bytes(b"corrupt")

        with patch.object(self.manager.deployments, "start", wraps=self.manager.deployments.start) as start:
            with self.assertRaises(Exception) as caught:
                self.manager.ensure_deployment_ready(deployment.id)

        self.assertEqual(getattr(caught.exception, "code", None), "bundle_not_deployable")
        start.assert_not_called()

    def test_bundle_delete_preview_reports_current_disk_bytes_for_removable_file(self) -> None:
        primary_path = Path(self.bundle.primary_path or "")
        recorded_size = primary_path.stat().st_size
        primary_path.write_bytes(primary_path.read_bytes() + b"expanded")
        actual_size = primary_path.stat().st_size
        self.assertGreater(actual_size, recorded_size)

        preview = self.manager.bundle_delete_preview(self.bundle.id)

        plan = next(file for file in preview.files if file.path == str(primary_path))
        self.assertTrue(plan.removable)
        self.assertEqual(plan.size_bytes, actual_size)
        self.assertEqual(preview.removable_bytes, actual_size)


if __name__ == "__main__":
    unittest.main()
