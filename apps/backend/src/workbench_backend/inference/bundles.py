"""Canonical model-bundle import and reuse (MOD-001)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from threading import RLock
from typing import Callable

from workbench_backend.errors import ManagerError
from workbench_backend.inference.hashes import cached_sha256_file, sha256_file
from workbench_backend.inference.hf_fetch import HuggingFaceDownload, HuggingFaceFetcher
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.inspection_cache import bundle_identity
from workbench_backend.inference.schemas import (
    BundleFile,
    BundleSource,
    BundleSourceKind,
    FileRole,
    HuggingFaceImportRequest,
    ImportJob,
    ImportProgress,
    ImportStage,
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
PROJECTOR_HINTS = ("mmproj", "projector")
_HF_RECORD_LOCK = RLock()
ProgressCallback = Callable[[ImportStage, str | None, int, int | None, int, int | None], None]
CancelCheck = Callable[[], bool]


def mmproj_companion(bundle: ModelBundle) -> BundleFile | None:
    """The recorded multimodal projector GGUF, if the bundle has one.

    Bundle import rejects multiple projector GGUFs because llama-server takes
    exactly one ``--mmproj`` and guessing would run a different model setup than
    the user selected.
    """
    candidates = [
        item
        for item in bundle.companions
        if item.role == FileRole.companion
        and item.name.lower().endswith(".gguf")
        and any(hint in item.name.lower() for hint in PROJECTOR_HINTS)
    ]
    if len(candidates) > 1:
        names = ", ".join(item.name for item in sorted(candidates, key=lambda candidate: candidate.name))
        raise ManagerError(
            f"Bundle has multiple multimodal projector GGUF files: {names}",
            code="bundle_ambiguous_mmproj",
            status_code=400,
        )
    return candidates[0] if candidates else None


def detect_quantization(names: list[str]) -> str | None:
    for name in names:
        match = QUANT_RE.search(name)
        if match:
            return match.group(1).upper()
    return None


def _shard_match(path: Path) -> re.Match[str] | None:
    return SHARD_RE.search(path.name)


def _shard_group_key(path: Path) -> str:
    parent = path.parent.as_posix().lower()
    stem = SHARD_RE.sub("", path.name).lower()
    return f"{parent}/{stem}"


def classify_files(paths: list[Path]) -> tuple[list[Path], list[Path], list[Path]]:
    ggufs = [path for path in paths if path.suffix.lower() == ".gguf"]
    others = [path for path in paths if path.suffix.lower() != ".gguf"]
    shards = [path for path in ggufs if _shard_match(path)]
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


def validate_bundle_selection(paths: list[Path]) -> tuple[list[Path], list[Path], list[Path]]:
    shard_paths = [path for path in paths if _shard_match(path)]
    primaries, shards, companions = classify_files(paths)
    projector_candidates = sorted(
        path
        for path in companions
        if path.suffix.lower() == ".gguf"
        and any(hint in path.name.lower() for hint in PROJECTOR_HINTS)
    )
    if len(projector_candidates) > 1:
        names = ", ".join(path.name for path in projector_candidates)
        raise ManagerError(
            f"Import included multiple multimodal projector GGUF files: {names}",
            code="bundle_ambiguous_mmproj",
            status_code=400,
        )
    if len(primaries) > 1:
        names = ", ".join(path.name for path in sorted(primaries))
        raise ManagerError(
            f"Import included multiple GGUF weights variants: {names}",
            code="bundle_ambiguous_weights",
            status_code=400,
        )
    if shard_paths:
        non_shard_primaries = [path for path in primaries if _shard_match(path) is None]
        if non_shard_primaries:
            names = ", ".join(path.name for path in sorted(non_shard_primaries + shard_paths))
            raise ManagerError(
                f"Import included both standalone and sharded GGUF weights: {names}",
                code="bundle_mixed_shards",
                status_code=400,
            )
        groups: dict[str, list[Path]] = {}
        totals: set[int] = set()
        for shard in shard_paths:
            match = _shard_match(shard)
            if match is None:
                continue
            groups.setdefault(_shard_group_key(shard), []).append(shard)
            totals.add(int(match.group("total")))
        if len(groups) > 1 or len(totals) > 1:
            names = ", ".join(path.name for path in sorted(shards + primaries))
            raise ManagerError(
                f"Import included mixed GGUF shard sets: {names}",
                code="bundle_mixed_shards",
                status_code=400,
            )
        expected_total = next(iter(totals))
        seen: set[int] = set()
        shard_count = 0
        for shard in shard_paths:
            match = _shard_match(shard)
            if match is None:
                continue
            shard_count += 1
            seen.add(int(match.group("index")))
        expected = set(range(1, expected_total + 1))
        if seen != expected or shard_count != expected_total:
            missing = ", ".join(f"{index:05d}" for index in sorted(expected - seen))
            detail = f"missing shard indexes: {missing}" if missing else "duplicate or out-of-range shard indexes"
            raise ManagerError(
                f"Import included an incomplete GGUF shard set; {detail}",
                code="bundle_incomplete_shards",
                status_code=400,
            )
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


def collect_bundle_files(source: Path) -> list[Path]:
    files = collect_source_files(source)
    if source.is_dir():
        return [
            path
            for path in files
            if not path.relative_to(source).parts[:2] == (".cache", "huggingface")
        ]
    return files


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def stable_hf_staging_path(
    root: Path,
    *,
    repo_id: str,
    revision: str,
    allow_patterns: list[str] | None,
) -> Path:
    selection = {
        "repo_id": repo_id,
        "revision": revision,
        "allow_patterns": sorted(allow_patterns or []),
    }
    digest = hashlib.sha256(
        json.dumps(selection, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    safe_repo = re.sub(r"[^A-Za-z0-9._-]+", "--", repo_id).strip(".-") or "repo"
    safe_revision = re.sub(r"[^A-Za-z0-9._-]+", "--", revision).strip(".-") or "revision"
    return root / "staging" / "huggingface" / safe_repo / safe_revision / digest


def file_identity(files: list[BundleFile]) -> tuple[tuple[str, str, int, str], ...]:
    return tuple(
        sorted((item.name, item.sha256, item.size_bytes, item.role.value) for item in files)
    )


def validate_relative_path_identity(files: list[BundleFile]) -> None:
    lowered = {item.name.lower() for item in files}
    if len(lowered) != len(files):
        raise ManagerError(
            "Import includes files whose relative paths differ only by case.",
            code="bundle_path_collision",
            status_code=400,
        )


def ensure_disk_space(paths: list[tuple[Path, int]]) -> None:
    by_volume: dict[Path, tuple[int, int]] = {}
    for target, bytes_needed in paths:
        if bytes_needed <= 0:
            continue
        volume_root = _existing_volume_root(target)
        usage = shutil.disk_usage(volume_root)
        expected, available = by_volume.get(volume_root, (0, usage.free))
        by_volume[volume_root] = (expected + bytes_needed, available)
    shortages = [
        {"path": str(root), "expected_bytes": expected, "available_bytes": available}
        for root, (expected, available) in by_volume.items()
        if expected > available
    ]
    if shortages:
        first = shortages[0]
        raise ManagerError(
            "There is not enough free disk space for this import.",
            code="disk_space_insufficient",
            status_code=507,
            details={
                "expected_bytes": first["expected_bytes"],
                "available_bytes": first["available_bytes"],
                "volumes": shortages,
            },
        )


def _existing_volume_root(path: Path) -> Path:
    resolved = path.resolve()
    anchor = Path(resolved.anchor)
    if anchor.exists():
        return anchor
    current = resolved
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


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

    def import_local(
        self,
        request: LocalImportRequest,
        *,
        job: ImportJob | None = None,
        install_root: Path | None = None,
        progress: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> ImportJob:
        job = job or self._new_job(BundleSourceKind.local, request.display_name)
        source = Path(request.source_path).expanduser()
        try:
            self._raise_if_cancelled(cancel_check)
            self._progress(progress, ImportStage.metadata, "Reading local files", 0, None, 0, None)
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
                copy_files=request.copy_files,
                install_root=install_root,
                job_id=job.id,
                progress=progress,
                cancel_check=cancel_check,
            )
        except ManagerError as exc:
            status = ImportStatus.stopped if exc.code == "import_cancelled" else ImportStatus.failed
            return self._fail_job(job, exc.message, status)
        except OSError as exc:
            return self._fail_job(job, str(exc), ImportStatus.interrupted)
        return self._complete_job(job, bundle)

    def import_huggingface(
        self,
        request: HuggingFaceImportRequest,
        *,
        job: ImportJob | None = None,
        progress: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> ImportJob:
        job = job or self._new_job(BundleSourceKind.huggingface, request.display_name)
        staging = stable_hf_staging_path(
            self.paths.state,
            repo_id=request.repo_id,
            revision=request.revision,
            allow_patterns=request.allow_patterns,
        )
        try:
            with _HF_RECORD_LOCK:
                self._raise_if_cancelled(cancel_check)
                self._progress(progress, ImportStage.metadata, "Resolving repository metadata", 0, None, 0, None)
                staging.mkdir(parents=True, exist_ok=True)
                self._progress(progress, ImportStage.transfer, "Downloading selected files", 0, None, 0, None)
                download = self.hf.download(
                    repo_id=request.repo_id,
                    revision=request.revision,
                    dest=staging,
                    allow_patterns=request.allow_patterns,
                )
                self._raise_if_cancelled(cancel_check)
                bundle = self.record_huggingface_download(
                    request,
                    download,
                    progress=progress,
                    cancel_check=cancel_check,
                )
        except ManagerError as exc:
            status = ImportStatus.stopped if exc.code == "import_cancelled" else ImportStatus.failed
            return self._fail_job(job, exc.message, status)
        except (OSError, InterruptedError) as exc:
            return self._fail_job(job, str(exc), ImportStatus.interrupted)
        except Exception as exc:  # huggingface_hub raises several network types
            status = (
                ImportStatus.interrupted
                if "interrupt" in str(exc).lower()
                else ImportStatus.failed
            )
            return self._fail_job(job, str(exc), status)
        return self._complete_job(job, bundle)

    def record_huggingface_download(
        self,
        request: HuggingFaceImportRequest,
        download: HuggingFaceDownload,
        *,
        install_root: Path | None = None,
        job_id: str | None = None,
        progress: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> ModelBundle:
        files = collect_bundle_files(download.local_dir)
        if not files:
            raise ManagerError(
                "Hugging Face download produced no files",
                code="hf_empty",
                status_code=400,
            )
        self._verify_expected_sizes(files, download.local_dir, download.expected_sizes)
        self._verify_expected_hashes(files, download.local_dir, download.expected_sha256, cancel_check=cancel_check)
        source = BundleSource(
            kind=BundleSourceKind.huggingface,
            repo_id=request.repo_id,
            requested_revision=request.revision,
            resolved_revision=download.resolved_revision,
        )
        bundle = self._reuse_completed_hf_bundle(
            files,
            source=source,
            reuse_root=download.local_dir,
            cancel_check=cancel_check,
        )
        if bundle is not None:
            return bundle
        return self._record_files(
            files,
            display_name=request.display_name or request.repo_id,
            source=source,
            reuse_root=download.local_dir,
            install_root=install_root,
            job_id=job_id,
            progress=progress,
            cancel_check=cancel_check,
        )

    def verify_bundle(self, bundle: ModelBundle, *, use_cache: bool = False) -> ModelBundle:
        cache_key = f"model-verification:{bundle.id}"
        verification_root = str(self.paths.models.resolve())
        try:
            identity = bundle_identity(bundle)
        except OSError:
            identity = None
        if use_cache and identity is not None:
            try:
                evidence = json.loads(self.store.get_setting(cache_key) or "null")
                if isinstance(evidence, dict) and evidence.get("root") == verification_root and evidence.get("identity") == identity and evidence.get("matches") is True:
                    return self.store.set_bundle_disk_matches(bundle.id, True) or bundle.model_copy(update={"disk_matches": False})
            except (ValueError, TypeError):
                pass
        matches = True
        for recorded in bundle.files:
            path = Path(recorded.path)
            if not path.is_file() or path.stat().st_size != recorded.size_bytes:
                matches = False
                break
            digest = cached_sha256_file(path) if use_cache else sha256_file(path)
            if digest != recorded.sha256:
                matches = False
                break
            if not is_under(path, Path(bundle.managed_root) if bundle.managed_root else self.paths.models):
                if recorded.ownership != "external":
                    matches = False
                    break
        if matches:
            try:
                matches = identity is not None and identity == bundle_identity(bundle)
            except OSError:
                matches = False
        self.store.put_setting(cache_key, json.dumps({"root": verification_root, "identity": identity, "matches": matches}))
        current = self.store.set_bundle_disk_matches(bundle.id, matches)
        return current or bundle.model_copy(update={"disk_matches": False})

    def inspectable_file(self, bundle: ModelBundle) -> Path:
        if bundle.primary_path:
            return Path(bundle.primary_path)
        raise ManagerError(
            "Bundle has no primary GGUF",
            code="bundle_no_primary",
            status_code=400,
        )

    def _reuse_completed_hf_bundle(
        self,
        files: list[Path],
        *,
        source: BundleSource,
        reuse_root: Path,
        cancel_check: CancelCheck | None = None,
    ) -> ModelBundle | None:
        selected = self._bundle_files_for_source(files, reuse_root=reuse_root, cancel_check=cancel_check)
        expected_identity = file_identity(selected)
        for bundle in self.store.list_bundles():
            if (
                bundle.status != ImportStatus.complete
                or bundle.source.kind != BundleSourceKind.huggingface
                or bundle.source.repo_id != source.repo_id
                or bundle.source.resolved_revision != source.resolved_revision
                or file_identity(bundle.files) != expected_identity
            ):
                continue
            verified = self.verify_bundle(bundle)
            if verified.disk_matches:
                return verified
        return None

    def _bundle_files_for_source(
        self,
        files: list[Path],
        *,
        reuse_root: Path,
        cancel_check: CancelCheck | None = None,
    ) -> list[BundleFile]:
        resolved_reuse_root = reuse_root.resolve()
        recorded: list[BundleFile] = []
        for path in files:
            source_path = path.resolve()
            rel_path = source_path.relative_to(resolved_reuse_root)
            recorded.append(
                BundleFile(
                    role=FileRole.companion,
                    name=rel_path.as_posix(),
                    path=str(source_path),
                    sha256=sha256_file(source_path, cancel_check),
                    size_bytes=source_path.stat().st_size,
                )
            )
        primaries, shards, _companions = validate_bundle_selection([Path(item.path) for item in recorded])
        validate_relative_path_identity(recorded)
        by_path = {item.path: item for item in recorded}
        for item in recorded:
            role = FileRole.companion
            path = Path(item.path)
            if path in primaries:
                role = FileRole.primary_weights
            elif path in shards:
                role = FileRole.shard
            by_path[item.path] = item.model_copy(update={"role": role})
        return list(by_path.values())

    def _record_files(
        self,
        files: list[Path],
        *,
        display_name: str,
        source: BundleSource,
        reuse_root: Path,
        copy_files: bool = True,
        install_root: Path | None = None,
        job_id: str | None = None,
        progress: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> ModelBundle:
        bundle_id = new_id("bundle")
        managed_install_root = (install_root or self.paths.models).resolve()
        dest_root = managed_install_root / bundle_id
        reuse_in_place = is_under(reuse_root, self.paths.models)
        copy_into_managed = copy_files and not reuse_in_place
        resolved_reuse_root = reuse_root.resolve()
        self._raise_if_cancelled(cancel_check)
        total_bytes = sum(path.stat().st_size for path in files)
        self._progress(progress, ImportStage.verify, "Verifying selected files", 0, len(files), 0, total_bytes)
        source_records = self._bundle_files_for_source(files, reuse_root=reuse_root, cancel_check=cancel_check)
        expected_by_name = {item.name: item for item in source_records}
        validate_relative_path_identity(source_records)
        recorded: list[BundleFile] = []
        done_files = 0
        done_bytes = 0
        if copy_into_managed:
            ensure_disk_space([(dest_root, total_bytes)])
            if job_id is not None:
                self.store.update_job_fields(job_id, owned_install_path=str(dest_root), bundle_id=bundle_id)
        try:
            for path in files:
                self._raise_if_cancelled(cancel_check)
                source_path = path.resolve()
                rel_path = source_path.relative_to(resolved_reuse_root)
                target = source_path if not copy_into_managed else dest_root / rel_path
                if copy_into_managed:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    self._copy_with_progress(
                        path,
                        target,
                        copied_before=done_bytes,
                        total_bytes=total_bytes,
                        files_done=done_files,
                        files_total=len(files),
                        progress=progress,
                        cancel_check=cancel_check,
                    )
                ownership = "managed" if copy_into_managed else "external"
                digest = sha256_file(target, cancel_check)
                expected = expected_by_name[rel_path.as_posix()]
                if digest != expected.sha256 or target.stat().st_size != expected.size_bytes:
                    raise ManagerError("A source file changed during import. Verify the source and retry.", code="import_source_changed", status_code=409)
                recorded.append(
                    BundleFile(
                        role=FileRole.companion,
                        name=rel_path.as_posix(),
                        path=str(target),
                        sha256=digest,
                        size_bytes=target.stat().st_size,
                        ownership=ownership,
                    )
                )
                done_files += 1
                done_bytes += target.stat().st_size
                self._progress(progress, ImportStage.install, "Installing selected files", done_files, len(files), done_bytes, total_bytes)
            self._raise_if_cancelled(cancel_check)
        except Exception:
            if copy_into_managed and dest_root.exists():
                shutil.rmtree(dest_root)
            raise
        roles_by_name = {item.name: item.role for item in source_records}
        by_path = {item.path: item for item in recorded}
        for item in recorded:
            by_path[item.path] = item.model_copy(update={"role": roles_by_name[item.name]})
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
        managed_root = None
        if any(item.ownership == "managed" for item in files_out):
            managed_root = str(resolved_reuse_root if reuse_in_place else dest_root)
        bundle = ModelBundle(
            id=bundle_id,
            display_name=display_name,
            quantization=detect_quantization([item.name for item in files_out]),
            source=source,
            files=files_out,
            shards=shard_files,
            companions=companion_files,
            primary_path=primary.path,
            managed_root=managed_root,
            created_at=utc_now(),
            status=ImportStatus.complete,
            disk_matches=True,
        )
        self.store.put_bundle(bundle)
        return bundle

    def _new_job(self, kind: BundleSourceKind, display_name: str | None) -> ImportJob:
        job = ImportJob(
            id=new_id("import"),
            kind=kind,
            status=ImportStatus.running,
            display_name=display_name,
            created_at=utc_now(),
            updated_at=utc_now(),
            started_at=utc_now(),
            install_root=str(self.paths.models),
        )
        return self.store.put_job(job)

    def _complete_job(self, job: ImportJob, bundle: ModelBundle) -> ImportJob:
        return self.store.put_job(
            job.model_copy(
                update={
                    "status": ImportStatus.complete,
                    "bundle_id": bundle.id,
                    "finished_at": utc_now(),
                    "updated_at": utc_now(),
                    "progress": ImportProgress(stage=ImportStage.done, message="Import complete"),
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
        current = self.store.get_job(job.id) or job
        return self.store.put_job(
            current.model_copy(
                update={
                    "status": status,
                    "bundle_id": None,
                    "error": error,
                    "finished_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
        )

    def _verify_expected_sizes(
        self,
        files: list[Path],
        root: Path,
        expected_sizes: dict[str, int | None],
    ) -> None:
        by_name = {path.resolve().relative_to(root.resolve()).as_posix(): path for path in files}
        if expected_sizes and set(by_name) != set(expected_sizes):
            raise ManagerError("Downloaded files do not match the exact recorded selection.", code="hf_download_selection", status_code=502)
        for name, expected in expected_sizes.items():
            if expected is None:
                continue
            path = by_name.get(name)
            if path is None:
                raise ManagerError(
                    f"Selected Hugging Face file is missing after download: {name}",
                    code="hf_download_missing",
                    status_code=502,
                )
            actual = path.stat().st_size
            if actual != expected:
                raise ManagerError(
                    f"Downloaded file size did not match Hugging Face metadata for {name}.",
                    code="hf_download_corrupt",
                    status_code=502,
                )

    def _verify_expected_hashes(
        self,
        files: list[Path],
        root: Path,
        expected_sha256: dict[str, str | None],
        *,
        cancel_check: CancelCheck | None = None,
    ) -> None:
        by_name = {path.resolve().relative_to(root.resolve()).as_posix(): path for path in files}
        for name, expected in expected_sha256.items():
            if not expected:
                continue
            path = by_name.get(name)
            if path is None:
                raise ManagerError(
                    f"Selected Hugging Face file is missing after download: {name}",
                    code="hf_download_missing",
                    status_code=502,
                )
            actual = sha256_file(path, cancel_check)
            if actual.lower() != expected.lower():
                raise ManagerError(
                    f"Downloaded file hash did not match Hugging Face metadata for {name}.",
                    code="hf_download_corrupt",
                    status_code=502,
                )

    def _copy_with_progress(
        self,
        source: Path,
        target: Path,
        *,
        copied_before: int,
        total_bytes: int,
        files_done: int,
        files_total: int,
        progress: ProgressCallback | None,
        cancel_check: CancelCheck | None,
    ) -> None:
        self._progress(progress, ImportStage.install, "Installing selected files", files_done, files_total, copied_before, total_bytes)
        with source.open("rb") as src, target.open("wb") as dst:
            while True:
                self._raise_if_cancelled(cancel_check)
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
                copied_before += len(chunk)
                self._progress(progress, ImportStage.install, "Installing selected files", files_done, files_total, copied_before, total_bytes)
        shutil.copystat(source, target)

    def _raise_if_cancelled(self, cancel_check: CancelCheck | None) -> None:
        if cancel_check is not None and cancel_check():
            raise ManagerError("Import was stopped before it was made ready.", code="import_cancelled", status_code=409)

    def _progress(
        self,
        progress: ProgressCallback | None,
        stage: ImportStage,
        message: str | None,
        files_done: int,
        files_total: int | None,
        bytes_done: int,
        bytes_total: int | None,
    ) -> None:
        if progress is not None:
            progress(stage, message, files_done, files_total, bytes_done, bytes_total)
