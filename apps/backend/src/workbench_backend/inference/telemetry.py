"""Request-scoped llama.cpp measurements from its existing response stream."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from workbench_backend.inference.ids import utc_now


class RequestTelemetry:
    """Observe server counts, never count chunks or query shared server slots.

    b11045 reports processed prompt tokens separately from cache reuse. During
    prefill only prompt_progress.total is the complete prompt; once generation
    starts cache_n + prompt_n is complete. predicted_per_second uses the
    server's generation interval, which excludes its first generated token.
    """

    def __init__(self, observer: Callable[[dict[str, Any]], None]) -> None:
        self.observer = observer
        self.request_id = uuid4().hex
        self.response_id: str | None = None
        self.latest: dict[str, Any] | None = None
        self.last_emitted = 0.0
        self.last_phase: str | None = None
        observer({"request_id": self.request_id, "reset": True})

    def receive(self, response: dict[str, Any]) -> None:
        response_id = response.get("id")
        if not isinstance(response_id, str) or not response_id:
            return
        if self.response_id is not None and response_id != self.response_id:
            return
        self.response_id = response_id
        timings = response.get("timings")
        progress = response.get("prompt_progress")
        if not isinstance(timings, dict):
            return
        output = _count(timings.get("predicted_n"))
        if output is None:
            return
        phase = "generating" if output > 0 else "prompt_processing"
        input_tokens = _count(progress.get("total")) if isinstance(progress, dict) else None
        if input_tokens is None and output > 0:
            cached, processed = _count(timings.get("cache_n")), _count(timings.get("prompt_n"))
            if cached is not None and processed is not None:
                input_tokens = cached + processed
        usage = response.get("usage")
        if isinstance(usage, dict) and _count(usage.get("prompt_tokens")) is not None:
            input_tokens = usage["prompt_tokens"]
        elapsed_ms = _number(timings.get("predicted_ms"))
        speed = _number(timings.get("predicted_per_second"))
        # A zero-duration first token carries no meaningful generation rate.
        if output < 2 or elapsed_ms is None or elapsed_ms <= 0:
            speed = None
        if self.latest is not None and output < self.latest["output_tokens"]:
            return
        self.latest = {
            "request_id": self.request_id,
            "phase": phase,
            "input_tokens": input_tokens,
            "output_tokens": output,
            "context_used_tokens": input_tokens + output if input_tokens is not None else None,
            "elapsed_seconds": elapsed_ms / 1000 if elapsed_ms is not None else 0.0,
            "tokens_per_second": speed,
            "basis": "llama_cpp_timings",
            "interval": "current_model_call_generation",
            "measured_at": utc_now(),
        }
        self._publish()

    def finish(self, *, interrupted: bool = False) -> None:
        if self.latest is None:
            return
        self.latest = {**self.latest, "phase": "interrupted" if interrupted else "completed",
                       "interval": "last_model_call_generation", "measured_at": utc_now()}
        self._publish(force=True)

    def _publish(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if self.latest is not None and (force or self.last_phase != self.latest["phase"] or now - self.last_emitted >= 0.25):
            self.observer(dict(self.latest))
            self.last_emitted = now
            self.last_phase = self.latest["phase"]


def _count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _number(value: Any) -> float | None:
    if type(value) not in {int, float}:
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) and number >= 0 else None
