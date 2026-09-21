"""Final Packet01 import boundary regressions.

These tests keep network and subprocess work faked at the external boundary
while exercising the production import services and durable records.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import BundleService
from workbench_backend.inference.hf_fetch import HuggingFaceDownload
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.import_jobs import ImportJobRunner, FUTURE_INSTALL_ROOT_KEY
from workbench_backend.inference.schemas import (
    BundleFile,
    BundleSource,
    BundleSourceKind,
    FileRole,
    HuggingFaceImportRequest,
    ImportJob,
    ImportStatus,
    LocalImportRequest,
    ModelBundle,
)
from workbench_backend.inference.store import RecordStore
from workbench_backend.paths import WorkbenchPaths

from support import write_tiny_gguf


class StaticHF:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def inspect(self, *, repo_id: str, revision: str = "main"):
        return SimpleNamespace(
            repo_id=repo_id,
            resolved_revision="a" * 40,
            file_sizes={name: len(payload) for name, payload in self.files.items()},
        )

    def download(self, *, repo_id: str, revision: str, dest: Path, allow_patterns: list[str] | None):
        local_dir = dest / ("a" * 40)
        local_dir.mkdir(parents=True, exist_ok=True)
        selected = {
            name: payload
            for name, payload in self.files.items()
            if allow_patterns is None or name in allow_patterns
        }
        for name, payload in selected.items():
            target = local_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        return HuggingFaceDownload(
            repo_id=repo_id,
            requested_revision=revision,
            resolved_revision="a" * 40,
            local_dir=local_dir,
            expected_sizes={name: len(payload) for name, payload in selected.items()},
            expected_sha256={name: hashlib.sha256(payload).hexdigest() for name, payload in selected.items()},
        )


class ImmediateDownloadProcess:
    pid = 43210
    returncode = 0

    def __init__(self, args: list[str], *, download_dir: Path, files: dict[str, bytes], **_kwargs: object) -> None:
        input_path = Path(args[-1])
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        local_dir = download_dir
        local_dir.mkdir(parents=True, exist_ok=True)
        expected_sizes: dict[str, int] = {}
        expected_sha256: dict[str, str] = {}
        for name, content in files.items():
            target = local_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            expected_sizes[name] = len(content)
            expected_sha256[name] = hashlib.sha256(content).hexdigest()
        Path(payload["output"]).write_text(
            json.dumps(
                {
                    "repo_id": payload["repo_id"],
                    "requested_revision": payload["revision"],
                    "resolved_revision": payload["revision"],
                    "local_dir": str(local_dir),
                    "expected_sizes": expected_sizes,
                    "expected_sha256": expected_sha256,
                }
            ),
            encoding="utf-8",
        )

    def poll(self) -> int:
        return self.returncode


class FinalImportBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root / "workbench").ensure()
        self.store = RecordStore(self.paths)

    def _runner(self, files: dict[str, bytes] | None = None) -> ImportJobRunner:
        bundles = BundleService(self.paths, self.store, hf=StaticHF(files or {}))
        runner = ImportJobRunner(self.paths, self.store, bundles)
        self.addCleanup(runner.close)
        return runner

    def test_hf_import_uses_future_install_root_and_repair_preserves_same_id(self) -> None:
        source = self.root / "source"
        primary = write_tiny_gguf(source / "demo-Q4_K_M.gguf", name="demo")
        files = {primary.name: primary.read_bytes()}
        future = self.root / "future-models"
        self.store.put_setting(FUTURE_INSTALL_ROOT_KEY, str(future))
        runner = self._runner(files)
        download_dir = self.paths.state / "fake-download"

        with (
            patch("workbench_backend.inference.import_jobs.subprocess.Popen", side_effect=lambda args, **kwargs: ImmediateDownloadProcess(args, download_dir=download_dir, files=files, **kwargs)),
            patch("workbench_backend.inference.import_jobs.psutil.Process", return_value=SimpleNamespace(create_time=lambda: 1.0)),
        ):
            job = runner.start_huggingface(HuggingFaceImportRequest(repo_id="org/demo", revision="main", allow_patterns=[primary.name]))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                finished = runner.get_job(job.id)
                if finished.status not in {ImportStatus.pending, ImportStatus.running, ImportStatus.stopping}:
                    break
                time.sleep(.01)
            runner.close()

        self.assertEqual(finished.status, ImportStatus.complete)
        bundle = self.store.get_bundle(finished.bundle_id or "")
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle.id, finished.bundle_id)
        self.assertTrue(Path(bundle.primary_path or "").is_relative_to(future.resolve()))

        Path(bundle.primary_path or "").write_bytes(b"corrupt")
        repair_job = self.store.put_job(
            ImportJob(
                id="import_repair",
                kind=BundleSourceKind.huggingface,
                status=ImportStatus.running,
                created_at=utc_now(),
                updated_at=utc_now(),
                repair_of_bundle_id=bundle.id,
            )
        )
        download = HuggingFaceDownload(
            repo_id="org/demo",
            requested_revision="a" * 40,
            resolved_revision="a" * 40,
            local_dir=download_dir,
            expected_sizes={primary.name: len(files[primary.name])},
            expected_sha256={primary.name: hashlib.sha256(files[primary.name]).hexdigest()},
        )

        repaired = runner._repair_huggingface_bundle(
            repair_job,
            HuggingFaceImportRequest(repo_id="org/demo", revision="a" * 40, allow_patterns=[primary.name]),
            download,
        )

        self.assertEqual(repaired.status, ImportStatus.complete)
        self.assertEqual(repaired.bundle_id, bundle.id)
        self.assertEqual(Path(bundle.primary_path or "").read_bytes(), files[primary.name])

    def test_cancel_during_hash_or_copy_leaves_no_owned_partial_install(self) -> None:
        source = self.root / "source"
        write_tiny_gguf(source / "demo-Q4_K_M.gguf", name="demo")
        bundles = BundleService(self.paths, self.store)

        def cancel_copy(source_path: Path, target: Path, **_kwargs: object) -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"partial")
            raise ManagerError("Import was stopped before it was made ready.", code="import_cancelled", status_code=409)

        with patch.object(bundles, "_copy_with_progress", side_effect=cancel_copy):
            job = bundles.import_local(LocalImportRequest(source_path=str(source)))

        self.assertEqual(job.status, ImportStatus.stopped)
        self.assertEqual(list(self.paths.models.iterdir()), [])

    def test_retry_rejects_stopping_even_without_transfer_pid(self) -> None:
        runner = self._runner()
        job = self.store.put_job(
            ImportJob(
                id="import_stopping",
                kind=BundleSourceKind.local,
                status=ImportStatus.stopping,
                source_path=str(self.root / "source"),
                created_at=utc_now(),
                updated_at=utc_now(),
                transfer_pid=None,
            )
        )

        with self.assertRaises(ManagerError) as raised:
            runner.retry_job(job.id)

        self.assertEqual(raised.exception.code, "job_active")

    def test_concurrent_retry_returns_same_attempt(self) -> None:
        source = self.root / "source"
        write_tiny_gguf(source / "demo-Q4_K_M.gguf", name="demo")
        runner = self._runner()
        failed = self.store.put_job(
            ImportJob(
                id="import_failed",
                kind=BundleSourceKind.local,
                status=ImportStatus.failed,
                source_path=str(source),
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )

        with patch.object(runner, "_launch", side_effect=lambda job, _request: job):
            first = runner.retry_job(failed.id)
            second = runner.retry_job(failed.id)

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.retry_of, failed.id)

    def test_shared_damaged_repair_file_is_protected(self) -> None:
        source = self.root / "source"
        primary = write_tiny_gguf(source / "demo-Q4_K_M.gguf", name="demo")
        files = {primary.name: primary.read_bytes()}
        bundles = BundleService(self.paths, self.store, hf=StaticHF(files))
        imported = bundles.import_huggingface(HuggingFaceImportRequest(repo_id="org/demo", revision="main", allow_patterns=[primary.name]))
        bundle = self.store.get_bundle(imported.bundle_id or "")
        self.assertIsNotNone(bundle)
        shared = ModelBundle(
            id="bundle_shared",
            display_name="shared",
            source=BundleSource(kind=BundleSourceKind.local, original_path=str(bundle.primary_path)),
            files=[
                BundleFile(
                    role=FileRole.primary_weights,
                    name=primary.name,
                    path=bundle.primary_path or "",
                    sha256=bundle.files[0].sha256,
                    size_bytes=bundle.files[0].size_bytes,
                    ownership="managed",
                )
            ],
            primary_path=bundle.primary_path,
            managed_root=bundle.managed_root,
            created_at=utc_now(),
        )
        self.store.put_bundle(shared)
        Path(bundle.primary_path or "").write_bytes(b"corrupt")
        repair_job = self.store.put_job(
            ImportJob(
                id="import_repair_shared",
                kind=BundleSourceKind.huggingface,
                status=ImportStatus.running,
                created_at=utc_now(),
                updated_at=utc_now(),
                repair_of_bundle_id=bundle.id,
            )
        )
        download_dir = self.paths.state / "repair-shared"
        download_dir.mkdir(parents=True)
        (download_dir / primary.name).write_bytes(files[primary.name])
        download = HuggingFaceDownload(
            repo_id="org/demo",
            requested_revision="a" * 40,
            resolved_revision="a" * 40,
            local_dir=download_dir,
            expected_sizes={primary.name: len(files[primary.name])},
            expected_sha256={primary.name: hashlib.sha256(files[primary.name]).hexdigest()},
        )
        runner = ImportJobRunner(self.paths, self.store, bundles)

        with self.assertRaises(ManagerError) as raised:
            runner._repair_huggingface_bundle(repair_job, HuggingFaceImportRequest(repo_id="org/demo", revision="a" * 40, allow_patterns=[primary.name]), download)

        self.assertEqual(raised.exception.code, "repair_shared_file")

    def test_cancel_after_download_process_exit_terminalizes_stopped_not_failed(self) -> None:
        source = self.root / "source"
        primary = write_tiny_gguf(source / "demo-Q4_K_M.gguf", name="demo")
        files = {primary.name: primary.read_bytes()}
        runner = self._runner(files)
        job = self.store.put_job(
            ImportJob(
                id="import_cancel_after_download",
                kind=BundleSourceKind.huggingface,
                status=ImportStatus.running,
                created_at=utc_now(),
                updated_at=utc_now(),
                repo_id="org/demo",
                requested_revision="main",
                resolved_revision="a" * 40,
                allow_patterns=[primary.name],
                staging_path=str(self.paths.state / "staging" / "hf"),
                install_root=str(self.paths.models),
                worker_id=runner.worker_id,
                cancel_requested=True,
            )
        )
        download_dir = self.paths.state / "downloaded-cancel"

        with (
            patch("workbench_backend.inference.import_jobs.subprocess.Popen", side_effect=lambda args, **kwargs: ImmediateDownloadProcess(args, download_dir=download_dir, files=files, **kwargs)),
            patch("workbench_backend.inference.import_jobs.psutil.Process", return_value=SimpleNamespace(create_time=lambda: 1.0)),
        ):
            finished = runner._run_huggingface_subprocess(job, HuggingFaceImportRequest(repo_id="org/demo", revision="a" * 40, allow_patterns=[primary.name]))

        self.assertEqual(finished.status, ImportStatus.stopped)
        self.assertNotEqual(finished.status, ImportStatus.failed)


if __name__ == "__main__":
    unittest.main()
