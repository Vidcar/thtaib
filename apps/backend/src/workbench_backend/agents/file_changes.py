"""Observed project-file changes, retained in the existing run record."""
from __future__ import annotations

import difflib
import hashlib
import os
import threading
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel

from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import new_id, utc_now

TEXT_LIMIT = 256_000
MUTATION_TOOLS = {"write_file", "edit_file", "rename_file", "delete_file"}
RESERVED_ROUTES = {"memories", "skills", "retrieved", "conversation_history", "large_tool_results"}


class FileImage(BaseModel):
    exists: bool
    sha256: str | None = None
    size_bytes: int = 0
    text: str | None = None


class ProjectFileChange(BaseModel):
    id: str
    run_id: str
    tool_call_id: str
    tool_name: str
    operation: Literal["created", "modified", "renamed", "deleted"]
    path: str
    destination: str | None = None
    before: FileImage
    after: FileImage | None = None
    status: Literal["pending", "changed", "unchanged", "failed", "unconfirmed"] = "pending"
    created_at: str
    observed_at: str | None = None
    error: str | None = None
    reversed_at: str | None = None


class ProjectFileChangeView(BaseModel):
    change: ProjectFileChange
    current_matches: bool = False
    reversal_available: bool = False
    reversal_unavailable_reason: str | None = None
    diff: str | None = None
    diff_unavailable_reason: str | None = None
    note: str = "Observed file changes only. This does not undo shell commands, remote actions or an entire run."


def project_file(root: Path, value: str) -> Path:
    """Resolve a single project file, excluding framework routes and links."""
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
            raise HarnessError("File changes cannot follow symbolic links or junctions.", code="project_file_link", status_code=403)
    if not path.resolve().is_relative_to(base) or path == base:
        raise HarnessError("The file is outside this project.", code="project_file_scope", status_code=403)
    if path.exists() and not path.is_file():
        raise HarnessError("Choose a file. Folder and recursive removal are unsupported.", code="project_file_not_regular", status_code=400)
    return path


def file_image(path: Path) -> FileImage:
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


def same_image(left: FileImage, right: FileImage) -> bool:
    return (left.exists, left.sha256, left.size_bytes) == (right.exists, right.sha256, right.size_bytes)


class FileChangeRecorder:
    def __init__(self, run: Any, publish: Callable[[Callable[[], None]], None]) -> None:
        self.run = run
        self.publish = publish
        self.lock = threading.Lock()

    def prepare(self, name: str, args: dict[str, Any], call_id: str) -> ProjectFileChange | None:
        if name not in MUTATION_TOOLS or not self.run.project_path:
            return None
        value = args.get("file_path")
        if not isinstance(value, str):
            return None
        # Built-in knowledge writes retain their existing middleware owner.
        if value.replace("\\", "/").lstrip("/").split("/")[0].lower() in RESERVED_ROUTES:
            if name in {"write_file", "edit_file"}:
                return None
        root = Path(self.run.project_path)
        source = project_file(root, value)
        before = file_image(source)
        destination = None
        if name == "rename_file":
            target = project_file(root, str(args.get("destination", "")))
            if target.exists():
                raise HarnessError("The rename destination already exists.", code="project_file_conflict", status_code=409)
            destination = target.relative_to(root.resolve()).as_posix()
        operation = "renamed" if name == "rename_file" else "deleted" if name == "delete_file" else "modified" if before.exists else "created"
        change = ProjectFileChange(id=new_id("filechange"), run_id=self.run.id, tool_call_id=call_id,
            tool_name=name, operation=operation, path=source.relative_to(root.resolve()).as_posix(),
            destination=destination, before=before, created_at=utc_now())
        self.publish(lambda: self.run.file_changes.append(change))
        return change

    def finish(self, change: ProjectFileChange | None, *, error: BaseException | None = None) -> None:
        if change is None:
            return
        try:
            root = Path(self.run.project_path)
            after = file_image(project_file(root, change.destination or change.path))
            changed = not same_image(change.before, after)
            status = "changed" if changed else "failed" if error else "unchanged"
            if change.operation == "renamed":
                source_after = file_image(project_file(root, change.path))
                if after.exists and not source_after.exists and same_image(change.before, after):
                    status = "changed"
                elif not after.exists and same_image(change.before, source_after):
                    status = "failed" if error else "unchanged"
                else:
                    status = "unconfirmed"
            if error is not None and status == "changed":
                # A failed operation cannot establish attribution of a changed
                # postimage; it may be partial work or a concurrent editor.
                status = "unconfirmed"
            updates = {"after": after, "status": status, "observed_at": utc_now(), "error": str(error) if error else None}
        except Exception as exc:
            updates = {"status": "unconfirmed", "observed_at": utc_now(), "error": str(exc)}
        def update() -> None:
            self.run.file_changes = [item.model_copy(update=updates) if item.id == change.id else item for item in self.run.file_changes]
        self.publish(update)


def change_view(root: Path, change: ProjectFileChange, *, run_active: bool) -> ProjectFileChangeView:
    view = ProjectFileChangeView(change=change)
    if change.before.text is not None or not change.before.exists:
        if change.after is not None and (change.after.text is not None or not change.after.exists):
            view.diff = "".join(difflib.unified_diff((change.before.text or "").splitlines(keepends=True),
                (change.after.text or "").splitlines(keepends=True), fromfile=change.path,
                tofile=change.destination or change.path))
    if view.diff is None:
        view.diff_unavailable_reason = "A complete before-and-after UTF-8 text capture is unavailable (binary, larger than 256 KB, or interrupted)."
    try:
        current = file_image(project_file(root, change.destination or change.path))
        view.current_matches = change.after is not None and same_image(current, change.after)
        if change.operation == "renamed" and project_file(root, change.path).exists():
            view.current_matches = False
    except (OSError, HarnessError) as exc:
        view.reversal_unavailable_reason = str(exc)
    if change.reversed_at:
        view.reversal_unavailable_reason = "This change has already been reversed."
    elif run_active:
        view.reversal_unavailable_reason = "Wait for work in this project to stop before reversing a file change."
    elif change.status != "changed" or change.after is None:
        view.reversal_unavailable_reason = "This operation has no confirmed changed file state."
    elif not view.current_matches:
        view.reversal_unavailable_reason = "The file has changed since this operation. Reversal would overwrite a later edit."
    elif change.before.exists and change.before.text is None and change.operation != "renamed":
        view.reversal_unavailable_reason = "The original content was binary or larger than 256 KB, so no complete reversible preimage was retained."
    view.reversal_available = view.reversal_unavailable_reason is None
    return view


def reverse_change(root: Path, change: ProjectFileChange) -> None:
    view = change_view(root, change, run_active=False)
    if not view.reversal_available:
        raise HarnessError(view.reversal_unavailable_reason or "This change cannot be reversed.", code="file_reversal_conflict", status_code=409)
    source = project_file(root, change.path)
    if change.operation == "renamed":
        project_file(root, change.destination or "").rename(source)
    elif not change.before.exists:
        source.unlink()
    else:
        content = (change.before.text or "").encode("utf-8")
        staged = source.with_name(f".{source.name}.{uuid4().hex}.restore")
        try:
            with staged.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            # Recheck after staging; a concurrent editor cannot be overlooked.
            if not same_image(file_image(source), change.after):
                raise HarnessError("The file changed while reversal was prepared.", code="file_reversal_conflict", status_code=409)
            os.replace(staged, source)
        finally:
            staged.unlink(missing_ok=True)
