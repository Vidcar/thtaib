"""Harness middleware: request capture (AGT-002) and tool policy (AGT-005)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
import time

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import BaseMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from workbench_backend.agents.effective_setup import MEMORY_GAP, RAG_GAP, SKILL_GAP
from workbench_backend.agents.context import observe_payload, require_context_fit
from workbench_backend.agents.harness_backend import is_reserved_framework_path
from workbench_backend.agents.memory_skills import (
    is_knowledge_route_path,
    is_memory_route_path,
    knowledge_routes_selected,
)
from workbench_backend.agents.replay import (
    RECONSTRUCTION_NOTE,
    FixtureBank,
    apply_recorded_reconstruction,
)
from workbench_backend.agents.schemas import AgentEvent, AgentRun, ModelRequestCapture, GenerationObservation
from workbench_backend.agents.tools import (
    FILESYSTEM_TOOL_NAMES,
    KNOWLEDGE_ROUTE_READ_TOOLS,
    SHELL_TOOL_NAMES,
    tool_name,
)
from workbench_backend.inference.ids import utc_now
from workbench_backend.knowledge.diagnostics import apply_capture_policy
from workbench_backend.knowledge.schemas import ContextCaptureSettings
from workbench_backend.agents.execution_policy import ExecutionControl, PLAN_TOOLS, CURRENT_TOOL_CALL
from workbench_backend.state.preferences import tool_authorization_metadata


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
        execution_control: ExecutionControl | None = None,
    ) -> None:
        super().__init__()
        self.run = run
        self.http_sink = http_sink if http_sink is not None else []
        self._settings_provider = settings_provider
        self.fixture_bank = fixture_bank
        self.execution_control = execution_control or ExecutionControl(run)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        self._require_dispatch_allowed()
        filtered = request.override(tools=self._presented(request.tools))
        self._observe_context(filtered)
        self.run.generation_observation = None
        before = len(self.http_sink)
        started = time.perf_counter()
        try:
            response = handler(filtered)
        except Exception as exc:
            self._safe_capture(
                filtered,
                _payload_after(self.http_sink, before),
                http_payloads=_payloads_after(self.http_sink, before),
                handler_returned=False,
                failure=exc,
            )
            raise
        self._safe_capture(
            filtered,
            _payload_after(self.http_sink, before),
            http_payloads=_payloads_after(self.http_sink, before),
            handler_returned=True,
        )
        self._observe_generation(response, time.perf_counter() - started)
        return response

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        async with self.execution_control.model_lock(self.run.deployment_id):
            return await self._awrap_model_call(request, handler)

    async def _awrap_model_call(self, request, handler):
        self._require_dispatch_allowed()
        filtered = request.override(tools=self._presented(request.tools))
        self._observe_context(filtered)
        self.run.generation_observation = None
        before = len(self.http_sink)
        started = time.perf_counter()
        try:
            response = await handler(filtered)
        except Exception as exc:
            self._safe_capture(
                filtered,
                _payload_after(self.http_sink, before),
                http_payloads=_payloads_after(self.http_sink, before),
                handler_returned=False,
                failure=exc,
            )
            raise
        self._safe_capture(
            filtered,
            _payload_after(self.http_sink, before),
            http_payloads=_payloads_after(self.http_sink, before),
            handler_returned=True,
        )
        self._observe_generation(response, time.perf_counter() - started)
        return response

    def _observe_generation(self, response: ModelResponse, elapsed: float) -> None:
        native = getattr(self.run, "generation_observation", None)
        if native is not None and native.basis == "llama_cpp_timings":
            return
        usages = [getattr(message, "usage_metadata", None) for message in response.result]
        reported = [usage.get("output_tokens") for usage in usages if isinstance(usage, dict)]
        tokens = sum(reported) if reported and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in reported) else None
        inputs = [usage.get("input_tokens") for usage in usages if isinstance(usage, dict)]
        input_tokens = sum(inputs) if inputs and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in inputs) else None
        context = getattr(self.run, "context_observation", None)
        limit = context.capacity_tokens if context is not None else None
        self.run.generation_observation = GenerationObservation(output_tokens=tokens,
            input_tokens=input_tokens, context_limit=limit if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0 else None,
            context_used_tokens=input_tokens + tokens if input_tokens is not None and tokens is not None else None,
            elapsed_seconds=elapsed, tokens_per_second=tokens / elapsed if tokens is not None and elapsed > 0 else None,
            measured_at=utc_now())

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Any],
    ) -> ToolMessage | Any:
        self._require_dispatch_allowed()
        blocked = self._reject_projectless_privileged_tool(request)
        if blocked is not None:
            return blocked
        with self.execution_control.tool_dispatch(self.run, _tool_call_parts(request)[2]):
            return self._authorization_result(self._wrap_tool_call(request, handler))

    def _authorization_result(self, result):
        if isinstance(result, ToolMessage):
            # Tools cannot supply their own authority evidence. Only the grant
            # captured by the permission gate may name a saved exception.
            additional = {key: value for key, value in result.additional_kwargs.items()
                if key not in {"authorization_source", "authorization_grant"}}
            return result.model_copy(update={"additional_kwargs": {**additional,
                **tool_authorization_metadata(self.run, result.tool_call_id)}})
        return result

    def _wrap_tool_call(self, request, handler):
        if self.fixture_bank is None:
            name, _, call_id = _tool_call_parts(request)
            if name == "task":
                token = CURRENT_TOOL_CALL.set(call_id)
                try:
                    return handler(request)
                finally:
                    CURRENT_TOOL_CALL.reset(token)
            return handler(request)
        return self._replay_tool_call(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> ToolMessage | Any:
        self._require_dispatch_allowed()
        blocked = self._reject_projectless_privileged_tool(request)
        if blocked is not None:
            return blocked
        with self.execution_control.tool_dispatch(self.run, _tool_call_parts(request)[2]):
            return self._authorization_result(await self._awrap_tool_call(request, handler))

    async def _awrap_tool_call(self, request, handler):
        if self.fixture_bank is None:
            name, _, call_id = _tool_call_parts(request)
            async def invoke() -> Any:
                if name == "task":
                    token = CURRENT_TOOL_CALL.set(call_id)
                    try:
                        return await handler(request)
                    finally:
                        CURRENT_TOOL_CALL.reset(token)
                return await handler(request)
            if name in {*FILESYSTEM_TOOL_NAMES, *SHELL_TOOL_NAMES}:
                # These upstream async backends run synchronous local work in
                # an executor. Cancelling the await cannot stop that work.
                # Retain ownership until it settles before confirming a stop.
                execution = asyncio.create_task(invoke())
                try:
                    return await asyncio.shield(execution)
                except asyncio.CancelledError:
                    try:
                        await execution
                    finally:
                        raise
            return await invoke()
        return self._replay_tool_call(request)

    def _require_dispatch_allowed(self) -> None:
        self.execution_control.require_dispatch(self.run)
        if self.run.status in {"cancel_requested", "cancelled"}:
            from workbench_backend.errors import HarnessError
            raise HarnessError("This run is stopping; no further model or tool call was dispatched.", code="run_cancelling", status_code=409)

    def _reject_projectless_privileged_tool(self, request: ToolCallRequest) -> ToolMessage | None:
        """File and host-shell tools need a project; execute must also be presented.

        When ``memory=`` / ``skills=`` is attached, ``ls`` / ``read_file`` may
        target knowledge routes, and ``edit_file`` / ``write_file`` may target
        ``/memories/**`` scratch only. Those edits are not STATE-005 versions.
        """

        name, args, call_id = _tool_call_parts(request)
        if self.run.work_mode == "plan" and name not in PLAN_TOOLS:
            return ToolMessage(content="Plan mode is read-only. This action was not executed. Switch to Work before requesting changes.", name=name, tool_call_id=call_id, status="error")
        if not self.run.presented_tools:
            return ToolMessage(content="Tools are explicitly off for this run; no action was executed.", name=name, tool_call_id=call_id, status="error")
        if name == "read_file" and self.run.framework_read_paths:
            path = str(args.get("file_path", "")).replace("\\", "/")
            parts = path.split("/")
            allowed = not path.startswith("//") and not any(part in {".", ".."} or ":" in part for part in parts)
            if allowed and any(path.startswith(prefix) and len(path) > len(prefix) for prefix in self.run.framework_read_paths):
                return None
            return ToolMessage(content="This reader can only open framework-saved tool results or conversation history, not project or knowledge files.", name=name, tool_call_id=call_id, status="error")
        if name not in self.run.presented_tools:
            if name in FILESYSTEM_TOOL_NAMES and not self.run.project_path and not _allow_projectless_knowledge_tool(name, args, self.run):
                return ToolMessage(content="Filesystem tools require a bound project folder or selected knowledge. The unselected action was not executed.", name=name, tool_call_id=call_id, status="error")
            return ToolMessage(content="This tool was not selected for this run. The action was not executed.", name=name, tool_call_id=call_id, status="error")
        if name in FILESYSTEM_TOOL_NAMES and not self.run.project_path:
            if _allow_projectless_knowledge_tool(name, args, self.run):
                return None
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
        if self.run.work_mode == "plan":
            allowed.intersection_update(PLAN_TOOLS)
        if self.run.framework_read_paths:
            allowed.add("read_file")
        selected: list[Any] = []
        for item in tools or []:
            name = tool_name(item)
            if name is None or name in allowed:
                if name == "read_file" and self.run.framework_read_paths:
                    description = "Read framework-saved tool results or conversation history with offset and limit pagination. Only these paths are permitted: " + ", ".join(self.run.framework_read_paths) + ". Project and knowledge files are not authorized by this reader."
                    if hasattr(item, "model_copy"):
                        item = item.model_copy(update={"description": description})
                selected.append(item)
        return selected

    def _observe_context(self, request: ModelRequest) -> None:
        if self.run.context_observation is None:
            return
        messages = ([request.system_message] if request.system_message else []) + list(request.messages)
        self.run.context_observation = observe_payload(self.run.context_observation, {
            "messages": messages, "tools": request.tools, "response_format": request.response_format,
        })
        require_context_fit(self.run.context_observation)

    def _capture(
        self,
        request: ModelRequest,
        http_payload: dict[str, Any] | None,
        *,
        http_payloads: list[dict[str, Any]] | None = None,
        handler_returned: bool = False,
        failure: Exception | None = None,
    ) -> None:
        setup = self.run.effective_setup
        gaps = list(setup.gaps) if setup is not None else [RAG_GAP]
        if setup is None:
            if not self.run.memory_version_refs:
                gaps.append(MEMORY_GAP)
            if not self.run.skill_version_refs:
                gaps.append(SKILL_GAP)
        if http_payload is None:
            gaps.append("http payload not observed for this model call")
        attempts = list(http_payloads or ([] if http_payload is None else [http_payload]))
        response_observed = any(item.get("response_received") is True for item in attempts)
        if failure is not None and response_observed:
            gaps.append("model call failed after transport response was observed")
        elif failure is not None:
            gaps.append("model call failed before response was observed")
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
                instructions=_captured_instructions(request, http_payload),
                messages=[_message_dict(message) for message in request.messages],
                available_tools=list(self.run.enabled_tools),
                presented_tools=[
                    name
                    for name in (_tool_names(request.tools))
                    if name in self.run.presented_tools or (name == "read_file" and self.run.framework_read_paths)
                ],
                generation_settings=generation,
                memory_versions=list(self.run.memory_version_refs),
                skill_versions=list(self.run.skill_version_refs),
                loaded_knowledge=list(setup.loaded_knowledge) if setup is not None else [],
                retrieved_material=list(self.run.retrieved_material),
                capture_gaps=gaps,
                http_payload=http_payload,
                http_payloads=attempts,
                request_prepared=True,
                transport_attempted=bool(attempts),
                transport_attempt_count=len(attempts),
                response_observed=response_observed,
                handler_returned=handler_returned,
                failure=_failure_dict(failure),
                selected_profile_id=setup.selected_profile_id if setup is not None else self.run.profile_id,
                applied_per_request=applied if handler_returned else {},
                startup_mismatches=(
                    [item.model_dump(mode="json") for item in setup.startup_mismatches]
                    if setup is not None
                    else []
                ),
                context_observation=self.run.context_observation,
            ),
            settings,
        )
        self.run.model_requests.append(captured)
        self.run.updated_at = utc_now()

    def _safe_capture(
        self,
        request: ModelRequest,
        http_payload: dict[str, Any] | None,
        *,
        http_payloads: list[dict[str, Any]] | None = None,
        handler_returned: bool = False,
        failure: Exception | None = None,
    ) -> None:
        try:
            self._capture(
                request,
                http_payload,
                http_payloads=http_payloads,
                handler_returned=handler_returned,
                failure=failure,
            )
        except Exception as capture_error:  # noqa: BLE001 - diagnostics must not mask model errors
            self.run.events.append(
                AgentEvent(
                    at=utc_now(),
                    kind="model_request_capture_failed",
                    detail={
                        "type": type(capture_error).__name__,
                    },
                )
            )


def _allow_projectless_knowledge_tool(
    name: str,
    args: dict[str, Any],
    run: AgentRun,
) -> bool:
    if not knowledge_routes_selected(run.memory_version_refs, run.skill_version_refs):
        return False
    path = _filesystem_tool_path(name, args)
    if name in KNOWLEDGE_ROUTE_READ_TOOLS:
        return path == "/" or is_knowledge_route_path(path) or is_reserved_framework_path(path)
    if name in {"write_file", "edit_file"}:
        return is_memory_route_path(path)
    return False


def _filesystem_tool_path(name: str, args: dict[str, Any]) -> str:
    if name == "ls":
        raw = args.get("path") or args.get("file_path") or "/"
    else:
        raw = args.get("file_path") or args.get("path") or ""
    return raw if isinstance(raw, str) and raw else ("/" if name == "ls" else "")


def _captured_instructions(request: ModelRequest, http_payload: dict[str, Any] | None) -> str | None:
    """Prefer the outbound payload. MemoryMiddleware is tail middleware."""

    outbound = _outbound_system_text(http_payload)
    if outbound:
        return outbound
    return _system_text(request)


def _outbound_system_text(http_payload: dict[str, Any] | None) -> str | None:
    if not http_payload:
        return None
    body = http_payload.get("body")
    if not isinstance(body, dict):
        return None
    messages = body.get("messages")
    if not isinstance(messages, list):
        return None
    parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "system":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content)
            continue
        if isinstance(content, list):
            for block in content:
                if isinstance(block, str) and block.strip():
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
    return "\n".join(parts) if parts else None


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
    return next((item for item in reversed(sink[before:]) if "body" in item), None)


def _payloads_after(sink: list[dict[str, Any]], before: int) -> list[dict[str, Any]]:
    if len(sink) <= before:
        return []
    return [dict(item) for item in sink[before:]]


def _failure_dict(exc: Exception | None) -> dict[str, Any] | None:
    if exc is None:
        return None
    return {
        "type": type(exc).__name__,
        "message": str(exc),
    }


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
    content = _diagnostic_content(getattr(message, "content", ""))
    payload: dict[str, Any] = {"role": str(role), "content": content}
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        payload["tool_calls"] = tool_calls
    return payload


def _diagnostic_content(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("data:"):
            return "<embedded-media-redacted>"
        return value[:8192] + ("…[truncated]" if len(value) > 8192 else "")
    if isinstance(value, list):
        return [_diagnostic_content(item) for item in value[:64]]
    if isinstance(value, dict):
        if value.get("type") in {"image_url", "image", "input_audio"}:
            return {"type": value.get("type"), "content": "<embedded-media-redacted>"}
        return {key: _diagnostic_content(item) for key, item in value.items()}
    return value
