"""Manual application backup and clean-root restore for STATE-011."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import time
import zipfile
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field

from workbench_backend import __version__
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.schemas import ModelBundle, RuntimeManifest
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.checkpointer import copy_checkpoints_for_backup
from workbench_backend.state.store import ApplicationStore

BACKUP_FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
INCLUDED_DIRS = ("knowledge", "cases", "snapshots", "workspaces")
STATE_JSON_DIRS = ("compatibility",)
STATE_JSON_FILES = ("bundles.json", "deployments.json", "profiles.json", "import_jobs.json")
RUNTIME_RECORD_FILES = ("runtime-manifest.json",)
EXCLUDED_NAMES = {"desktop_backend_shared_secret"}
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
LIVE_RUN_STATUSES = {"queued", "running", "cancel_requested"}
WINDOWS_DEVICE_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class BackupError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class BackupFile(BaseModel):
    path: str
    sha256: str
    size_bytes: int


class BackupExternalReference(BaseModel):
    kind: Literal["project", "model", "runtime", "credential"]
    path: str | None = None
    id: str | None = None
    included: Literal[False] = False
    missing: bool = False


class BackupManifest(BaseModel):
    format: Literal["local-ai-workbench-backup"] = "local-ai-workbench-backup"
    format_version: Literal[1] = BACKUP_FORMAT_VERSION
    product_version: str = __version__
    backup_id: str
    created_at: str
    source_root: str
    files: list[BackupFile] = Field(default_factory=list)
    directories: list[str] = Field(default_factory=list)
    included_roots: list[str] = Field(default_factory=list)
    external_references: list[BackupExternalReference] = Field(default_factory=list)
    checkpoint_versions: dict[str, str] = Field(default_factory=dict)
    credentials_excluded: Literal[True] = True
    no_effect_replay: Literal[True] = True
    note: str = (
        "Application records, compatible checkpoints, retained assets stored in "
        "application.sqlite, and application-owned JSON records are included. "
        "Models, runtimes, project folders, credentials, remote copies and prior "
        "exports are references only."
    )


class BackupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination: str = Field(min_length=1, max_length=4096)


class BackupCreateResult(BaseModel):
    archive_path: str
    manifest: BackupManifest


class BackupRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archive_path: str = Field(min_length=1, max_length=4096)
    destination_root: str = Field(min_length=1, max_length=4096)


class BackupRestoreResult(BaseModel):
    destination_root: str
    manifest: BackupManifest
    missing_dependencies: list[BackupExternalReference] = Field(default_factory=list)
    activated: Literal[False] = False
    no_effect_replay: Literal[True] = True


class MaintenanceGate:
    """Process-local mutation lease gate for backup integration points."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._active_reason: str | None = None
        self._active_mutations = 0

    def begin(self, reason: str, *, wait_timeout: float = 5.0) -> None:
        with self._lock:
            if self._active_reason is not None:
                raise BackupError("Maintenance is already active.", code="maintenance_active")
            self._active_reason = reason
            drained = self._condition.wait_for(lambda: self._active_mutations == 0, timeout=wait_timeout)
            if not drained:
                self._active_reason = None
                self._condition.notify_all()
                raise BackupError(
                    "Backup could not drain active mutations before the timeout.",
                    code="maintenance_drain_timeout",
                )

    def end(self) -> None:
        with self._lock:
            self._active_reason = None
            self._condition.notify_all()

    @contextmanager
    def mutation(self) -> Iterator[None]:
        with self._lock:
            if self._active_reason is not None:
                raise BackupError(
                    "Application maintenance is active; mutation or queue dispatch is blocked.",
                    code="maintenance_gate_active",
                )
            self._active_mutations += 1
        try:
            yield
        finally:
            with self._lock:
                self._active_mutations -= 1
                self._condition.notify_all()

    def reject_if_active(self) -> None:
        with self.mutation():
            return

    @property
    def active_reason(self) -> str | None:
        with self._lock:
            return self._active_reason


