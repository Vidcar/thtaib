"""Confined read-only access to files in a selected project."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from workbench_backend.errors import HarnessError

TEXT_LIMIT = 256_000
RESERVED_ROUTES = {"memories", "skills", "retrieved", "conversation_history", "large_tool_results"}


class FileImage(BaseModel):
    exists: bool
    sha256: str | None = None
    size_bytes: int = 0
    text: str | None = None


def project_file(root: Path, value: str) -> Path:
    """Resolve one regular project file without following links or framework routes."""
    normalized = value.replace("\\", "/")
    parts = PurePosixPath(normalized.lstrip("/")).parts
    if (not parts or normalized.startswith("//") or any(part in {"..", "."} or ":" in part
            or part.rstrip(" .") != part or part.split(".")[0].upper() in
            {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}
            for part in parts) or parts[0].lower() in RESERVED_ROUTES):
        raise HarnessError("Choose a regular file inside this project, outside managed knowledge and history.", code="project_file_scope", status_code=403)
    base = root.resolve()
    path = base.joinpath(*parts)
    for candidate in (path, *path.parents):
        if candidate == base:
            break
        if candidate.is_symlink() or candidate.is_junction():
            raise HarnessError("Project files cannot follow symbolic links or junctions.", code="project_file_link", status_code=403)
    if not path.resolve().is_relative_to(base) or path == base:
        raise HarnessError("The file is outside this project.", code="project_file_scope", status_code=403)
    if path.exists() and not path.is_file():
        raise HarnessError("Choose a regular file rather than a folder.", code="project_file_not_regular", status_code=400)
    return path


def file_image(path: Path) -> FileImage:
    """Read a bounded text preview while recording complete byte identity."""
    if not path.exists():
        return FileImage(exists=False)
    digest = hashlib.sha256()
    captured = bytearray()
    size = 0
    before = path.stat()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
            if size <= TEXT_LIMIT:
                captured.extend(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise HarnessError("The file changed while it was being inspected. Retry after editing stops.", code="project_file_changed", status_code=409)
    text = None
    if size <= TEXT_LIMIT and b"\x00" not in captured:
        try:
            text = captured.decode("utf-8")
        except UnicodeDecodeError:
            pass
    return FileImage(exists=True, sha256=digest.hexdigest(), size_bytes=size, text=text)
