"""Smallest enabled tool set for the embedded harness (AGT-005).

These are harmless visibility tools. Full workers/sandbox stay OQ-003.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from workbench_backend.inference.ids import utc_now

ENABLED_TOOL_NAMES = ("echo", "time_now")


@tool("echo")
def echo_tool(text: str) -> str:
    """Echo the given text back unchanged. Harmless visibility tool."""

    return text


@tool("time_now")
def time_now_tool() -> str:
    """Return the current UTC time as ISO-8601. Harmless clock tool."""

    return utc_now()


ENABLED_TOOLS: dict[str, BaseTool] = {
    "echo": echo_tool,
    "time_now": time_now_tool,
}


def enabled_catalogue() -> list[str]:
    return list(ENABLED_TOOL_NAMES)


def resolve_presented_tools(requested: list[str] | None) -> tuple[list[str], list[str]]:
    """Return (presented, denied). Denied names are not in the enabled catalogue."""

    if requested is None:
        return list(ENABLED_TOOL_NAMES), []
    presented: list[str] = []
    denied: list[str] = []
    seen: set[str] = set()
    for name in requested:
        if name in seen:
            continue
        seen.add(name)
        if name in ENABLED_TOOLS:
            presented.append(name)
        else:
            denied.append(name)
    return presented, denied


def tools_for_names(names: list[str]) -> list[BaseTool]:
    return [ENABLED_TOOLS[name] for name in names if name in ENABLED_TOOLS]


def tool_name(tool_obj: object) -> str | None:
    if isinstance(tool_obj, dict):
        name = tool_obj.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool_obj, "name", None)
    return name if isinstance(name, str) else None
