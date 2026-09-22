"""Storage and process safety at the durable import boundary."""
import tempfile
import unittest
import subprocess
import sys
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import psutil

from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import BundleService
from workbench_backend.inference.import_jobs import ImportJobRunner
from workbench_backend.inference.schemas import BundleSourceKind, ImportJob, ImportStatus
from workbench_backend.inference.schemas import ImportStage
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
        marker = self.paths.state / 'actual-worker.json'
        child = subprocess.Popen([sys.executable, '-c',
            'import os,time,json,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"pid":os.getpid()})); time.sleep(60)', str(marker)])
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(marker.exists())
        actual_pid = json.loads(marker.read_text())['pid']
        actual = psutil.Process(actual_pid)
        self.addCleanup(lambda: actual.kill() if actual.is_running() else None)
        identity = psutil.Process(child.pid).create_time()
        job = self.job('real-child', ImportStatus.running, worker_id='old-worker',
                       transfer_pid=child.pid, transfer_create_time=identity)
        self.runner.reconcile_on_startup()
        child.wait(timeout=5)
        current = self.store.get_job(job.id)
        self.assertEqual(current.status, ImportStatus.interrupted)
        self.assertIsNone(current.transfer_pid)
        self.assertIsNotNone(child.poll())
        self.assertFalse(actual.is_running(), 'The launcher exited but its real Python worker survived')

    def test_real_python_worker_adopts_only_durable_launcher_before_transfer(self):
        marker = self.paths.state / 'transfer-started.json'
        owner = psutil.Process(os.getpid())
        payload = {'job_id': 'launcher-transfer', 'application_db': str(self.paths.application_db),
                   'parent_pid': owner.pid, 'parent_create_time': owner.create_time()}
        job = self.job(payload['job_id'], ImportStatus.running, worker_id=self.runner.worker_id)
        source = '\n'.join([
            'import os,json,sys,time',
            'from pathlib import Path',
            'from workbench_backend.inference.import_jobs import _wait_for_durable_transfer_identity',
            '_wait_for_durable_transfer_identity(json.loads(sys.argv[1]))',
            'Path(sys.argv[2]).write_text(json.dumps({"pid":os.getpid()}))',
            'time.sleep(60)',
        ])
        child = subprocess.Popen([sys.executable, '-c', source, json.dumps(payload), str(marker)])
        identity = psutil.Process(child.pid).create_time()
        self.addCleanup(lambda: self.runner._terminate_transfer(self.store.get_job(job.id)))
        self.addCleanup(lambda: child.wait(timeout=5) if child.poll() is not None else None)
        self.store.update_job_fields(job.id, transfer_pid=child.pid, transfer_create_time=identity)
        deadline = time.monotonic() + 15
        while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(marker.exists(), f'Actual worker did not pass the durable identity handshake (exit={child.poll()})')
        actual_pid = json.loads(marker.read_text())['pid']
        current = self.store.get_job(job.id)
        self.assertEqual(current.transfer_pid, actual_pid)
        self.assertAlmostEqual(current.transfer_create_time, psutil.Process(actual_pid).create_time())
        self.runner.cancel_job(job.id)
        child.wait(timeout=5)
        self.assertFalse(psutil.pid_exists(actual_pid))

    def test_stopped_job_cannot_pass_durable_handshake_or_begin_transfer(self):
        from workbench_backend.inference.import_jobs import _wait_for_durable_transfer_identity
        owner = psutil.Process(os.getpid())
        self.job('stopped-transfer', ImportStatus.stopping, cancel_requested=True,
                 transfer_pid=owner.pid, transfer_create_time=owner.create_time())
        with self.assertRaisesRegex(RuntimeError, 'stopped before'):
            _wait_for_durable_transfer_identity({'job_id': 'stopped-transfer',
                'application_db': str(self.paths.application_db), 'parent_pid': owner.pid,
                'parent_create_time': owner.create_time()})

    def test_progress_update_cannot_replace_a_workers_new_durable_identity(self):
        job = self.job('identity-race', ImportStatus.running, transfer_pid=123, transfer_create_time=1.0)
        original = self.runner.get_job
        def handoff_after_read(job_id):
            old = original(job_id)
            self.store.update_job_fields(job_id, transfer_pid=456, transfer_create_time=2.0)
            return old
        with patch.object(self.runner, 'get_job', side_effect=handoff_after_read):
            self.runner._record_progress(job.id, ImportStage.transfer, 'Downloading selected files', 0, 1, 100, 200)
        current = self.store.get_job(job.id)
        self.assertEqual((current.transfer_pid, current.transfer_create_time), (456, 2.0))
        self.assertEqual(current.progress.bytes_done, 100)

    def test_transfer_progress_counts_payloads_without_hub_metadata_or_alternatives(self):
        root = self.paths.state / 'progress'
        cache = root / '.cache' / 'huggingface' / 'download'
        cache.mkdir(parents=True)
        (root / 'README.md').write_bytes(b'card')
        (root / 'model.gguf').write_bytes(b'complete')
        (root / 'other.gguf').write_bytes(b'exclude alternative')
        (cache / 'mmproj.hash.incomplete').write_bytes(b'partial')
        (cache / 'model.gguf.metadata').write_bytes(b'not payload')
        (cache / 'model.gguf.lock').write_bytes(b'not payload')
        self.assertEqual(self.runner._transfer_progress(root, ['README.md', 'model.gguf', 'mmproj.gguf']), (2, 19))

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
