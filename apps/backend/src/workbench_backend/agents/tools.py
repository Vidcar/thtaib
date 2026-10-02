"""Enabled tool catalogue for the embedded harness (AGT-005).

Visibility tools are application-owned. Filesystem tools are Deep Agents
built-ins, bound to project storage. ``execute`` is the host-shell tool from
``LocalShellBackend`` and is enabled only when a project (cwd) is bound.
Named ``task`` remains selected-helper-only; destructive file extensions and
host operations require explicit selection.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal
from langchain_core.tools import BaseTool, ToolException, tool
from workbench_backend.inference.ids import utc_now
from workbench_backend.agents.schemas import UserQuestion
from workbench_backend.agents.tool_catalogue import model_description

VISIBILITY_TOOL_NAMES = ("echo", "time_now")
FILESYSTEM_TOOL_NAMES = ("ls", "read_file", "write_file", "edit_file", "glob", "grep", "delete", "apply_edits")
# Project discovery stays in a saved selection and is admitted only with a project.
# The definition-loading preference does not make an unpinned read required.
OPTIONAL_PROJECT_READS = frozenset({"ls", "read_file", "glob", "grep"})
KNOWLEDGE_ROUTE_READ_TOOLS = ("ls", "read_file")
SHELL_TOOL_NAMES = ("execute", "execute_skill_script", "start_command", "command_status", "stop_command")
# Presented This-computer commands do not need a project. Their cwd is the
# resolved user profile. Skill scripts and preview stay project-bound.
PROJECT_FREE_HOST_COMMANDS = frozenset({"execute", "start_command", "command_status", "stop_command"})
PLANNING_TOOL_NAMES = ("write_todos",)
INPUT_TOOL_NAMES = ("ask_user",)
MEMORY_TOOL_NAMES = ("propose_memory",)
ATTACHMENT_TOOL_NAMES = ("read_attachment",)
RESULT_TOOL_NAMES = ("read_tool_result",)
RESOURCE_TOOL_NAMES = ("list_connection_resources", "read_connection_resource")
OPT_IN_TOOL_NAMES = frozenset(("echo", *SHELL_TOOL_NAMES, "delete", "apply_edits", *RESOURCE_TOOL_NAMES))
ENABLED_TOOL_NAMES = (*VISIBILITY_TOOL_NAMES, *FILESYSTEM_TOOL_NAMES, *SHELL_TOOL_NAMES, *PLANNING_TOOL_NAMES, *INPUT_TOOL_NAMES, *MEMORY_TOOL_NAMES, *ATTACHMENT_TOOL_NAMES, *RESULT_TOOL_NAMES, *RESOURCE_TOOL_NAMES)


@lru_cache(maxsize=1)
def _optional_visual_tool_groups() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Load owned worker tool names only when catalogue discovery needs them.

    The workers import harness modules, so eager imports here would couple the
    core tool definitions to optional runtime initialization.
    """

    from workbench_backend.browser.service import BROWSER_TOOL_NAMES
    from workbench_backend.preview.service import PREVIEW_TOOL_NAMES
    from workbench_backend.desktop_automation.service import DESKTOP_TOOL_NAMES

    return BROWSER_TOOL_NAMES, PREVIEW_TOOL_NAMES, DESKTOP_TOOL_NAMES


@tool("echo", description=model_description("echo", ""))
def echo_tool(text: str) -> str:
    """Echo the given text back unchanged. Harmless visibility tool."""

    return text


@tool("time_now", description=model_description("time_now", ""))
def time_now_tool() -> str:
    """Return the current UTC time as ISO-8601. Harmless clock tool."""

    return utc_now()


