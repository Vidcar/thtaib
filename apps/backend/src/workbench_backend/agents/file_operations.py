"""Selected project mutation extensions; native file tools keep their ownership."""
from __future__ import annotations

import asyncio
from collections import deque
import contextvars
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import threading
from typing import Annotated
import weakref

from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field

from workbench_backend.agents.harness_backend import canonical_root, is_reserved_framework_path
from workbench_backend.agents.project_files import project_file
from workbench_backend.errors import HarnessError

MAX_EDIT_BYTES = 4_000_000
MAX_DELETE_ENTRIES = 100_000
_locks: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
_lock_guard = threading.Lock()
# Set only around an admitted mutation. The synchronous tool body borrows this
# same lease; a different project, or a direct caller, still acquires.
ADMITTED_PROJECT_MUTATION: contextvars.ContextVar = contextvars.ContextVar("admitted_project_mutation", default=None)


class _MutationWaiter:
    __slots__ = ("kind", "signal", "admitted")

    def __init__(self, kind: str, signal) -> None:
        self.kind = kind
        self.signal = signal
        self.admitted = False


class ProjectMutationLease:
    """Per-path gate whose asynchronous waiters do not occupy worker threads.

    The mutex covers only the queue. An async waiter parks on a Future and a
    synchronous caller parks on an Event. Release transfers ownership in FIFO
    order and leaves the gate held, so cancelling one waiter cannot admit two.
    """

    def __init__(self) -> None:
        self._mutex = threading.Lock()
        self._held = False
        self._waiters: deque[_MutationWaiter] = deque()

    def waiting(self) -> int:
        with self._mutex:
            return len(self._waiters)

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if not blocking:
            with self._mutex:
                if self._held or self._waiters:
                    return False
                self._held = True
                return True
        waiter = None
        with self._mutex:
            if not self._held:
                self._held = True
                return True
            event = threading.Event()
            waiter = _MutationWaiter("sync", event)
            self._waiters.append(waiter)
        if timeout is None or timeout < 0:
            event.wait()
            return True
        if event.wait(timeout):
            return True
        with self._mutex:
            if not waiter.admitted:
                try:
                    self._waiters.remove(waiter)
                except ValueError:
                    pass
                return False
        self.release()
        return False

    async def acquire_async(self) -> None:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        waiter = _MutationWaiter("async", future)
        with self._mutex:
            if not self._held:
                self._held = True
                return
            self._waiters.append(waiter)
        try:
            await future
        except asyncio.CancelledError:
            release = False
            with self._mutex:
                if waiter.admitted:
                    release = True
                else:
                    try:
                        self._waiters.remove(waiter)
                    except ValueError:
                        release = waiter.admitted
            if release:
                self.release()
            raise

    def release(self) -> None:
        with self._mutex:
            if not self._held:
                raise RuntimeError("project mutation lease released while free")
            self._handoff_locked()

    def _handoff_locked(self) -> None:
        while self._waiters:
            waiter = self._waiters.popleft()
            if waiter.kind == "async":
                future = waiter.signal
                if future.cancelled() or future.done():
                    continue
                waiter.admitted = True
                future.get_loop().call_soon_threadsafe(self._resolve_future, future)
                return
            waiter.admitted = True
            waiter.signal.set()
            return
        self._held = False

    @staticmethod
    def _resolve_future(future) -> None:
        if not future.done():
            future.set_result(True)

    def __enter__(self):
        if ADMITTED_PROJECT_MUTATION.get() is self:
            return self
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        if ADMITTED_PROJECT_MUTATION.get() is self:
            return False
        self.release()
        return False


class ExactEdit(BaseModel):
    old_string: str = Field(min_length=1, description="Exact text in the original file; every edit is matched against that same original.")
    new_string: str
    replace_all: bool = False


class ApplyEditsInput(BaseModel):
    file_path: str = Field(min_length=1, description="Project-relative regular UTF-8 file; framework/host paths and links are refused.")
    edits: Annotated[list[ExactEdit], Field(min_length=1, max_length=64)]
    base_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$", description="Omit for a read-only preview and original hash. Supply that unchanged original-byte hash to apply atomically.")


def project_mutation_lock(project: Path) -> ProjectMutationLease:
    """Lease for one canonical path. Callers order a file, not a whole folder."""
    return file_order_lock(project)


