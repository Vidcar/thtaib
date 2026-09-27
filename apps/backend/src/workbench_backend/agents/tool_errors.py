"""Expected tool refusals stay within their own native tool-call identity."""

from __future__ import annotations

from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException


def recoverable_tool_error(error: Exception, *, name: str, call_id: str) -> ToolMessage | None:
    """Declared tool errors and read-only decoding failures are correctable.

    MCPAdapter reports a server's declared ``isError`` result as ToolException.
    Persistence failures, cancellation and unknown-side-effect HarnessErrors
    must retain their application-owned failure/recovery path.
    """
    if isinstance(error, UnicodeDecodeError) and name in {"grep", "read_file"}:
        return ToolMessage(
            content=("The file read or search could not decode text. No complete result was returned. "
                     "Try a narrower search or another file read; do not treat this as no matches. "
                     f"Decoder error: {str(error)[:1000]}"),
            name=name, tool_call_id=call_id, status="error",
        )
    if not isinstance(error, ToolException):
        return None
    return ToolMessage(content=str(error) or "The tool could not complete this action.",
        name=name, tool_call_id=call_id, status="error")
