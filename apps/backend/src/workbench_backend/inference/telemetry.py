"""Request-scoped llama.cpp measurements from its existing response stream."""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from workbench_backend.inference.ids import utc_now


_logger = logging.getLogger(__name__)


class LatestGenerationPublisher:
    """Record measurements immediately and publish only the newest live value.

    Publication may use the application store, so it runs independently of the
    model call. A request reset and its latest value are retained separately to
    preserve the model-call boundary without queuing every intermediate value.
    """

    def __init__(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._callback = callback
        self._condition = threading.Condition()
        self._latest: dict[str, Any] | None = None
        self._request_id: str | None = None
        self._pending_reset: dict[str, Any] | None = None
        self._pending_sample: dict[str, Any] | None = None
        self._publishing = False
        self._closed = False
        self._publication_disabled = False
        self._worker: threading.Thread | None = None

    def publish(self, sample: dict[str, Any]) -> None:
        recorded = dict(sample)
        request_id = recorded.get("request_id")
        with self._condition:
            if self._closed:
                return
            if recorded.get("reset"):
                self._request_id = request_id
                if not self._publication_disabled:
                    self._pending_reset = recorded
                    self._pending_sample = None
            elif request_id == self._request_id:
                if not self._publication_disabled:
                    self._pending_sample = recorded
            else:
                return
            self._latest = recorded
            if self._worker is None and not self._publication_disabled:
                self._worker = threading.Thread(target=self._drain, name="generation-measurements", daemon=True)
                try:
                    self._worker.start()
                except Exception:  # noqa: BLE001 - preserve the sample if publishing cannot start
                    self._publication_disabled = True
                    self._pending_reset = None
                    self._pending_sample = None
                    self._worker = None
            self._condition.notify()

    def latest_sample(self) -> dict[str, Any] | None:
        with self._condition:
            return dict(self._latest) if self._latest is not None else None

    def wait_idle(self, timeout: float) -> bool:
        """Wait for a test or diagnostic, never from the generation path."""
        with self._condition:
            return self._condition.wait_for(
                lambda: not self._publishing and self._pending_reset is None and self._pending_sample is None,
                timeout=timeout,
            )

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._pending_reset = None
            self._pending_sample = None
            self._condition.notify_all()

    def _drain(self) -> None:
        reported_error = False
        while True:
            with self._condition:
                while not self._closed and self._pending_reset is None and self._pending_sample is None:
                    self._condition.wait()
                if self._closed:
                    self._condition.notify_all()
                    return
                if self._pending_reset is not None:
                    sample = self._pending_reset
                    self._pending_reset = None
                else:
                    sample = self._pending_sample
                    self._pending_sample = None
                self._publishing = True
            try:
                # An in-flight callback can become stale while a newer request
                # starts. The owner also checks request identity before applying.
                self._callback(dict(sample))
                reported_error = False
            except BaseException:  # noqa: BLE001 - measurements cannot fail generation
                if not reported_error:
                    _logger.exception("Generation measurement publication failed")
                    reported_error = True
            finally:
                with self._condition:
                    self._publishing = False
                    self._condition.notify_all()


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
