"""Present a subscription that joins at a cursor instead of replaying tokens.

The durable log still starts at seq 0 for recovery. A client that already
painted the snapshot passes `since` and only receives later events. The
message assembler on that client has not seen message-start, so the first
continuation is preceded by the text already in the snapshot.
"""
from __future__ import annotations

import copy
from typing import Any

from workbench_backend.interaction.projection import (
    PartialArchiveAccumulator,
    archive_messages,
    message_resume_seed,
)


class ResumeProjection:
    def __init__(self, service: Any, thread_id: str, since: int, *, run_started_seq: int = 0) -> None:
        self.service = service
        self.thread_id = thread_id
        self.since = since
        self._started: set[tuple[Any, ...]] = set()
        self._run_started_seq = max(0, run_started_seq)
        self._observed_through = self._run_started_seq
        self._prepared = False
        self._partial = PartialArchiveAccumulator()
        self._message_prefixes: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        self._open_tools: dict[str, dict[str, Any]] = {}

    def _prepare(self) -> None:
        if self._prepared or self.since <= 0:
            return
        self._replay_through(self.since)
        self._prepared = True

    def _replay_through(self, through: int) -> None:
        if through <= self._observed_through:
            return
        for item in self.service.replay(self.thread_id, self._observed_through, through):
            self._observe(item)

    def _observe(self, item: dict[str, Any]) -> None:
        seq = int(item.get("seq", self._observed_through))
        if seq <= self._observed_through:
            return
        self._observed_through = seq
        self._partial.consume(item)
        params = item.get("params") or {}
        data = params.get("data") or {}
        if item.get("method") == "messages":
            key = (tuple(params.get("namespace") or []), params.get("node"))
            if data.get("event") == "message-start":
                self._message_prefixes[key] = [item]
            elif key in self._message_prefixes:
                self._message_prefixes[key].append(item)
            if data.get("event") == "message-finish":
                self._message_prefixes.pop(key, None)
        elif item.get("method") == "tools":
            call_id = data.get("tool_call_id")
            if isinstance(call_id, str) and call_id:
                if data.get("event") == "tool-started":
                    self._open_tools[call_id] = item
                elif data.get("event") in {"tool-finished", "tool-error"}:
                    self._open_tools.pop(call_id, None)

    def _reset_for_run(self, started: int, through: int) -> None:
        self._run_started_seq = max(0, started)
        self._observed_through = self._run_started_seq
        self._partial = PartialArchiveAccumulator()
        self._message_prefixes.clear()
        self._open_tools.clear()
        self._started.clear()
        self._replay_through(through)

    def opening(self, options: dict[str, Any]) -> list[dict[str, Any]]:
        if self.since <= 0 or "tools" not in (options.get("channels") or []):
            return []
        self._prepare()
        wires = []
        for item in self._open_tools.values():
            wire = copy.deepcopy(item)
            wire["seq"] = self.since
            # This is a reconstruction for a subscriber that joined after the
            # original start. Give it a stable identity distinct from the raw
            # event, so the SDK can pass it through its cursor boundary once.
            wire["event_id"] = f"resume:tool:{self.thread_id}:{item.get('event_id', item.get('seq'))}"
            if self.service.matches(wire, options):
                wires.append(wire)
        return wires

    def consume(self, item: dict[str, Any], *, matches: bool) -> list[dict[str, Any]]:
        if self.since <= 0:
            return [item] if matches else []
        self._prepare()
        method = item.get("method")
        params = item.get("params") or {}
        if method == "values" and not params.get("namespace"):
            data = params.get("data") or {}
            workbench = (data.get("workbench") or {}) if isinstance(data, dict) else {}
            started = workbench.get("run_started_seq") if isinstance(workbench, dict) else None
            if isinstance(started, int) and started != self._run_started_seq:
                self._reset_for_run(started, int(item.get("seq", self.since)) - 1)
        if not matches:
            self._observe(item)
            return []
        if params.get("measurement"):
            self._observe(item)
            return [item]
        if method == "values" and not params.get("namespace"):
            self._observe(item)
            return [self._values_with_partial(item)]
        if method != "messages":
            self._observe(item)
            return [item]
        key = (tuple(params.get("namespace") or []), params.get("node"))
        data = params.get("data") or {}
        if data.get("event") == "message-start":
            self._started.add(key)
            self._observe(item)
            return [item]
        if key in self._started:
            self._observe(item)
            return [item]
        self._started.add(key)
        prefix = self._message_prefixes.get(key, [])
        seed_seq = max(self.since, int(item.get("seq", self.since)) - 1)
        seeded = message_resume_seed(prefix, seq=seed_seq)
        self._observe(item)
        return [*seeded, item]

    def present(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        return self.consume(item, matches=True)

    def _values_with_partial(self, item: dict[str, Any]) -> dict[str, Any]:
        wire = copy.deepcopy(item)
        data = wire.setdefault("params", {}).setdefault("data", {})
        if not isinstance(data, dict):
            return wire
        partials, incomplete = self._partial.snapshot()
        if partials:
            data["messages"] = archive_messages(list(data.get("messages") or []), partials)
        if incomplete:
            current = data.setdefault("workbench", {})
            if isinstance(current, dict):
                current["incomplete_message_ids"] = sorted(set(current.get("incomplete_message_ids") or []) | set(incomplete))
        return wire
