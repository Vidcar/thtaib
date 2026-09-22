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
    archive_messages,
    message_resume_seed,
    open_tool_starts,
    partial_archive,
)


class ResumeProjection:
    def __init__(self, service: Any, thread_id: str, since: int) -> None:
        self.service = service
        self.thread_id = thread_id
        self.since = since
        self._started: set[tuple[Any, ...]] = set()

    def opening(self, options: dict[str, Any]) -> list[dict[str, Any]]:
        if self.since <= 0 or "tools" not in (options.get("channels") or []):
            return []
        wires = []
        for item in open_tool_starts(self.service.replay(self.thread_id, 0, self.since)):
            wire = copy.deepcopy(item)
            wire["seq"] = self.since
            if self.service.matches(wire, options):
                wires.append(wire)
        return wires

    def present(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        if self.since <= 0:
            return [item]
        method = item.get("method")
        params = item.get("params") or {}
        if method == "values" and not params.get("namespace"):
            return [self._values_with_partial(item)]
        if method != "messages":
            return [item]
        key = (tuple(params.get("namespace") or []), params.get("node"))
        data = params.get("data") or {}
        if data.get("event") == "message-start":
            self._started.add(key)
            return [item]
        if key in self._started:
            return [item]
        self._started.add(key)
        prefix = self._message_prefix(item)
        seed_seq = max(self.since, int(item.get("seq", self.since)) - 1)
        return [*message_resume_seed(prefix, seq=seed_seq), item]

    def _message_prefix(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        params = item.get("params") or {}
        namespace = tuple(params.get("namespace") or [])
        node = params.get("node")
        matched: list[dict[str, Any]] = []
        for event in self.service.replay(self.thread_id, 0, int(item.get("seq", 0)) - 1):
            if event.get("method") != "messages":
                continue
            event_params = event.get("params") or {}
            if tuple(event_params.get("namespace") or []) != namespace or event_params.get("node") != node:
                continue
            data = event_params.get("data") or {}
            if data.get("event") == "message-start":
                matched = [event]
            elif matched:
                matched.append(event)
        return matched

    def _values_with_partial(self, item: dict[str, Any]) -> dict[str, Any]:
        wire = copy.deepcopy(item)
        data = wire.setdefault("params", {}).setdefault("data", {})
        if not isinstance(data, dict):
            return wire
        started = 0
        binding = self.service.binding(self.thread_id)
        workbench = binding["snapshot"].get("workbench") or {}
        if isinstance(workbench.get("run_started_seq"), int):
            started = workbench["run_started_seq"]
        partials, incomplete = partial_archive(self.service.replay(self.thread_id, started, int(wire.get("seq", self.since))))
        if partials:
            data["messages"] = archive_messages(list(data.get("messages") or []), partials)
        if incomplete:
            current = data.setdefault("workbench", {})
            if isinstance(current, dict):
                current["incomplete_message_ids"] = sorted(set(current.get("incomplete_message_ids") or []) | set(incomplete))
        return wire