@tool("ask_user", args_schema=UserQuestion, description=model_description("ask_user", ""))
def ask_user_tool(prompt: str, answer_type: Literal["text", "choice", "file", "folder"] = "text", choices: list[str] | None = None) -> str:
    """Ask the user for text, a choice, or an explicitly selected file/folder. Never request credentials. A path answer does not grant tools new access."""
    question = UserQuestion(prompt=prompt, answer_type=answer_type, choices=choices or [])
    if question.answer_type == "choice" and not question.choices:
        return "A choice question requires choices."
    return "This question requires user input."


ENABLED_TOOLS: dict[str, BaseTool] = {
    "echo": echo_tool,
    "time_now": time_now_tool,
    "ask_user": ask_user_tool,
}


def enabled_catalogue() -> list[str]:
    """Product discovery catalogue. Independent of whether a run has a project."""

    browser, preview, desktop = _optional_visual_tool_groups()
    return [*ENABLED_TOOL_NAMES, *browser, *preview, *desktop]


_GROUP_LABELS = {
    "project": "Project files",
    "shell": "This computer",
    "browser": "Browser",
    "windows": "One window",
    "preview": "Preview",
    "diagnostics": "Diagnostics",
    "planning": "Planning",
    "input": "Questions",
    "knowledge": "Knowledge",
    "connections": "Connections",
}
_OPT_IN_GROUPS = frozenset({"browser", "windows", "preview"})


def standard_context_key(*, project_bound: bool, knowledge_routes: bool = False, attachment_available: bool = False, capture_routes: bool = False) -> str:
    return "-".join((
        "project" if project_bound else "projectless",
        "knowledge" if knowledge_routes else "noknowledge",
        "attachments" if attachment_available else "noattachments",
        "capture" if capture_routes else "nocapture",
    ))


def tool_descriptions() -> list[dict[str, object]]:
    from workbench_backend.agents.execution_policy import PLAN_TOOLS
    from workbench_backend.agents.tool_catalogue import TOOL_PRESENTATIONS
    described = []
    for name in enabled_catalogue():
        presentation = TOOL_PRESENTATIONS[name]
        described.append({
            "id": name,
            "name": presentation.label,
            "description": presentation.description,
            "group": presentation.group,
            "prerequisites": list(presentation.prerequisites),
            "opt_in": name in OPT_IN_TOOL_NAMES or presentation.group in _OPT_IN_GROUPS,
            "plan_eligible": name in PLAN_TOOLS,
        })
    return described


def catalogue_projection() -> dict[str, object]:
    """Backend-owned groups, Standard sets and Plan eligibility for one catalogue."""

    from workbench_backend.agents.execution_policy import PLAN_TOOLS
    from workbench_backend.agents.tool_catalogue import TOOL_PRESENTATIONS
    tools = tool_descriptions()
    order = []
    for name in enabled_catalogue():
        group = TOOL_PRESENTATIONS[name].group
        if group not in order:
            order.append(group)
    defaults = {}
    for project_bound in (False, True):
        for knowledge_routes in (False, True):
            for attachment_available in (False, True):
                for capture_routes in (False, True):
                    key = standard_context_key(project_bound=project_bound, knowledge_routes=knowledge_routes,
                        attachment_available=attachment_available, capture_routes=capture_routes)
                    presented, _denied, _files, _shell = resolve_presented_tools(
                        None, project_bound=project_bound, knowledge_routes=knowledge_routes,
                        attachment_available=attachment_available, capture_routes=capture_routes)
                    defaults[key] = presented
    return {
        "enabled": enabled_catalogue(),
        "tools": tools,
        "groups": [{"id": group, "label": _GROUP_LABELS.get(group, group.replace("_", " ").title())} for group in order],
        "defaults": defaults,
        "plan_tools": sorted(PLAN_TOOLS),
        "plan_public_web_remote_names": ["read_web_page", "search_web"],
    }


