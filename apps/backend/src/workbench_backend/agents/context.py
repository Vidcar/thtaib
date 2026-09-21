"""Context observations and preflight checks for one harness request."""

from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from deepagents.middleware.summarization import SummarizationMiddleware

from pydantic import BaseModel, Field

from workbench_backend.errors import HarnessError
from workbench_backend.inference.schemas import Deployment, SettingsBag
from workbench_backend.inference.user_content import UserContentBlock, user_message_content

TOKEN_MARGIN_RATIO = 0.08
DEFAULT_OUTPUT_RESERVATION = 512


class BudgetedSummarizationMiddleware(SummarizationMiddleware):
    """Use Deep Agents' one compaction path with our already-reserved input limit.

    Pinned deepagents 0.7.15 otherwise subtracts output and 5% again from the
    model profile. Only that version-sensitive budget seam is overridden.
    """

    @property
    def name(self) -> str:
        # Upstream uses subclass names; explicitly replace the default entry.
        return "SummarizationMiddleware"

    def __init__(self, *args: Any, allowed_tools: set[str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.allowed_tools = allowed_tools

    def _selected_request(self, request: Any) -> Any:
        if self.allowed_tools is None:
            return request
        from workbench_backend.agents.tools import tool_name
        return request.override(tools=[tool for tool in request.tools if tool_name(tool) in self.allowed_tools])

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        return super().wrap_model_call(self._selected_request(request), handler)

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        return await super().awrap_model_call(self._selected_request(request), handler)

    def _input_budget(self, request: Any) -> int | None:
        profile = request.model.profile or {}
        value = profile.get("max_input_tokens")
        return value if type(value) is int else None


class ContextObservation(BaseModel):
    schema_version: int = 1
    capacity_tokens: int | None = None
    capacity_source: Literal["server_props.n_ctx", "unknown"] = "unknown"
    output_reservation_tokens: int = DEFAULT_OUTPUT_RESERVATION
    estimated_input_tokens: int = 0
    usable_input_tokens: int | None = None
    margin_tokens: int = 0
    fits: bool | None = None
    counting_method: str = "UTF-8 character estimate (3 chars/token), serialized messages/tools/schema, 2048 tokens/image, 8% capacity margin; not tokenizer usage"
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
    reservation = _output_reservation(per_request)
    messages = [*(history or []), HumanMessage(content=user_message_content(task, content_blocks))]
    payload = {"messages": messages, "system": system_prompt or "", "tools": tools or [], "response_format": output_schema}
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
        raise HarnessError(
            "The selected setup does not have enough observed context for the retained conversation. "
            "Choose a larger context, compact while the previous setup still fits, or start a fresh conversation. No history was removed.",
            code="context_capacity_exceeded",
            status_code=409,
            details=observation.model_dump(mode="json"),
        )


def _capacity(deployment: Deployment) -> tuple[int | None, Literal["server_props.n_ctx", "unknown"]]:
    if deployment.server_props is not None and deployment.server_props.n_ctx:
        return deployment.server_props.n_ctx, "server_props.n_ctx"
    return None, "unknown"


def _output_reservation(per_request: SettingsBag | None) -> int:
    value: Any = None
    if per_request is not None:
        value = per_request.applied.get("max_completion_tokens", per_request.applied.get("max_tokens"))
    if isinstance(value, int) and value > 0:
        return value
    return DEFAULT_OUTPUT_RESERVATION


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
            value = value.model_dump(exclude={"usage_metadata", "response_metadata", "id"})
        elif hasattr(value, "args_schema"):
            value = convert_to_openai_tool(value)
        if isinstance(value, dict):
            if value.get("type") in {"image_url", "image"}:
                images += 1
                return {"type": "image", "content": "[image]"}
            return {key: simplify(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [simplify(item) for item in value]
        return value
    serialized = json.dumps(simplify(payload), ensure_ascii=False, default=str, separators=(",", ":"))
    return _estimate_tokens(serialized) + images * 2048


def count_context_tokens(messages: list[Any], *, tools: list[Any] | None = None) -> int:
    return estimate_payload({"messages": messages, "tools": tools or []})


def observe_payload(base: ContextObservation, payload: dict[str, Any]) -> ContextObservation:
    observation = base.model_copy(deep=True)
    observation.estimated_input_tokens = estimate_payload({key: value for key, value in payload.items() if key in {"messages", "tools", "response_format"}})
    observation.fits = None if observation.usable_input_tokens is None else observation.estimated_input_tokens <= observation.usable_input_tokens
    return observation


def validate_retained_messages(deployment: Deployment, messages: list[BaseMessage]) -> None:
    """Reject known setup mismatches and incomplete call/result pairs without rewriting history."""
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
        if getattr(message, "invalid_tool_calls", None):
            raise HarnessError("The retained conversation contains an invalid tool call.", code="context_invalid_tool_call", status_code=409)
        calls = getattr(message, "tool_calls", [])
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
