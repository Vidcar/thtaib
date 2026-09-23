"""Enabled tool catalogue for the embedded harness (AGT-005).

Visibility tools are application-owned. Filesystem tools are Deep Agents
built-ins, bound to project storage. ``execute`` is the host-shell tool from
``LocalShellBackend`` and is enabled only when a project (cwd) is bound.
``task`` and ``delete`` stay out of the enabled catalogue.
"""

from __future__ import annotations

from typing import Any, Literal
from langchain_core.tools import BaseTool, ToolException, tool
from workbench_backend.inference.ids import utc_now

VISIBILITY_TOOL_NAMES = ("echo", "time_now")
FILESYSTEM_TOOL_NAMES = ("ls", "read_file", "write_file", "edit_file", "glob", "grep", "rename_file", "delete_file")
KNOWLEDGE_ROUTE_READ_TOOLS = ("ls", "read_file")
SHELL_TOOL_NAMES = ("execute",)
PLANNING_TOOL_NAMES = ("write_todos",)
INPUT_TOOL_NAMES = ("ask_user",)
MEMORY_TOOL_NAMES = ("propose_memory",)
ATTACHMENT_TOOL_NAMES = ("read_attachment",)
ENABLED_TOOL_NAMES = (*VISIBILITY_TOOL_NAMES, *FILESYSTEM_TOOL_NAMES, *SHELL_TOOL_NAMES, *PLANNING_TOOL_NAMES, *INPUT_TOOL_NAMES, *MEMORY_TOOL_NAMES, *ATTACHMENT_TOOL_NAMES)


@tool("echo")
def echo_tool(text: str) -> str:
    """Echo the given text back unchanged. Harmless visibility tool."""

    return text


@tool("time_now")
def time_now_tool() -> str:
    """Return the current UTC time as ISO-8601. Harmless clock tool."""

    return utc_now()


@tool("ask_user")
def ask_user_tool(prompt: str, answer_type: str = "text", choices: list[str] | None = None) -> str:
    """Ask the user for text, a choice, or an explicitly selected file/folder. Never request credentials. A path answer does not grant tools new access."""
    from langgraph.types import interrupt
    from workbench_backend.agents.schemas import UserQuestion
    question = UserQuestion(prompt=prompt, answer_type=answer_type, choices=choices or [])
    if question.answer_type == "choice" and not question.choices:
        return "A choice question requires choices."
    response = interrupt({"kind": "ask_user", "question": question.model_dump(mode="json")})
    if isinstance(response, dict) and response.get("cancelled"):
        return "The user cancelled this question. Do not repeat it unless asked."
    return str(response.get("answer", "")) if isinstance(response, dict) else str(response)


ENABLED_TOOLS: dict[str, BaseTool] = {
    "echo": echo_tool,
    "time_now": time_now_tool,
    "ask_user": ask_user_tool,
}


def enabled_catalogue() -> list[str]:
    """Product discovery catalogue. Independent of whether a run has a project."""

    return list(ENABLED_TOOL_NAMES)


def enabled_for_project(
    project_bound: bool,
    *,
    knowledge_routes: bool = False,
    attachment_available: bool = False,
) -> list[str]:
    """Tools enabled for one run.

    Project filesystem and host-shell tools need a project cwd.
    ``ls`` / ``read_file`` may also be enabled for ``/memories/`` and
    ``/skills/`` when official ``memory=`` / ``skills=`` is attached.
    """

    if project_bound:
        return [name for name in ENABLED_TOOL_NAMES if name not in ATTACHMENT_TOOL_NAMES or attachment_available]
    enabled = [*VISIBILITY_TOOL_NAMES, *PLANNING_TOOL_NAMES, *INPUT_TOOL_NAMES, *MEMORY_TOOL_NAMES]
    if knowledge_routes:
        enabled.extend(KNOWLEDGE_ROUTE_READ_TOOLS)
    if attachment_available:
        enabled.extend(ATTACHMENT_TOOL_NAMES)
    return enabled


