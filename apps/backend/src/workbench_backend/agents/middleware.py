"""Harness middleware: request capture (AGT-002) and tool policy (AGT-005)."""

from __future__ import annotations

from workbench_backend.errors import HarnessError

import asyncio
import base64
import binascii
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
import time

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from workbench_backend.agents.effective_setup import MEMORY_GAP, RAG_GAP, SKILL_GAP
from workbench_backend.agents.context import estimate_payload, ContextCapacityExceeded
from workbench_backend.agents.project_outline import ProjectOutlineCache
from workbench_backend.agents.harness_backend import CAPTURES_PREFIX, is_reserved_framework_path
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
from workbench_backend.agents.schemas import AgentEvent, AgentRun, ModelRequestCapture, GenerationObservation, ToolOutcome, ToolMode
from workbench_backend.agents.tool_outcomes import file_evidence, result_outcome
from workbench_backend.agents.tool_errors import recoverable_tool_error
from workbench_backend.inference.telemetry import current_request_purpose
from workbench_backend.inference.request_projection import TOOL_CONTEXT_MARKER
from workbench_backend.agents.tools import (
    FILESYSTEM_TOOL_NAMES,
    KNOWLEDGE_ROUTE_READ_TOOLS,
    SHELL_TOOL_NAMES,
    tool_name,
)
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.image_validation import (
    CANNOT_READ_IMAGE,
    MAX_IMAGE_BYTES,
    MAX_TOOL_IMAGE_BYTES_PER_REQUEST,
    validate_image_bytes,
)
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
        asset_service: Any = None,
        capture_backend: Any = None,
        tool_image_preparer: Callable[[], bool] | None = None,
        generation_recorder: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.run = run
        self.http_sink = http_sink if http_sink is not None else []
        self._settings_provider = settings_provider
        self.fixture_bank = fixture_bank
        self.execution_control = execution_control or ExecutionControl(run)
        self.asset_service = asset_service
        self.capture_backend = capture_backend
        self.tool_image_preparer = tool_image_preparer
        self.generation_recorder = generation_recorder
        self.outline_cache = ProjectOutlineCache()
        self._outline_initialized = "snapshot_text" in (run.project_outline or {})
        self._outline_text = (run.project_outline or {}).get("snapshot_text", "")

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        self._require_dispatch_allowed()
        filtered = self._with_outline(self._with_current_tool_images(request.override(tools=self._presented(request.tools))))
        self._observe_context(filtered)
        self.run.generation_observation = None
        before = len(self.http_sink)
        started = time.perf_counter()
        try:
            response = handler(filtered)
        except Exception as exc:
            if self.generation_recorder is not None:
                self.generation_recorder()
            self._record_undispatched_model_calls(exc)
            self._safe_capture(
                filtered,
                _payload_after(self.http_sink, before),
                http_payloads=_payloads_after(self.http_sink, before),
                handler_returned=False,
                failure=exc,
            )
            raise
        if self.generation_recorder is not None:
            self.generation_recorder()
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
        filtered = await asyncio.to_thread(lambda: self._with_outline(self._with_current_tool_images(
            request.override(tools=self._presented(request.tools)))))
        self._observe_context(filtered)
        self.run.generation_observation = None
        before = len(self.http_sink)
        started = time.perf_counter()
        try:
            response = await handler(filtered)
        except Exception as exc:
            if self.generation_recorder is not None:
                self.generation_recorder()
            self._record_undispatched_model_calls(exc)
            self._safe_capture(
                filtered,
                _payload_after(self.http_sink, before),
                http_payloads=_payloads_after(self.http_sink, before),
                handler_returned=False,
                failure=exc,
            )
            raise
        if self.generation_recorder is not None:
            self.generation_recorder()
        self._safe_capture(
            filtered,
            _payload_after(self.http_sink, before),
            http_payloads=_payloads_after(self.http_sink, before),
            handler_returned=True,
        )
        self._observe_generation(response, time.perf_counter() - started)
        return response

    def _record_undispatched_model_calls(self, error: Exception) -> None:
        """Retain adapter evidence even when native model completion is rejected.

        The model middleware owns the correct parent/helper scope. These calls
        never reached ToolNode, so recording them must not reserve dispatch or
        add messages to the execution checkpoint.
        """
        if not isinstance(error, HarnessError) or error.code not in {
            "response_limit_reached", "adapter_invalid_tool_call", "adapter_incomplete_tool_call",
        }:
            return
        for item in error.details.get("tool_calls", []):
            call_id, name, outcome = item.get("call_id"), item.get("name"), item.get("outcome")
            if not call_id or not name or call_id in self.run.tool_outcomes:
                continue
            if outcome not in {"incomplete_arguments", "not_dispatched"}:
                continue
            self.execution_control.record_tool_outcome(self.run, ToolOutcome(
                call_id=call_id, name=name, outcome=outcome,
                failure_category="input", recovery_action="continue",
                detail=("The model stopped before producing complete arguments. This call was not executed."
                        if outcome == "incomplete_arguments" else
                        "This call had complete arguments, but its response batch was rejected before dispatch."),
                evidence={"proposed_path": item["file_path"]} if item.get("file_path") else {},
                updated_at=utc_now(),
            ))

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
            self._record_tool_result(request, blocked)
            return blocked
        with self.execution_control.tool_dispatch(self.run, _tool_call_parts(request)[2]):
            self._begin_tool(request)
            try:
                result = self._wrap_tool_call(request, handler)
            except BaseException as exc:
                result = self._handle_tool_failure(request, exc)
                if result is None:
                    raise
            result = self._offload_read_file_image(result)
            self._record_tool_result(request, result)
            return self._authorization_result(result)

    def _begin_tool(self, request):
        name, args, call_id = _tool_call_parts(request)
        self.run.activity_phase = "using_tools"
        self.execution_control.record_tool_outcome(self.run, ToolOutcome(call_id=call_id, name=name,
            outcome="running", recovery_action="inspect_effects", evidence=file_evidence(self.run, name, args), updated_at=utc_now()))

    def _record_tool_result(self, request, result):
        name, _, call_id = _tool_call_parts(request)
        previous = self.run.tool_outcomes.get(call_id)
        if previous is not None and previous.outcome in {"succeeded", "failed"} and isinstance(result, ToolMessage) and previous.result == result.content:
            return
        self.execution_control.record_tool_outcome(self.run,
            result_outcome(call_id, name, result, previous.evidence if previous else {},
                process_stopped=True if name == "execute" and sys.platform == "win32" and self.run.tool_mode != ToolMode.recorded_tool else None))
        if self.run.project_path and name in {"write_file", "edit_file", "execute", "delete_file", "move_file"}:
            self.outline_cache.invalidate(self.run.project_path)

    def _handle_tool_failure(self, request, exc):
        from langgraph.errors import GraphInterrupt
        name, _, call_id = _tool_call_parts(request)
        previous = self.run.tool_outcomes.get(call_id)
        if name == "task" and previous is not None and previous.outcome == "failed" and previous.evidence.get("helper_status") in {"failed", "cancelled"}:
            # The owned inline helper finalizer recorded its terminal result.
            # Preserve it; uncertain nested effects have their own scoped rows.
            return None
        recoverable = recoverable_tool_error(exc, name=name, call_id=call_id)
        if recoverable is not None:
            return recoverable
        interrupted = isinstance(exc, GraphInterrupt)
        self.execution_control.record_tool_outcome(self.run, ToolOutcome(call_id=call_id, name=name,
            outcome="not_dispatched" if interrupted else "uncertain",
            failure_category=None if interrupted else "runtime", recovery_action="none" if interrupted else "inspect_effects",
            detail="Waiting for approval or an answer." if interrupted else str(exc),
            evidence=previous.evidence if previous else {}, updated_at=utc_now()))
        return None

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
            _, _, call_id = _tool_call_parts(request)
            token = CURRENT_TOOL_CALL.set(call_id)
            try:
                return handler(request)
            finally:
                CURRENT_TOOL_CALL.reset(token)
        return self._replay_tool_call(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> ToolMessage | Any:
        self._require_dispatch_allowed()
        blocked = self._reject_projectless_privileged_tool(request)
        if blocked is not None:
            self._record_tool_result(request, blocked)
            return blocked
        with self.execution_control.tool_dispatch(self.run, _tool_call_parts(request)[2]):
            await asyncio.to_thread(self._begin_tool, request)
            try:
                result = await self._awrap_tool_call(request, handler)
            except BaseException as exc:
                previous = self.run.tool_outcomes.get(_tool_call_parts(request)[2])
                # Shielded Windows work may have settled while cancellation was
                # waiting. Keep its returned result and process-stop evidence;
                # interrupted command effects still require inspection.
                if (isinstance(exc, asyncio.CancelledError) and previous is not None
                    and (previous.outcome in {"succeeded", "failed"} or previous.outcome == "uncertain" and previous.result is not None)):
                    raise
                result = self._handle_tool_failure(request, exc)
                if result is None:
                    raise
            self._record_tool_result(request, result)
            return self._authorization_result(await asyncio.to_thread(self._offload_read_file_image, result))

    def _offload_read_file_image(self, result: ToolMessage | Any) -> ToolMessage | Any:
        """Replace a successful native image result with a durable asset path."""

        if (not isinstance(result, ToolMessage) or result.name != "read_file"
            or result.status == "error" or self.asset_service is None
            or self.capture_backend is None or not self.run.capture_routes_enabled):
            return result
        source_path = result.additional_kwargs.get("read_file_path")
        media_type = result.additional_kwargs.get("read_file_media_type")
        if not isinstance(source_path, str) or not isinstance(media_type, str):
            return result
        images = [block for block in result.content_blocks
            if isinstance(block, dict) and block.get("type") == "image"]
        if not images:
            return result
        if len(images) != 1 or media_type not in {"image/png", "image/jpeg", "image/webp"}:
            from workbench_backend.errors import HarnessError
            raise HarnessError("Only one PNG, JPEG, or WebP image can be read at a time.",
                code="tool_image_invalid", status_code=422)
        if _CAPTURE_FILE_PATH.fullmatch(source_path):
            # The read-only backend already verified session ownership; reuse
            # the same retained asset instead of creating another capture.
            path = source_path
            asset_id = source_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            digest = None
        else:
            encoded = images[0].get("base64")
            if not isinstance(encoded, str) or len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
                from workbench_backend.errors import HarnessError
                raise HarnessError("The image result exceeds the supported size.",
                    code="tool_image_invalid", status_code=422)
            try:
                content = base64.b64decode(encoded, validate=True)
                validate_image_bytes(content, media_type)
            except (ValueError, binascii.Error) as exc:
                from workbench_backend.errors import HarnessError
                raise HarnessError("The image result could not be verified.",
                    code="tool_image_invalid", status_code=422) from exc
            asset, path = self.asset_service.retain_tool_image(self.run, content,
                content_type=media_type, source_path=source_path,
                source_tool_call_id=result.tool_call_id)
            asset_id = asset.id
            digest = asset.sha256
        text = "\n".join(block["text"] for block in result.content_blocks
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str))
        reference = f"Image retained at {path}. Use read_file on that path to inspect it again."
        return result.model_copy(update={
            "content": f"{text}\n{reference}" if text else reference,
            "additional_kwargs": {**result.additional_kwargs,
                "capture_path": path, "capture_asset_id": asset_id,
                "capture_media_type": media_type,
                **({"capture_sha256": digest} if digest is not None else {})},
        })

    def _saved_screenshot(self, message: ToolMessage) -> tuple[str, str] | None:
        path = message.additional_kwargs.get("capture_path")
        mime_type = message.additional_kwargs.get("capture_media_type")
        if not isinstance(path, str):
            match = _SAVED_SCREENSHOT.search(message.content if isinstance(message.content, str) else "")
            if match is None:
                return None
            path = match.group(1)
            mime_type = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}.get(Path(path).suffix.lower())
        if not isinstance(path, str) or _CAPTURE_FILE_PATH.fullmatch(path) is None:
            return None
        if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            return None
        return path, mime_type

    def _images_allowed_now(self) -> bool:
        backend = self.capture_backend
        if backend is None:
            return False
        flag = getattr(backend, "image_inputs_allowed", True)
        return bool(flag()) if callable(flag) else bool(flag)

    def _with_current_tool_images(self, request: ModelRequest) -> ModelRequest:
        """Hydrate canonical capture references at their original tool boundaries."""
        if self.capture_backend is None or not self.run.capture_routes_enabled:
            return request
        messages = list(request.messages)
        if self.run.presented_tools and any(isinstance(message, ToolMessage) and self._saved_screenshot(message) for message in messages) and self.tool_image_preparer is not None:
            try:
                self.tool_image_preparer()
            except Exception:
                # A check that cannot finish leaves the page text usable.
                pass
        return request.override(messages=self._tool_image_messages(messages, hydrate=True))

    def tool_image_messages_for_count(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """Count the same visual positions without loading bytes or running probes.

        Native summarization keeps canonical message indices; inserting derived
        messages before it would invalidate its checkpoint cutoff positions.
        """
        return self._tool_image_messages(messages, hydrate=False)

    def _tool_image_messages(self, messages: list[BaseMessage], *, hydrate: bool) -> list[BaseMessage]:
        if self.capture_backend is None or not self.run.capture_routes_enabled:
            return messages
        projected: list[BaseMessage] = []
        content: list[dict[str, Any]] = []
        image_bytes = 0
        denied = False
        allowed = self._images_allowed_now()
        batch_calls: set[str] = set()

        def finish_batch() -> None:
            nonlocal content, denied
            if content:
                projected.append(HumanMessage(content=[{"type": "text", "text": "<tool_response>\n"}, *content,
                    {"type": "text", "text": "\n</tool_response>"}], additional_kwargs={TOOL_CONTEXT_MARKER: True}))
            elif denied:
                projected.append(HumanMessage(content=f"<tool_response>\n{CANNOT_READ_IMAGE}\n</tool_response>",
                    additional_kwargs={TOOL_CONTEXT_MARKER: True}))
            content, denied = [], False

        for message in messages:
            if not isinstance(message, ToolMessage):
                finish_batch()
                batch_calls = {call["id"] for call in message.tool_calls} if isinstance(message, AIMessage) else set()
            projected.append(message)
            if not isinstance(message, ToolMessage) or message.tool_call_id not in batch_calls:
                continue
            item = self._saved_screenshot(message)
            if item is None:
                continue
            path, mime_type = item
            if not allowed:
                denied = denied or CANNOT_READ_IMAGE not in (message.content if isinstance(message.content, str) else "")
                continue
            encoded = ""
            if hydrate:
                loaded = self.capture_backend.read(path.removeprefix("/captures"))
                if loaded.error or loaded.file_data is None:
                    if loaded.error and CANNOT_READ_IMAGE in loaded.error:
                        denied = denied or CANNOT_READ_IMAGE not in (message.content if isinstance(message.content, str) else "")
                        continue
                    raise HarnessError("The retained image is unavailable. Read or capture it again.",
                        code="capture_unavailable", status_code=409)
                encoded = loaded.file_data["content"]
                image_bytes += len(encoded) * 3 // 4
                if image_bytes > MAX_TOOL_IMAGE_BYTES_PER_REQUEST:
                    raise ContextCapacityExceeded("Retained images exceed the model request's image byte budget. "
                        "Native context compaction could not retain all of them. Read fewer images or start a fresh conversation.",
                        code="tool_images_too_large", status_code=422)
            content.extend([
                {"type": "text", "text": f"Image from tool call {message.tool_call_id} at {path}:"},
                {"type": "image", "base64": encoded, "mime_type": mime_type},
            ])
        finish_batch()
        return projected

    async def _awrap_tool_call(self, request, handler):
        if self.fixture_bank is None:
            name, _, call_id = _tool_call_parts(request)
            async def invoke() -> Any:
                token = CURRENT_TOOL_CALL.set(call_id)
                try:
                    result = await handler(request)
                    result = await asyncio.to_thread(self._offload_read_file_image, result)
                    self._record_tool_result(request, result)
                    return result
                finally:
                    CURRENT_TOOL_CALL.reset(token)
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
            if name in FILESYSTEM_TOOL_NAMES and not self.run.project_path and not (
                _allow_projectless_knowledge_tool(name, args, self.run)
                or _allow_projectless_capture_tool(name, args, self.run)
            ):
                return ToolMessage(content="Filesystem tools require a bound project folder or selected knowledge. The unselected action was not executed.", name=name, tool_call_id=call_id, status="error")
            return ToolMessage(content="This tool was not selected for this run. The action was not executed.", name=name, tool_call_id=call_id, status="error")
        if name in FILESYSTEM_TOOL_NAMES and not self.run.project_path:
            if (_allow_projectless_knowledge_tool(name, args, self.run)
                or _allow_projectless_capture_tool(name, args, self.run)):
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
        # The inference adapter guards its canonical outbound projection after
        # native compaction and all middleware. Counting native objects here
        # duplicates reasoning and rejects history before it can be reduced.
        return

    def _with_outline(self, request):
        self.run.activity_phase = "thinking"
        system = request.system_message
        content = system.content if system else ""
        if not isinstance(content, str):
            return request
        if not self._outline_initialized:
            self._outline_initialized = True
            preface = "Initial project snapshot for this run. Files may change; use tool results and fresh reads for current facts.\n"
            outline = self.outline_cache.build(self.run.project_path, self.run.task, self.run.presented_tools,
                max_tokens=1024 - (len(preface) + 2) // 3)
            from dataclasses import asdict
            self.run.project_outline = {key: value for key, value in asdict(outline).items() if key != "text"}
            if outline.text:
                text = preface + outline.text
                candidate = request.override(system_message=SystemMessage(content=content + "\n\n" + text))
                project = getattr(request.model, "project_context_payload", None)
                limit = self.run.context_observation.usable_input_tokens if self.run.context_observation else None
                payload = project([candidate.system_message, *self.tool_image_messages_for_count(candidate.messages)],
                    tools=candidate.tools, response_format=candidate.response_format) if project is not None and limit is not None else None
                if payload is not None and estimate_payload(payload) > limit:
                    self.run.project_outline["omitted_for_capacity"] = True
                else:
                    self._outline_text = text
                    self.run.project_outline["included"] = True
                    self.run.project_outline["estimated_tokens"] = (len(text) + 2) // 3
            self.run.project_outline["snapshot_text"] = self._outline_text
        if not self._outline_text or content.endswith(self._outline_text):
            return request
        return request.override(system_message=SystemMessage(content=content + "\n\n" + self._outline_text))

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
                purpose=current_request_purpose(),
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
    normalized = path if path.startswith("/") else f"/{path.lstrip('/')}"
    is_capture_path = normalized == CAPTURES_PREFIX.rstrip("/") or normalized.startswith(CAPTURES_PREFIX)
    if name in KNOWLEDGE_ROUTE_READ_TOOLS:
        return path == "/" or is_knowledge_route_path(path) or (
            is_reserved_framework_path(path) and not is_capture_path
        )
    if name in {"write_file", "edit_file"}:
        return is_memory_route_path(path)
    return False


_CAPTURE_FILE_PATH = re.compile(r"^/captures/asset_[0-9a-f]{32}\.(png|jpg|webp)$")
_SAVED_SCREENSHOT = re.compile(r"Saved screenshot: (/captures/asset_[0-9a-f]{32}\.(?:png|jpg|webp))")


def _allow_projectless_capture_tool(name: str, args: dict[str, Any], run: AgentRun) -> bool:
    """Permit only session-backed capture reads through the mounted backend."""

    if not run.capture_routes_enabled or name not in KNOWLEDGE_ROUTE_READ_TOOLS:
        return False
    path = _filesystem_tool_path(name, args).replace("\\", "/")
    if path.startswith("//") or any(part in {".", ".."} or ":" in part for part in path.split("/")):
        return False
    if name == "ls":
        return path in {"/", "/captures", "/captures/"}
    return _CAPTURE_FILE_PATH.fullmatch(path) is not None


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
