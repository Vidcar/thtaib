"""Harness middleware: request capture (AGT-002) and tool policy (AGT-005)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import BaseMessage

from workbench_backend.agents.schemas import AgentRun, ModelRequestCapture
from workbench_backend.agents.tools import ENABLED_TOOL_NAMES, tool_name
from workbench_backend.inference.ids import utc_now

CAPTURE_GAPS = [
    "no durable memory configured (AGT-004)",
    "no retrieval / RAG (OQ-006 unresolved)",
    "no skill versions bound for this milestone",
]


class WorkbenchHarnessMiddleware(AgentMiddleware):
    """Record the post-middleware model request and keep enabled tools visible.

    Tool-selection may narrow *presentation* for a call. The enabled catalogue
    on the run is never rewritten here.
    """

    def __init__(self, run: AgentRun, http_sink: list[dict[str, Any]] | None = None) -> None:
        super().__init__()
        self.run = run
        self.http_sink = http_sink if http_sink is not None else []

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        filtered = request.override(tools=self._presented(request.tools))
        self._capture(filtered)
        return handler(filtered)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        filtered = request.override(tools=self._presented(request.tools))
        self._capture(filtered)
        return await handler(filtered)

    def _presented(self, tools: list[Any] | None) -> list[Any]:
        allowed = set(self.run.presented_tools)
        selected: list[Any] = []
        for item in tools or []:
            name = tool_name(item)
            if name is None or name in allowed:
                selected.append(item)
        return selected

    def _capture(self, request: ModelRequest) -> None:
        http_payload = self.http_sink[-1] if self.http_sink else None
        gaps = list(CAPTURE_GAPS)
        if http_payload is None:
            gaps.append("http payload not yet observed at wrap_model_call time")
        self.run.model_requests.append(
            ModelRequestCapture(
                at=utc_now(),
                instructions=_system_text(request),
                messages=[_message_dict(message) for message in request.messages],
                available_tools=list(ENABLED_TOOL_NAMES),
                presented_tools=[
                    name
                    for name in (_tool_names(request.tools))
                    if name in self.run.presented_tools
                ],
                generation_settings=dict(request.model_settings or {}),
                capture_gaps=gaps,
                http_payload=http_payload,
            )
        )
        self.run.updated_at = utc_now()


def _system_text(request: ModelRequest) -> str | None:
    if request.system_prompt:
        return request.system_prompt
    message = request.system_message
    if message is None:
        return None
    content = message.content
    if isinstance(content, str):
        return content
    return str(content)


def _tool_names(tools: list[Any] | None) -> list[str]:
    names: list[str] = []
    for item in tools or []:
        name = tool_name(item)
        if name:
            names.append(name)
    return names


def _message_dict(message: BaseMessage | Any) -> dict[str, Any]:
    role = getattr(message, "type", None) or getattr(message, "role", "unknown")
    content = getattr(message, "content", "")
    payload: dict[str, Any] = {"role": str(role), "content": content}
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        payload["tool_calls"] = tool_calls
    return payload
