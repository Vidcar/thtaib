"""Controlled display projection of public native protocol events."""
from __future__ import annotations

import time
from typing import Any

from langchain_protocol import Event
from langchain_core.messages import BaseMessage
from langchain_core.language_models.chat_model_stream import ChatModelStream


def event(method: str, data: Any, namespace: list[str] | None = None) -> Event:
    return {"type": "event", "method": method, "params": {
        "namespace": namespace or [], "timestamp": int(time.time() * 1000), "data": data,
    }}  # type: ignore[return-value]


def wire_value(value: Any) -> Any:
    if isinstance(value, BaseMessage):
        return message_dict(value)
    if isinstance(value, dict):
        return {key: wire_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [wire_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported public protocol value: {type(value).__name__}")


def message_dict(value: Any) -> dict[str, Any] | None:
    raw = value if isinstance(value, dict) else value.model_dump(mode="json")
    if raw.get("type") not in {"human", "ai", "tool"}:
        return None
    if raw.get("additional_kwargs", {}).get("lc_source") == "summarization":
        return None
    if isinstance(value, BaseMessage):
        # A provider may keep reasoning outside `content` (for example in
        # additional_kwargs). The public projection is the canonical
        # cross-provider representation used by LangChain's v3 event bridge.
        # Keep ordinary text as a string for existing consumers, but persist
        # the full blocks whenever that projection contains reasoning.
        blocks = value.content_blocks
        if any(block.get("type") == "reasoning" for block in blocks):
            raw["content"] = blocks
    return {key: raw[key] for key in (
        "id", "type", "content", "name", "tool_calls", "invalid_tool_calls", "tool_call_id", "status",
    ) if key in raw and raw[key] is not None}


def archive_messages(existing: list[dict[str, Any]], values: list[Any]) -> list[dict[str, Any]]:
    """Index complete upstream messages; never assemble text/tool deltas here."""
    result = [dict(item) for item in existing]
    positions = {item["id"]: index for index, item in enumerate(result) if item.get("id")}
    for value in values:
        item = message_dict(value)
        if item is None or not item.get("id"):
            continue
        index = positions.get(item["id"])
        if index is None:
            positions[item["id"]] = len(result)
            result.append(item)
        else:
            result[index] = item
    return result


def partial_archive(events: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Use the public upstream projection to retain interrupted real output.

    No graph/model pump is bound. Reading text/reasoning projections cannot
    invoke anything: their only input is the already-persisted event iterator.
    Incomplete tool arguments remain in durable replay, never executable calls.
    """
    active: dict[tuple[str, ...], ChatModelStream] = {}
    for item in events:
        if item["method"] != "messages":
            continue
        params = item["params"]
        key = tuple(params.get("namespace", []))
        data = params["data"]
        if data.get("event") == "message-start":
            active[key] = ChatModelStream(namespace=list(key), message_id=data.get("id"))
        projection = active.get(key)
        if projection is None:
            continue
        if data.get("event") == "error":
            # Failure is owned by the application run. Keep the last observed
            # projections readable without turning the error into completion.
            continue
        projection.dispatch(data)
        if data.get("event") == "message-finish":
            active.pop(key, None)
    messages, incomplete = [], []
    for namespace, projection in active.items():
        if namespace or not projection.message_id:
            continue
        blocks = []
        text, reasoning = "".join(projection.text), "".join(projection.reasoning)
        if reasoning:
            blocks.append({"type": "reasoning", "reasoning": reasoning})
        if text:
            blocks.append({"type": "text", "text": text})
        incomplete.append(projection.message_id)
        if blocks:
            messages.append({"type": "ai", "id": projection.message_id, "content": blocks})
    return messages, incomplete


def native_event(raw: dict[str, Any]) -> list[Event]:
    """Python v3 already normalizes content blocks; adapt local tuple to wire."""
    method = raw.get("method")
    params = raw.get("params", {})
    data = params.get("data")
    metadata: dict[str, Any] = {}
    if isinstance(data, tuple):
        data, metadata = data
    if metadata.get("lc_source") == "summarization":
        return []
    namespace = params.get("namespace", [])
    if method == "lifecycle" and namespace:
        # Root completion is the application's confirmed worker outcome.
        # Nested discovery keeps native identity/causation for scoped selectors.
        public = {key: wire_value(data[key]) for key in ("event", "graph_name", "cause", "error") if key in data}
        projected = event(method, public, namespace)
        for key in ("timestamp", "node"):
            if key in params:
                projected["params"][key] = params[key]
        return [projected]
    if method in {"messages", "tools"}:
        projected = event(method, wire_value(data), namespace)
        projected["params"]["timestamp"] = params.get("timestamp", projected["params"]["timestamp"])
        # Preserve upstream graph identity without exporting callback/config data.
        if metadata.get("langgraph_node"):
            projected["params"]["node"] = metadata["langgraph_node"]
        return [projected]
    if method == "values":
        interrupts = params.get("interrupts") or []
        result = []
        for interrupt in interrupts:
            ident = interrupt.get("id") if isinstance(interrupt, dict) else getattr(interrupt, "id", None)
            value = interrupt.get("value") if isinstance(interrupt, dict) else getattr(interrupt, "value", None)
            if ident:
                result.append(event("input.requested", {"interrupt_id": ident, "payload": value}, namespace))
        return result
    # Graph files, runtime configuration, checkpoints and private state are not
    # renderer data. Product projections have explicit owners in service.py.
    return []