def file_order_path(project: Path, file_path: str):
    """Canonical key for one project-relative file. The folder itself is not a key."""
    normalized = str(file_path).replace("\\", "/").lstrip("/")
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("File order needs one project-relative path.")
    return canonical_root(Path(project).resolve().joinpath(*parts))


def file_order_lock(path: Path) -> ProjectMutationLease:
    """Serialize readers and writers of one file. A different file does not wait."""
    key = str(canonical_root(path))
    with _lock_guard:
        current = _locks.get(key)
        if current is None:
            current = ProjectMutationLease()
            _locks[key] = current
        return current


def edited_original(text: str, edits: list[ExactEdit]) -> tuple[str, int]:
    """All matches refer to the original; reject ambiguous and overlapping ranges."""
    replacements: list[tuple[int, int, str]] = []
    for edit in edits:
        positions, offset = [], 0
        while (index := text.find(edit.old_string, offset)) >= 0:
            positions.append(index)
            offset = index + 1  # also detect self-overlapping old strings
        if not positions or len(positions) != 1 and not edit.replace_all:
            raise HarnessError("Each exact edit must match once, or explicitly use replace_all for every occurrence.", code="edit_match_invalid", status_code=400)
        replacements.extend((index, index + len(edit.old_string), edit.new_string) for index in positions)
    replacements.sort(key=lambda item: item[0])
    if any(left[1] > right[0] for left, right in zip(replacements, replacements[1:])):
        raise HarnessError("The edits overlap in the original file. Combine them into one exact edit.", code="edit_overlap", status_code=400)
    pieces, offset = [], 0
    for start, end, replacement in replacements:
        pieces.extend((text[offset:start], replacement))
        offset = end
    pieces.append(text[offset:])
    return "".join(pieces), len(replacements)


def apply_edits_tool(run, *, cancel_requested=None):
    def apply(file_path: str, edits: list[ExactEdit], base_sha256: str | None = None) -> str:
        if (not run.project_path or "apply_edits" not in run.presented_tools
                or "apply_edits" not in run.enabled_tools or run.work_mode == "plan"):
            raise HarnessError("Structured edits require selected Work-mode project access.", code="tool_not_selected", status_code=403)
        target = project_file(Path(run.project_path), file_path)
        with file_order_lock(file_order_path(Path(run.project_path), file_path)):
            if not target.is_file() or target.stat().st_size > MAX_EDIT_BYTES:
                raise HarnessError(f"Choose an existing UTF-8 text file of at most {MAX_EDIT_BYTES} bytes.", code="edit_file_size", status_code=400)
            original = target.read_bytes()
            try:
                text = original.decode("utf-8")
            except UnicodeDecodeError:
                raise HarnessError("Structured edits require a UTF-8 text file.", code="edit_file_encoding", status_code=400) from None
            if "\x00" in text:
                raise HarnessError("Binary files cannot be edited as text.", code="edit_file_encoding", status_code=400)
            digest = hashlib.sha256(original).hexdigest()
            if base_sha256 is not None and digest != base_sha256:
                raise HarnessError("The original file changed. Inspect a new preview before applying it.", code="edit_base_changed", status_code=409,
                    details={"current_sha256": digest})
            edited, count = edited_original(text, [ExactEdit.model_validate(item) for item in edits])
            content = edited.encode("utf-8")
            if len(content) > MAX_EDIT_BYTES:
                raise HarnessError("The edited file would exceed the structured-edit byte limit.", code="edit_file_size", status_code=400)
            result = {"file_path": file_path, "base_sha256": digest, "result_sha256": hashlib.sha256(content).hexdigest(),
                "replacements": count, "size_bytes": len(content), "status": "preview" if base_sha256 is None else "applied"}
            if base_sha256 is None:
                result["next_action"] = "Supply this base_sha256 with the same edits to apply; the preview made no changes."
                return json.dumps(result, ensure_ascii=False)
            if cancel_requested and cancel_requested():
                raise HarnessError("The edit was cancelled before replacement; the original is unchanged.", code="cancelled", status_code=409)
            temporary = None
            try:
                # Place replacement on the same volume, preserve mode and fsync
                # before a single replace. Every validation precedes mutation.
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".workbench-edit-", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, target.stat().st_mode)
                if project_file(Path(run.project_path), file_path) != target or target.read_bytes() != original:
                    raise HarnessError("The file changed before replacement. No edits were applied.", code="edit_base_changed", status_code=409)
                if cancel_requested and cancel_requested():
                    raise HarnessError("The edit was cancelled before replacement; the original is unchanged.", code="cancelled", status_code=409)
                os.replace(temporary, target)
                temporary = None
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return json.dumps(result, ensure_ascii=False)
    def validated_apply(**arguments):
        try:
            return apply(**arguments)
        except HarnessError as error:
            if error.code != "cancelled":
                raise ToolException(str(error)) from error
            raise
    return StructuredTool.from_function(name="apply_edits", func=validated_apply, args_schema=ApplyEditsInput, handle_tool_error=True,
        description="Preview or apply a group of exact edits against one original UTF-8 project file. Omit base_sha256 to preview; supply the returned hash to atomically apply. Overlapping, unmatched or stale edits change no bytes. Never combine with another mutation of that file in one tool-call batch.")


