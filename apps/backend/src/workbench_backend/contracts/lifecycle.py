"""Shared run/cancel lifecycle names for cancel honesty (Issue #42).

Issue #42 consumes these names for harness cancel request vs confirmed stop.
`cancel_requested` is still live; confirmed `cancelled` is not.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RunLifecycleStatus(str, Enum):
    """Shared run lifecycle states, including honest cancel request vs confirmed stop."""

    queued = "queued"
    running = "running"
    cancel_requested = "cancel_requested"
    cancelled = "cancelled"
    completed = "completed"
    failed = "failed"


LIVE_RUN_LIFECYCLE_STATUSES: tuple[RunLifecycleStatus, ...] = (
    RunLifecycleStatus.queued,
    RunLifecycleStatus.running,
    RunLifecycleStatus.cancel_requested,
)

TERMINAL_RUN_LIFECYCLE_STATUSES: tuple[RunLifecycleStatus, ...] = (
    RunLifecycleStatus.cancelled,
    RunLifecycleStatus.completed,
    RunLifecycleStatus.failed,
)


def is_run_lifecycle_live(status: RunLifecycleStatus | str) -> bool:
    """True when the workspace must not be treated as quiescent.

    `cancel_requested` is still live. Confirmed `cancelled` is not.
    """
    return RunLifecycleStatus(status) in LIVE_RUN_LIFECYCLE_STATUSES


class RunLifecycleContract(BaseModel):
    """Documented lifecycle vocabulary for generated consumers."""

    model_config = ConfigDict(title="RunLifecycleContract")

    status_values: list[RunLifecycleStatus] = Field(
        default_factory=lambda: list(RunLifecycleStatus),
        description="Canonical status names. Issue #42 consumes cancel_requested and cancelled.",
    )
    live_statuses: list[RunLifecycleStatus] = Field(
        default_factory=lambda: list(LIVE_RUN_LIFECYCLE_STATUSES),
        description="Still live; quiescence must treat these as not idle.",
    )
    terminal_statuses: list[RunLifecycleStatus] = Field(
        default_factory=lambda: list(TERMINAL_RUN_LIFECYCLE_STATUSES),
        description="Confirmed stop or finished outcomes.",
    )
    cancel_requested_is_live: Literal[True] = True
    cancelled_means_confirmed_stop: Literal[True] = True