def enabled_for_project(
    project_bound: bool,
    *,
    knowledge_routes: bool = False,
    capture_routes: bool = False,
    attachment_available: bool = False,
) -> list[str]:
    """Tools enabled for one run.

    Project filesystem and host-shell tools need a project cwd.
    ``ls`` / ``read_file`` may also be enabled for ``/memories/`` and
    ``/skills/`` when official ``memory=`` / ``skills=`` is attached.
    """

    if project_bound:
        return [name for name in ENABLED_TOOL_NAMES if name not in ATTACHMENT_TOOL_NAMES or attachment_available]
    enabled = [*VISIBILITY_TOOL_NAMES, *PLANNING_TOOL_NAMES, *INPUT_TOOL_NAMES, *MEMORY_TOOL_NAMES, *RESULT_TOOL_NAMES, *RESOURCE_TOOL_NAMES]
    if knowledge_routes or capture_routes:
        enabled.extend(KNOWLEDGE_ROUTE_READ_TOOLS)
    if attachment_available:
        enabled.extend(ATTACHMENT_TOOL_NAMES)
    return enabled


def unpinned_project_reads(names, input_policy) -> set[str]:
    """Project reads that stay optional under either definition-loading preference.

    A missing policy keeps the historical strict check. Pinned names stay required.
    Callers still treat skill-required names, mutations and shell as required.
    """

    if input_policy is None:
        return set()
    pinned = set(getattr(input_policy, "pinned_tools", ()) or ())
    return {name for name in names if name in OPTIONAL_PROJECT_READS and name not in pinned}


def resolve_presented_tools(
    requested: list[str] | None,
    *,
    project_bound: bool,
    knowledge_routes: bool = False,
    capture_routes: bool = False,
    external_names: list[str] | None = None,
    attachment_available: bool = False,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return (presented, denied, filesystem_blocked, shell_blocked).

    Denied names are not in the product catalogue. Optional browser, preview,
    and desktop tools are presented only when explicitly requested. Project filesystem names
    requested without a project are ``filesystem_requires_project``.
    ``ls`` / ``read_file`` are allowed without a project only when knowledge
    or retained capture routes are attached. Presented ``execute`` and the
    owned job tools do not need a project. ``execute_skill_script`` and
    project preview without a project are ``shell_requires_project``.
    """

    external = list(dict.fromkeys(external_names or []))
    browser, preview, desktop = _optional_visual_tool_groups()
    optional = set((*browser, *preview, *desktop))
    enabled = [*enabled_for_project(project_bound, knowledge_routes=knowledge_routes,
        capture_routes=capture_routes, attachment_available=attachment_available), *external]
    if requested is None:
        # Project files are a useful default context. Host commands require
        # an explicit per-conversation capability choice from Chat.
        return [name for name in enabled if name not in OPT_IN_TOOL_NAMES], [], [], []
    presented: list[str] = []
    denied: list[str] = []
    filesystem_blocked: list[str] = []
    shell_blocked: list[str] = []
    seen: set[str] = set()
    for name in requested:
        if name in seen:
            continue
        seen.add(name)
        if name in {"search_knowledge", "find_tools", "read_reference", "task"}:
            # Known dynamic tool: harness presents it only for this turn's
            # authorized corpus. An empty selection leaves it idle, as with
            # read_attachment, instead of breaking a saved tool preference.
            continue
        if name not in ENABLED_TOOL_NAMES and name not in optional and name not in external:
            denied.append(name)
        elif name in preview and not project_bound:
            shell_blocked.append(name)
        elif name in optional:
            presented.append(name)
        elif name in FILESYSTEM_TOOL_NAMES and not project_bound:
            if (knowledge_routes or capture_routes) and name in KNOWLEDGE_ROUTE_READ_TOOLS:
                presented.append(name)
            else:
                filesystem_blocked.append(name)
        elif name in SHELL_TOOL_NAMES and not project_bound:
            if name in PROJECT_FREE_HOST_COMMANDS:
                presented.append(name)
            else:
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


def tool_name(tool_obj: object) -> str | None:
    if isinstance(tool_obj, dict):
        name = tool_obj.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool_obj, "name", None)
    return name if isinstance(name, str) else None
