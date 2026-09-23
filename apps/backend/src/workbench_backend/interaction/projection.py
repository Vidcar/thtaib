"""Controlled display projection of public native protocol events."""
from __future__ import annotations

import time
from typing import Any

from langchain_protocol import Event
from langchain_core.messages import BaseMessage, ToolMessage
from langgraph.types import Command
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


def message_resume_seed(prefix: list[dict[str, Any]], *, seq: int) -> list[dict[str, Any]]:
    """One message-start and the current blocks, so a later delta appends.

    The desktop assembler starts empty. A subscriber that joins after
    message-start would otherwise treat the next delta as the whole answer.
    """
    start = next((item for item in prefix if item.get("params", {}).get("data", {}).get("event") == "message-start"), None)
    if start is None:
        return []
    blocks: dict[int, dict[str, Any]] = {}
    for item in prefix:
        _accumulate_message_block(blocks, item.get("params", {}).get("data") or {})
    params = dict(start["params"])
    seeds = [{"type": "event", "method": "messages", "seq": seq, "params": params}]
    for index in sorted(blocks):
        block = blocks[index]
        if not _block_has_visible_content(block):
            continue
        seed_params: dict[str, Any] = {
            "namespace": list(params.get("namespace") or []),
            "timestamp": params.get("timestamp", 0),
            "data": {"event": "content-block-start", "index": index, "content": block},
        }
        if "node" in params:
            seed_params["node"] = params["node"]
        seeds.append({"type": "event", "method": "messages", "seq": seq, "params": seed_params})
    return seeds


def open_tool_starts(events: Any) -> list[dict[str, Any]]:
    """tool-started events that have not finished by the end of `events`."""
    open_calls: dict[str, dict[str, Any]] = {}
    for item in events:
        if item.get("method") != "tools":
            continue
        data = item.get("params", {}).get("data") or {}
        call_id = data.get("tool_call_id")
        if not isinstance(call_id, str) or not call_id:
            continue
        if data.get("event") == "tool-started":
            open_calls[call_id] = item
        elif data.get("event") in {"tool-finished", "tool-error"}:
            open_calls.pop(call_id, None)
    return list(open_calls.values())


def _accumulate_message_block(blocks: dict[int, dict[str, Any]], data: dict[str, Any]) -> None:
    event_name = data.get("event")
    index = data.get("index", 0)
    if not isinstance(index, int) or isinstance(index, bool):
        index = 0
    if event_name == "content-block-finish" and isinstance(data.get("content"), dict):
        blocks[index] = dict(data["content"])
        return
    if event_name != "content-block-delta":
        return
    delta = data.get("delta") or {}
    kind = delta.get("type")
    current = blocks.get(index, {})
    if kind == "text-delta":
        blocks[index] = {"type": "text", "text": f"{current.get('text', '')}{delta.get('text', '')}"}
    elif kind == "reasoning-delta":
        blocks[index] = {"type": "reasoning", "reasoning": f"{current.get('reasoning', '')}{delta.get('reasoning', '')}"}
    elif kind == "block-delta" and isinstance(delta.get("fields"), dict):
        # Tool-call deltas already carry the accumulated arguments.
        blocks[index] = dict(delta["fields"])


def _block_has_visible_content(block: dict[str, Any]) -> bool:
    if block.get("text") or block.get("reasoning") or block.get("args"):
        return True
    return block.get("type") not in {None, "text", "reasoning"}


def partial_archive(events: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Use the public upstream projection to retain interrupted real output.

    No graph/model pump is bound. Reading text/reasoning projections cannot
    invoke anything: their only input is the already-persisted event iterator.
    Incomplete tool arguments remain inert content blocks, never executable calls.
    """
    active: dict[tuple[str, ...], ChatModelStream] = {}
    blocks_by_namespace: dict[tuple[str, ...], dict[int, dict[str, Any]]] = {}
    finished: dict[str, dict[str, Any]] = {}
    for item in events:
        if finished and item["method"] == "values" and not item["params"].get("namespace"):
            # A completed message event can precede its graph values update.
            # Keep that finished output only until the authoritative complete
            # message arrives, so hydration cannot briefly drop the answer.
            for message in item["params"].get("data", {}).get("messages", []):
                if isinstance(message, dict):
                    finished.pop(message.get("id"), None)
        if item["method"] != "messages":
            continue
        params = item["params"]
        key = tuple(params.get("namespace", []))
        data = params["data"]
        if data.get("event") == "message-start":
            active[key] = ChatModelStream(namespace=list(key), message_id=data.get("id"))
            blocks_by_namespace[key] = {}
        projection = active.get(key)
        if projection is None:
            continue
        if data.get("event") == "error":
            # Failure is owned by the application run. Keep the last observed
            # projections readable without turning the error into completion.
            continue
        projection.dispatch(data)
        _accumulate_message_block(blocks_by_namespace[key], data)
        if data.get("event") == "message-finish":
            if not key and projection.output_message is not None:
                message = message_dict(projection.output_message)
                if message is not None and message.get("id"):
                    finished[message["id"]] = message
            active.pop(key, None)
            blocks_by_namespace.pop(key, None)
    messages, incomplete = list(finished.values()), []
    for namespace, projection in active.items():
        if namespace or not projection.message_id:
            continue
        blocks = []
        text, reasoning = "".join(projection.text), "".join(projection.reasoning)
        if reasoning:
            blocks.append({"type": "reasoning", "reasoning": reasoning})
        if text:
            blocks.append({"type": "text", "text": text})
        # Native block deltas carry complete argument snapshots. Retain those
        # bytes as display-only chunks, including unfinished JSON. Do not parse
        # them into tool_calls or claim that the tool was ever executed.
        for _index, block in sorted(blocks_by_namespace[namespace].items()):
            if block.get("type") in {"tool_call_chunk", "tool_call", "invalid_tool_call"}:
                blocks.append({"type": "tool_call_chunk", **{
                    key: block[key] for key in ("id", "name", "args") if key in block
                }})
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
        if method == "tools" and isinstance(data, dict) and isinstance(data.get("output"), Command):
            # Framework tools such as write_todos return a graph state update.
            # Its public tool reply is displayable; routing and other state are
            # execution-only and must never enter the renderer replay archive.
            update = data["output"].update
            messages = update.get("messages", []) if isinstance(update, dict) else []
            messages = [messages] if isinstance(messages, ToolMessage) else messages if isinstance(messages, (list, tuple)) else []
            public_output = next((message for message in messages if isinstance(message, ToolMessage)
                                  and message.tool_call_id == data.get("tool_call_id")), None)
            data = {**data, "output": public_output}
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
