"""Lossless native/external schema projection at the application model boundary."""
from __future__ import annotations

import copy
from typing import Any

from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool, convert_to_openai_function


def model_tool_schema(tool: Any, *, strict: bool | None = None) -> dict[str, Any]:
    if not isinstance(tool, BaseTool):
        if isinstance(tool, dict) and tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            # The official converter treats an already wrapped tool as final,
            # ignoring strict. Apply its function formatter before wrapping.
            return {**copy.deepcopy(tool), "function": convert_to_openai_function(tool["function"], strict=strict)}
        return convert_to_openai_tool(tool, strict=strict)
    if (tool.metadata or {}).get("type") == "custom_tool":
        result = convert_to_openai_tool(tool, strict=strict)
        extras = getattr(tool, "extras", None)
        if isinstance(extras, dict):
            for key in ("defer_loading", "async"):
                if key in extras:
                    result[key] = copy.deepcopy(extras[key])
        return result
    original = tool.tool_call_schema
    if not original:
        return convert_to_openai_tool(tool, strict=strict)
    schema = copy.deepcopy(original if isinstance(original, dict) else original.model_json_schema())
    # These two keys are root schema annotations. Never walk property maps,
    # defaults, constants, enums or examples: their title keys are literal data.
    schema.pop("title", None)
    schema.pop("description", None)
    result = convert_to_openai_tool({"name": tool.name, "description": tool.description,
        "parameters": schema}, strict=strict)
    # Preserve the pinned adapter's supported provider extras after native
    # argument projection; they do not confer application authority.
    extras = getattr(tool, "extras", None)
    if isinstance(extras, dict):
        for key in ("defer_loading", "async"):
            if key in extras:
                result[key] = copy.deepcopy(extras[key])
    return result
