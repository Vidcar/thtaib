"""Enabled tool catalogue for the embedded harness (AGT-005).

Visibility tools are application-owned. Filesystem tools are Deep Agents
built-ins, bound to project storage. ``execute`` is the host-shell tool from
``LocalShellBackend`` and is enabled only when a project (cwd) is bound.
``task`` and ``delete`` stay out of the enabled catalogue.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal
from langchain_core.tools import BaseTool, ToolException, tool
from workbench_backend.inference.ids import utc_now

VISIBILITY_TOOL_NAMES = ("echo", "time_now")
FILESYSTEM_TOOL_NAMES = ("ls", "read_file", "write_file", "edit_file", "glob", "grep")
KNOWLEDGE_ROUTE_READ_TOOLS = ("ls", "read_file")
SHELL_TOOL_NAMES = ("execute",)
PLANNING_TOOL_NAMES = ("write_todos",)
INPUT_TOOL_NAMES = ("ask_user",)
MEMORY_TOOL_NAMES = ("propose_memory",)
ATTACHMENT_TOOL_NAMES = ("read_attachment",)
ENABLED_TOOL_NAMES = (*VISIBILITY_TOOL_NAMES, *FILESYSTEM_TOOL_NAMES, *SHELL_TOOL_NAMES, *PLANNING_TOOL_NAMES, *INPUT_TOOL_NAMES, *MEMORY_TOOL_NAMES, *ATTACHMENT_TOOL_NAMES)


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
    from workbench_backend.agents.schemas import UserQuestion
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


def tool_descriptions() -> list[dict[str, str]]:
    descriptions = {
        "echo": ("Echo", "Return supplied text unchanged for a connection check."),
        "time_now": ("Current time", "Read the current time."),
        "ls": ("List files", "List files in the authorized project or selected knowledge."),
        "read_file": ("Read files", "Read authorized text files with line ranges and supported images with a verified vision setup."),
        "write_file": ("Create files", "Write a project file; Access determines approval."),
        "edit_file": ("Edit files", "Replace matching text in an authorized project file."),
        "glob": ("Find files", "Find file paths matching a pattern."),
        "grep": ("Search files", "Find matching text inside authorized files."),
        "execute": ("Run commands", "Execute a command on this computer in the bound project folder."),
        "write_todos": ("Checklist", "Maintain the visible task checklist."),
        "ask_user": ("Ask questions", "Pause for your answer to a task question."),
        "propose_memory": ("Suggest memory", "Propose a durable memory change for separate review."),
        "read_attachment": ("Read attachments", "Read the retained files attached to this conversation."),
        "browser_navigate": ("Open page", "Navigate the isolated test browser to a URL."),
        "browser_navigate_back": ("Go back", "Go back in the isolated test browser."),
        "browser_tabs": ("Browser tabs", "List, create, close, or select test browser tabs."),
        "browser_snapshot": ("Page structure", "Inspect a page's accessibility snapshot."),
        "browser_find": ("Find on page", "Find an element in the current page."),
        "browser_click": ("Click on page", "Click an element in the test browser."),
        "browser_hover": ("Hover on page", "Hover over an element in the test browser."),
        "browser_press_key": ("Press browser key", "Send a key to the test browser."),
        "browser_type": ("Type on page", "Type into the test browser."),
        "browser_select_option": ("Select page option", "Choose an option in a page control."),
        "browser_fill_form": ("Fill page form", "Fill controls in a page form."),
        "browser_resize": ("Resize browser", "Set the test browser viewport size."),
        "browser_console_messages": ("Page console", "Inspect page console messages."),
        "browser_network_requests": ("Page requests", "Inspect requests made by the page."),
        "browser_take_screenshot": ("Page screenshot", "Save a screenshot from the test browser."),
        "browser_wait_for": ("Wait for page", "Wait for a page element or condition."),
        "browser_handle_dialog": ("Handle page dialog", "Respond to a page dialog."),
        "start_preview": ("Start project preview", "Start an owned local server for the bound project."),
        "stop_preview": ("Stop project preview", "Stop the owned local project server."),
        "preview_status": ("Project preview status", "Read the preview state, localhost health and recent bounded server log."),
        "desktop_list_windows": ("List windows", "List windows allowed by this conversation's desktop access."),
        "desktop_inspect": ("Inspect window", "Inspect accessible controls in the selected window."),
        "desktop_search": ("Find window control", "Find an accessible control in the selected window."),
        "desktop_wait": ("Wait for window", "Wait for a window or control state."),
        "desktop_invoke": ("Invoke window control", "Invoke an accessible control in the selected window."),
        "desktop_set_value": ("Set window value", "Set the value of an accessible control."),
        "desktop_send_keys": ("Send window keys", "Send keys to the selected window."),
        "desktop_screenshot": ("Window screenshot", "Save a screenshot of an authorized window or element."),
    }
    return [{"id": name, "name": descriptions[name][0], "description": descriptions[name][1]} for name in enabled_catalogue()]


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
    enabled = [*VISIBILITY_TOOL_NAMES, *PLANNING_TOOL_NAMES, *INPUT_TOOL_NAMES, *MEMORY_TOOL_NAMES]
    if knowledge_routes or capture_routes:
        enabled.extend(KNOWLEDGE_ROUTE_READ_TOOLS)
    if attachment_available:
        enabled.extend(ATTACHMENT_TOOL_NAMES)
    return enabled


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
    or retained capture routes are attached. ``execute`` without a project is
    ``shell_requires_project``. Project preview uses the same project requirement.
    """

    external = list(dict.fromkeys(external_names or []))
    browser, preview, desktop = _optional_visual_tool_groups()
    optional = set((*browser, *preview, *desktop))
    enabled = [*enabled_for_project(project_bound, knowledge_routes=knowledge_routes,
        capture_routes=capture_routes, attachment_available=attachment_available), *external]
    if requested is None:
        # Project files are a useful default context. Host commands require
        # an explicit per-conversation capability choice from Chat.
        return [name for name in enabled if name not in SHELL_TOOL_NAMES], [], [], []
    presented: list[str] = []
    denied: list[str] = []
    filesystem_blocked: list[str] = []
    shell_blocked: list[str] = []
    seen: set[str] = set()
    for name in requested:
        if name in seen:
            continue
        seen.add(name)
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