class BackupService:
    def __init__(
        self,
        paths: WorkbenchPaths,
        app_store: ApplicationStore,
        *,
        maintenance_gate: MaintenanceGate | None = None,
        active_work: Callable[[], list[str]] | None = None,
        reconcile: Callable[[], None] | None = None,
        quiescence_timeout: float = 15.0,
    ) -> None:
        self.paths = paths.ensure()
        self.app_store = app_store
        self.maintenance_gate = maintenance_gate or MaintenanceGate()
        self.active_work = active_work or (lambda: [])
        self.reconcile = reconcile or (lambda: None)
        self.quiescence_timeout = quiescence_timeout

    def create_backup(self, request: BackupCreateRequest) -> BackupCreateResult:
        destination = Path(request.destination).expanduser().resolve()
        if destination.exists() and destination.is_dir():
            destination = destination / f"{new_id('backup')}.workbench-backup.zip"
        if destination.exists():
            raise BackupError("Backup archive already exists; refusing to overwrite it.", code="backup_archive_exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging: Path | None = None
        self.maintenance_gate.begin("manual_backup")
        try:
            active = self.active_work()
            deadline = time.monotonic() + self.quiescence_timeout
            while active and time.monotonic() < deadline:
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
                active = self.active_work()
            if active:
                raise BackupError(
                    "Work has not reached a safe stopping point. Finish or stop it, then retry the backup.",
                    code="backup_not_quiescent",
                )
            self.reconcile()
            staging = _new_staging_dir(self.paths.root, "backup")
            manifest = self._stage_backup(staging)
            manifest_path = staging / MANIFEST_NAME
            manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
            files = _collect_files(staging)
            manifest.directories = _collect_empty_directories(staging)
            manifest.files = [
                BackupFile(path=relative, sha256=sha256_file(path), size_bytes=path.stat().st_size)
                for path, relative in files
                if relative != MANIFEST_NAME
            ]
            manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
            _write_zip(staging, destination)
            return BackupCreateResult(archive_path=str(destination), manifest=manifest)
        finally:
            self.maintenance_gate.end()
            if staging is not None and staging.exists():
                shutil.rmtree(staging)

    def restore_backup(self, request: BackupRestoreRequest) -> BackupRestoreResult:
        archive = Path(request.archive_path).expanduser().resolve(strict=True)
        destination = Path(request.destination_root).expanduser().resolve()
        if destination.exists() and any(destination.iterdir()):
            raise BackupError("Restore destination must be a clean empty root.", code="restore_destination_not_clean")
        staging = _new_staging_dir(self.paths.root, "restore")
        destination_created = False
        try:
            _extract_zip_safely(archive, staging)
            manifest = _read_manifest(staging)
            _verify_checkpoint_versions(manifest)
            _verify_manifest_files(staging, manifest)
            _verify_sqlite_integrity(staging / "application.sqlite", required=True)
            _verify_application_schema_compatible(staging)
            _verify_application_linkages(staging / "application.sqlite")
            if (staging / "checkpoints.sqlite").exists():
                _verify_sqlite_integrity(staging / "checkpoints.sqlite", required=False)
            self._copy_restored_tree(staging, destination)
            destination_created = True
            _reconcile_restored_application_db(destination / "application.sqlite", destination, Path(manifest.source_root))
            _rebase_restored_json_files(destination, destination, Path(manifest.source_root))
            missing = _missing_dependencies(manifest)
            return BackupRestoreResult(
                destination_root=str(destination),
                manifest=manifest,
                missing_dependencies=missing,
            )
        except Exception:
            if destination_created and destination.exists():
                shutil.rmtree(destination)
            raise
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def _stage_backup(self, staging: Path) -> BackupManifest:
        included_roots = ["application.sqlite"]
        _copy_application_db(self.app_store, staging / "application.sqlite")
        _verify_sqlite_integrity(staging / "application.sqlite", required=True)
        if self.paths.checkpoints_db.exists():
            copy_checkpoints_for_backup(self.paths.checkpoints_db, staging / "checkpoints.sqlite")
            _verify_sqlite_integrity(staging / "checkpoints.sqlite", required=False)
            included_roots.append("checkpoints.sqlite")
        for dirname in INCLUDED_DIRS:
            source = getattr(self.paths, dirname)
            if source.exists():
                _copy_tree_safely(source, staging / dirname)
                included_roots.append(dirname)
        state_root = staging / "state"
        for dirname in STATE_JSON_DIRS:
            source = self.paths.state / dirname
            if source.exists():
                _copy_tree_safely(source, state_root / dirname)
                included_roots.append(f"state/{dirname}")
        for filename in STATE_JSON_FILES:
            source = self.paths.state / filename
            if source.exists():
                _copy_record_file(source, state_root / filename)
                included_roots.append(f"state/{filename}")
        for filename in RUNTIME_RECORD_FILES:
            source = self.paths.runtimes / filename
            if source.exists():
                _copy_record_file(source, staging / "runtimes" / filename)
                included_roots.append(f"runtimes/{filename}")
        return BackupManifest(
            backup_id=new_id("backup"),
            created_at=utc_now(),
            source_root=str(self.paths.root),
            included_roots=included_roots,
            external_references=self._external_references(),
            checkpoint_versions=_checkpoint_versions(),
        )

    def _external_references(self) -> list[BackupExternalReference]:
        refs: dict[tuple[str, str], BackupExternalReference] = {}
        for conversation in self.app_store.list_conversations(include_archived=True):
            project = getattr(conversation, "area_project_path", None) or conversation.project_path
            if project:
                refs[("project", str(project))] = BackupExternalReference(
                    kind="project",
                    path=str(project),
                    missing=not Path(project).exists(),
                )
        for run in self.app_store.list_runs():
            if run.project_path:
                refs[("project", run.project_path)] = BackupExternalReference(
                    kind="project",
                    path=run.project_path,
                    missing=not Path(run.project_path).exists(),
                )
            if run.deployment_id:
                refs[("model", run.deployment_id)] = BackupExternalReference(
                    kind="model",
                    id=run.deployment_id,
                    missing=False,
                )
            setup = run.effective_setup
            if setup and setup.loaded_deployment_id:
                refs[("runtime", setup.loaded_deployment_id)] = BackupExternalReference(
                    kind="runtime",
                    id=setup.loaded_deployment_id,
                    missing=False,
                )
        for bundle in self._bundle_records():
            for path in _bundle_reference_paths(bundle):
                refs[("model", str(path))] = BackupExternalReference(
                    kind="model",
                    id=bundle.id,
                    path=str(path),
                    missing=not path.is_file(),
                )
        runtime_manifest = self.paths.runtimes / "runtime-manifest.json"
        if runtime_manifest.exists():
            refs[("runtime", str(runtime_manifest))] = BackupExternalReference(
                kind="runtime",
                path=str(runtime_manifest),
                missing=False,
            )
            if manifest := self._runtime_manifest_record(runtime_manifest):
                for path in _runtime_reference_paths(manifest, self.paths.runtimes):
                    refs[("runtime", str(path))] = BackupExternalReference(
                        kind="runtime",
                        path=str(path),
                        missing=not path.is_file(),
                    )
        for name in EXCLUDED_NAMES:
            candidate = self.paths.state / name
            if candidate.exists():
                refs[("credential", str(candidate))] = BackupExternalReference(
                    kind="credential",
                    path=str(candidate),
                    missing=False,
                )
        return list(refs.values())

    def _bundle_records(self) -> list[ModelBundle]:
        path = self.paths.state / "bundles.json"
        if not path.is_file():
            return []
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(records, list):
            return []
        bundles: list[ModelBundle] = []
        for record in records:
            try:
                bundles.append(ModelBundle.model_validate(record))
            except Exception:
                continue
        return bundles

    def _runtime_manifest_record(self, path: Path) -> RuntimeManifest | None:
        try:
            return RuntimeManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _copy_restored_tree(self, staging: Path, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        for relative in _read_manifest(staging).directories:
            (destination / PurePosixPath(relative)).mkdir(parents=True, exist_ok=True)
        for path, relative in _collect_files(staging):
            if relative == MANIFEST_NAME:
                continue
            target = destination / PurePosixPath(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _copy_application_db(app_store: ApplicationStore, destination: Path) -> None:
    with app_store._lock:
        conn = app_store._conn
        if conn is None:
            raise BackupError("Application store is closed.", code="application_store_closed")
        dest_conn = sqlite3.connect(str(destination))
        try:
            conn.backup(dest_conn)
            dest_conn.commit()
        finally:
            dest_conn.close()


def _copy_record_file(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise BackupError(f"Refusing to back up symlink: {source.name}", code="backup_symlink_rejected")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_tree_safely(source: Path, destination: Path) -> None:
    root = source.resolve()
    for path in sorted(root.rglob("*")):
        relative = _safe_relative(path.relative_to(root).as_posix())
        if path.name in EXCLUDED_NAMES:
            continue
        if path.is_symlink():
            raise BackupError(f"Refusing to back up symlink: {relative}", code="backup_symlink_rejected")
        if path.is_dir():
            (destination / relative).mkdir(parents=True, exist_ok=True)
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _bundle_reference_paths(bundle: ModelBundle) -> list[Path]:
    paths: dict[str, Path] = {}
    if bundle.primary_path:
        primary = Path(bundle.primary_path)
        paths[str(primary)] = primary
    for item in [*bundle.files, *bundle.shards, *bundle.companions]:
        path = Path(item.path)
        paths[str(path)] = path
    return list(paths.values())


def _runtime_reference_paths(manifest: RuntimeManifest, archive_root: Path) -> list[Path]:
    paths: dict[str, Path] = {}
    executable = Path(manifest.executable)
    paths[str(executable)] = executable
    # Local pins name the executable itself as their asset; release pins keep
    # downloaded archives beside the manifest, outside the extracted directory.
    names = () if manifest.release_tag == "local" else (manifest.asset_name, manifest.companion_asset_name)
    for name in names:
        if name:
            path = archive_root / name
            paths[str(path)] = path
    return list(paths.values())


def _collect_files(root: Path) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_dir():
            continue
        if path.is_symlink():
            raise BackupError("Backup contains a symlink.", code="backup_symlink_rejected")
        files.append((path, path.relative_to(root).as_posix()))
    return files


def _collect_empty_directories(root: Path) -> list[str]:
    directories: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_dir() or path.is_symlink():
            continue
        if any(path.iterdir()):
            continue
        directories.append(path.relative_to(root).as_posix())
    return directories


def _write_zip(staging: Path, destination: Path) -> None:
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    if tmp.exists():
        raise BackupError("Temporary backup archive already exists.", code="backup_temp_exists")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in _collect_empty_directories(staging):
            archive.writestr(f"{relative}/", b"")
        for path, relative in _collect_files(staging):
            archive.write(path, relative)
    tmp.replace(destination)


def _extract_zip_safely(archive_path: Path, destination: Path) -> None:
    seen: set[str] = set()
    dirs: set[str] = set()
    with zipfile.ZipFile(archive_path, "r") as archive:
        for info in archive.infolist():
            relative = _safe_relative(info.filename)
            if relative in seen:
                raise BackupError("Backup archive contains duplicate members.", code="restore_duplicate_member")
            seen.add(relative)
            parts = PurePosixPath(relative).parts
            for idx in range(1, len(parts)):
                parent = PurePosixPath(*parts[:idx]).as_posix()
                if parent in seen:
                    raise BackupError("Backup archive contains file/directory collision.", code="restore_path_collision")
                dirs.add(parent)
            if relative in dirs:
                raise BackupError("Backup archive contains file/directory collision.", code="restore_path_collision")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise BackupError("Backup archive contains a symlink.", code="restore_symlink_rejected")
            if info.is_dir():
                (destination / relative).mkdir(parents=True, exist_ok=True)
                continue
            target = (destination / relative).resolve()
            try:
                target.relative_to(destination.resolve())
            except ValueError as exc:
                raise BackupError("Backup archive path escapes restore staging.", code="restore_path_traversal") from exc
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)


def _read_manifest(root: Path) -> BackupManifest:
    path = root / MANIFEST_NAME
    if not path.is_file():
        raise BackupError("Backup manifest is missing.", code="manifest_missing")
    try:
        manifest = BackupManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BackupError("Backup manifest is invalid.", code="manifest_invalid") from exc
    if manifest.format_version != BACKUP_FORMAT_VERSION:
        raise BackupError("Backup format version is not compatible.", code="backup_incompatible")
    return manifest


def _verify_manifest_files(root: Path, manifest: BackupManifest) -> None:
    expected = {item.path: item for item in manifest.files}
    actual = {relative: path for path, relative in _collect_files(root) if relative != MANIFEST_NAME}
    if set(actual) != set(expected):
        raise BackupError("Backup file manifest does not match archive contents.", code="manifest_file_set_mismatch")
    for relative, item in expected.items():
        path = actual[relative]
        if path.stat().st_size != item.size_bytes or sha256_file(path) != item.sha256:
            raise BackupError(f"Backup file failed integrity check: {relative}", code="backup_integrity_mismatch")
    for relative in manifest.directories:
        directory = root / PurePosixPath(_safe_relative(relative))
        if not directory.is_dir():
            raise BackupError("Backup directory manifest does not match archive contents.", code="manifest_directory_missing")


def _missing_dependencies(manifest: BackupManifest) -> list[BackupExternalReference]:
    missing: list[BackupExternalReference] = []
    for ref in manifest.external_references:
        if ref.path and _reference_path_missing(ref):
            missing.append(ref.model_copy(update={"missing": True}))
        elif ref.missing:
            missing.append(ref)
    return missing


def _reference_path_missing(ref: BackupExternalReference) -> bool:
    path = Path(ref.path or "")
    if ref.kind == "project":
        return not path.exists()
    return not path.is_file()


def _safe_relative(relative: str) -> str:
    posix = PurePosixPath(relative.replace("\\", "/"))
    text = posix.as_posix()
    if posix.is_absolute() or ".." in posix.parts or text in {"", "."}:
        raise BackupError("Unsafe backup relative path.", code="unsafe_backup_path")
    for part in posix.parts:
        stem = part.split(".", 1)[0].lower()
        if ":" in part or stem in WINDOWS_DEVICE_NAMES:
            raise BackupError("Unsafe Windows backup path.", code="unsafe_backup_path")
    return text


def _new_staging_dir(root: Path, purpose: str) -> Path:
    staging_root = root / "state" / "backup-staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    for _ in range(100):
        candidate = staging_root / f"{purpose}-{new_id('stage')}"
        try:
            candidate.mkdir(exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise BackupError("Could not create a unique backup staging directory.", code="backup_staging_collision")


def _checkpoint_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in ("langgraph", "langgraph-checkpoint", "langgraph-checkpoint-sqlite"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def _verify_checkpoint_versions(manifest: BackupManifest) -> None:
    current = _checkpoint_versions()
    for package, expected in manifest.checkpoint_versions.items():
        if current.get(package) != expected:
            raise BackupError(
                f"Checkpoint framework version mismatch for {package}.",
                code="checkpoint_version_mismatch",
            )


def _verify_sqlite_integrity(path: Path, *, required: bool) -> None:
    if not path.exists():
        if required:
            raise BackupError("Required application database is missing.", code="application_db_missing")
        return
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        if row is None or row[0] != "ok":
            raise BackupError(f"SQLite integrity check failed for {path.name}.", code="sqlite_integrity_failed")
        if required:
            tables = {item[0] for item in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "schema_meta" not in tables or "runs" not in tables or "conversations" not in tables:
                raise BackupError("Application database is missing required tables.", code="application_db_invalid")
    finally:
        conn.close()


def _verify_application_schema_compatible(root: Path) -> None:
    """Validate and migrate supported application.sqlite schemas before restore activation."""
    store: ApplicationStore | None = None
    try:
        store = ApplicationStore(WorkbenchPaths(root))
    except ValueError as exc:
        if "different runtime version" not in str(exc):
            raise BackupError(
                "Application database is not valid for this runtime.",
                code="application_db_invalid",
            ) from exc
        raise BackupError(
            "Application database schema is not compatible with this runtime.",
            code="application_schema_incompatible",
        ) from exc
    except Exception as exc:
        raise BackupError(
            "Application database is not valid for this runtime.",
            code="application_db_invalid",
        ) from exc
    finally:
        if store is not None:
            store.close()


def _verify_application_linkages(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        tables = {item[0] for item in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "runs" in tables and "run_checkpoints" in tables:
            row = conn.execute(
                """
                SELECT run_checkpoints.run_id
                FROM run_checkpoints
                LEFT JOIN runs ON runs.id = run_checkpoints.run_id
                WHERE runs.id IS NULL
                LIMIT 1
                """
            ).fetchone()
            if row is not None:
                raise BackupError("Application database has a checkpoint linked to a missing run.", code="application_linkage_invalid")
        if "runs" in tables and "run_files" in tables:
            row = conn.execute(
                """
                SELECT run_files.run_id
                FROM run_files
                LEFT JOIN runs ON runs.id = run_files.run_id
                WHERE runs.id IS NULL
                LIMIT 1
                """
            ).fetchone()
            if row is not None:
                raise BackupError("Application database has a file link for a missing run.", code="application_linkage_invalid")
        if "conversations" in tables and "runs" in tables:
            run_ids = {row["id"] for row in conn.execute("SELECT id FROM runs").fetchall()}
            for row in conn.execute("SELECT id, payload FROM conversations").fetchall():
                payload = json.loads(row["payload"])
                for run_id in payload.get("run_ids") or []:
                    if run_id not in run_ids:
                        raise BackupError("Application database has a conversation linked to a missing run.", code="application_linkage_invalid")
                source_run_id = payload.get("source_run_id")
                if source_run_id and source_run_id not in run_ids:
                    raise BackupError("Application database has a branch linked to a missing source run.", code="application_linkage_invalid")
        # An asset's source session is immutable provenance. Deleting that
        # session can leave a valid retained copy used by another consumer.
        # Validate live consumer links below, not historical provenance.
        if "retained_asset_consumers" in tables:
            row = conn.execute(
                """
                SELECT retained_asset_consumers.asset_id
                FROM retained_asset_consumers
                LEFT JOIN retained_assets ON retained_assets.id = retained_asset_consumers.asset_id
                WHERE retained_assets.id IS NULL
                LIMIT 1
                """
            ).fetchone()
            if row is not None:
                raise BackupError("Application database has a retained asset consumer linked to a missing asset.", code="application_linkage_invalid")
            if "runs" in tables:
                row = conn.execute(
                    """
                    SELECT consumer_id
                    FROM retained_asset_consumers
                    LEFT JOIN runs ON runs.id = retained_asset_consumers.consumer_id
                    WHERE consumer_kind = 'run' AND runs.id IS NULL
                    LIMIT 1
                    """
                ).fetchone()
                if row is not None:
                    raise BackupError("Application database has a retained asset linked to a missing run.", code="application_linkage_invalid")
            if "conversations" in tables:
                row = conn.execute(
                    """
                    SELECT consumer_id
                    FROM retained_asset_consumers
                    LEFT JOIN conversations ON conversations.id = retained_asset_consumers.consumer_id
                    WHERE consumer_kind = 'session' AND conversations.id IS NULL
                    LIMIT 1
                    """
                ).fetchone()
                if row is not None:
                    raise BackupError("Application database has a retained asset linked to a missing session.", code="application_linkage_invalid")
        if "interaction_threads" in tables:
            if "conversations" in tables:
                row = conn.execute(
                    """
                    SELECT interaction_threads.id
                    FROM interaction_threads
                    LEFT JOIN conversations ON conversations.id = interaction_threads.conversation_id
                    WHERE interaction_threads.conversation_id IS NOT NULL
                      AND conversations.id IS NULL
                    LIMIT 1
                    """
                ).fetchone()
                if row is not None:
                    raise BackupError("Application database has an interaction linked to a missing conversation.", code="application_linkage_invalid")
            if "runs" in tables:
                row = conn.execute(
                    """
                    SELECT interaction_threads.id
                    FROM interaction_threads
                    LEFT JOIN runs ON runs.id = interaction_threads.run_id
                    WHERE interaction_threads.run_id IS NOT NULL
                      AND runs.id IS NULL
                    LIMIT 1
                    """
                ).fetchone()
                if row is not None:
                    raise BackupError("Application database has an interaction linked to a missing run.", code="application_linkage_invalid")
        if "interaction_events" in tables and "interaction_threads" in tables:
            row = conn.execute(
                """
                SELECT interaction_events.thread_id
                FROM interaction_events
                LEFT JOIN interaction_threads ON interaction_threads.id = interaction_events.thread_id
                WHERE interaction_threads.id IS NULL
                LIMIT 1
                """
            ).fetchone()
            if row is not None:
                raise BackupError("Application database has interaction events linked to a missing interaction.", code="application_linkage_invalid")
    finally:
        conn.close()


def _reconcile_restored_application_db(db_path: Path, destination: Path, source_root: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        for table in ("runs", "conversations"):
            rows = conn.execute(f"SELECT id, payload FROM {table}").fetchall()
            for row in rows:
                payload = json.loads(row["payload"])
                if table == "runs":
                    _reconcile_run_payload(payload)
                else:
                    _reconcile_conversation_payload(payload)
                _rebase_payload_paths(payload, destination, source_root)
                conn.execute(
                    f"UPDATE {table} SET payload = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(payload), utc_now(), row["id"]),
                )
        tables = {item[0] for item in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "retained_assets" in tables:
            for row in conn.execute("SELECT id, payload FROM retained_assets").fetchall():
                payload = json.loads(row["payload"])
                _rebase_payload_paths(payload, destination, source_root)
                conn.execute("UPDATE retained_assets SET payload=?, project_path=? WHERE id=?",
                    (json.dumps(payload), payload.get("project_path"), row["id"]))
        if "retained_asset_consumers" in tables:
            for row in conn.execute("SELECT asset_id, consumer_id FROM retained_asset_consumers WHERE consumer_kind='project'").fetchall():
                value = {"project_path": row["consumer_id"]}
                _rebase_payload_paths(value, destination, source_root)
                conn.execute("UPDATE retained_asset_consumers SET consumer_id=? WHERE asset_id=? AND consumer_kind='project' AND consumer_id=?",
                    (value["project_path"], row["asset_id"], row["consumer_id"]))
        conn.commit()
    finally:
        conn.close()


def _reconcile_run_payload(payload: dict[str, Any]) -> None:
    if payload.get("status") in LIVE_RUN_STATUSES:
        payload["status"] = "failed"
        payload["error"] = "Run was not replayed after backup restore."
        payload["finished_at"] = payload.get("finished_at") or utc_now()
        events = payload.setdefault("events", [])
        if isinstance(events, list):
            events.append({"at": utc_now(), "kind": "restore_reconciled", "detail": {"replayed": False}})
    payload["pending_interrupt"] = None


def _reconcile_conversation_payload(payload: dict[str, Any]) -> None:
    payload["current_run_id"] = None
    queue = payload.get("queue")
    if isinstance(queue, list):
        for item in queue:
            if isinstance(item, dict) and item.get("status") in {"queued", "dispatching"}:
                item["status"] = "paused"
                item["pause_reason"] = "failed"
                item["updated_at"] = utc_now()


def _rebase_payload_paths(value: Any, destination: Path, source_root: Path) -> None:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key in {"tree_path", "path", "project_path", "mutable_reference"} and isinstance(item, str):
                try:
                    relative = Path(item).relative_to(source_root)
                except ValueError:
                    continue
                if relative.parts and relative.parts[0] in {"snapshots", "workspaces"}:
                    value[key] = str(destination / relative)
            _rebase_payload_paths(item, destination, source_root)
    elif isinstance(value, list):
        for item in value:
            _rebase_payload_paths(item, destination, source_root)


def _rebase_restored_json_files(root: Path, destination: Path, source_root: Path) -> None:
    bundles = root / "state" / "bundles.json"
    if bundles.is_file():
        payload = json.loads(bundles.read_text(encoding="utf-8"))
        for bundle in payload:
            # Weights are excluded from backups. The restored application may
            # reference them but must not inherit ownership of source files.
            bundle["managed_root"] = None
            for collection in ("files", "shards", "companions"):
                for item in bundle.get(collection, []):
                    item["ownership"] = "external"
        bundles.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    records = [*(root / "snapshots").glob("*/manifest.json"), *(root / "cases").glob("*.json")]
    for path in records:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        _rebase_payload_paths(payload, destination, source_root)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    deployments = root / "state" / "deployments.json"
    if deployments.is_file():
        payload = json.loads(deployments.read_text(encoding="utf-8"))
        for deployment in payload:
            if deployment.get("scope") == "managed":
                deployment.update(status="stopped", pid=None, process_identity=None, health=None,
                    resource_usage={"available": False, "reason": "Restored deployment is stopped"})
        deployments.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    imports = root / "state" / "import_jobs.json"
    if imports.is_file():
        payload = json.loads(imports.read_text(encoding="utf-8"))
        for job in payload:
            if job.get("status") in {"pending", "running", "stopping"}:
                job.update(status="stopped", transfer_pid=None, transfer_create_time=None, finished_at=utc_now())
        imports.write_text(json.dumps(payload, indent=2), encoding="utf-8")
