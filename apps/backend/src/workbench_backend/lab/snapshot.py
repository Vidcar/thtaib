"""Application-owned directory snapshots. Not git-commit-as-snapshot."""

from __future__ import annotations

import os
import shutil
import stat
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from workbench_backend.errors import LabError
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.lab.schemas import (
    SnapshotExclusion,
    SnapshotFile,
    SnapshotKind,
    SnapshotManifest,
)
from workbench_backend.paths import WorkbenchPaths

EXCLUDED_DIR_NAMES = frozenset(
    {
        ".scratch",
        ".venv",
        "venv",
        "node_modules",
        ".git",
        "__pycache__",
    }
)

EXCLUDED_FILE_GLOBS = (
    ".env",
    ".env.*",
    "*.gguf",
    "*.gguf.part",
    "*mmproj*",
    "*.pem",
    "*.key",
    "*secret*",
    "*credential*",
    ".netrc",
    "id_rsa",
    "id_rsa.pub",
    "*.p12",
    "*.pfx",
)

ENVIRONMENT_EXCLUSIONS = (
    "process environment variables",
    "OS user profile",
    "installed system packages",
    "managed inference runtime and weights (referenced by id only)",
    "worker or container environment (OQ-003)",
)


def exclusion_reason(relative: str) -> str | None:
    posix = PurePosixPath(relative.replace("\\", "/"))
    for part in posix.parts:
        if part in EXCLUDED_DIR_NAMES:
            if part == ".scratch":
                return "scratch"
            if part in {".venv", "venv"}:
                return "venv"
            if part == "node_modules":
                return "node_modules"
            return f"excluded_dir:{part}"
        reason = _name_reason(part)
        if reason:
            return reason
    return _name_reason(posix.name)


def _name_reason(name: str) -> str | None:
    lower = name.lower()
    if lower.endswith(".gguf") or ".gguf." in lower or "mmproj" in lower:
        return "weights"
    for pattern in EXCLUDED_FILE_GLOBS:
        if fnmatch(name, pattern) or fnmatch(lower, pattern.lower()):
            if pattern in {".env", ".env.*", ".netrc"}:
                return "env_credentials"
            if pattern in {"*.gguf", "*.gguf.part", "*mmproj*"}:
                return "weights"
            return "secrets"
    return None


def plan_snapshot(
    project_root: Path,
    *,
    allowlist: list[str] | None = None,
) -> tuple[list[tuple[Path, str]], list[SnapshotExclusion]]:
    root = project_root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    included: list[tuple[Path, str]] = []
    excluded: list[SnapshotExclusion] = []
    seen: set[str] = set()

    candidates: list[Path] = []
    if allowlist is not None:
        for rel in allowlist:
            requested = PurePosixPath(rel.replace("\\", "/"))
            if requested.is_absolute() or Path(rel).drive or ".." in requested.parts or requested.as_posix() in {"", "."}:
                excluded.append(SnapshotExclusion(path=rel, reason="allowlist_invalid"))
                continue
            candidate = root.joinpath(*requested.parts)
            symlink_reason = _symlink_reason(root, candidate)
            if symlink_reason:
                excluded.append(SnapshotExclusion(path=requested.as_posix(), reason=symlink_reason))
            elif candidate.is_file():
                candidates.append(candidate)
            else:
                excluded.append(SnapshotExclusion(path=requested.as_posix(), reason="allowlist_missing"))
    else:
        def raise_walk_error(error: OSError) -> None:
            raise error

        for current, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=raise_walk_error):
            directory = Path(current)
            kept_dirs: list[str] = []
            for name in sorted(dirs):
                path = directory / name
                relative = path.relative_to(root).as_posix()
                reason = _symlink_reason(root, path) or exclusion_reason(relative)
                if reason:
                    excluded.append(SnapshotExclusion(path=relative, reason=reason))
                else:
                    kept_dirs.append(name)
            dirs[:] = kept_dirs
            candidates.extend(directory / name for name in sorted(files))

    for path in candidates:
        relative = path.relative_to(root).as_posix()
        if relative in seen:
            continue
        seen.add(relative)
        symlink_reason = _symlink_reason(root, path)
        if symlink_reason:
            excluded.append(SnapshotExclusion(path=relative, reason=symlink_reason))
            continue
        reason = exclusion_reason(relative)
        if reason:
            excluded.append(SnapshotExclusion(path=relative, reason=reason))
            continue
        if not path.is_file():
            excluded.append(SnapshotExclusion(path=relative, reason="not_a_file"))
            continue
        included.append((path, relative))
    return included, excluded


