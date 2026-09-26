"""Pinned chat-completions serialization shared by context estimates and sending.

Use LangChain's installed serializer, including its v1-content normalization.
Only Workbench's supported reasoning replay and tool-image routing are added.
No checkpoint message is rewritten here.
"""
from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, convert_to_messages
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai.chat_models.base import _convert_message_to_dict, _convert_from_v1_to_chat_completions

from workbench_backend.errors import HarnessError
from workbench_backend.inference.image_validation import MAX_TOOL_IMAGE_BYTES_PER_REQUEST, validate_image_data_url


ReasoningReplayScope = Literal["none", "current_turn", "full_history"]
TOOL_CONTEXT_MARKER = "workbench_tool_context"

def project_outbound_payload(payload: dict[str, Any], messages: Any, *, reasoning_scope: ReasoningReplayScope) -> dict[str, Any]:
    """Pure final projection used by the real adapter and its budget counter."""
    payload = deepcopy(payload)
    # A malformed historical call may be closed by native error ToolMessages.
    # Send an inert protocol placeholder; keep original partial arguments in state.
    # This never creates a tool invocation or changes a successful result.
    source = _source_messages(messages) or []
    failed_ids = {message.tool_call_id for message in source
                  if message.type == "tool" and getattr(message, "status", None) == "error"}
    invalid_ids = {call["id"] for message in source if isinstance(message, AIMessage)
                   for call in message.invalid_tool_calls if call.get("id") in failed_ids}
    for outbound in payload.get("messages", []):
        for call in outbound.get("tool_calls", []):
            if call.get("id") in invalid_ids:
                call["function"]["arguments"] = "{}"
                call["function"]["name"] = call["function"].get("name") or "unknown"
    # Replay before inserting tool-image user messages so identities cannot shift.
    _add_reasoning_replay(payload, messages, scope=reasoning_scope)
    _project_tool_images(payload)
    if payload.get("tools") == []:
        payload.pop("tools")
        payload.pop("tool_choice", None)
    return payload


def project_context_payload(messages: list[Any], *, tools: list[Any] | None = None,
                            response_format: Any = None, reasoning_scope: ReasoningReplayScope = "none") -> dict[str, Any]:
    """Project native messages with the pinned adapter's outbound serializer."""
    native = convert_to_messages(messages)
    payload: dict[str, Any] = {"messages": [
        _convert_message_to_dict(_convert_from_v1_to_chat_completions(message))
        if isinstance(message, AIMessage) else _convert_message_to_dict(message)
        for message in native
    ]}
    if tools:
        payload["tools"] = [convert_to_openai_tool(tool) for tool in tools]
    if response_format is not None:
        payload["response_format"] = response_format
    return project_outbound_payload(payload, native, reasoning_scope=reasoning_scope)


def _project_tool_images(payload: dict[str, Any]) -> None:
    """Move tool images behind a complete tool-result batch for chat-completions.

    LangChain converts image blocks to `image_url`, but leaves them inside a
    `tool` message. llama.cpp's OpenAI-compatible endpoint receives the image
    as a following `user` message, while the tool result and call ID remain in
    their original order. This changes only the outbound request, not graph
    state or checkpoint messages.
    """

    messages = payload.get("messages")
    if not isinstance(messages, list):
        return
    projected: list[dict[str, Any]] = []
    pending: list[tuple[str, dict[str, Any]]] = []
    image_bytes = 0

    def flush() -> None:
        if not pending:
            return
        sources = ", ".join(dict.fromkeys(source for source, _ in pending))
        projected.append({
            "role": "user",
            "content": [
                {"type": "text", "text": f"<tool_response>\nImage result from tool call(s) {sources}:"},
                *(block for _, block in pending),
                {"type": "text", "text": "\n</tool_response>"},
            ],
        })
        pending.clear()

    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "tool":
            flush()
            projected.append(message)
            continue
        content = message.get("content")
        if not isinstance(content, list):
            projected.append(message)
            continue
        kept: list[Any] = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "image_url":
                kept.append(block)
                continue
            image_url = block.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else image_url
            if not isinstance(url, str):
                raise HarnessError("A tool returned an invalid image block.", code="tool_image_invalid", status_code=422)
            try:
                image_bytes += validate_image_data_url(url)
            except ValueError as exc:
                raise HarnessError(str(exc), code="tool_image_invalid", status_code=422) from exc
            if image_bytes > MAX_TOOL_IMAGE_BYTES_PER_REQUEST:
                raise HarnessError("Too many image bytes for one model request. Read fewer images or summarize the conversation.",
                    code="tool_images_too_large", status_code=422)
            pending.append((str(message.get("tool_call_id") or "unknown"), block))
        if len(kept) == len(content):
            projected.append(message)
        else:
            projected.append({**message, "content": kept or "Image delivered in the following message."})
    flush()
    payload["messages"] = projected


def _add_reasoning_replay(payload: dict[str, Any], input_: Any, *, scope: ReasoningReplayScope) -> None:
    messages = payload.get("messages")
    source = _source_messages(input_)
    if not isinstance(messages, list) or source is None:
        return
    # Full-history preservation and replay within a tool cycle are distinct.
    # Qwen's native template retains reasoning after the latest actual query,
    # even when earlier-turn preservation is disabled. Tool-image context is
    # application supplied and must not move that user-query boundary.
    last_query = max((index for index, message in enumerate(source)
        if message.type == "human" and not message.additional_kwargs.get(TOOL_CONTEXT_MARKER)), default=-1)
    for index, (outbound, original) in enumerate(zip(messages, source, strict=False)):
        if not isinstance(outbound, dict) or not isinstance(original, AIMessage):
            continue
        outbound.pop("reasoning_content", None)
        if scope == "none" or scope == "current_turn" and index <= last_query:
            continue
        reasoning = original.additional_kwargs.get("reasoning_content")
        if reasoning is None:
            reasoning = original.additional_kwargs.get("reasoning")
        if reasoning not in (None, ""):
            outbound["reasoning_content"] = reasoning


def _source_messages(input_: Any) -> Sequence[BaseMessage] | None:
    if (
        isinstance(input_, Sequence)
        and not isinstance(input_, str)
        and all(isinstance(message, BaseMessage) for message in input_)
    ):
        return input_
    return None
