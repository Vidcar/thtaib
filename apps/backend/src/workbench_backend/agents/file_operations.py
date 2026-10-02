"""Selected project mutation extensions; native file tools keep their ownership."""
from __future__ import annotations

import asyncio
from collections import deque
from contextlib import asynccontextmanager, contextmanager
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
    __slots__ = ("signal", "exclusive", "admitted")

    def __init__(self, signal, exclusive: bool) -> None:
        self.signal = signal
        self.exclusive = exclusive
        self.admitted = False


class ProjectMutationLease:
    """Per-path gate. Async waiters park on a Future and do not occupy a worker.

    Shared holders, used for ancestor directories, do not block each other.
    An exclusive holder blocks both. A synchronous caller takes the lease or
    fails. It does not block a pool thread. Release admits the next future
    and leaves the gate held, so cancelling one waiter cannot admit two.
    """

    def __init__(self) -> None:
        self._mutex = threading.Lock()
        self._exclusive = False
        self._shared = 0
        self._waiters: deque[_MutationWaiter] = deque()

    def waiting(self) -> int:
        with self._mutex:
            return len(self._waiters)

    def _busy_for(self, exclusive: bool) -> bool:
        if self._exclusive:
            return True
        return exclusive and self._shared > 0

    def acquire(self, *, exclusive: bool = True) -> bool:
        with self._mutex:
            if self._waiters or self._busy_for(exclusive):
                return False
            if exclusive:
                self._exclusive = True
            else:
                self._shared += 1
            return True

    async def acquire_async(self, *, exclusive: bool = True) -> None:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        waiter = _MutationWaiter(future, exclusive)
        with self._mutex:
            if not self._waiters and not self._busy_for(exclusive):
                if exclusive:
                    self._exclusive = True
                else:
                    self._shared += 1
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
                self.release(exclusive=waiter.exclusive)
            raise

    def release(self, *, exclusive: bool = True) -> None:
        with self._mutex:
            if exclusive:
                if not self._exclusive:
                    raise RuntimeError("project mutation lease released while free")
                self._exclusive = False
            else:
                if self._shared <= 0:
                    raise RuntimeError("project mutation lease released while free")
                self._shared -= 1
                if self._shared:
                    return
            self._handoff_locked()

    def _handoff_locked(self) -> None:
        while self._waiters:
            waiter = self._waiters[0]
            future = waiter.signal
            if future.cancelled() or future.done():
                self._waiters.popleft()
                continue
            if self._busy_for(waiter.exclusive):
                return
            self._waiters.popleft()
            waiter.admitted = True
            if waiter.exclusive:
                self._exclusive = True
            else:
                self._shared += 1
            future.get_loop().call_soon_threadsafe(self._resolve_future, future)
            if waiter.exclusive:
                return

    @staticmethod
    def _resolve_future(future) -> None:
        if not future.done():
            future.set_result(True)


class ExactEdit(BaseModel):
    old_string: str = Field(min_length=1, description="Exact text in the original file; every edit is matched against that same original.")
    new_string: str
    replace_all: bool = False


class ApplyEditsInput(BaseModel):
    file_path: str = Field(min_length=1, description="Project-relative regular UTF-8 file; framework/host paths and links are refused.")
    edits: Annotated[list[ExactEdit], Field(min_length=1, max_length=64)]
    base_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$", description="Omit for a read-only preview and original hash. Supply that unchanged original-byte hash to apply atomically.")


def file_order_path(project: Path, file_path: str):
    """Canonical key for one project-relative file. `.` collapses; `..` is refused."""
    normalized = str(file_path).replace("\\", "/").strip()
    if not normalized or normalized.startswith("//"):
        raise ValueError("File order needs one project-relative path.")
    parts = []
    for part in PurePosixPath(normalized).parts:
        if part in {"/", "."}:
            continue
        if part == ".." or ":" in part or part != part.strip():
            raise ValueError("File order needs one project-relative path.")
        parts.append(part)
    root = Path(project).resolve()
    # `/` and a collapsed `.` are the project root. Deletion still refuses it.
    if not parts:
        return canonical_root(root)
    return canonical_root(root.joinpath(*parts))


def file_order_lock(path: Path) -> ProjectMutationLease:
    """Serialize readers and writers of one file. A different file does not wait."""
    key = str(canonical_root(path))
    with _lock_guard:
        current = _locks.get(key)
        if current is None:
            current = ProjectMutationLease()
            _locks[key] = current
        return current


_BUSY = "This file is already being changed. Retry after that change finishes."


def _order_chain(path: Path) -> list[tuple[ProjectMutationLease, bool]]:
    """Shared ancestor locks, then an exclusive leaf. High to low avoids deadlock."""
    canonical = canonical_root(path)
    chain = [(file_order_lock(parent), False) for parent in reversed(canonical.parents)]
    chain.append((file_order_lock(canonical), True))
    return chain


def paths_overlap(left: Path, right: Path) -> bool:
    first, second = canonical_root(left), canonical_root(right)
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


@contextmanager
def hold_file_order(path: Path):
    """Hold the ancestor chain. A nested call on the same leaf borrows it."""
    leaf = file_order_lock(path)
    if ADMITTED_PROJECT_MUTATION.get() is leaf:
        yield leaf
        return
    held: list[tuple[ProjectMutationLease, bool]] = []
    try:
        for lease, exclusive in _order_chain(path):
            if not lease.acquire(exclusive=exclusive):
                raise ToolException(_BUSY)
            held.append((lease, exclusive))
        token = ADMITTED_PROJECT_MUTATION.set(leaf)
        try:
            yield leaf
        finally:
            ADMITTED_PROJECT_MUTATION.reset(token)
    finally:
        for lease, exclusive in reversed(held):
            lease.release(exclusive=exclusive)


@asynccontextmanager
async def ahold_file_order(path: Path):
    """Async chain. Waiters park on a future and do not occupy a worker."""
    leaf = file_order_lock(path)
    if ADMITTED_PROJECT_MUTATION.get() is leaf:
        yield leaf
        return
    held: list[tuple[ProjectMutationLease, bool]] = []
    try:
        for lease, exclusive in _order_chain(path):
            await lease.acquire_async(exclusive=exclusive)
            held.append((lease, exclusive))
        token = ADMITTED_PROJECT_MUTATION.set(leaf)
        try:
            yield leaf
        finally:
            ADMITTED_PROJECT_MUTATION.reset(token)
    finally:
        for lease, exclusive in reversed(held):
            lease.release(exclusive=exclusive)


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
        with hold_file_order(file_order_path(Path(run.project_path), file_path)):
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
        description="Preview or apply a group of exact edits against one original UTF-8 project file. Omit base_sha256 to preview; supply the returned hash to atomically apply. Overlapping, unmatched or stale edits change no bytes.")


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