def capture_project_snapshot(
    paths: WorkbenchPaths,
    *,
    workspace_id: str,
    project_root: Path,
    kind: SnapshotKind,
    allowlist: list[str] | None = None,
    unresolved_side_effects: list[str] | None = None,
    snapshot_id: str | None = None,
) -> SnapshotManifest:
    """Write one application-owned directory snapshot. Not a second snapshot system."""

    snapshot_id = snapshot_id or new_id("snap")
    if not snapshot_id.startswith("snap_") or not all(
        char.isalnum() or char in {"_", "-"} for char in snapshot_id
    ):
        raise ValueError("Invalid snapshot identity.")
    final = paths.snapshots / snapshot_id
    staging = paths.snapshots / f".{snapshot_id}.staging"
    paths.snapshots.mkdir(parents=True, exist_ok=True)
    if final.exists() or staging.exists():
        raise FileExistsError(f"Snapshot identity is already in use: {snapshot_id}")
    staging.mkdir()
    try:
        included, exclusions = write_snapshot_tree(project_root, staging / "tree", allowlist=allowlist)
        manifest = SnapshotManifest(
            id=snapshot_id,
            workspace_id=workspace_id,
            captured_at=utc_now(),
            kind=kind,
            included_files=included,
            exclusions=exclusions,
            environment_exclusions=list(ENVIRONMENT_EXCLUSIONS),
            unresolved_side_effects=list(unresolved_side_effects or []),
            allowlist=allowlist,
            tree_path=str(final / "tree"),
        )
        (staging / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        staging.rename(final)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def discard_incomplete_snapshot_staging(paths: WorkbenchPaths, snapshot_id: str) -> None:
    """Remove only the reserved staging tree after an interrupted capture."""
    if not snapshot_id.startswith("snap_") or not all(
        char.isalnum() or char in {"_", "-"} for char in snapshot_id
    ):
        raise ValueError("Invalid snapshot identity.")
    staging = paths.snapshots / f".{snapshot_id}.staging"
    if staging.is_symlink() or staging.is_junction():
        staging.unlink()
    elif staging.exists():
        shutil.rmtree(staging)


def write_snapshot_tree(
    project_root: Path,
    dest_tree: Path,
    *,
    allowlist: list[str] | None = None,
) -> tuple[list[SnapshotFile], list[SnapshotExclusion]]:
    included, excluded = plan_snapshot(project_root, allowlist=allowlist)
    dest_tree.mkdir(parents=True, exist_ok=True)
    files: list[SnapshotFile] = []
    for source, relative in included:
        target = dest_tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _copy_stable_file(project_root.resolve(), source, target)
        files.append(
            SnapshotFile(
                path=relative,
                sha256=sha256_file(target),
                size_bytes=target.stat().st_size,
            )
        )
    return files, excluded


def iter_snapshot_tree_files(tree_path: Path) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for source in sorted(tree_path.rglob("*"), key=lambda path: path.as_posix()):
        if source.is_dir() and not source.is_symlink():
            continue
        relative = _tree_relative(tree_path, source)
        files.append((source, relative))
    return files


def verify_snapshot_tree(tree_path: Path, included_files: list[SnapshotFile]) -> None:
    if not tree_path.is_dir():
        raise LabError(
            "Snapshot tree is missing; an empty included-file list is not a substitute "
            "for the captured tree.",
            code="snapshot_tree_missing",
            status_code=409,
        )
    expected = _expected_files(included_files)
    found: dict[str, SnapshotFile] = {}
    for source, relative in iter_snapshot_tree_files(tree_path):
        if source.is_symlink() or not source.is_file():
            raise LabError(
                f"Snapshot tree contains unexpected file: {relative}",
                code="snapshot_unexpected_file",
                status_code=409,
                details={"path": relative},
            )
        if relative not in expected:
            raise LabError(
                f"Snapshot tree contains unexpected file: {relative}",
                code="snapshot_unexpected_file",
                status_code=409,
                details={"path": relative},
            )
        found[relative] = SnapshotFile(
            path=relative,
            sha256=sha256_file(source),
            size_bytes=source.stat().st_size,
        )
    for relative, recorded in expected.items():
        actual = found.get(relative)
        if actual is None:
            raise LabError(
                f"Snapshot is missing expected file: {relative}",
                code="snapshot_file_missing",
                status_code=409,
                details={"path": relative},
            )
        if actual.sha256 != recorded.sha256 or actual.size_bytes != recorded.size_bytes:
            raise LabError(
                f"Snapshot hash mismatch for {relative}",
                code="snapshot_hash_mismatch",
                status_code=409,
                details={"path": relative},
            )


def restore_snapshot_tree(
    tree_path: Path,
    dest_project: Path,
    *,
    included_files: list[SnapshotFile],
) -> None:
    verify_snapshot_tree(tree_path, included_files)
    dest = dest_project
    if dest.exists() and _tree_has_entries(dest):
        raise LabError(
            "Restore destination is not empty; refusing to mix an incomplete restore.",
            code="snapshot_restore_incomplete",
            status_code=409,
        )
    dest.mkdir(parents=True, exist_ok=True)
    try:
        for item in included_files:
            relative = _safe_relative(item.path)
            source = tree_path / relative
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        verify_snapshot_tree(dest, included_files)
    except Exception:
        _discard_failed_staging(dest)
        raise


def project_fingerprints(project_root: Path) -> dict[str, str]:
    if not project_root.is_dir():
        return {}
    included, _excluded = plan_snapshot(project_root)
    return {relative: sha256_file(path) for path, relative in included}


def read_text_files(project_root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not project_root.is_dir():
        return out
    included, _excluded = plan_snapshot(project_root)
    for path, relative in included:
        try:
            out[relative] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            out[relative] = f"<binary {path.stat().st_size} bytes>"
    return out


def write_text_files(project_root: Path, files: dict[str, str]) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        if exclusion_reason(relative):
            continue
        if ".." in PurePosixPath(relative).parts:
            continue
        target = (project_root / relative).resolve()
        if not _is_within(project_root.resolve(), target):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _expected_files(included_files: list[SnapshotFile]) -> dict[str, SnapshotFile]:
    expected: dict[str, SnapshotFile] = {}
    for item in included_files:
        relative = _safe_relative(item.path)
        recorded = item.model_copy(update={"path": relative})
        existing = expected.get(relative)
        if existing is not None and (
            existing.sha256 != recorded.sha256 or existing.size_bytes != recorded.size_bytes
        ):
            raise LabError(
                f"Snapshot hash mismatch for {relative}",
                code="snapshot_hash_mismatch",
                status_code=409,
                details={"path": relative},
            )
        expected[relative] = recorded
    return expected


def _safe_relative(relative: str) -> str:
    posix = PurePosixPath(relative.replace("\\", "/"))
    if posix.is_absolute() or ".." in posix.parts or posix.as_posix() in {"", "."}:
        raise LabError(
            f"Snapshot tree contains unexpected file: {relative}",
            code="snapshot_unexpected_file",
            status_code=409,
            details={"path": relative},
        )
    return posix.as_posix()


def _tree_relative(tree_path: Path, source: Path) -> str:
    return source.relative_to(tree_path).as_posix()


def _tree_has_entries(path: Path) -> bool:
    if not path.is_dir():
        return True
    return any(True for _ in path.iterdir())


def _discard_failed_staging(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)


def _symlink_reason(root: Path, path: Path) -> str | None:
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink() or current.is_junction():
            try:
                return "symlink_escape" if not _is_within(root, current.resolve(strict=True)) else "symlink"
            except OSError:
                return "symlink"
    return None


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _copy_stable_file(root: Path, source: Path, target: Path) -> None:
    if _symlink_reason(root, source):
        raise OSError(f"Snapshot source became a symlink: {source}")
    before = source.stat()
    if not stat.S_ISREG(before.st_mode):
        raise OSError(f"Snapshot source is not a regular file: {source}")
    with source.open("rb") as opened:
        if _file_identity(os.fstat(opened.fileno())) != _file_identity(before):
            raise OSError(f"Snapshot source changed while opening: {source}")
        if not _is_within(root, source.resolve(strict=True)):
            raise OSError(f"Snapshot source escaped the project: {source}")
        with target.open("wb") as copied:
            shutil.copyfileobj(opened, copied)
        if _file_identity(os.fstat(opened.fileno())) != _file_identity(before):
            raise OSError(f"Snapshot source changed while copying: {source}")
    if _symlink_reason(root, source) or _file_identity(source.stat()) != _file_identity(before):
        raise OSError(f"Snapshot source changed after copying: {source}")
    if target.stat().st_size != before.st_size:
        raise OSError(f"Snapshot copy size mismatch: {source}")


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False
