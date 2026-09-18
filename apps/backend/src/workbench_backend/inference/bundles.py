"""Canonical model-bundle import and reuse (MOD-001)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from workbench_backend.errors import ManagerError
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.hf_fetch import HuggingFaceFetcher
from workbench_backend.inference.ids import new_id, utc_now
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

SHARD_RE = re.compile(r"-(?P<index>\d{5})-of-(?P<total>\d{5})\.gguf$", re.I)
QUANT_RE = re.compile(
    r"(?:[.-])(IQ\d[_A-Z0-9]+|Q\d[_A-Z0-9]+|F16|F32|BF16|Q8_0)(?:[.-]|$)",
    re.I,
)
COMPANION_HINTS = ("mmproj", "projector", "tokenizer", "chat_template")


def detect_quantization(names: list[str]) -> str | None:
    for name in names:
        match = QUANT_RE.search(name)
        if match:
            return match.group(1).upper()
    return None


def classify_files(paths: list[Path]) -> tuple[list[Path], list[Path], list[Path]]:
    ggufs = [path for path in paths if path.suffix.lower() == ".gguf"]
    others = [path for path in paths if path.suffix.lower() != ".gguf"]
    shards = [path for path in ggufs if SHARD_RE.search(path.name)]
    companions = [
        path
        for path in ggufs
        if any(hint in path.name.lower() for hint in COMPANION_HINTS)
        and path not in shards
    ]
    primaries = [path for path in ggufs if path not in shards and path not in companions]
    if not primaries and shards:
        primaries = [sorted(shards)[0]]
        shards = [path for path in shards if path != primaries[0]]
    companions.extend(others)
    return primaries, shards, companions


def collect_source_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    if not source.is_dir():
        raise ManagerError(
            f"Local source does not exist: {source}",
            code="local_source_missing",
            status_code=400,
        )
    return sorted(path for path in source.rglob("*") if path.is_file())


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class BundleService:
    def __init__(
        self,
        paths: WorkbenchPaths,
        store: RecordStore,
        *,
        hf: HuggingFaceFetcher | None = None,
    ) -> None:
        self.paths = paths.ensure()
        self.store = store
        self.hf = hf or HuggingFaceFetcher()

    def import_local(self, request: LocalImportRequest) -> ImportJob:
        job = self._new_job(BundleSourceKind.local, request.display_name)
        source = Path(request.source_path).expanduser()
        try:
            files = collect_source_files(source)
            if not files:
                raise ManagerError(
                    "Local import found no files",
                    code="local_import_empty",
                    status_code=400,
                )
            bundle = self._record_files(
                files,
                display_name=request.display_name or source.name,
                source=BundleSource(
                    kind=BundleSourceKind.local,
                    original_path=str(source.resolve()),
                ),
                reuse_root=source if source.is_dir() else source.parent,
            )
        except ManagerError as exc:
            return self._fail_job(job, exc.message, ImportStatus.failed)
        except OSError as exc:
            return self._fail_job(job, str(exc), ImportStatus.interrupted)
        return self._complete_job(job, bundle)

    def import_huggingface(self, request: HuggingFaceImportRequest) -> ImportJob:
        job = self._new_job(BundleSourceKind.huggingface, request.display_name)
        staging = self.paths.state / "staging" / job.id
        try:
            download = self.hf.download(
                repo_id=request.repo_id,
                revision=request.revision,
                dest=staging,
                allow_patterns=request.allow_patterns,
            )
            files = collect_source_files(download.local_dir)
            if not files:
                raise ManagerError(
                    "Hugging Face download produced no files",
                    code="hf_empty",
                    status_code=400,
                )
            bundle = self._record_files(
                files,
                display_name=request.display_name or request.repo_id,
                source=BundleSource(
                    kind=BundleSourceKind.huggingface,
                    repo_id=request.repo_id,
                    requested_revision=request.revision,
                    resolved_revision=download.resolved_revision,
                ),
                reuse_root=download.local_dir,
            )
            if staging.exists() and staging.resolve() != Path(bundle.primary_path or "").parent.resolve():
                shutil.rmtree(staging, ignore_errors=True)
        except ManagerError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            return self._fail_job(job, exc.message, ImportStatus.failed)
        except (OSError, InterruptedError) as exc:
            shutil.rmtree(staging, ignore_errors=True)
            return self._fail_job(job, str(exc), ImportStatus.interrupted)
        except Exception as exc:  # huggingface_hub raises several network types
            shutil.rmtree(staging, ignore_errors=True)
            status = (
                ImportStatus.interrupted
                if "interrupt" in str(exc).lower()
                else ImportStatus.failed
            )
            return self._fail_job(job, str(exc), status)
        return self._complete_job(job, bundle)

    def verify_bundle(self, bundle: ModelBundle) -> ModelBundle:
        matches = True
        for recorded in bundle.files:
            path = Path(recorded.path)
            if not path.is_file() or sha256_file(path) != recorded.sha256:
                matches = False
                break
            if not is_under(path, self.paths.models):
                matches = False
                break
        updated = bundle.model_copy(update={"disk_matches": matches})
        return self.store.put_bundle(updated)

    def inspectable_file(self, bundle: ModelBundle) -> Path:
        if bundle.primary_path:
            return Path(bundle.primary_path)
        raise ManagerError(
            "Bundle has no primary GGUF",
            code="bundle_no_primary",
            status_code=400,
        )

    def _record_files(
        self,
        files: list[Path],
        *,
        display_name: str,
        source: BundleSource,
        reuse_root: Path,
    ) -> ModelBundle:
        bundle_id = new_id("bundle")
        dest_root = self.paths.models / bundle_id
        reuse_in_place = is_under(reuse_root, self.paths.models)
        recorded: list[BundleFile] = []
        for path in files:
            target = path.resolve() if reuse_in_place else dest_root / path.name
            if not reuse_in_place:
                dest_root.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            recorded.append(
                BundleFile(
                    role=FileRole.companion,
                    name=target.name,
                    path=str(target),
                    sha256=sha256_file(target),
                    size_bytes=target.stat().st_size,
                )
            )
        primaries, shards, companions = classify_files([Path(item.path) for item in recorded])
        by_path = {item.path: item for item in recorded}
        for item in recorded:
            role = FileRole.companion
            path = Path(item.path)
            if path in primaries:
                role = FileRole.primary_weights
            elif path in shards:
                role = FileRole.shard
            by_path[item.path] = item.model_copy(update={"role": role})
        files_out = list(by_path.values())
        shard_files = [item for item in files_out if item.role == FileRole.shard]
        companion_files = [item for item in files_out if item.role == FileRole.companion]
        primary = next(
            (item for item in files_out if item.role == FileRole.primary_weights),
            None,
        )
        if primary is None:
            raise ManagerError(
                "Import did not include a GGUF weights file",
                code="bundle_no_gguf",
                status_code=400,
            )
        bundle = ModelBundle(
            id=bundle_id,
            display_name=display_name,
            quantization=detect_quantization([item.name for item in files_out]),
            source=source,
            files=files_out,
            shards=shard_files,
            companions=companion_files,
            primary_path=primary.path,
            created_at=utc_now(),
            status=ImportStatus.complete,
            disk_matches=True,
        )
        return self.verify_bundle(bundle)

    def _new_job(self, kind: BundleSourceKind, display_name: str | None) -> ImportJob:
        job = ImportJob(
            id=new_id("import"),
            kind=kind,
            status=ImportStatus.running,
            display_name=display_name,
            created_at=utc_now(),
        )
        return self.store.put_job(job)

    def _complete_job(self, job: ImportJob, bundle: ModelBundle) -> ImportJob:
        return self.store.put_job(
            job.model_copy(
                update={
                    "status": ImportStatus.complete,
                    "bundle_id": bundle.id,
                    "finished_at": utc_now(),
                    "error": None,
                }
            )
        )

    def _fail_job(
        self,
        job: ImportJob,
        error: str,
        status: ImportStatus,
    ) -> ImportJob:
        return self.store.put_job(
            job.model_copy(
                update={
                    "status": status,
                    "bundle_id": None,
                    "error": error,
                    "finished_at": utc_now(),
                }
            )
        )
