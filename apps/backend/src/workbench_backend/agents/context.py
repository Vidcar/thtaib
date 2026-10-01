"""Observe actual context; Deep Agents owns compaction and input budgeting."""

from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.exceptions import ContextOverflowError
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel, Field

from workbench_backend.errors import HarnessError
from workbench_backend.inference.schemas import Deployment, SettingsBag
from workbench_backend.inference.request_projection import project_context_payload
from workbench_backend.inference.telemetry import request_purpose, current_request_purpose
from workbench_backend.inference.user_content import UserContentBlock, user_message_content


class ContextCapacityExceeded(HarnessError, ContextOverflowError):
    """A terminal native overflow translated at the application boundary."""


class ContextObservation(BaseModel):
    schema_version: int = 2
    purpose: Literal["work", "summary", "review", "probe"] = "work"
    capacity_tokens: int | None = None
    capacity_source: Literal["server_props.n_ctx", "unknown"] = "unknown"
    input_tokens: int = 0
    configured_output_tokens: int | None = None
    counting_basis: Literal["native", "estimated"] = "estimated"
    counting_method: str = "Deep Agents / LangChain approximate token counter; not tokenizer usage"
    fits: bool | None = None
    summarization_path: Literal["deepagents-upstream"] = "deepagents-upstream"
    notes: list[str] = Field(default_factory=list)


class SummaryDispatchModel(BaseChatModel):
    """Public model-call decorator for app cancellation and housekeeping visibility.

    Only the SDK's summarization model is decorated. Its prompt, settings,
    profile, retry policy and compaction mechanism remain upstream-owned.
    """

    delegate: BaseChatModel
    dispatch: Any = Field(exclude=True, repr=False)
    observer: Any = Field(default=None, exclude=True, repr=False)

    @property
    def _llm_type(self) -> str:
        return self.delegate._llm_type

    def _get_ls_params(self, **kwargs: Any) -> dict[str, Any]:
        return self.delegate._get_ls_params(**kwargs)

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> BaseMessage:
        with self.dispatch(), request_purpose("summary"):
            if self.observer is not None:
                self.observer(self._convert_input(input).to_messages())
            return self.delegate.invoke(input, config=config, **kwargs)

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> BaseMessage:
        with self.dispatch(), request_purpose("summary"):
            if self.observer is not None:
                self.observer(self._convert_input(input).to_messages())
            return await self.delegate.ainvoke(input, config=config, **kwargs)

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: Any = None, **kwargs: Any) -> ChatResult:
        result = self.invoke(messages, stop=stop, **kwargs)
        return ChatResult(generations=[ChatGeneration(message=result)])


def observe_context(
    *, deployment: Deployment, per_request: SettingsBag | None,
    system_prompt: str | None, task: str,
    content_blocks: list[UserContentBlock] | None, tool_count: int,
    output_schema: dict[str, Any] | None, continuing_thread: bool,
    history: list[BaseMessage] | None = None, tools: list[Any] | None = None,
) -> ContextObservation:
    capacity = deployment.server_props.n_ctx if deployment.server_props is not None else None
    capacity = capacity if type(capacity) is int and capacity > 0 else None
    from workbench_backend.inference.adapter import _reasoning_replay_scope
    messages = [*([SystemMessage(content=system_prompt)] if system_prompt else []),
                *(history or []), HumanMessage(content=user_message_content(task, content_blocks))]
    payload = project_context_payload(messages, tools=tools, response_format=output_schema,
                                      reasoning_scope=_reasoning_replay_scope(deployment, per_request))
    output = per_request.applied.get("max_tokens") if per_request is not None else None
    notes = []
    if capacity is None:
        notes.append("Running capacity is unknown; Deep Agents uses its native fallback.")
    if continuing_thread:
        notes.append("Context reduction uses the existing Deep Agents checkpoint thread.")
    return ContextObservation(capacity_tokens=capacity,
        capacity_source="server_props.n_ctx" if capacity is not None else "unknown",
        input_tokens=estimate_payload(payload), configured_output_tokens=output if type(output) is int else None,
        notes=notes)


