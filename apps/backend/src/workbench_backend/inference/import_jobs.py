"""Durable import-job orchestration for model bundle imports."""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
import argparse
from contextlib import nullcontext
import json
import os
import sqlite3
import fnmatch

import psutil
from huggingface_hub import scan_cache_dir, get_token
from huggingface_hub.errors import CacheNotFound

from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import BundleService, collect_bundle_files, ensure_disk_space, stable_hf_staging_path
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.hf_fetch import HuggingFaceDownload, HuggingFaceFetcher
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.schemas import (
    BundleSourceKind,
    HuggingFaceImportRequest,
    ImportJob,
    ImportProgress,
    ImportStage,
    ImportStatus,
    LocalImportRequest,
    ModelBundle,
    StorageLocation,
    StorageSummary,
)
from workbench_backend.inference.store import RecordStore
from workbench_backend.paths import WorkbenchPaths

FUTURE_INSTALL_ROOT_KEY = "models.future_install_root"


class ImportJobRunner:
    """Owns asynchronous import workers and durable job state.

    Hugging Face transfers run in an owned subprocess because
    ``huggingface_hub.snapshot_download`` does not expose a cooperative
    cancellation callback. The subprocess still uses ``HuggingFaceFetcher`` and
    the pinned Hugging Face library boundary.
    """

    def __init__(
        self,
        paths: WorkbenchPaths,
        store: RecordStore,
        bundles: BundleService,
        lifecycle: object | None = None,
        require_repair_allowed=None,
    ) -> None:
        self.paths = paths.ensure()
        self.store = store
        self.bundles = bundles
        self.lifecycle = lifecycle
        self.require_repair_allowed = require_repair_allowed
        self.worker_id = f"import_worker_{uuid.uuid4().hex[:12]}"
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.RLock()
        self._job_lock = threading.RLock()

    def close(self) -> None:
        for job in self.store.list_active_jobs():
            if job.worker_id == self.worker_id:
                self.cancel_job(job.id)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with self._lock:
                threads = list(self._threads.values())
            if not threads:
                return
            for thread in threads:
                thread.join(timeout=0.2)
        for job in self.store.list_active_jobs():
            if job.worker_id == self.worker_id and job.transfer_pid is not None:
                self._terminate_transfer(job)
        with self._lock:
            alive = [thread for thread in self._threads.values() if thread.is_alive()]
        if alive:
            raise ManagerError("Import workers have not confirmed shutdown; retained files remain protected.", code="import_stop_unconfirmed", status_code=409)

    def reconcile_on_startup(self) -> list[ImportJob]:
        reconciled: list[ImportJob] = []
        for job in self.store.list_active_jobs():
            if job.worker_id != self.worker_id:
                try:
                    self._terminate_transfer(job)
                except ManagerError as exc:
                    reconciled.append(self.store.put_job(job.model_copy(update={
                        "status": ImportStatus.stopping, "cancel_requested": True,
                        "error": exc.message, "updated_at": utc_now(),
                    })))
                    continue
                bundle = self.store.get_bundle(job.bundle_id or "")
                if bundle is not None and bundle.status == ImportStatus.complete:
                    reconciled.append(self.store.update_job_fields(job.id, status=ImportStatus.complete,
                        finished_at=utc_now(), updated_at=utc_now(), cancel_requested=False,
                        transfer_pid=None, transfer_create_time=None,
                        progress=ImportProgress(stage=ImportStage.done, message="Recovered completed installation")))
                    continue
                reconciled.append(
                    self.store.put_job(
                        job.model_copy(
                            update={
                                "status": ImportStatus.interrupted,
                                "error": "Import worker stopped before the job finished.",
                                "finished_at": utc_now(),
                                "updated_at": utc_now(),
                                "cancel_requested": False,
                                "transfer_pid": None,
                                "transfer_create_time": None,
                            }
                        )
                    )
                )
        return reconciled

    def start_huggingface(self, request: HuggingFaceImportRequest, *, retry_of: str | None = None) -> ImportJob:
        with self._job_lock:
            listing = self.bundles.hf.inspect(repo_id=request.repo_id, revision=request.revision)
            pinned = request.model_copy(update={"repo_id": listing.repo_id, "revision": listing.resolved_revision})
            staging = stable_hf_staging_path(
                self.paths.state,
                repo_id=pinned.repo_id,
                revision=pinned.revision,
                allow_patterns=request.allow_patterns,
            )
            selected_bytes = self._selected_known_bytes(listing, request.allow_patterns)
            if selected_bytes:
                self._preflight_hf_space(staging, self._future_install_root(), selected_bytes)
            self._require_no_active_staging(staging)
            job = ImportJob(
                id=new_id("import"),
                kind=BundleSourceKind.huggingface,
                status=ImportStatus.pending,
                display_name=request.display_name,
                created_at=utc_now(),
                updated_at=utc_now(),
                repo_id=pinned.repo_id,
                requested_revision=request.revision,
                resolved_revision=pinned.revision,
                allow_patterns=request.allow_patterns,
                staging_path=str(staging),
                install_root=str(self._future_install_root()),
                retry_of=retry_of,
                progress=ImportProgress(stage=ImportStage.queued, message="Waiting to start", bytes_total=selected_bytes,
                    files_total=len([name for name in listing.file_sizes if request.allow_patterns is None or
                        any(fnmatch.fnmatchcase(name, pattern) for pattern in request.allow_patterns)]) or None),
            )
            self.store.put_job(job)
        return self._launch(job, pinned)

    def start_local(self, request: LocalImportRequest, *, retry_of: str | None = None) -> ImportJob:
        with self._job_lock:
            job = ImportJob(
                id=new_id("import"),
                kind=BundleSourceKind.local,
                status=ImportStatus.pending,
                display_name=request.display_name,
                created_at=utc_now(),
                updated_at=utc_now(),
                source_path=request.source_path,
                install_root=str(self._future_install_root()),
                retry_of=retry_of,
                progress=ImportProgress(stage=ImportStage.queued, message="Waiting to start"),
            )
            self.store.put_job(job)
            self.store.put_setting(self._copy_files_key(job.id), "true" if request.copy_files else "false")
        return self._launch(job, request)

    def list_jobs(self) -> list[ImportJob]:
        return self.store.list_jobs()

    def get_job(self, job_id: str) -> ImportJob:
        job = self.store.get_job(job_id)
        if job is None:
            raise ManagerError("Unknown import job", code="job_missing", status_code=404)
        return job

    def bundle_jobs(self, bundle: ModelBundle) -> list[ImportJob]:
        """Find the installed bundle's imports, repairs and retry lineage."""
        jobs = [job for job in self.store.list_jobs() if job.bundle_id in {None, bundle.id}
                and job.repair_of_bundle_id in {None, bundle.id}]
        related = {job.id for job in jobs if job.bundle_id == bundle.id or job.repair_of_bundle_id == bundle.id}
        while True:
            expanded = related | {job.retry_of for job in jobs if job.id in related and job.retry_of} | {
                job.id for job in jobs if job.retry_of in related
            }
            if expanded == related:
                return [job for job in jobs if job.id in related]
            related = expanded

    def job_is_active(self, job: ImportJob) -> bool:
        with self._lock:
            thread = self._threads.get(job.id)
            return (job.status in {ImportStatus.pending, ImportStatus.running, ImportStatus.stopping}
                    or job.transfer_pid is not None or (thread is not None and thread.is_alive()))

    def purge_bundle_jobs(self, bundle: ModelBundle) -> None:
        """Remove only this model's inactive import records and owned staging."""
        with self._job_lock:
            jobs = self.bundle_jobs(bundle)
            if any(self.job_is_active(job) for job in jobs):
                raise ManagerError("Stop the model's import before deleting it.", code="job_active", status_code=409)
            ignored = {job.id for job in jobs}
            for job in jobs:
                if job.staging_path:
                    staging = Path(job.staging_path)
                    if staging.exists() and self._owns_staging(staging) and not self._staging_is_referenced(staging, ignore_job_ids=ignored):
                        shutil.rmtree(staging)
                self.store.delete_job(job.id)

    def bundle_staging_files(self, bundle: ModelBundle) -> list[Path]:
        jobs = self.bundle_jobs(bundle)
        ignored = {job.id for job in jobs}
        files: dict[str, Path] = {}
        for job in jobs:
            if not job.staging_path:
                continue
            root = Path(job.staging_path)
            if not self._owns_staging(root) or self._staging_is_referenced(root, ignore_job_ids=ignored):
                continue
            for path in root.rglob("*"):
                if path.is_file() and path.resolve().is_relative_to(root.resolve()):
                    files[str(path.resolve()).casefold()] = path
        return list(files.values())

    def cancel_job(self, job_id: str) -> ImportJob:
        with self._job_lock:
            job = self.get_job(job_id)
            if job.status not in {ImportStatus.pending, ImportStatus.running, ImportStatus.stopping}:
                return job
            stopping = self.store.put_job(
                job.model_copy(
                    update={
                        "status": ImportStatus.stopping,
                        "cancel_requested": True,
                        "updated_at": utc_now(),
                        "progress": job.progress.model_copy(update={"message": "Stopping import"}),
                    }
                )
            )
        if stopping.transfer_pid is not None:
            self._terminate_transfer(stopping)
        with self._lock:
            owned_thread = self._threads.get(job_id)
        if stopping.status == ImportStatus.stopping and owned_thread is None:
            return self.store.put_job(self.get_job(job_id).model_copy(update={
                "status": ImportStatus.stopped, "transfer_pid": None, "transfer_create_time": None,
                "finished_at": utc_now(), "updated_at": utc_now(),
            }))
        return self.get_job(job_id)

    def retry_job(self, job_id: str) -> ImportJob:
        with self._job_lock:
            attempts = [job for job in self.store.list_jobs() if job.retry_of == job_id]
            if attempts:
                return attempts[-1]
            return self._retry_job_locked(job_id)

    def _retry_job_locked(self, job_id: str) -> ImportJob:
        job = self.get_job(job_id)
        if job.status == ImportStatus.complete:
            return job
        if job.status in {ImportStatus.pending, ImportStatus.running, ImportStatus.stopping}:
            raise ManagerError("Wait for the current import attempt to stop before retrying.", code="job_active", status_code=409)
        if job.repair_of_bundle_id:
            return self.start_repair(job.repair_of_bundle_id, retry_of=job.id)
        if job.kind == BundleSourceKind.huggingface:
            if not job.repo_id:
                raise ManagerError("Hugging Face retry is missing its source repository.", code="job_retry_source", status_code=400)
            request = HuggingFaceImportRequest(
                repo_id=job.repo_id,
                revision=job.resolved_revision or job.requested_revision or "main",
                allow_patterns=job.allow_patterns,
                display_name=job.display_name,
            )
            retried = self.start_huggingface(request, retry_of=job.id)
        else:
            if not job.source_path:
                raise ManagerError("Local retry is missing its source path.", code="job_retry_source", status_code=400)
            copy_files = self.store.get_setting(self._copy_files_key(job.id)) != "false"
            retried = self.start_local(LocalImportRequest(source_path=job.source_path, display_name=job.display_name, copy_files=copy_files), retry_of=job.id)
        if job.kind == BundleSourceKind.local:
            self.store.put_setting(self._copy_files_key(retried.id), self.store.get_setting(self._copy_files_key(job.id)) or "true")
        return retried

    def start_repair(self, bundle_id: str, *, retry_of: str | None = None) -> ImportJob:
        bundle = self.store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)
        if bundle.source.kind != BundleSourceKind.huggingface or not bundle.source.repo_id or not bundle.source.resolved_revision:
            raise ManagerError("Only Hugging Face bundles with a recorded revision can be repaired.", code="repair_source", status_code=400)
        request = HuggingFaceImportRequest(
            repo_id=bundle.source.repo_id,
            revision=bundle.source.resolved_revision,
            allow_patterns=[item.name.replace("[", "[[]").replace("?", "[?]").replace("*", "[*]") for item in bundle.files],
            display_name=bundle.display_name,
        )
        with self._job_lock:
            staging = stable_hf_staging_path(
                self.paths.state,
                repo_id=request.repo_id,
                revision=request.revision,
                allow_patterns=request.allow_patterns,
            )
            self._require_no_active_staging(staging)
            job = ImportJob(
                id=new_id("import"),
                kind=BundleSourceKind.huggingface,
                status=ImportStatus.pending,
                display_name=bundle.display_name,
                created_at=utc_now(),
                updated_at=utc_now(),
                repo_id=request.repo_id,
                requested_revision=bundle.source.requested_revision,
                resolved_revision=request.revision,
                allow_patterns=request.allow_patterns,
                staging_path=str(staging),
                install_root=str(self._future_install_root()),
                repair_of_bundle_id=bundle.id,
                retry_of=retry_of,
                progress=ImportProgress(stage=ImportStage.repair, message="Repairing recorded bundle"),
            )
            self.store.put_job(job)
        return self._launch(job, request)

    def set_install_location(self, path: str) -> StorageSummary:
        target = Path(path).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        if not target.is_dir():
            raise ManagerError("Install location must be a directory.", code="storage_location", status_code=400)
        probe = target / f".workbench-write-test-{uuid.uuid4().hex}"
        try:
            probe.write_text("ok", encoding="utf-8")
        except OSError as exc:
            raise ManagerError("Install location is not writable.", code="storage_location_writable", status_code=400) from exc
        finally:
            probe.unlink(missing_ok=True)
        self.store.put_setting(FUTURE_INSTALL_ROOT_KEY, str(target))
        return self.storage_summary()

    def discard_job(self, job_id: str) -> ImportJob:
        with self._job_lock:
            return self._discard_job_locked(job_id)

    def _discard_job_locked(self, job_id: str) -> ImportJob:
        job = self.get_job(job_id)
        if job.status in {ImportStatus.pending, ImportStatus.running, ImportStatus.stopping}:
            raise ManagerError("Stop the import before discarding it.", code="job_active", status_code=409)
        self._discard_partial_owned_install(job)
        if job.staging_path:
            staging = Path(job.staging_path)
            if self._owns_staging(staging) and not self._staging_is_referenced(staging, ignore_job_ids={job.id}):
                if staging.exists():
                    shutil.rmtree(staging)
        return self.store.put_job(
            job.model_copy(
                update={
                    "status": ImportStatus.discarded,
                    "updated_at": utc_now(),
                    "finished_at": job.finished_at or utc_now(),
                    "progress": ImportProgress(stage=ImportStage.cleanup, message="Discarded stopped import"),
                }
            )
        )

    def storage_summary(self) -> StorageSummary:
        # Only recorded, explicitly managed files belong to this product. A user
        # may select a directory that also contains unrelated files.
        managed_files = {Path(item.path).resolve() for bundle in self.store.list_bundles()
                         for item in bundle.files if item.ownership == "managed"
                         and bundle.managed_root and Path(item.path).resolve().is_relative_to(Path(bundle.managed_root).resolve())}
        managed = sum(path.stat().st_size for path in managed_files if path.is_file())
        staging_root = self.paths.state / "staging"
        staging = self._bytes_under(staging_root)
        download_metadata = [path for path in staging_root.rglob("*") if path.is_file()
                             and ".cache" in path.relative_to(staging_root).parts and path.suffix != ".incomplete"]
        download_metadata_bytes = sum(path.stat().st_size for path in download_metadata)
        staging -= download_metadata_bytes
        partial_roots = {Path(job.owned_install_path).resolve() for job in self.store.list_jobs()
                         if job.owned_install_path and job.status != ImportStatus.complete
                         and not any(_paths_overlap(Path(job.owned_install_path).resolve(), path) for path in managed_files)}
        staging += sum(self._bytes_under(path) for path in partial_roots)
        cache, cache_root, cache_reclaimable = self._hf_cache_usage()
        metadata_paths = [path for path in self.paths.state.rglob("*") if path.is_file()
                          and not path.resolve().is_relative_to(staging_root.resolve())
                          and not path.resolve().is_relative_to((self.paths.state / "huggingface-cache").resolve())]
        metadata_paths.extend(path for path in self.paths.root.glob("application.sqlite*") if path.is_file())
        metadata = sum(path.stat().st_size for path in metadata_paths) + download_metadata_bytes
        future = Path(self.store.get_setting(FUTURE_INSTALL_ROOT_KEY) or self.paths.models)
        capacity_root = future
        while not capacity_root.exists() and capacity_root != capacity_root.parent:
            capacity_root = capacity_root.parent
        usage = shutil.disk_usage(capacity_root)
        reclaimable_staging = sum(self._bytes_under(path) for path in self._cleanup_staging_candidates())
        roots = {Path(bundle.managed_root).resolve() for bundle in self.store.list_bundles() if bundle.managed_root}
        locations = [StorageLocation(kind="managed", path=str(root),
                     bytes=sum(path.stat().st_size for path in managed_files if path.is_file() and path.is_relative_to(root)),
                     reference_count=sum(1 for b in self.store.list_bundles() if b.managed_root and Path(b.managed_root).resolve() == root))
                     for root in sorted(roots)]
        locations.extend([
            StorageLocation(kind="staging", path=str(staging_root), bytes=staging, removable=reclaimable_staging > 0, reference_count=self._staging_reference_count(staging_root)),
            StorageLocation(kind="cache", path=str(cache_root), bytes=cache, removable=cache_reclaimable > 0, reference_count=0),
            StorageLocation(kind="metadata", path=str(self.paths.state), bytes=metadata, reference_count=0),
        ])
        locations.extend(StorageLocation(kind="staging", path=str(path), bytes=self._bytes_under(path), reference_count=1) for path in sorted(partial_roots))
        return StorageSummary(
            install_root=str(self.paths.models),
            future_install_root=self.store.get_setting(FUTURE_INSTALL_ROOT_KEY) or str(self.paths.models),
            managed_bytes=managed,
            staging_bytes=staging,
            cache_bytes=cache,
            metadata_bytes=metadata,
            reclaimable_bytes=reclaimable_staging + cache_reclaimable,
            capacity_bytes=usage.total,
            available_bytes=usage.free,
            locations=locations,
        )

    def cleanup_unreferenced_staging(self) -> list[str]:
        with self._job_lock:
            removed = []
            for path in self._cleanup_staging_candidates():
                if path.exists():
                    shutil.rmtree(path)
                    removed.append(str(path))
            return removed

    def _cleanup_staging_candidates(self) -> list[Path]:
        removed: list[Path] = []
        candidates: dict[str, Path] = {}
        for job in self.store.list_jobs():
            if job.status not in {ImportStatus.complete, ImportStatus.discarded}:
                continue
            if not job.staging_path:
                continue
            path = Path(job.staging_path)
            if self._owns_staging(path):
                candidates[str(path.resolve())] = path
        for path in candidates.values():
            ignored = {
                job.id
                for job in self.store.list_jobs()
                if job.staging_path
                and Path(job.staging_path).resolve() == path.resolve()
                and job.status in {ImportStatus.complete, ImportStatus.discarded}
            }
            if not path.exists() or self._staging_is_referenced(path, ignore_job_ids=ignored):
                continue
            removed.append(path)
        # Avoid overlapping recursive deletions or counting their bytes twice.
        return [path for path in removed if not any(path != other and path.resolve().is_relative_to(other.resolve()) for other in removed)]

    def cleanup_cache(self) -> list[str]:
        with self._job_lock:
            try:
                cache_info = scan_cache_dir(self.paths.state / "huggingface-cache" / "hub")
            except CacheNotFound:
                return []
            revisions = self._unreferenced_cache_revisions(cache_info)
            if revisions:
                cache_info.delete_revisions(*revisions).execute()
            return revisions

    def _unreferenced_cache_revisions(self, cache_info) -> list[str]:
        protected = {b.source.resolved_revision for b in self.store.list_bundles() if b.source.resolved_revision}
        for job in self.store.list_jobs():
            if job.status not in {ImportStatus.complete, ImportStatus.discarded}:
                if not job.resolved_revision:
                    return []
                protected.add(job.resolved_revision)
        return sorted({revision.commit_hash for repo in cache_info.repos for revision in repo.revisions
                       if revision.commit_hash not in protected})

    def _hf_cache_usage(self) -> tuple[int, Path, int]:
        cache_dir = self.paths.state / "huggingface-cache" / "hub"
        try:
            cache_info = scan_cache_dir(cache_dir)
        except CacheNotFound:
            return self._bytes_under(cache_dir.parent), cache_dir.parent, 0
        reclaimable = 0
        try:
            revisions = self._unreferenced_cache_revisions(cache_info)
            if revisions:
                reclaimable = int(getattr(cache_info.delete_revisions(*revisions), "expected_freed_size", 0) or 0)
        except Exception:
            reclaimable = 0
        return self._bytes_under(cache_dir.parent), cache_dir.parent, reclaimable

    def _launch(self, job: ImportJob, request: HuggingFaceImportRequest | LocalImportRequest) -> ImportJob:
        with self._job_lock:
            current = self.get_job(job.id)
            if current.cancel_requested or current.status in {ImportStatus.stopped, ImportStatus.discarded}:
                return current
            return self._launch_locked(current, request)

    def _launch_locked(self, job: ImportJob, request: HuggingFaceImportRequest | LocalImportRequest) -> ImportJob:
        started = self.store.put_job(
            job.model_copy(
                update={
                    "status": ImportStatus.running,
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                    "worker_id": self.worker_id,
                    "progress": job.progress.model_copy(update={"stage": ImportStage.queued, "message": "Starting import"}),
                }
            )
        )
        thread = threading.Thread(target=self._run, args=(started.id, request), name=f"import-job-{started.id}", daemon=True)
        with self._lock:
            self._threads[started.id] = thread
        thread.start()
        return started

    def _run(self, job_id: str, request: HuggingFaceImportRequest | LocalImportRequest) -> None:
        job = self.get_job(job_id)
        try:
            if isinstance(request, HuggingFaceImportRequest):
                result = self._run_huggingface_subprocess(
                    job,
                    request,
                )
            else:
                current = self.get_job(job_id)
                local_request = request.model_copy(
                    update={"copy_files": self.store.get_setting(self._copy_files_key(job_id)) != "false"}
                )
                result = self.bundles.import_local(
                    local_request,
                    job=current,
                    install_root=Path(current.install_root) if current.install_root else self.paths.models,
                    progress=lambda *args: self._record_progress(job_id, *args),
                    cancel_check=lambda: self.get_job(job_id).cancel_requested,
                )
            if result.status == ImportStatus.stopped:
                self._discard_partial_owned_install(result)
            if result.status == ImportStatus.complete:
                bundle = self.store.get_bundle(result.bundle_id or "")
                if bundle is not None and bundle.source.resolved_revision:
                    result = result.model_copy(update={"resolved_revision": bundle.source.resolved_revision})
                    self.store.put_job(result)
        except ManagerError as exc:
            current = self.get_job(job_id)
            if exc.code == "import_stop_unconfirmed":
                self.store.put_job(
                    current.model_copy(
                        update={
                            "status": ImportStatus.stopping,
                            "error": exc.message,
                            "updated_at": utc_now(),
                            "cancel_requested": True,
                        }
                    )
                )
                return
            if exc.code == "import_cancelled":
                self.store.put_job(
                    current.model_copy(
                        update={
                            "status": ImportStatus.stopped,
                            "error": exc.message,
                            "finished_at": utc_now(),
                            "updated_at": utc_now(),
                        }
                    )
                )
                return
            self.store.put_job(
                current.model_copy(
                    update={
                        "status": ImportStatus.failed,
                        "error": exc.message,
                        "finished_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                )
            )
        except Exception as exc:
            current = self.get_job(job_id)
            self.store.put_job(
                current.model_copy(
                    update={
                        "status": ImportStatus.interrupted,
                        "error": str(exc),
                        "finished_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                )
            )
        finally:
            with self._lock:
                self._threads.pop(job_id, None)

    def _record_progress(
        self,
        job_id: str,
        stage: ImportStage,
        message: str | None,
        files_done: int,
        files_total: int | None,
        bytes_done: int,
        bytes_total: int | None,
    ) -> None:
        with self._job_lock:
            job = self.get_job(job_id)
            if job.cancel_requested and job.status == ImportStatus.running:
                job = job.model_copy(update={"status": ImportStatus.stopping})
            self.store.update_job_fields(job_id, status=job.status, updated_at=utc_now(),
                progress=ImportProgress(stage=stage, message=message, files_done=files_done,
                    files_total=files_total, bytes_done=bytes_done, bytes_total=bytes_total),
            )

    def _repair_huggingface_bundle(
        self,
        job: ImportJob,
        request: HuggingFaceImportRequest,
        download: HuggingFaceDownload,
    ) -> ImportJob:
        bundle = self.store.get_bundle(job.repair_of_bundle_id or "")
        if bundle is None:
            raise ManagerError("Unknown bundle to repair.", code="bundle_missing", status_code=404)
        guard = (
            self.lifecycle.mutate("repair_bundle", bundle_ids={bundle.id})
            if self.lifecycle is not None and hasattr(self.lifecycle, "mutate")
            else nullcontext()
        )
        with guard:
            bundle = self.store.get_bundle(bundle.id)
            if bundle is None:
                raise ManagerError("The model was removed before repair began.", code="bundle_missing", status_code=404)
            if self.require_repair_allowed is not None:
                self.require_repair_allowed(bundle.id)
            cancel_check = lambda: self.get_job(job.id).cancel_requested
            files = collect_bundle_files(download.local_dir)
            if download.expected_sizes:
                files = [path for path in files if path.relative_to(download.local_dir).as_posix() in download.expected_sizes]
            self.bundles._verify_expected_sizes(files, download.local_dir, download.expected_sizes)
            self.bundles._verify_expected_hashes(files, download.local_dir, download.expected_sha256, cancel_check=cancel_check)
            by_name = {path.resolve().relative_to(download.local_dir.resolve()).as_posix(): path for path in files}
            for recorded in bundle.files:
                self.bundles._raise_if_cancelled(lambda: self.get_job(job.id).cancel_requested)
                source = by_name.get(recorded.name)
                if source is None:
                    raise ManagerError(f"Repair download is missing {recorded.name}.", code="repair_missing_file", status_code=502)
                target = Path(recorded.path)
                if recorded.ownership != "managed" or not bundle.managed_root or Path(bundle.managed_root).name != bundle.id or not target.resolve().is_relative_to(Path(bundle.managed_root).resolve()):
                    raise ManagerError("Repair target is outside the managed bundle directory.", code="repair_scope", status_code=409)
                if target.is_file() and target.stat().st_size == recorded.size_bytes and sha256_file(target, cancel_check) == recorded.sha256:
                    continue
                if any(Path(item.path).resolve() == target.resolve() for other in self.store.list_bundles() if other.id != bundle.id for item in other.files):
                    raise ManagerError("A damaged file is shared by another model. Remove its other reference before repair.", code="repair_shared_file", status_code=409)
                if source.stat().st_size != recorded.size_bytes or sha256_file(source, cancel_check) != recorded.sha256:
                    raise ManagerError("Repair download does not match the recorded file.", code="repair_download_corrupt", status_code=502)
                target.parent.mkdir(parents=True, exist_ok=True)
                self._atomic_copy_with_cancel(source, target, lambda: self.get_job(job.id).cancel_requested)
            verified = self.bundles.verify_bundle(bundle)
        if not verified.disk_matches:
            raise ManagerError("Repair completed but bundle verification still failed.", code="repair_verify", status_code=502)
        return self.store.put_job(
            job.model_copy(
                update={
                    "status": ImportStatus.complete,
                    "bundle_id": bundle.id,
                    "resolved_revision": request.revision,
                    "finished_at": utc_now(),
                    "updated_at": utc_now(),
                    "progress": ImportProgress(stage=ImportStage.done, message="Repair complete"),
                    "error": None,
                }
            )
        )

    def _discard_partial_owned_install(self, job: ImportJob) -> None:
        if not job.owned_install_path:
            return
        target = Path(job.owned_install_path).resolve()
        if not target.exists():
            return
        if not job.install_root or target.parent != Path(job.install_root).resolve() or not target.name.startswith("bundle_") or Path(job.owned_install_path).is_symlink():
            raise ManagerError("The partial installation is outside this job's recorded destination.", code="job_cleanup_scope", status_code=409)
        if any(_paths_overlap(target, Path(item.path).resolve()) for bundle in self.store.list_bundles() for item in bundle.files):
            return
        shutil.rmtree(target)

    def _atomic_copy_with_cancel(self, source: Path, target: Path, cancel_check: callable) -> None:
        tmp = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with source.open("rb") as src, tmp.open("wb") as dst:
                while True:
                    if cancel_check():
                        raise ManagerError("Import was stopped before it was made ready.", code="import_cancelled", status_code=409)
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
            shutil.copystat(source, tmp)
            tmp.replace(target)
        finally:
            tmp.unlink(missing_ok=True)

    def _run_huggingface_subprocess(
        self,
        job: ImportJob,
        request: HuggingFaceImportRequest,
    ) -> ImportJob:
        staging = Path(job.staging_path or stable_hf_staging_path(
            self.paths.state,
            repo_id=request.repo_id,
            revision=request.revision,
            allow_patterns=request.allow_patterns,
        ))
        result_path = staging / "download-result.json"
        input_path = staging / "download-request.json"
        staging.mkdir(parents=True, exist_ok=True)
        result_path.unlink(missing_ok=True)
        input_payload = {
            "job_id": job.id,
            "repo_id": request.repo_id,
            "revision": request.revision,
            "dest": str(staging),
            "allow_patterns": request.allow_patterns,
            "output": str(result_path),
            "application_db": str(self.paths.application_db),
            "parent_pid": os.getpid(),
            "parent_create_time": psutil.Process(os.getpid()).create_time(),
            "force_download": bool(job.retry_of or job.repair_of_bundle_id),
        }
        input_path.write_text(json.dumps(input_payload), encoding="utf-8")
        self._record_progress(job.id, ImportStage.transfer, "Downloading selected files", 0, job.progress.files_total, 0, job.progress.bytes_total)
        child_env = os.environ.copy()
        cache_root = self.paths.state / "huggingface-cache"
        child_env["HF_HOME"] = str(cache_root / "home")
        child_env["HF_HUB_CACHE"] = str(cache_root / "hub")
        child_env["HF_XET_CACHE"] = str(cache_root / "xet")
        child_env["HF_HUB_DISABLE_XET"] = "1"
        token = get_token()
        if token:
            child_env["HF_TOKEN"] = token
        proc = subprocess.Popen(
            [sys.executable, "-m", "workbench_backend.inference.import_jobs", "download", str(input_path)],
            cwd=str(Path.cwd()),
            env=child_env,
        )
        create_time = psutil.Process(proc.pid).create_time()
        self.store.put_job(
            self.get_job(job.id).model_copy(
                update={
                    "transfer_pid": proc.pid,
                    "transfer_create_time": create_time,
                    "updated_at": utc_now(),
                }
            )
        )
        last_progress = 0.0
        while proc.poll() is None:
            current = self.get_job(job.id)
            if current.cancel_requested:
                self._terminate_transfer(current)
                return self.store.put_job(
                    current.model_copy(
                        update={
                            "status": ImportStatus.stopped,
                            "error": "Import download was stopped.",
                            "finished_at": utc_now(),
                            "updated_at": utc_now(),
                            "transfer_pid": None,
                            "transfer_create_time": None,
                        }
                    )
                )
            if time.monotonic() - last_progress >= 1.0:
                files_done, bytes_done = self._transfer_progress(staging / request.revision, request.allow_patterns)
                if (files_done, bytes_done) != (current.progress.files_done, current.progress.bytes_done):
                    self._record_progress(job.id, ImportStage.transfer, "Downloading selected files",
                        files_done, current.progress.files_total, bytes_done, current.progress.bytes_total)
                last_progress = time.monotonic()
            time.sleep(0.1)
        current = self.get_job(job.id)
        if current.transfer_pid != proc.pid:
            # An exited launcher is not evidence that its adopted worker
            # exited. Confirm that separate durable owner before releasing it.
            self._terminate_transfer(current)
        current = self.store.put_job(current.model_copy(update={"transfer_pid": None, "transfer_create_time": None, "updated_at": utc_now()}))
        if current.cancel_requested:
            return self.store.put_job(current.model_copy(update={"status": ImportStatus.stopped, "finished_at": utc_now(), "error": "Import download was stopped."}))
        if proc.returncode != 0:
            error = "Hugging Face download failed."
            if result_path.exists():
                try:
                    error = str(json.loads(result_path.read_text(encoding="utf-8")).get("error") or error)
                except json.JSONDecodeError:
                    pass
            return self.store.put_job(
                current.model_copy(
                    update={
                        "status": ImportStatus.failed,
                        "error": error,
                        "finished_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                )
            )
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        download = HuggingFaceDownload(
            repo_id=str(payload["repo_id"]),
            requested_revision=str(payload["requested_revision"]),
            resolved_revision=str(payload["resolved_revision"]),
            local_dir=Path(str(payload["local_dir"])),
            expected_sizes=dict(payload.get("expected_sizes") or {}),
            expected_sha256=dict(payload.get("expected_sha256") or {}),
            source_repo_id=payload.get("source_repo_id"),
            source_revision=payload.get("source_revision"),
            source_files=list(payload.get("source_files") or []),
        )
        try:
            current = self.get_job(job.id)
            if current.repair_of_bundle_id:
                return self._repair_huggingface_bundle(current, request, download)
            bundle = self.bundles.record_huggingface_download(
                request,
                download,
                install_root=Path(job.install_root or self.paths.models),
                job_id=job.id,
                progress=lambda *args: self._record_progress(job.id, *args),
                cancel_check=lambda: self.get_job(job.id).cancel_requested,
            )
        except ManagerError as exc:
            status = ImportStatus.stopped if exc.code == "import_cancelled" else ImportStatus.failed
            return self.store.put_job(
                current.model_copy(
                    update={
                        "status": status,
                        "error": exc.message,
                        "finished_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                )
            )
        return self.store.put_job(
            current.model_copy(
                update={
                    "status": ImportStatus.complete,
                    "bundle_id": bundle.id,
                    "resolved_revision": download.resolved_revision,
                    "finished_at": utc_now(),
                    "updated_at": utc_now(),
                    "progress": ImportProgress(stage=ImportStage.done, message="Import complete"),
                    "error": None,
                }
            )
        )

    def _future_install_root(self) -> Path:
        return Path(self.store.get_setting(FUTURE_INSTALL_ROOT_KEY) or self.paths.models).resolve()

    @staticmethod
    def _transfer_progress(root: Path, allow_patterns: list[str] | None) -> tuple[int, int]:
        """Observe payload bytes written by huggingface_hub, at most once/sec."""
        files_done = bytes_done = 0
        if not root.is_dir():
            return files_done, bytes_done
        for path in root.rglob("*"):
            relative = path.relative_to(root).as_posix()
            incomplete = ".cache/" in relative and path.name.endswith(".incomplete")
            complete = not relative.startswith(".cache/") and (
                allow_patterns is None or any(fnmatch.fnmatchcase(relative, pattern) for pattern in allow_patterns)
            )
            if not incomplete and not complete:
                continue
            try:
                if path.is_file():
                    bytes_done += path.stat().st_size
                    files_done += int(complete)
            except FileNotFoundError:
                # The library atomically renames completed partials while the
                # parent observes them; the next bounded sample catches up.
                continue
        return files_done, bytes_done

    @staticmethod
    def _copy_files_key(job_id: str) -> str:
        return f"import_job.{job_id}.copy_files"

    def _require_no_active_staging(self, staging: Path) -> None:
        resolved = staging.resolve()
        for job in self.store.list_active_jobs():
            if job.staging_path and _paths_overlap(resolved, Path(job.staging_path).resolve()):
                raise ManagerError(
                    "An import for the same selected files is already running.",
                    code="job_selection_active",
                    status_code=409,
                )

    def _selected_known_bytes(self, listing: object, allow_patterns: list[str] | None) -> int | None:
        import fnmatch

        file_sizes = getattr(listing, "file_sizes", None)
        if not isinstance(file_sizes, dict) or not file_sizes:
            return None
        available = [name for name in file_sizes if allow_patterns is None or any(fnmatch.fnmatchcase(name, pattern) for pattern in allow_patterns)]
        sizes = [file_sizes.get(name) for name in available]
        if not sizes or any(size is None for size in sizes):
            return None
        return sum(int(size) for size in sizes)

    def _preflight_hf_space(self, staging: Path, install_root: Path, selected_bytes: int) -> None:
        ensure_disk_space([(staging, selected_bytes), (install_root, selected_bytes)])

    def _terminate_transfer(self, job: ImportJob) -> None:
        if job.transfer_pid is None:
            return
        try:
            proc = psutil.Process(job.transfer_pid)
            if job.transfer_create_time is None:
                raise ManagerError("Cannot verify the download process identity; its files remain protected.", code="import_stop_unconfirmed", status_code=409)
            if abs(proc.create_time() - job.transfer_create_time) > 0.01:
                return
            # A Windows virtual-environment Python launcher can be the durable
            # owner until the actual worker adopts its identity. Stop that
            # verified tree from the leaves before releasing the launcher.
            for child in reversed(proc.children(recursive=True)):
                try:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
                except psutil.NoSuchProcess:
                    continue
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except psutil.NoSuchProcess:
            return
        except psutil.Error as exc:
            raise ManagerError("Could not confirm that the download stopped; its files remain protected. Try stopping it again.", code="import_stop_unconfirmed", status_code=409) from exc

    def _owns_staging(self, path: Path) -> bool:
        try:
            root = (self.paths.state / "staging").resolve()
            resolved = path.resolve()
            resolved.relative_to(root)
            return resolved != root and not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents) if p != root)
        except ValueError:
            return False

    def _staging_is_referenced(self, path: Path, *, ignore_job_ids: set[str] | None = None) -> bool:
        resolved = path.resolve()
        ignored = ignore_job_ids or set()
        for job in self.store.list_jobs():
            if job.id in ignored:
                continue
            if job.staging_path:
                other = Path(job.staging_path).resolve()
                if _paths_overlap(resolved, other):
                    return True
        for bundle in self.store.list_bundles():
            for item in [*bundle.files, *bundle.shards, *bundle.companions]:
                if _paths_overlap(resolved, Path(item.path).resolve()):
                    return True
        return False

    def _staging_reference_count(self, path: Path) -> int:
        resolved = path.resolve()
        count = 0
        for job in self.store.list_jobs():
            if job.staging_path:
                try:
                    Path(job.staging_path).resolve().relative_to(resolved)
                    count += 1
                except ValueError:
                    pass
        return count

    def _bytes_under(self, root: Path) -> int:
        if not root.exists():
            return 0
        total = 0
        for path in root.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total


def _paths_overlap(left: Path, right: Path) -> bool:
    try:
        left.relative_to(right)
        return True
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return True
    except ValueError:
        return False


def _download_child(input_path: Path) -> int:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    output = Path(str(payload["output"]))
    try:
        _wait_for_durable_transfer_identity(payload)
        download = HuggingFaceFetcher().download(
            repo_id=str(payload["repo_id"]),
            revision=str(payload["revision"]),
            dest=Path(str(payload["dest"])),
            allow_patterns=payload.get("allow_patterns"),
            force_download=bool(payload.get("force_download")),
        )
        output.write_text(
            json.dumps(
                {
                    "repo_id": download.repo_id,
                    "requested_revision": download.requested_revision,
                    "resolved_revision": download.resolved_revision,
                    "local_dir": str(download.local_dir),
                    "expected_sizes": download.expected_sizes,
                    "expected_sha256": download.expected_sha256,
                    "source_repo_id": download.source_repo_id,
                    "source_revision": download.source_revision,
                    "source_files": download.source_files,
                }
            ),
            encoding="utf-8",
        )
        return 0
    except Exception as exc:
        output.write_text(json.dumps({"error": str(exc)}), encoding="utf-8")
        return 1


def _wait_for_durable_transfer_identity(payload: dict[str, object]) -> None:
    job_id = str(payload["job_id"])
    db_path = str(payload["application_db"])
    parent_pid = int(payload["parent_pid"])
    parent_create_time = float(payload["parent_create_time"])
    own = psutil.Process(os.getpid())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        parent = psutil.Process(parent_pid)
        if abs(parent.create_time() - parent_create_time) > 0.01:
            raise RuntimeError("Import owner process changed before transfer identity was recorded.")
        try:
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute("SELECT payload FROM import_jobs WHERE id = ?", (job_id,)).fetchone()
                if row is not None:
                    encoded = str(row[0])
                    job = json.loads(encoded)
                    if job.get("cancel_requested") or job.get("status") != ImportStatus.running.value:
                        raise RuntimeError("Import was stopped before its transfer could begin.")
                    recorded_pid = job.get("transfer_pid")
                    recorded_time = float(job.get("transfer_create_time") or 0)
                    if recorded_pid == own.pid and abs(recorded_time - own.create_time()) <= 0.01:
                        return
                    # On Windows Popen(sys.executable) may launch a venv
                    # redirector whose child executes this code. Adopt only a
                    # durably recorded ancestor, never an unrelated process.
                    # The compare-and-swap also prevents a concurrent stop or
                    # newer owner from being overwritten before side effects.
                    if recorded_pid != parent_pid and any(
                        ancestor.pid == recorded_pid and abs(ancestor.create_time() - recorded_time) <= 0.01
                        for ancestor in own.parents()
                    ):
                        job.update(transfer_pid=own.pid, transfer_create_time=own.create_time(), updated_at=utc_now())
                        changed = conn.execute(
                            "UPDATE import_jobs SET payload=?,updated_at=? WHERE id=? AND payload=?",
                            (json.dumps(job), job["updated_at"], job_id, encoded),
                        ).rowcount
                        conn.commit()
                        if changed:
                            return
            finally:
                conn.close()
        except sqlite3.Error:
            pass
        time.sleep(0.05)
    raise TimeoutError("The download worker could not confirm safe startup. Retry the download; if it repeats, restart Workbench.")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("download")
    download.add_argument("input")
    args = parser.parse_args()
    if args.command == "download":
        return _download_child(Path(args.input))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
