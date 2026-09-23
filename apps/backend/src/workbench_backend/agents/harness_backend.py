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

import re
from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend, StateBackend
from deepagents.backends.protocol import BackendProtocol

from workbench_backend.agents.memory_skills import knowledge_routes_selected
from workbench_backend.agents.schemas import AgentRun, ToolMode
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
)
RETRIEVED_PREFIX = "/retrieved/"
MEMORIES_PREFIX = "/memories/"
SKILLS_PREFIX = "/skills/"
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


def build_run_backend(run: AgentRun, paths: WorkbenchPaths, *, prepare_storage: bool = True) -> BackendProtocol | None:
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
    default: BackendProtocol
    if run.tool_mode is ToolMode.recorded_tool:
        default = StateBackend()
    elif host_shell_requested(run):
        # Host shell cwd is the user-chosen project. inherit_env so PATH and
        # the Windows host environment are the real machine, not an empty env.
        # virtual_mode does not restrict execute() (LocalShellBackend docs).
        default = LocalShellBackend(
            root_dir=run.project_path,
            virtual_mode=True,
            inherit_env=True,
        )
    elif run.project_path:
        default = FilesystemBackend(root_dir=run.project_path, virtual_mode=True)
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
