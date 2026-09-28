"""Context observations and preflight checks for one harness request."""

from __future__ import annotations

import asyncio
import json
from contextlib import nullcontext
from typing import Any, Literal

from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, get_buffer_string
from langchain_core.utils.function_calling import convert_to_openai_tool
from deepagents.middleware.summarization import SummarizationMiddleware

from pydantic import BaseModel, Field

from workbench_backend.errors import HarnessError
from workbench_backend.inference.schemas import Deployment, SettingsBag
from workbench_backend.inference.request_projection import project_context_payload
from workbench_backend.inference.telemetry import request_purpose, current_request_purpose
from workbench_backend.inference.response_budget import TOKEN_MARGIN_RATIO, bind_output_budget, output_reservation
from workbench_backend.inference.user_content import UserContentBlock, user_message_content

DEFAULT_OUTPUT_RESERVATION = 0


class BudgetedSummarizationMiddleware(SummarizationMiddleware):
    """Use Deep Agents' one compaction path with our already-reserved input limit.

    Pinned deepagents 0.7.19 otherwise subtracts output and 5% again from the
    model profile. Compaction and summary generation remain upstream-owned.
    """

    @property
    def name(self) -> str:
        # Upstream uses subclass names; explicitly replace the default entry.
        return "SummarizationMiddleware"

    def __init__(self, *args: Any, allowed_tools: set[str] | None = None,
                 on_context_failure: Any = None, request_preparer: Any = None,
                 execution_control: Any = None, run: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.allowed_tools = allowed_tools
        self.on_context_failure = on_context_failure
        self.request_preparer = request_preparer
        self.execution_control = execution_control
        self.run = run

    def _selected_request(self, request: Any) -> Any:
        if self.allowed_tools is not None:
            from workbench_backend.agents.tools import tool_name
            request = request.override(tools=[tool for tool in request.tools if tool_name(tool) in self.allowed_tools])
        if self.request_preparer is not None:
            # Admission may contain raw checkpoint history already covered by a
            # native summary. Decide optional context against the active prompt,
            # then preserve canonical indices for the summarizer's own cutoff.
            prepared = self.request_preparer(request.override(messages=self._get_effective_messages(request)))
            request = prepared.override(messages=request.messages)
        return request

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        try:
            return super().wrap_model_call(self._selected_request(request), handler)
        except ContextOverflowError as exc:
            if isinstance(exc, HarnessError):
                raise
            raise ContextCapacityExceeded(str(exc), code="context_capacity_exceeded", status_code=409) from exc

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        try:
            selected = await asyncio.to_thread(self._selected_request, request)
            return await super().awrap_model_call(selected, handler)
        except ContextOverflowError as exc:
            if isinstance(exc, HarnessError):
                raise
            raise ContextCapacityExceeded(str(exc), code="context_capacity_exceeded", status_code=409) from exc

    def _create_summary(self, messages_to_summarize: list[Any]) -> str:
        dispatch = self.execution_control.model_dispatch(self.run, purpose="summary") if self.execution_control is not None else nullcontext()
        with dispatch, request_purpose("summary"):
            self._validate_summary_request(messages_to_summarize)
            return super()._create_summary(messages_to_summarize)

    async def _acreate_summary(self, messages_to_summarize: list[Any]) -> str:
        dispatch = self.execution_control.model_dispatch(self.run, purpose="summary") if self.execution_control is not None else nullcontext()
        with dispatch, request_purpose("summary"):
            self._validate_summary_request(messages_to_summarize)
            return await super()._acreate_summary(messages_to_summarize)

    def _validate_summary_request(self, messages: list[Any]) -> None:
        """Guard the installed SDK's actual summary prompt before any model.

        The SDK still owns cutoff, history storage and summary generation. This
        also protects connected/custom models that lack our transport guard.
        """
        observation = self.run.context_observation if self.run is not None else None
        if observation is None or not messages:
            return
        trimmed = self._lc_helper._trim_messages_for_summary(messages)
        if not trimmed:
            return
        prompt = self._lc_helper.summary_prompt.format(messages=get_buffer_string(trimmed, format="xml")).rstrip()
        observed = observe_payload(observation, project_context_payload([HumanMessage(content=prompt)]))
        self.run.housekeeping_context["summary"] = observed
        require_context_fit(observed)

    def _check_reduction(self, original: Any, reduced: Any, error: Exception | None) -> None:
        try:
            return super()._check_reduction(original, reduced, error)
        except ContextOverflowError:
            if self.on_context_failure is not None:
                count = self._count_tokens(reduced.messages, reduced.system_message, reduced.tools)
                self.on_context_failure(count, self._input_budget(reduced))
            raise

    def _input_budget(self, request: Any) -> int | None:
        profile = request.model.profile or {}
        value = profile.get("max_input_tokens")
        return value if type(value) is int else None


class ContextCapacityExceeded(HarnessError, ContextOverflowError):
    """An application fit check that native Deep Agents compaction recognizes."""


class ContextObservation(BaseModel):
    schema_version: int = 1
    purpose: Literal["work", "summary", "review", "probe"] = "work"
    capacity_tokens: int | None = None
    capacity_source: Literal["server_props.n_ctx", "unknown"] = "unknown"
    output_reservation_tokens: int = DEFAULT_OUTPUT_RESERVATION
    estimated_input_tokens: int = 0
    usable_input_tokens: int | None = None
    margin_tokens: int = 0
    fits: bool | None = None
    counting_method: str = "Character estimate (3 chars/token), outbound messages/tools/schema counted once, 2048 tokens/image, 8% capacity margin; not tokenizer usage"
    summarization_path: Literal["deepagents-upstream"] = "deepagents-upstream"
    notes: list[str] = Field(default_factory=list)


def observe_context(
    *,
    deployment: Deployment,
    per_request: SettingsBag | None,
    system_prompt: str | None,
    task: str,
    content_blocks: list[UserContentBlock] | None,
    tool_count: int,
    output_schema: dict[str, Any] | None,
    continuing_thread: bool,
    history: list[BaseMessage] | None = None,
    tools: list[Any] | None = None,
) -> ContextObservation:
    capacity, source = _capacity(deployment)
    resolved = bind_output_budget(deployment, per_request or SettingsBag())
    reservation = output_reservation(resolved)
    from workbench_backend.inference.adapter import _reasoning_replay_scope
    messages = [*([SystemMessage(content=system_prompt)] if system_prompt else []),
                *(history or []), HumanMessage(content=user_message_content(task, content_blocks))]
    payload = project_context_payload(messages, tools=tools, response_format=output_schema,
                                      reasoning_scope=_reasoning_replay_scope(deployment, resolved))
    estimated = estimate_payload(payload)
    margin = int(capacity * TOKEN_MARGIN_RATIO) if capacity else 0
    fits = None if capacity is None else estimated + reservation + margin <= capacity
    notes: list[str] = []
    if capacity is None:
        notes.append("Running context capacity is unknown; no verified limit was invented.")
    if continuing_thread:
        notes.append("Continuing-thread preflight uses the existing Deep Agents checkpoint thread.")
    return ContextObservation(
        capacity_tokens=capacity,
        capacity_source=source,
        output_reservation_tokens=reservation,
        estimated_input_tokens=estimated,
        usable_input_tokens=max(0, capacity-reservation-margin) if capacity is not None else None,
        margin_tokens=margin,
        fits=fits,
        notes=notes,
    )


def require_context_fit(observation: ContextObservation) -> None:
    if observation.fits is False:
        raise ContextCapacityExceeded(
            "The model request exceeds the observed context budget. "
            "Automatic compaction could not make this request fit. Reduce selected context or increase the model context size. No history was removed.",
            code="context_capacity_exceeded",
            status_code=409,
            details=observation.model_dump(mode="json"),
        )


def _capacity(deployment: Deployment) -> tuple[int | None, Literal["server_props.n_ctx", "unknown"]]:
    if deployment.server_props is not None and deployment.server_props.n_ctx:
        return deployment.server_props.n_ctx, "server_props.n_ctx"
    return None, "unknown"


def _output_reservation(per_request: SettingsBag | None) -> int:
    return output_reservation(per_request)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 2) // 3)


