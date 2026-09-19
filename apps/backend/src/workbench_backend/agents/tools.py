"""Smallest enabled tool set for the embedded harness (AGT-005).

These are harmless visibility tools. Full workers/sandbox stay OQ-003.
Recorded-tool wrappers replay fixtures; they are not live integrations.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, StructuredTool, tool

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


def tools_for_names(
    names: list[str],
    *,
    recorded_fixtures: list[dict[str, Any]] | None = None,
) -> list[BaseTool]:
    selected = [name for name in names if name in ENABLED_TOOLS]
    if not recorded_fixtures:
        return [ENABLED_TOOLS[name] for name in selected]
    bank = _FixtureBank(recorded_fixtures)
    return [_recorded_wrapper(name, bank) for name in selected]


class _FixtureBank:
    def __init__(self, fixtures: list[dict[str, Any]]) -> None:
        self._remaining = [dict(item) for item in fixtures]

    def take(self, name: str) -> str:
        for index, item in enumerate(self._remaining):
            if str(item.get("name")) == name:
                self._remaining.pop(index)
                result = item.get("result")
                return result if isinstance(result, str) else str(result)
        return (
            f"[recorded-tool] no fixture for {name}. "
            "This is not a live tool call and is not proof of a current live integration."
        )


def _recorded_wrapper(name: str, bank: _FixtureBank) -> BaseTool:
    original = ENABLED_TOOLS[name]

    def replay(**_kwargs: Any) -> str:
        return bank.take(name)

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
    )


def tool_name(tool_obj: object) -> str | None:
    if isinstance(tool_obj, dict):
        name = tool_obj.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool_obj, "name", None)
    return name if isinstance(name, str) else None
