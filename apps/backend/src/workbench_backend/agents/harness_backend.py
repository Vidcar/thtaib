"""Deep Agents filesystem / host-shell backend for one harness run (STATE-002).

Live runs attach ``CompositeBackend`` so framework internals stay out of the
user's project. A bound project uses ``LocalShellBackend`` as the default only
when ``execute`` is presented (Windows host shell with approvals). Otherwise
the default is ``FilesystemBackend`` so Deep Agents does not put a live
``execute`` tool on the node. Recorded-tool mode attaches no live project,
host-shell, or retrieval backend; knowledge routes may use scratch so
official ``memory=`` / ``skills=`` can ``download_files`` (LAB-003).
"""

from __future__ import annotations

import base64
import os
import re
import stat
from collections.abc import Callable
from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend, StateBackend
from deepagents.backends.protocol import BackendProtocol, FileData, ReadResult

from workbench_backend.agents.memory_skills import knowledge_routes_selected
from workbench_backend.agents.schemas import AgentRun, ToolMode
from workbench_backend.inference.image_validation import CANNOT_READ_IMAGE, MAX_IMAGE_BYTES, validate_image_bytes
from workbench_backend.paths import WorkbenchPaths

# Deep Agents 0.7.15 FilesystemMiddleware / summarization write these when
# CompositeBackend.artifacts_root is "/". See:
# https://docs.langchain.com/oss/python/deepagents/backends
# and deepagents/middleware/filesystem.py (_large_tool_results_prefix).
# /memories/ and /skills/ are derived STATE-005 files for official
# memory= / skills= (harness scratch, never the project or knowledge\).
RESERVED_FRAMEWORK_PREFIXES = (
    "/large_tool_results/",
    "/conversation_history/",
    "/retrieved/",
    "/memories/",
    "/skills/",
    "/captures/",
)
RETRIEVED_PREFIX = "/retrieved/"
MEMORIES_PREFIX = "/memories/"
SKILLS_PREFIX = "/skills/"
CAPTURES_PREFIX = "/captures/"
HARNESS_SCRATCH_DIRNAME = "harness"
_UNSAFE_THREAD_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_IMAGE_SUFFIX_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
_OTHER_IMAGE_SUFFIXES = {".gif", ".heic", ".heif"}


class _BoundedImageReads:
    """Keep upstream `read_file`, but validate still-image bytes before encoding."""

    def __init__(self, *args, image_inputs_allowed: bool | Callable[[], bool] = False, **kwargs) -> None:
        self.image_inputs_allowed = image_inputs_allowed
        super().__init__(*args, **kwargs)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        mime_type = _IMAGE_SUFFIX_MIME.get(Path(file_path).suffix.lower())
        if mime_type is None:
            if Path(file_path).suffix.lower() in _OTHER_IMAGE_SUFFIXES:
                return ReadResult(error="Only PNG, JPEG, and WebP images are supported in Chat.")
            return super().read(file_path, offset, limit)
        if not _images_allowed(self.image_inputs_allowed):
            return ReadResult(error=CANNOT_READ_IMAGE)
        try:
            resolved = self._resolve_path(file_path)
        except (OSError, RuntimeError, ValueError):
            return ReadResult(error="Image path is unavailable or outside the authorized project.")
        try:
            descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    return ReadResult(error="Image path is not a regular file.")
                raw = handle.read(MAX_IMAGE_BYTES + 1)
            validate_image_bytes(raw, mime_type)
        except ValueError as exc:
            return ReadResult(error=f"Cannot read image '{file_path}': {exc}")
        except (OSError, RuntimeError):
            return ReadResult(error=f"Cannot read image '{file_path}': file unavailable.")
        return ReadResult(file_data=FileData(content=base64.b64encode(raw).decode("ascii"), encoding="base64"))


class BoundedImageFilesystemBackend(_BoundedImageReads, FilesystemBackend):
    """Project file backend with bounded, verified image reads."""


class BoundedImageLocalShellBackend(_BoundedImageReads, LocalShellBackend):
    """Host-shell backend with the same image-read policy."""


def sanitize_thread_id(thread_id: str) -> str:
    cleaned = _UNSAFE_THREAD_CHARS.sub("_", thread_id).strip("._")
    return (cleaned or "unnamed")[:120]


