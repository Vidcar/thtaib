"""Durable model-import jobs and storage accounting."""

from __future__ import annotations

import tempfile
import time
import unittest
import hashlib
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import BundleService
from workbench_backend.inference.hf_fetch import HuggingFaceDownload
from workbench_backend.inference.import_jobs import ImportJobRunner
from workbench_backend.inference import import_jobs as import_job_module
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.schemas import (
    BundleSourceKind,
    HuggingFaceImportRequest,
    ImportJob,
    ImportProgress,
    ImportStage,
    ImportStatus,
    LocalImportRequest,
)
from workbench_backend.inference.store import RecordStore
from workbench_backend.paths import WorkbenchPaths

from support import write_tiny_gguf


class FakeHF:
    def __init__(
        self,
        files: dict[str, bytes],
        *,
        expected_sizes: dict[str, int | None] | None = None,
        expected_sha256: dict[str, str | None] | None = None,
    ) -> None:
        self.files = files
        self.expected_sizes = expected_sizes
        self.expected_sha256 = expected_sha256
        self.calls: list[dict[str, object]] = []

    def download(self, *, repo_id: str, revision: str, dest: Path, allow_patterns: list[str] | None):
        self.calls.append({"repo_id": repo_id, "revision": revision, "dest": dest, "allow_patterns": allow_patterns})
        local_dir = dest / "cafebabedead"
        local_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in self.files.items():
            path = local_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        return HuggingFaceDownload(
            repo_id=repo_id,
            requested_revision=revision,
            resolved_revision="cafebabedead",
            local_dir=local_dir,
            expected_sizes=self.expected_sizes or {name: len(payload) for name, payload in self.files.items()},
            expected_sha256=self.expected_sha256 or {},
        )


class ImportJobRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.store = RecordStore(self.paths)
        self.source = self.root / "incoming"
        self.primary = write_tiny_gguf(self.source / "demo-Q4_K_M.gguf", name="demo")
        self.bundles = BundleService(self.paths, self.store)
        self.runner = ImportJobRunner(self.paths, self.store, self.bundles)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _wait_done(self, job_id: str) -> ImportJob:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = self.store.get_job(job_id)
            if job and job.status not in {ImportStatus.pending, ImportStatus.running, ImportStatus.stopping}:
                thread = self.runner._threads.get(job_id)
                if thread is not None:
                    thread.join(timeout=1)
                return job
            time.sleep(0.02)
        self.fail(f"job {job_id} did not finish")

    def test_async_local_import_records_sqlite_job_and_progress(self) -> None:
        job = self.runner.start_local(LocalImportRequest(source_path=str(self.source), display_name="demo"))

        finished = self._wait_done(job.id)

        self.assertEqual(finished.status, ImportStatus.complete)
        self.assertIsNotNone(finished.bundle_id)
        self.assertEqual(finished.progress.stage, ImportStage.done)
        self.assertFalse((self.paths.state / "import_jobs.json").exists())
        conn = sqlite3.connect(self.paths.application_db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM import_jobs").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 1)

    def test_reconcile_marks_stale_running_job_interrupted(self) -> None:
        stale = self.store.put_job(
            ImportJob(
                id="import_stale",
                kind=BundleSourceKind.local,
                status=ImportStatus.running,
                created_at="2026-09-20T00:00:00Z",
                updated_at="2026-09-20T00:00:00Z",
                worker_id="old-worker",
                transfer_pid=1234,
                transfer_create_time=99.0,
            )
        )
        terminated: list[str] = []

        with patch.object(self.runner, "_terminate_transfer", side_effect=lambda job: terminated.append(job.id)):
            reconciled = self.runner.reconcile_on_startup()

        self.assertEqual(stale.id, reconciled[0].id)
        self.assertEqual(reconciled[0].status, ImportStatus.interrupted)
        self.assertEqual(terminated, [stale.id])

    def test_cancel_terminates_recorded_transfer_process(self) -> None:
        running = self.store.put_job(
            ImportJob(
                id="import_running",
                kind=BundleSourceKind.huggingface,
                status=ImportStatus.running,
                created_at="2026-09-20T00:00:00Z",
                updated_at="2026-09-20T00:00:00Z",
                worker_id=self.runner.worker_id,
                transfer_pid=1234,
                transfer_create_time=99.0,
            )
        )
        terminated: list[str] = []

        with patch.object(self.runner, "_terminate_transfer", side_effect=lambda job: terminated.append(job.id)):
            stopped = self.runner.cancel_job(running.id)

        self.assertEqual(stopped.status, ImportStatus.stopped)
        self.assertIsNone(stopped.transfer_pid)
        self.assertTrue(stopped.cancel_requested)
        self.assertEqual(terminated, [running.id])

    def test_retry_huggingface_reuses_recorded_revision(self) -> None:
        failed = self.store.put_job(
            ImportJob(
                id="import_failed",
                kind=BundleSourceKind.huggingface,
                status=ImportStatus.failed,
                created_at="2026-09-20T00:00:00Z",
                updated_at="2026-09-20T00:00:00Z",
                repo_id="org/demo",
                requested_revision="main",
                resolved_revision="cafebabedead",
                allow_patterns=["demo-Q4_K_M.gguf"],
            )
        )
        captured: list[HuggingFaceImportRequest] = []

        retry_ids: list[str | None] = []

        def fake_start(request: HuggingFaceImportRequest, *, retry_of: str | None = None) -> ImportJob:
            captured.append(request)
            retry_ids.append(retry_of)
            return ImportJob(
                id="import_retry",
                kind=BundleSourceKind.huggingface,
                status=ImportStatus.pending,
                created_at="2026-09-20T00:00:01Z",
                updated_at="2026-09-20T00:00:01Z",
            )

        with patch.object(self.runner, "start_huggingface", side_effect=fake_start):
            self.runner.retry_job(failed.id)

        self.assertEqual(captured[0].revision, "cafebabedead")
        self.assertEqual(retry_ids, [failed.id])

    def test_discard_removes_only_owned_unreferenced_staging(self) -> None:
        staging = self.paths.state / "staging" / "huggingface" / "org--demo" / "main" / "abc"
        (staging / "file.tmp").parent.mkdir(parents=True, exist_ok=True)
        (staging / "file.tmp").write_text("partial", encoding="utf-8")
        job = self.store.put_job(
            ImportJob(
                id="import_stopped",
                kind=BundleSourceKind.huggingface,
                status=ImportStatus.stopped,
                created_at="2026-09-20T00:00:00Z",
                updated_at="2026-09-20T00:00:00Z",
                staging_path=str(staging),
            )
        )

        discarded = self.runner.discard_job(job.id)

        self.assertEqual(discarded.status, ImportStatus.discarded)
        self.assertFalse(staging.exists())

    def test_storage_summary_reports_future_install_root_and_bytes(self) -> None:
        job = self.runner.start_local(LocalImportRequest(source_path=str(self.source)))
        self._wait_done(job.id)

        summary = self.runner.storage_summary()

        self.assertEqual(summary.future_install_root, str(self.paths.models))
        self.assertGreater(summary.managed_bytes, 0)
        self.assertTrue(any(location.kind == "managed" for location in summary.locations))

    def test_set_install_location_persists_future_root(self) -> None:
        future = self.root / "future-models"

        summary = self.runner.set_install_location(str(future))

        self.assertEqual(summary.future_install_root, str(future.resolve()))
        again = ImportJobRunner(self.paths, self.store, self.bundles).storage_summary()
        self.assertEqual(again.future_install_root, str(future.resolve()))

    def test_future_install_root_is_frozen_for_new_local_import(self) -> None:
        future = self.root / "future-models"
        self.runner.set_install_location(str(future))

        job = self.runner.start_local(LocalImportRequest(source_path=str(self.source)))
        finished = self._wait_done(job.id)

        bundle = self.store.get_bundle(finished.bundle_id or "")
        self.assertIsNotNone(bundle)
        self.assertEqual(finished.install_root, str(future.resolve()))
        self.assertTrue(Path(bundle.primary_path or "").is_relative_to(future.resolve()))

    def test_hf_start_preflights_known_selected_bytes_before_launch(self) -> None:
        class InspectOnlyHF:
            def inspect(self, *, repo_id: str, revision: str = "main"):
                return SimpleNamespace(
                    repo_id=repo_id,
                    resolved_revision="a" * 40,
                    file_sizes={"demo.gguf": 10_000},
                )

        runner = ImportJobRunner(self.paths, self.store, BundleService(self.paths, self.store, hf=InspectOnlyHF()))

        with (
            patch("workbench_backend.inference.bundles.shutil.disk_usage", return_value=SimpleNamespace(total=100, used=95, free=5)),
            patch.object(runner, "_launch") as launch,
        ):
            with self.assertRaises(ManagerError) as raised:
                runner.start_huggingface(HuggingFaceImportRequest(repo_id="org/demo", revision="main", allow_patterns=["demo.gguf"]))

        self.assertEqual(raised.exception.code, "disk_space_insufficient")
        self.assertEqual(raised.exception.details["expected_bytes"], 20_000)
        launch.assert_not_called()

    def test_worker_exception_terminalizes_interrupted_job(self) -> None:
        job = self.store.put_job(
            ImportJob(
                id="import_boom",
                kind=BundleSourceKind.local,
                status=ImportStatus.running,
                created_at="2026-09-20T00:00:00Z",
                updated_at="2026-09-20T00:00:00Z",
                worker_id=self.runner.worker_id,
                source_path=str(self.source),
            )
        )
        with patch.object(self.bundles, "import_local", side_effect=RuntimeError("boom")):
            self.runner._run(job.id, LocalImportRequest(source_path=str(self.source)))

        finished = self.store.get_job(job.id)
        self.assertEqual(finished.status, ImportStatus.interrupted)
        self.assertIn("boom", finished.error or "")

    def test_download_child_waits_for_durable_transfer_identity(self) -> None:
        proc = import_job_module.psutil.Process(os.getpid())
        self.store.put_job(
            ImportJob(
                id="import_child",
                kind=BundleSourceKind.huggingface,
                status=ImportStatus.running,
                created_at="2026-09-20T00:00:00Z",
                updated_at="2026-09-20T00:00:00Z",
                transfer_pid=os.getpid(),
                transfer_create_time=proc.create_time(),
            )
        )

        import_job_module._wait_for_durable_transfer_identity(
            {
                "job_id": "import_child",
                "application_db": str(self.paths.application_db),
                "parent_pid": os.getpid(),
                "parent_create_time": proc.create_time(),
            }
        )


class ImportVerificationTests(unittest.TestCase):
    def test_local_import_can_record_external_original_without_copying(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp) / "workbench").ensure()
            external = Path(tmp) / "external"
            primary = write_tiny_gguf(external / "demo-Q4_K_M.gguf", name="demo")
            store = RecordStore(paths)
            bundles = BundleService(paths, store)

            job = bundles.import_local(LocalImportRequest(source_path=str(external), copy_files=False))

            self.assertEqual(job.status, ImportStatus.complete)
            bundle = store.get_bundle(job.bundle_id or "")
            self.assertIsNotNone(bundle)
            self.assertEqual(bundle.primary_path, str(primary.resolve()))
            self.assertTrue(all(item.ownership == "external" for item in bundle.files))
            self.assertIsNone(bundle.managed_root)
            verified = bundles.verify_bundle(bundle)
            self.assertTrue(verified.disk_matches)
            self.assertFalse(any(paths.models.rglob("*.gguf")))

    def test_copy_files_false_preserves_original_inside_models_as_external(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp) / "workbench").ensure()
            original = write_tiny_gguf(paths.models / "manual" / "demo-Q4_K_M.gguf", name="demo")
            store = RecordStore(paths)
            bundles = BundleService(paths, store)

            job = bundles.import_local(LocalImportRequest(source_path=str(original), copy_files=False))

            bundle = store.get_bundle(job.bundle_id or "")
            self.assertIsNotNone(bundle)
            self.assertEqual(bundle.primary_path, str(original.resolve()))
            self.assertEqual(bundle.files[0].ownership, "external")
            self.assertIsNone(bundle.managed_root)

    def test_copy_failure_removes_owned_partial_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp) / "workbench").ensure()
            source = Path(tmp) / "source"
            write_tiny_gguf(source / "demo-Q4_K_M.gguf", name="demo")
            store = RecordStore(paths)
            bundles = BundleService(paths, store)

            def fail_copy(source_path: Path, target: Path, **_kwargs) -> None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"partial")
                raise OSError("copy failed")

            with patch.object(bundles, "_copy_with_progress", side_effect=fail_copy):
                job = bundles.import_local(LocalImportRequest(source_path=str(source)))

            self.assertEqual(job.status, ImportStatus.interrupted)
            self.assertEqual(list(paths.models.iterdir()), [])

    def test_local_import_preflights_disk_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp) / "workbench").ensure()
            source = Path(tmp) / "source"
            write_tiny_gguf(source / "demo-Q4_K_M.gguf", name="demo")
            store = RecordStore(paths)
            bundles = BundleService(paths, store)

            with (
                patch("workbench_backend.inference.bundles.shutil.disk_usage", return_value=SimpleNamespace(total=100, used=99, free=1)),
                patch.object(bundles, "_copy_with_progress") as copy,
            ):
                job = bundles.import_local(LocalImportRequest(source_path=str(source)))

            self.assertEqual(job.status, ImportStatus.failed)
            self.assertIn("not enough free disk space", job.error or "")
            copy.assert_not_called()

    def test_hf_import_rejects_size_mismatch_before_bundle_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp)).ensure()
            source = Path(tmp) / "source"
            primary = write_tiny_gguf(source / "demo-Q4_K_M.gguf", name="demo")
            store = RecordStore(paths)
            hf = FakeHF({primary.name: primary.read_bytes()}, expected_sizes={primary.name: primary.stat().st_size + 1})
            bundles = BundleService(paths, store, hf=hf)

            job = bundles.import_huggingface(HuggingFaceImportRequest(repo_id="org/demo", revision="main"))

            self.assertEqual(job.status, ImportStatus.failed)
            self.assertIn("did not match", job.error or "")
            self.assertEqual(store.list_bundles(), [])

    def test_hf_import_rejects_hash_mismatch_before_bundle_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp)).ensure()
            source = Path(tmp) / "source"
            primary = write_tiny_gguf(source / "demo-Q4_K_M.gguf", name="demo")
            store = RecordStore(paths)
            hf = FakeHF({primary.name: primary.read_bytes()}, expected_sha256={primary.name: "0" * 64})
            bundles = BundleService(paths, store, hf=hf)

            job = bundles.import_huggingface(HuggingFaceImportRequest(repo_id="org/demo", revision="main"))

            self.assertEqual(job.status, ImportStatus.failed)
            self.assertIn("hash did not match", job.error or "")
            self.assertEqual(store.list_bundles(), [])

    def test_repair_preserves_same_bundle_id_and_restores_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp)).ensure()
            source = Path(tmp) / "source"
            primary = write_tiny_gguf(source / "demo-Q4_K_M.gguf", name="demo")
            store = RecordStore(paths)
            good_bytes = primary.read_bytes()
            hf = FakeHF(
                {primary.name: good_bytes},
                expected_sha256={primary.name: hashlib.sha256(good_bytes).hexdigest()},
            )
            bundles = BundleService(paths, store, hf=hf)
            imported = bundles.import_huggingface(HuggingFaceImportRequest(repo_id="org/demo", revision="cafebabedead"))
            bundle = store.get_bundle(imported.bundle_id or "")
            self.assertIsNotNone(bundle)
            Path(bundle.primary_path or "").write_bytes(b"corrupt-but-repairable")
            runner = ImportJobRunner(paths, store, bundles)
            download = hf.download(repo_id="org/demo", revision="cafebabedead", dest=paths.state / "repair", allow_patterns=[primary.name])
            job = ImportJob(
                id="import_repair",
                kind=BundleSourceKind.huggingface,
                status=ImportStatus.running,
                created_at="2026-09-20T00:00:00Z",
                updated_at="2026-09-20T00:00:00Z",
                repair_of_bundle_id=bundle.id,
            )
            store.put_job(job)

            repaired = runner._repair_huggingface_bundle(job, HuggingFaceImportRequest(repo_id="org/demo", revision="cafebabedead", allow_patterns=[primary.name]), download)

            self.assertEqual(repaired.status, ImportStatus.complete)
            self.assertEqual(repaired.bundle_id, bundle.id)
            self.assertEqual(Path(bundle.primary_path or "").read_bytes(), good_bytes)

    def test_repair_only_replaces_broken_files_and_uses_lifecycle_guard(self) -> None:
        class FakeLifecycle:
            def __init__(self) -> None:
                self.bundle_ids: list[set[str]] = []

            def mutate(self, _operation: str, *, bundle_ids: set[str]):
                self.bundle_ids.append(bundle_ids)
                from contextlib import nullcontext

                return nullcontext()

        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp)).ensure()
            source = Path(tmp) / "source"
            primary = write_tiny_gguf(source / "demo-Q4_K_M.gguf", name="demo")
            companion = source / "tokenizer.json"
            companion.write_text("{}", encoding="utf-8")
            store = RecordStore(paths)
            good_bytes = primary.read_bytes()
            hf = FakeHF(
                {primary.name: good_bytes, companion.name: companion.read_bytes()},
                expected_sha256={primary.name: hashlib.sha256(good_bytes).hexdigest()},
            )
            bundles = BundleService(paths, store, hf=hf)
            imported = bundles.import_huggingface(HuggingFaceImportRequest(repo_id="org/demo", revision="cafebabedead"))
            bundle = store.get_bundle(imported.bundle_id or "")
            self.assertIsNotNone(bundle)
            healthy = next(item for item in bundle.files if item.name == "tokenizer.json")
            healthy_path = Path(healthy.path)
            before_hash = sha256_file(healthy_path)
            Path(bundle.primary_path or "").write_bytes(b"corrupt-but-repairable")
            lifecycle = FakeLifecycle()
            runner = ImportJobRunner(paths, store, bundles, lifecycle=lifecycle)
            download = hf.download(repo_id="org/demo", revision="cafebabedead", dest=paths.state / "repair", allow_patterns=[item.name for item in bundle.files])
            job = ImportJob(
                id="import_repair_guarded",
                kind=BundleSourceKind.huggingface,
                status=ImportStatus.running,
                created_at="2026-09-20T00:00:00Z",
                updated_at="2026-09-20T00:00:00Z",
                repair_of_bundle_id=bundle.id,
            )
            store.put_job(job)

            repaired = runner._repair_huggingface_bundle(job, HuggingFaceImportRequest(repo_id="org/demo", revision="cafebabedead", allow_patterns=[item.name for item in bundle.files]), download)

            self.assertEqual(repaired.bundle_id, bundle.id)
            self.assertEqual(lifecycle.bundle_ids, [{bundle.id}])
            self.assertEqual(Path(bundle.primary_path or "").read_bytes(), good_bytes)
            self.assertEqual(sha256_file(healthy_path), before_hash)


if __name__ == "__main__":
    unittest.main()
