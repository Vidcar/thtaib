"""Canonical model-bundle import and reuse (MOD-001)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from threading import RLock

from workbench_backend.errors import ManagerError
from workbench_backend.inference.hashes import cached_sha256_file, sha256_file
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
PROJECTOR_HINTS = ("mmproj", "projector")
_HF_RECORD_LOCK = RLock()


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
        staging = stable_hf_staging_path(
            self.paths.state,
            repo_id=request.repo_id,
            revision=request.revision,
            allow_patterns=request.allow_patterns,
        )
        try:
            with _HF_RECORD_LOCK:
                staging.mkdir(parents=True, exist_ok=True)
                download = self.hf.download(
                    repo_id=request.repo_id,
                    revision=request.revision,
                    dest=staging,
                    allow_patterns=request.allow_patterns,
                )
                files = collect_bundle_files(download.local_dir)
                if not files:
                    raise ManagerError(
                        "Hugging Face download produced no files",
                        code="hf_empty",
                        status_code=400,
                    )
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
                )
                if bundle is None:
                    bundle = self._record_files(
                        files,
                        display_name=request.display_name or request.repo_id,
                        source=source,
                        reuse_root=download.local_dir,
                    )
        except ManagerError as exc:
            return self._fail_job(job, exc.message, ImportStatus.failed)
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

    def verify_bundle(self, bundle: ModelBundle, *, use_cache: bool = False) -> ModelBundle:
        matches = True
        for recorded in bundle.files:
            path = Path(recorded.path)
            if not path.is_file():
                matches = False
                break
            digest = cached_sha256_file(path) if use_cache else sha256_file(path)
            if digest != recorded.sha256:
                matches = False
                break
            if not is_under(path, self.paths.models):
                matches = False
                break
        updated = bundle.model_copy(update={"disk_matches": matches})
        if updated == bundle:
            return bundle
        return self.store.put_bundle(updated)

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
    ) -> ModelBundle | None:
        selected = self._bundle_files_for_source(files, reuse_root=reuse_root)
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
                    sha256=sha256_file(source_path),
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
    ) -> ModelBundle:
        bundle_id = new_id("bundle")
        dest_root = self.paths.models / bundle_id
        reuse_in_place = is_under(reuse_root, self.paths.models)
        resolved_reuse_root = reuse_root.resolve()
        source_records = self._bundle_files_for_source(files, reuse_root=reuse_root)
        validate_relative_path_identity(source_records)
        recorded: list[BundleFile] = []
        for path in files:
            source_path = path.resolve()
            rel_path = source_path.relative_to(resolved_reuse_root)
            target = source_path if reuse_in_place else dest_root / rel_path
            if not reuse_in_place:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            recorded.append(
                BundleFile(
                    role=FileRole.companion,
                    name=rel_path.as_posix(),
                    path=str(target),
                    sha256=sha256_file(target),
                    size_bytes=target.stat().st_size,
                )
            )
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
        self.store.put_bundle(bundle)
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
