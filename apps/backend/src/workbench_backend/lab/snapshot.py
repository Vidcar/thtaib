"""Application-owned directory snapshots. Not git-commit-as-snapshot."""

from __future__ import annotations

import shutil
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from workbench_backend.errors import LabError
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.lab.schemas import SnapshotExclusion, SnapshotFile

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
    root = project_root.resolve()
    included: list[tuple[Path, str]] = []
    excluded: list[SnapshotExclusion] = []
    seen: set[str] = set()

    candidates: list[Path]
    if allowlist:
        candidates = []
        for rel in allowlist:
            candidate = (root / rel).resolve()
            if candidate.is_file():
                candidates.append(candidate)
            else:
                excluded.append(SnapshotExclusion(path=_rel(root, Path(rel)), reason="allowlist_missing"))
    else:
        candidates = [path for path in root.rglob("*") if path.is_file() or path.is_symlink()]

    for path in candidates:
        relative = _rel(root, path)
        if relative in seen:
            continue
        seen.add(relative)
        if path.is_symlink() or path.is_file():
            resolved = path.resolve()
            if not _is_within(root, resolved):
                excluded.append(SnapshotExclusion(path=relative, reason="symlink_escape"))
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
        shutil.copy2(source, target)
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


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return Path(path).as_posix().replace("\\", "/")


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False
