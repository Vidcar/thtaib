"""Deep Agents filesystem / host-shell backend for one harness run (STATE-002).

Live runs attach ``CompositeBackend`` so framework internals stay out of the
user's project. A bound project uses ``LocalShellBackend`` as the default
(Windows host shell with approvals). Recorded-tool mode attaches nothing
(LAB-003 / Issue #67).
"""

from __future__ import annotations

import re
from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend, StateBackend
from deepagents.backends.protocol import BackendProtocol

from workbench_backend.agents.schemas import AgentRun, ToolMode
from workbench_backend.paths import WorkbenchPaths

# Deep Agents 0.7.15 FilesystemMiddleware / summarization write these when
# CompositeBackend.artifacts_root is "/". See:
# https://docs.langchain.com/oss/python/deepagents/backends
# and deepagents/middleware/filesystem.py (_large_tool_results_prefix).
RESERVED_FRAMEWORK_PREFIXES = ("/large_tool_results/", "/conversation_history/")
HARNESS_SCRATCH_DIRNAME = "harness"
_UNSAFE_THREAD_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


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


def build_run_backend(run: AgentRun, paths: WorkbenchPaths) -> BackendProtocol | None:
    """Attach a live CompositeBackend, or none for recorded-tool replay.

    Default backend is the bound project (virtual ``/``) when one exists,
    otherwise ``StateBackend`` so a file write cannot land in a surprise
    directory. Reserved prefixes always route to product-data scratch.
    """

    if run.tool_mode is ToolMode.recorded_tool:
        return None
    scratch = harness_scratch_root(paths, run.thread_id or run.id)
    large = scratch / "large_tool_results"
    history = scratch / "conversation_history"
    large.mkdir(parents=True, exist_ok=True)
    history.mkdir(parents=True, exist_ok=True)
    routes: dict[str, BackendProtocol] = {
        "/large_tool_results/": FilesystemBackend(root_dir=large, virtual_mode=True),
        "/conversation_history/": FilesystemBackend(root_dir=history, virtual_mode=True),
    }
    default: BackendProtocol
    if run.project_path:
        # Host shell cwd is the user-chosen project. inherit_env so PATH and
        # the Windows host environment are the real machine, not an empty env.
        # virtual_mode does not restrict execute() (LocalShellBackend docs).
        default = LocalShellBackend(
            root_dir=run.project_path,
            virtual_mode=True,
            inherit_env=True,
        )
    else:
        default = StateBackend()
    return CompositeBackend(default=default, routes=routes, artifacts_root="/")
