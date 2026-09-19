"""Enabled tool catalogue for the embedded harness (AGT-005).

Visibility tools are application-owned. Filesystem tools are Deep Agents
built-ins, bound to project storage via FilesystemBackend (STATE-002).
``execute`` / ``task`` stay out of the enabled catalogue (OQ-003).
Recorded-tool wrappers replay fixtures by invocation identity; they are not
live integrations and are not proof of live behaviour.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, StructuredTool, tool

from workbench_backend.agents.replay import FixtureBank
from workbench_backend.inference.ids import utc_now

VISIBILITY_TOOL_NAMES = ("echo", "time_now")
FILESYSTEM_TOOL_NAMES = ("ls", "read_file", "write_file", "edit_file", "glob", "grep")
ENABLED_TOOL_NAMES = (*VISIBILITY_TOOL_NAMES, *FILESYSTEM_TOOL_NAMES)


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
        if name in ENABLED_TOOL_NAMES:
            presented.append(name)
        else:
            denied.append(name)
    return presented, denied


def tools_for_names(
    names: list[str],
    *,
    recorded_fixtures: list[dict[str, Any]] | None = None,
    fixture_bank: FixtureBank | None = None,
) -> list[BaseTool]:
    selected = [name for name in names if name in ENABLED_TOOLS]
    bank = fixture_bank
    if bank is None and recorded_fixtures:
        bank = FixtureBank(recorded_fixtures)
    if bank is None:
        return [ENABLED_TOOLS[name] for name in selected]
    return [_recorded_wrapper(name, bank) for name in selected]


def _recorded_wrapper(name: str, bank: FixtureBank) -> BaseTool:
    original = ENABLED_TOOLS[name]

    def replay(**kwargs: Any) -> str:
        return bank.take(name, kwargs)

    replay.__name__ = f"recorded_{name}"
    replay.__doc__ = (
        f"{original.description} Recorded-tool fixture replay; "
        "not a live integration and not proof of live behaviour."
    )
    return StructuredTool.from_function(
        func=replay,
        name=name,
        description=replay.__doc__,
        args_schema=original.args_schema,
        handle_tool_error=False,
    )


def tool_name(tool_obj: object) -> str | None:
    if isinstance(tool_obj, dict):
        name = tool_obj.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool_obj, "name", None)
    return name if isinstance(name, str) else None