def estimate_payload(payload: Any) -> int:
    """Use the SDK counter for advisory estimates, with no application veto."""
    if isinstance(payload, dict) and isinstance(payload.get("messages"), list):
        messages = []
        for message in payload["messages"]:
            if isinstance(message, dict) and isinstance(message.get("reasoning_content"), str):
                message = dict(message)
                reasoning = message["reasoning_content"]
                content = message.get("content")
                message["content"] = ([{"type": "text", "text": reasoning}, *content]
                    if isinstance(content, list) else reasoning + "\n" + (content or ""))
            messages.append(message)
        if payload.get("response_format") is not None:
            messages.append(SystemMessage(content=json.dumps(payload["response_format"], ensure_ascii=False, default=str)))
        return count_tokens_approximately(messages, tools=payload.get("tools"))
    if isinstance(payload, BaseMessage):
        return count_tokens_approximately([payload])
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
    return count_tokens_approximately([HumanMessage(content=content)])


def count_context_tokens(messages: list[Any], *, tools: list[Any] | None = None) -> int:
    return count_tokens_approximately(messages, tools=tools)


def token_counter_for_model(model: Any, *, response_format: Any = None, message_projection: Any = None,
                            request_message_projection: Any = None, extra_tools: list[Any] | None = None,
                            tools_projection: Any = None, request_settings: dict[str, Any] | None = None) -> Any:
    """Configure the SDK counter with native template counting when available."""
    projection = getattr(model, "project_context_payload", project_context_payload)
    native_counter = getattr(model, "count_input_tokens", None)
    omitted_tools = object()

    def count(messages: list[Any], *, tools: Any = omitted_tools) -> int:
        full_request = tools is not omitted_tools
        projected = message_projection(messages) if message_projection is not None else messages
        if full_request and request_message_projection is not None:
            projected = request_message_projection(projected)
        counted_tools = [*(tools or []), *(extra_tools or [])] if full_request else None
        if full_request and tools_projection is not None:
            counted_tools = tools_projection(counted_tools)
        payload = projection(projected, tools=counted_tools,
            response_format=response_format if full_request else None)
        if full_request and request_settings:
            payload.update(request_settings)
        native = native_counter(payload) if callable(native_counter) else None
        return native if type(native) is int else estimate_payload(payload)
    return count


def observe_payload(base: ContextObservation, payload: dict[str, Any], *, native_counter: Any = None) -> ContextObservation:
    observation = base.model_copy(deep=True)
    observation.purpose = current_request_purpose()
    native = native_counter(payload) if callable(native_counter) else None
    measured = type(native) is int
    observation.input_tokens = native if measured else estimate_payload(payload)
    observation.counting_basis = "native" if measured else "estimated"
    observation.counting_method = ("llama.cpp input_tokens: selected native template, tools and media"
        if measured else "Deep Agents / LangChain approximate token counter; not tokenizer usage")
    observation.fits = (observation.input_tokens <= observation.capacity_tokens
        if measured and observation.capacity_tokens is not None else None)
    return observation


def _native_text_history(message: BaseMessage, blocks: list[Any]) -> bool:
    """Recognize SDK text and duplicate call blocks, without rewriting history.

    llama.cpp accepts OpenAI text blocks even when its template reports string
    content only. The pinned serializer moves canonical AI call blocks into
    ``tool_calls``. Only accept those duplicates when the retained call agrees;
    other structured content still needs explicit template support.
    """
    calls = getattr(message, "tool_calls", [])
    return all(
        isinstance(block, dict) and (
            block.get("type") == "text" and isinstance(block.get("text"), str)
            or message.type == "ai" and block.get("type") == "tool_call"
            and any(all(block.get(key) == call.get(key) for key in ("id", "name", "args"))
                    for call in calls)
        ) for block in blocks
    )


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
            if (blocks and props.chat_template_caps.get("supports_typed_content") is False
                    and not _native_text_history(message, blocks)):
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