def validate_delete_target(run, args: dict) -> dict:
    """Validate the complete subtree before native deletion, without implementing it."""
    value = args.get("file_path")
    if not run.project_path or not isinstance(value, str) or not value:
        raise HarnessError("Deletion requires a concrete selected project path.", code="delete_scope", status_code=403)
    normalized = value.replace("\\", "/")
    parts = PurePosixPath(normalized.lstrip("/")).parts
    if (not parts or is_reserved_framework_path(normalized) or any(part in {".", ".."} or ":" in part
            or part.rstrip(" .") != part for part in parts) or normalized.startswith("//")):
        raise HarnessError("Choose a path below the project root, outside retained/knowledge routes.", code="delete_scope", status_code=403)
    root = Path(run.project_path).resolve()
    target = root.joinpath(*parts)
    for candidate in (target, *target.parents):
        if canonical_root(candidate) == canonical_root(root):
            break
        if candidate.is_symlink() or candidate.is_junction():
            raise HarnessError("Deletion cannot traverse a symbolic link or junction.", code="delete_link", status_code=403)
    if not canonical_root(target).is_relative_to(canonical_root(root)) or canonical_root(target) == canonical_root(root):
        raise HarnessError("The project root and host paths cannot be deleted.", code="delete_scope", status_code=403)
    found, files, total_bytes = 0, 0, 0
    pending = [target]
    while pending:
        current = pending.pop()
        found += 1
        if found > MAX_DELETE_ENTRIES:
            raise HarnessError("The deletion subtree exceeds the explicit inspection limit; no deletion started.", code="delete_inspection_limit", status_code=400)
        if current.is_symlink() or current.is_junction():
            raise HarnessError("The deletion subtree contains a symbolic link or junction; no deletion started.", code="delete_link", status_code=403)
        if current.is_dir():
            pending.extend(current.iterdir())
        elif current.is_file():
            files += 1
            total_bytes += current.stat().st_size
        elif current.exists():
            raise HarnessError("The deletion subtree contains an unsupported file kind.", code="delete_kind", status_code=403)
    return {"path": normalized, "before_exists": target.exists(), "before_entries": found if target.exists() else 0,
        "before_files": files, "before_bytes": total_bytes, "expected_absent": True}


def validate_mutation_batch(run, request) -> None:
    """Include structured edits and delete ancestors in the native batch boundary."""
    messages = getattr(getattr(request, "runtime", None), "state", {}).get("messages", [])
    calls = next((getattr(message, "tool_calls", []) for message in reversed(messages)
        if getattr(message, "type", None) == "ai"), [])
    paths = []
    for call in calls:
        name, args = call.get("name"), call.get("args", {})
        if name not in {"write_file", "edit_file", "delete", "apply_edits"} or name == "apply_edits" and args.get("base_sha256") is None:
            continue
        value = args.get("file_path")
        if isinstance(value, str):
            normalized = value.replace("\\", "/").lstrip("/")
            path = canonical_root(Path(run.project_path) / normalized) if run.project_path else None
            if path is not None:
                paths.append((name, path))
    for index, (name, path) in enumerate(paths):
        for other_name, other_path in paths[index + 1:]:
            if path == other_path or name == "delete" and other_path.is_relative_to(path) or other_name == "delete" and path.is_relative_to(other_path):
                raise HarnessError("Competing mutations of the same file or deletion subtree cannot share one tool-call batch. Run dependent changes in later batches.", code="file_mutation_conflict", status_code=400)