def is_reserved_framework_path(virtual_path: str) -> bool:
    """True when a virtual tool path is a Deep Agents internal prefix."""

    normalized = virtual_path if virtual_path.startswith("/") else f"/{virtual_path.lstrip('/')}"
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in RESERVED_FRAMEWORK_PREFIXES
    )


def harness_scratch_root(paths: WorkbenchPaths, thread_id: str) -> Path:
    """Per-thread scratch under the product data root, not the project."""

    return paths.state / HARNESS_SCRATCH_DIRNAME / sanitize_thread_id(thread_id)


def _images_allowed(flag: bool | Callable[[], bool]) -> bool:
    return bool(flag()) if callable(flag) else bool(flag)


def build_run_backend(
    run: AgentRun,
    paths: WorkbenchPaths,
    *,
    prepare_storage: bool = True,
    image_inputs_allowed: bool | Callable[[], bool] = False,
    capture_backend: BackendProtocol | None = None,
) -> BackendProtocol | None:
    """Attach a CompositeBackend, or none for recorded-tool without knowledge.

    Default backend is the bound project (virtual ``/``) when one exists,
    otherwise ``StateBackend`` so a file write cannot land in a surprise
    directory. The project default is ``LocalShellBackend`` only when
    ``execute`` is presented; otherwise ``FilesystemBackend``. Reserved
    prefixes including ``/retrieved/``, ``/memories/`` and ``/skills/``
    always route to product-data scratch. Recorded-tool still attaches no
    live project, host-shell, or retrieval backend; knowledge routes may
    use scratch so official ``memory=`` / ``skills=`` can ``download_files``.
    """

    knowledge_routes = knowledge_routes_selected(
        run.memory_version_refs,
        run.skill_version_refs,
    )
    if run.tool_mode is ToolMode.recorded_tool:
        capture_backend = None
    if run.tool_mode is ToolMode.recorded_tool and not knowledge_routes:
        return None
    scratch = harness_scratch_root(paths, run.id if run.parent_run_id else run.thread_id or run.id)
    large = scratch / "large_tool_results"
    history = scratch / "conversation_history"
    retrieved = scratch / "retrieved"
    memories = scratch / "memories"
    skills = scratch / "skills"
    if prepare_storage:
        for directory in (large, history, retrieved, memories, skills):
            directory.mkdir(parents=True, exist_ok=True)
    routes: dict[str, BackendProtocol] = {
        "/large_tool_results/": FilesystemBackend(root_dir=large, virtual_mode=True),
        "/conversation_history/": FilesystemBackend(root_dir=history, virtual_mode=True),
        RETRIEVED_PREFIX: FilesystemBackend(root_dir=retrieved, virtual_mode=True),
        MEMORIES_PREFIX: FilesystemBackend(root_dir=memories, virtual_mode=True),
        SKILLS_PREFIX: FilesystemBackend(root_dir=skills, virtual_mode=True),
    }
    if capture_backend is not None:
        routes[CAPTURES_PREFIX] = capture_backend
    default: BackendProtocol
    if run.tool_mode is ToolMode.recorded_tool:
        default = StateBackend()
    elif host_shell_requested(run):
        # Host shell cwd is the user-chosen project. inherit_env so PATH and
        # the Windows host environment are the real machine, not an empty env.
        # virtual_mode does not restrict execute() (LocalShellBackend docs).
        default = BoundedImageLocalShellBackend(
            root_dir=run.project_path,
            virtual_mode=True,
            inherit_env=True,
            image_inputs_allowed=image_inputs_allowed,
        )
    elif run.project_path:
        default = BoundedImageFilesystemBackend(root_dir=run.project_path, virtual_mode=True,
            image_inputs_allowed=image_inputs_allowed)
    else:
        default = StateBackend()
    return CompositeBackend(default=default, routes=routes, artifacts_root="/")


def host_shell_requested(run: AgentRun) -> bool:
    """True when this run may attach LocalShellBackend and interrupt_on.

    Deep Agents registers ``execute`` on any sandbox default. The host shell
    is therefore attached only when the user-visible catalogue presents it.
    """

    if run.tool_mode is ToolMode.recorded_tool:
        return False
    if not run.project_path:
        return False
    return "execute" in run.presented_tools
