"""Expected tool refusals stay within their own native tool-call identity."""

from __future__ import annotations

from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException


def recoverable_tool_error(error: Exception, *, name: str, call_id: str) -> ToolMessage | None:
    """Only explicit tool errors are correctable; never absorb runtime failures.

    MCPAdapter reports a server's declared ``isError`` result as ToolException.
    Persistence failures, cancellation and unknown-side-effect HarnessErrors
    must retain their application-owned failure/recovery path.
    """
    if not isinstance(error, ToolException):
        return None
    return ToolMessage(content=str(error) or "The tool could not complete this action.",
        name=name, tool_call_id=call_id, status="error")