def resolve_presented_tools(
    requested: list[str] | None,
    *,
    project_bound: bool,
    knowledge_routes: bool = False,
    external_names: list[str] | None = None,
    attachment_available: bool = False,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return (presented, denied, filesystem_blocked, shell_blocked).

    Denied names are not in the product catalogue. Project filesystem names
    requested without a project are ``filesystem_requires_project``.
    ``ls`` / ``read_file`` are allowed without a project only when knowledge
    routes are attached. ``execute`` without a project is
    ``shell_requires_project``.
    """

    external = list(dict.fromkeys(external_names or []))
    enabled = [*enabled_for_project(project_bound, knowledge_routes=knowledge_routes, attachment_available=attachment_available), *external]
    if requested is None:
        return enabled, [], [], []
    presented: list[str] = []
    denied: list[str] = []
    filesystem_blocked: list[str] = []
    shell_blocked: list[str] = []
    seen: set[str] = set()
    for name in requested:
        if name in seen:
            continue
        seen.add(name)
        if name not in ENABLED_TOOL_NAMES and name not in external:
            denied.append(name)
        elif name in FILESYSTEM_TOOL_NAMES and not project_bound:
            if knowledge_routes and name in KNOWLEDGE_ROUTE_READ_TOOLS:
                presented.append(name)
            else:
                filesystem_blocked.append(name)
        elif name in SHELL_TOOL_NAMES and not project_bound:
            shell_blocked.append(name)
        elif name in ATTACHMENT_TOOL_NAMES and not attachment_available:
            continue
        elif name in enabled:
            presented.append(name)
        else:
            denied.append(name)
    return presented, denied, filesystem_blocked, shell_blocked


def tools_for_names(names: list[str]) -> list[BaseTool]:
    selected = [name for name in names if name in ENABLED_TOOLS]
    return [ENABLED_TOOLS[name] for name in selected]


def memory_proposal_tool(run_id: str, knowledge: Any) -> BaseTool:
    @tool("propose_memory")
    def propose_memory(content: str, scope: Literal["user", "project", "agent"] = "user",
                       scope_id: str | None = None, display_name: str | None = None,
                       entry_id: str | None = None, base_version: str | None = None) -> str:
        """Propose durable memory for review. Pending is not saved. Updating an entry requires its exact base version. Scope IDs must match this run's project or agent setup. Ordinary tool approval cannot permit automatic saving."""
        from workbench_backend.errors import KnowledgeError
        try:
            return knowledge.propose_memory(run_id=run_id, content=content, scope=scope, scope_id=scope_id,
                display_name=display_name, entry_id=entry_id, base_version=base_version).model_dump_json()
        except KnowledgeError as exc:
            raise ToolException(f"{exc.code}: {exc.message}") from exc
    propose_memory.handle_tool_error = True
    return propose_memory


def project_mutation_tools(project_path: str) -> list[BaseTool]:
    from pathlib import Path
    from deepagents.backends import FilesystemBackend
    from workbench_backend.agents.file_changes import project_file
    from workbench_backend.errors import HarnessError
    root = Path(project_path).resolve()
    backend = FilesystemBackend(root_dir=root, virtual_mode=True)

    @tool("rename_file")
    def rename_file(file_path: str, destination: str) -> str:
        """Rename one regular project file to a new, unused project path. The application applies the current Access approval policy. Does not move folders or overwrite an existing destination."""
        try:
            source, target = project_file(root, file_path), project_file(root, destination)
            if not source.is_file():
                raise ToolException("The source file does not exist.")
            if target.exists():
                raise ToolException("The destination already exists; nothing was overwritten.")
            if not target.parent.is_dir():
                raise ToolException("The destination folder does not exist.")
            source.rename(target)
            return f"Renamed {file_path} to {destination}."
        except (HarnessError, OSError) as exc:
            raise ToolException(str(exc)) from exc

    @tool("delete_file")
    def delete_file(file_path: str) -> str:
        """Delete one regular project file under the current Access approval policy. Folder and recursive deletion are unsupported. Complete small UTF-8 preimages can be reviewed and restored."""
        try:
            path = project_file(root, file_path)
            if not path.is_file():
                raise ToolException("The selected file does not exist.")
            result = backend.delete('/' + path.relative_to(root).as_posix())
            if result.error:
                raise ToolException(result.error)
            return f"Deleted {file_path}."
        except (HarnessError, OSError) as exc:
            raise ToolException(str(exc)) from exc

    rename_file.handle_tool_error = True
    delete_file.handle_tool_error = True
    return [rename_file, delete_file]


def tool_name(tool_obj: object) -> str | None:
    if isinstance(tool_obj, dict):
        name = tool_obj.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool_obj, "name", None)
    return name if isinstance(name, str) else None
