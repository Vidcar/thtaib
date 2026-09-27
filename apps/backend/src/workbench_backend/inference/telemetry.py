"""Request-scoped llama.cpp measurements from its existing response stream."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
import logging
import math
import threading
import time
from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from workbench_backend.inference.ids import utc_now


_logger = logging.getLogger(__name__)
RequestPurpose = Literal["work", "summary", "review", "probe"]
COMPLETED_REQUEST_LIMIT = 64
_request_purpose: contextvars.ContextVar[RequestPurpose] = contextvars.ContextVar("inference_request_purpose", default="work")


def current_request_purpose() -> RequestPurpose:
    return _request_purpose.get()


@contextmanager
def request_purpose(purpose: RequestPurpose):
    """Attribute framework-internal calls without changing model settings."""
    if purpose not in {"work", "summary", "review", "probe"}:
        raise ValueError("Unknown model request purpose")
    token = _request_purpose.set(purpose)
    try:
        yield
    finally:
        _request_purpose.reset(token)


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
        self._latest_by_purpose: dict[str, dict[str, Any]] = {}
        self._completed: dict[str, dict[str, Any]] = {}
        self._request_ids: dict[str, str | None] = {}
        self._pending: dict[tuple[str, str], dict[str, Any]] = {}
        self._publishing = False
        self._closed = False
        self._publication_disabled = False
        self._worker: threading.Thread | None = None

    def publish(self, sample: dict[str, Any]) -> None:
        recorded = dict(sample)
        request_id = recorded.get("request_id")
        purpose = recorded.get("purpose", "work")
        with self._condition:
            if self._closed:
                return
            # Final evidence belongs to its request, even when the live display
            # has already reset for the next call. Keep only small measurements.
            if isinstance(request_id, str) and recorded.get("phase") in {"completed", "interrupted"}:
                self._completed[request_id] = recorded
                while len(self._completed) > COMPLETED_REQUEST_LIMIT:
                    self._completed.pop(next(iter(self._completed)))
            if recorded.get("reset"):
                self._request_ids[purpose] = request_id
                if not self._publication_disabled:
                    self._pending[(purpose, "reset")] = recorded
                    self._pending.pop((purpose, "sample"), None)
            elif request_id == self._request_ids.get(purpose):
                if not self._publication_disabled:
                    self._pending[(purpose, "sample")] = recorded
            else:
                return
            self._latest = recorded
            self._latest_by_purpose[purpose] = recorded
            if self._worker is None and not self._publication_disabled:
                self._worker = threading.Thread(target=self._drain, name="generation-measurements", daemon=True)
                try:
                    self._worker.start()
                except Exception:  # noqa: BLE001 - preserve the sample if publishing cannot start
                    self._publication_disabled = True
                    self._pending.clear()
                    self._worker = None
            self._condition.notify()

    def latest_sample(self, purpose: str | None = None) -> dict[str, Any] | None:
        with self._condition:
            latest = self._latest if purpose is None else self._latest_by_purpose.get(purpose)
            return dict(latest) if latest is not None else None

    def latest_samples(self) -> dict[str, dict[str, Any]]:
        with self._condition:
            return {purpose: dict(sample) for purpose, sample in self._latest_by_purpose.items()}

    def completed_samples(self) -> list[dict[str, Any]]:
        """Return bounded final call evidence without waiting for publication."""
        with self._condition:
            return [dict(sample) for sample in self._completed.values()]

    def wait_idle(self, timeout: float) -> bool:
        """Wait for a test or diagnostic, never from the generation path."""
        with self._condition:
            return self._condition.wait_for(
                lambda: not self._publishing and not self._pending,
                timeout=timeout,
            )

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._pending.clear()
            self._condition.notify_all()

    def _drain(self) -> None:
        reported_error = False
        while True:
            with self._condition:
                while not self._closed and not self._pending:
                    self._condition.wait()
                if self._closed:
                    self._condition.notify_all()
                    return
                key = next(iter(self._pending))
                sample = self._pending.pop(key)
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
        self.purpose = current_request_purpose()
        self.request_id = uuid4().hex
        self.response_id: str | None = None
        self.started_at = utc_now()
        self.started_monotonic = time.monotonic()
        self.first_output_seconds: float | None = None
        self.latest: dict[str, Any] | None = None
        self.last_emitted = 0.0
        self.last_phase: str | None = None
        observer({"request_id": self.request_id, "purpose": self.purpose, "reset": True})

    def receive(self, response: dict[str, Any]) -> None:
        response_id = response.get("id")
        if not isinstance(response_id, str) or not response_id:
            return
        if self.response_id is not None and response_id != self.response_id:
            return
        self.response_id = response_id
        if self.first_output_seconds is None and _has_output_delta(response):
            self.first_output_seconds = max(0.0, time.monotonic() - self.started_monotonic)
        timings = response.get("timings")
        progress = response.get("prompt_progress")
        if not isinstance(timings, dict):
            return
        output = _count(timings.get("predicted_n"))
        if output is None:
            return
        phase = "generating" if output > 0 else "prompt_processing"
        input_tokens = _count(progress.get("total")) if isinstance(progress, dict) else None
        cached, processed = _count(timings.get("cache_n")), _count(timings.get("prompt_n"))
        if input_tokens is None and output > 0:
            if cached is not None and processed is not None:
                input_tokens = cached + processed
        usage = response.get("usage")
        if isinstance(usage, dict) and _count(usage.get("prompt_tokens")) is not None:
            input_tokens = usage["prompt_tokens"]
        elapsed_ms = _number(timings.get("predicted_ms"))
        prompt_ms = _number(timings.get("prompt_ms"))
        speed = _number(timings.get("predicted_per_second"))
        # A zero-duration first token carries no meaningful generation rate.
        if output < 2 or elapsed_ms is None or elapsed_ms <= 0:
            speed = None
        if self.latest is not None and output < self.latest["output_tokens"]:
            return
        self.latest = {
            "request_id": self.request_id,
            "purpose": self.purpose,
            "cached_input_tokens": cached,
            "processed_input_tokens": processed,
            "prefill_seconds": prompt_ms / 1000 if prompt_ms is not None else None,
            "request_started_at": self.started_at,
            "time_to_first_token_seconds": self.first_output_seconds,
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


def _has_output_delta(response: dict[str, Any]) -> bool:
    """A complete nonstream response cannot establish its first-output time."""
    for choice in response.get("choices") or []:
        if not isinstance(choice, dict) or not isinstance(delta := choice.get("delta"), dict):
            continue
        if any(isinstance(delta.get(key), str) and delta[key] for key in ("content", "reasoning_content", "reasoning")):
            return True
        for call in delta.get("tool_calls") or []:
            function = call.get("function") if isinstance(call, dict) else None
            if isinstance(function, dict) and any(isinstance(function.get(key), str) and function[key] for key in ("name", "arguments")):
                return True
    return False


def _number(value: Any) -> float | None:
    if type(value) not in {int, float}:
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) and number >= 0 else None
