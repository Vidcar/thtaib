"""Storage and process safety at the durable import boundary."""
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import psutil

from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import BundleService
from workbench_backend.inference.import_jobs import ImportJobRunner
from workbench_backend.inference.schemas import BundleSourceKind, ImportJob, ImportStatus
from workbench_backend.inference.store import RecordStore
from workbench_backend.paths import WorkbenchPaths


class ImportStorageSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = WorkbenchPaths(Path(self.tmp.name)).ensure()
        self.store = RecordStore(self.paths)
        self.runner = ImportJobRunner(self.paths, self.store, BundleService(self.paths, self.store))

    def job(self, identity, status, **values):
        return self.store.put_job(ImportJob(id=identity, kind=BundleSourceKind.huggingface,
            status=status, created_at="2026-09-21T00:00:00Z", **values))

    def test_cleanup_preserves_retained_partial_and_does_not_offer_its_bytes(self):
        retained = self.paths.state / "staging" / "hf" / "retained"
        retained.mkdir(parents=True)
        (retained / "partial").write_bytes(b"keep partial")
        self.job("retained", ImportStatus.stopped, staging_path=str(retained))
        summary = self.runner.storage_summary()
        self.assertEqual(summary.reclaimable_bytes, 0)
        self.assertEqual(self.runner.cleanup_unreferenced_staging(), [])
        self.assertEqual((retained / "partial").read_bytes(), b"keep partial")

    def test_cache_operations_never_scan_default_shared_cache(self):
        from huggingface_hub.errors import CacheNotFound
        calls = []
        def scan(path=None):
            calls.append(path)
            raise CacheNotFound("missing", cache_dir=Path(path or self.tmp.name))
        with patch("workbench_backend.inference.import_jobs.scan_cache_dir", side_effect=scan):
            self.runner.storage_summary()
            self.runner.cleanup_cache()
        self.assertTrue(calls)
        self.assertTrue(all(path is not None and Path(path).is_relative_to(self.paths.state) for path in calls))

    def test_restart_does_not_terminalize_process_when_stop_fails(self):
        job = self.job("old", ImportStatus.running, worker_id="old-worker", transfer_pid=42,
            transfer_create_time=1.0)
        with patch("workbench_backend.inference.import_jobs.psutil.Process", side_effect=psutil.AccessDenied(42)):
            self.runner.reconcile_on_startup()
        current = self.store.get_job(job.id)
        self.assertEqual(current.status, ImportStatus.stopping)
        self.assertEqual(current.transfer_pid, 42)
        with self.assertRaises(ManagerError):
            self.runner.discard_job(job.id)

    def test_reused_pid_is_not_terminated(self):
        job = self.job("reused", ImportStatus.running, worker_id="old-worker", transfer_pid=42,
            transfer_create_time=1.0)
        with patch("workbench_backend.inference.import_jobs.psutil.Process") as process:
            process.return_value.create_time.return_value = 2.0
            self.runner.reconcile_on_startup()
            process.return_value.terminate.assert_not_called()
        self.assertEqual(self.store.get_job(job.id).status, ImportStatus.interrupted)

    def test_reconcile_confirms_real_owned_process_exit(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        identity = psutil.Process(child.pid).create_time()
        job = self.job('real-child', ImportStatus.running, worker_id='old-worker',
                       transfer_pid=child.pid, transfer_create_time=identity)
        self.runner.reconcile_on_startup()
        child.wait(timeout=5)
        current = self.store.get_job(job.id)
        self.assertEqual(current.status, ImportStatus.interrupted)
        self.assertIsNone(current.transfer_pid)
        self.assertIsNotNone(child.poll())

    def test_restart_partial_install_is_retained_until_explicit_discard(self):
        partial = self.paths.models / 'bundle_partial'
        partial.mkdir()
        (partial/'partial.gguf').write_bytes(b'partial')
        job = self.job('orphan-install', ImportStatus.running, worker_id='old-worker',
                       install_root=str(self.paths.models), owned_install_path=str(partial))
        self.runner.reconcile_on_startup()
        self.assertTrue(partial.exists())
        self.assertEqual(self.runner.storage_summary().staging_bytes, 7)
        self.runner.discard_job(job.id)
        self.assertFalse(partial.exists())


if __name__ == "__main__":
    unittest.main()