def _media_overhead(blocks: list[UserContentBlock] | None) -> int:
    total = 0
    for block in blocks or []:
        if getattr(block, "type", None) == "text":
            total += _estimate_tokens(getattr(block, "text", ""))
        elif getattr(block, "type", None) == "image_url":
            total += 2048
    return total


def estimate_payload(payload: Any) -> int:
    """Disclosed estimate, never model tokenization or a cloud-model lookup."""
    images = 0
    def simplify(value: Any) -> Any:
        nonlocal images
        if isinstance(value, BaseMessage):
            value = project_context_payload([value])["messages"][0]
        elif hasattr(value, "args_schema"):
            value = convert_to_openai_tool(value)
        if isinstance(value, dict):
            value_type = value.get("type")
            if isinstance(value_type, str) and value_type in {"image_url", "image"}:
                images += 1
                return {"type": "image", "content": "[image]"}
            return {key: simplify(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [simplify(item) for item in value]
        return value
    serialized = json.dumps(simplify(payload), ensure_ascii=False, default=str, separators=(",", ":"))
    return _estimate_tokens(serialized) + images * 2048


def count_context_tokens(messages: list[Any], *, tools: list[Any] | None = None) -> int:
    return estimate_payload(project_context_payload(messages, tools=tools))


def token_counter_for_model(model: Any, *, response_format: Any = None, message_projection: Any = None) -> Any:
    """Bind native compaction counting to this adapter's actual replay policy."""
    projection = getattr(model, "project_context_payload", None)
    if projection is None:
        projection = project_context_payload

    def count(messages: list[Any], *, tools: list[Any] | None = None) -> int:
        if message_projection is not None:
            messages = message_projection(messages)
        return estimate_payload(projection(messages, tools=tools, response_format=response_format))
    return count


def observe_payload(base: ContextObservation, payload: dict[str, Any]) -> ContextObservation:
    observation = base.model_copy(deep=True)
    observation.purpose = current_request_purpose()
    observation.estimated_input_tokens = estimate_payload({key: value for key, value in payload.items() if key in {"messages", "tools", "response_format"}})
    observation.fits = None if observation.usable_input_tokens is None else observation.estimated_input_tokens <= observation.usable_input_tokens
    return observation


def validate_retained_messages(deployment: Deployment, messages: list[BaseMessage], *, allow_recovery: bool = False) -> None:
    """Validate a native repair preview without altering checkpoints or effects."""
    if allow_recovery:
        from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
        from langchain_core.messages import RemoveMessage
        repaired = PatchToolCallsMiddleware().before_agent({"messages": messages}, None)
        if repaired is not None:
            messages = [item for item in repaired["messages"] if not isinstance(item, RemoveMessage)]
    failed_ids = {message.tool_call_id for message in messages
                  if message.type == "tool" and getattr(message, "status", None) == "error"}
    props = deployment.server_props
    pending: set[str] = set()
    for message in messages:
        kind = message.type
        if props:
            if kind == "system" and props.chat_template_caps.get("supports_system_role") is False:
                raise HarnessError("This setup cannot preserve the conversation's system instructions.", code="context_system_unsupported", status_code=409)
            blocks = message.content if isinstance(message.content, list) else []
            if blocks and props.chat_template_caps.get("supports_typed_content") is False:
                raise HarnessError("This setup cannot preserve structured content blocks in the conversation.", code="context_content_unsupported", status_code=409)
            if any(isinstance(b, dict) and b.get("type") in {"image", "image_url"} for b in blocks) and props.modalities.get("vision") is False:
                raise HarnessError("This setup cannot read images retained in the conversation. Select a vision setup or start a fresh conversation.", code="context_image_unsupported", status_code=409)
        invalid = getattr(message, "invalid_tool_calls", [])
        if any(not call.get("id") or call["id"] not in failed_ids for call in invalid):
            raise HarnessError("The retained conversation contains an unresolved invalid tool call.", code="context_invalid_tool_call", status_code=409)
        calls = [*getattr(message, "tool_calls", []), *invalid]
        if calls:
            if len(calls) > 1 and props and props.chat_template_caps.get("supports_parallel_tool_calls") is False:
                raise HarnessError("This setup cannot preserve multiple tool calls in one retained message.", code="context_parallel_tools_unsupported", status_code=409)
            if props and (props.chat_template_caps.get("supports_tool_calls") is False or props.chat_template_caps.get("supports_tools") is False):
                raise HarnessError("This setup cannot preserve the conversation's tool calls/results.", code="context_tools_unsupported", status_code=409)
            for call in calls:
                if not call.get("id") or call["id"] in pending:
                    raise HarnessError("Tool call identities are missing or duplicated.", code="context_tool_pair_invalid", status_code=409)
                pending.add(call["id"])
        if kind == "tool":
            ident = getattr(message, "tool_call_id", None)
            if ident not in pending:
                raise HarnessError("A retained tool result has no matching call.", code="context_tool_pair_invalid", status_code=409)
            pending.remove(ident)
        elif pending and not calls:
            raise HarnessError("A retained tool call has no completed result.", code="context_tool_pair_invalid", status_code=409)
    if pending:
        raise HarnessError("The previous tool calls have no completed results. Resolve the previous run or start a fresh conversation.", code="context_tool_pair_invalid", status_code=409)
