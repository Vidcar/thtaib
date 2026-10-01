"""Process-local mutation lease used while the desktop is quitting."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator


class MaintenanceError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class MaintenanceGate:
    """Block new mutations while quit drains work that is already in flight."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._active_reason: str | None = None
        self._active_mutations = 0

    def begin(self, reason: str, *, wait_timeout: float = 5.0) -> None:
        with self._lock:
            if self._active_reason is not None:
                raise MaintenanceError("Maintenance is already active.", code="maintenance_active")
            self._active_reason = reason
            drained = self._condition.wait_for(lambda: self._active_mutations == 0, timeout=wait_timeout)
            if not drained:
                self._active_reason = None
                self._condition.notify_all()
                raise MaintenanceError(
                    "Maintenance could not drain active mutations before the timeout.",
                    code="maintenance_drain_timeout",
                )

    def end(self) -> None:
        with self._lock:
            self._active_reason = None
            self._condition.notify_all()

    @contextmanager
    def mutation(self) -> Iterator[None]:
        with self._lock:
            if self._active_reason is not None:
                raise MaintenanceError(
                    "Application maintenance is active; mutation or queue dispatch is blocked.",
                    code="maintenance_gate_active",
                )
            self._active_mutations += 1
        try:
            yield
        finally:
            with self._lock:
                self._active_mutations -= 1
                self._condition.notify_all()

    @property
    def active_reason(self) -> str | None:
        with self._lock:
            return self._active_reason
