"""Harness middleware: request capture (AGT-002) and tool policy (AGT-005)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import BaseMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from workbench_backend.agents.effective_setup import MEMORY_GAP, RAG_GAP, SKILL_GAP
from workbench_backend.agents.replay import (
    RECONSTRUCTION_NOTE,
    FixtureBank,
    apply_recorded_reconstruction,
)
from workbench_backend.agents.schemas import AgentEvent, AgentRun, ModelRequestCapture
from workbench_backend.agents.tools import FILESYSTEM_TOOL_NAMES, SHELL_TOOL_NAMES, tool_name
from workbench_backend.inference.ids import utc_now
from workbench_backend.knowledge.diagnostics import apply_capture_policy
from workbench_backend.knowledge.schemas import ContextCaptureSettings


class WorkbenchHarnessMiddleware(AgentMiddleware):
    """Record the post-middleware model request and keep enabled tools visible.

    Tool-selection may narrow *presentation* for a call. The enabled catalogue
    on the run is never rewritten here.
    """

    def __init__(
        self,
        run: AgentRun,
        http_sink: list[dict[str, Any]] | None = None,
        settings_provider: Callable[[], ContextCaptureSettings] | None = None,
        *,
        fixture_bank: FixtureBank | None = None,
    ) -> None:
        super().__init__()
        self.run = run
        self.http_sink = http_sink if http_sink is not None else []
        self._settings_provider = settings_provider
        self.fixture_bank = fixture_bank

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        filtered = request.override(tools=self._presented(request.tools))
        before = len(self.http_sink)
        response = handler(filtered)
        self._capture(filtered, _payload_after(self.http_sink, before))
        return response

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        filtered = request.override(tools=self._presented(request.tools))
        before = len(self.http_sink)
        response = await handler(filtered)
        self._capture(filtered, _payload_after(self.http_sink, before))
        return response

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Any],
    ) -> ToolMessage | Any:
        blocked = self._reject_projectless_privileged_tool(request)
        if blocked is not None:
            return blocked
        if self.fixture_bank is None:
            return handler(request)
        return self._replay_tool_call(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> ToolMessage | Any:
        blocked = self._reject_projectless_privileged_tool(request)
        if blocked is not None:
            return blocked
        if self.fixture_bank is None:
            return await handler(request)
        return self._replay_tool_call(request)

    def _reject_projectless_privileged_tool(self, request: ToolCallRequest) -> ToolMessage | None:
        """File and host-shell tools need a project; execute must also be presented."""

        name, _args, call_id = _tool_call_parts(request)
        if name in FILESYSTEM_TOOL_NAMES and not self.run.project_path:
            return ToolMessage(
                content=(
                    "Filesystem tools require a bound project folder. "
                    "This run has no project; the file was not written."
                ),
                name=name,
                tool_call_id=call_id,
                status="error",
            )
        if name in SHELL_TOOL_NAMES and not self.run.project_path:
            return ToolMessage(
                content=(
                    "The host shell requires a bound project folder as cwd. "
                    "This run has no project; the command was not executed."
                ),
                name=name,
                tool_call_id=call_id,
                status="error",
            )
        if name in SHELL_TOOL_NAMES and name not in self.run.presented_tools:
            return ToolMessage(
                content=(
                    "The host shell is not presented on this run. "
                    "The command was not executed."
                ),
                name=name,
                tool_call_id=call_id,
                status="error",
            )
        return None

    def _replay_tool_call(self, request: ToolCallRequest) -> ToolMessage:
        """Replay from fixtures. Never invoke the live tool handler."""

        name, args, call_id = _tool_call_parts(request)
        result = self.fixture_bank.take(name, args) if self.fixture_bank is not None else ""
        reconstructions = apply_recorded_reconstruction(name, args, self.run.project_path)
        now = utc_now()
        for item in reconstructions:
            self.run.events.append(
                AgentEvent(
                    at=now,
                    kind="recorded_reconstruction",
                    detail=item,
                )
            )
        if reconstructions:
            self.run.events.append(
                AgentEvent(
                    at=now,
                    kind="recorded_reconstruction_note",
                    detail={"note": RECONSTRUCTION_NOTE},
                )
            )
        return ToolMessage(
            content=result,
            name=name,
            tool_call_id=call_id,
            status="success",
        )

    def _presented(self, tools: list[Any] | None) -> list[Any]:
        allowed = set(self.run.presented_tools)
        selected: list[Any] = []
        for item in tools or []:
            name = tool_name(item)
            if name is None or name in allowed:
                selected.append(item)
        return selected

    def _capture(self, request: ModelRequest, http_payload: dict[str, Any] | None) -> None:
        setup = self.run.effective_setup
        gaps = list(setup.gaps) if setup is not None else [RAG_GAP]
        if setup is None:
            if not self.run.memory_version_refs:
                gaps.append(MEMORY_GAP)
            if not self.run.skill_version_refs:
                gaps.append(SKILL_GAP)
        if http_payload is None:
            gaps.append("http payload not observed for this model call")
        applied = dict(setup.bags.per_request.applied) if setup is not None else {}
        generation = dict(applied)
        generation.update(request.model_settings or {})
        settings = (
            self._settings_provider()
            if self._settings_provider is not None
            else ContextCaptureSettings()
        )
        captured = apply_capture_policy(
            ModelRequestCapture(
                at=utc_now(),
                instructions=_system_text(request),
                messages=[_message_dict(message) for message in request.messages],
                available_tools=list(self.run.enabled_tools),
                presented_tools=[
                    name
                    for name in (_tool_names(request.tools))
                    if name in self.run.presented_tools
                ],
                generation_settings=generation,
                memory_versions=list(self.run.memory_version_refs),
                skill_versions=list(self.run.skill_version_refs),
                loaded_knowledge=list(setup.loaded_knowledge) if setup is not None else [],
                capture_gaps=gaps,
                http_payload=http_payload,
                selected_profile_id=setup.selected_profile_id if setup is not None else self.run.profile_id,
                applied_per_request=applied,
                startup_mismatches=(
                    [item.model_dump(mode="json") for item in setup.startup_mismatches]
                    if setup is not None
                    else []
                ),
            ),
            settings,
        )
        self.run.model_requests.append(captured)
        self.run.updated_at = utc_now()


def _tool_call_parts(request: ToolCallRequest) -> tuple[str, dict[str, Any], str]:
    call = request.tool_call
    if isinstance(call, dict):
        name = str(call.get("name") or "")
        raw_args = call.get("args")
        call_id = call.get("id")
    else:
        name = str(getattr(call, "name", "") or "")
        raw_args = getattr(call, "args", {})
        call_id = getattr(call, "id", None)
    args = raw_args if isinstance(raw_args, dict) else {}
    return name, args, str(call_id) if call_id is not None else ""


def _payload_after(sink: list[dict[str, Any]], before: int) -> dict[str, Any] | None:
    if len(sink) <= before:
        return None
    return sink[-1]


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
