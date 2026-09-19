"""Shared SSE envelope for run and Chat conversation events (API-006).

The snapshot record remains the module-local GET shape until those routes
move onto the generated path. This module owns the stream envelope only.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from workbench_backend.contracts.lifecycle import RunLifecycleStatus

LAST_EVENT_ID_HEADER = "Last-Event-ID"
RUN_EVENTS_PATH = "/v1/events"


class RunStreamEventType(str, Enum):
    snapshot = "snapshot"
    run_event = "run_event"
    stream_end = "stream_end"


class SharedAgentEvent(BaseModel):
    """One application harness event. Not a raw LangGraph stream chunk."""

    model_config = ConfigDict(title="SharedAgentEvent")

    at: str
    kind: str
    detail: dict[str, Any] = Field(default_factory=dict)


class RunStreamEnvelope(BaseModel):
    """JSON `data` for each SSE message on GET /v1/events."""

    model_config = ConfigDict(title="RunStreamEnvelope")

    type: RunStreamEventType
    seq: int | None = Field(
        default=None,
        description="1-based AgentEvent index on the run. Set on run_event; used as SSE id.",
    )
    run_id: str | None = None
    conversation_id: str | None = None
    status: RunLifecycleStatus | None = None
    event: SharedAgentEvent | None = None
    snapshot: dict[str, Any] | None = Field(
        default=None,
        description="GET-equivalent agent-run or chat-conversation record.",
    )


class RunStreamContract(BaseModel):
    """Documented stream route, headers and event names for generated consumers."""

    model_config = ConfigDict(title="RunStreamContract")

    path: Literal["/v1/events"] = RUN_EVENTS_PATH
    method: Literal["GET"] = "GET"
    media_type: Literal["text/event-stream"] = "text/event-stream"
    auth_header: Literal["X-Workbench-Local-Token"] = "X-Workbench-Local-Token"
    last_event_id_header: Literal["Last-Event-ID"] = LAST_EVENT_ID_HEADER
    query_one_of: list[Literal["run_id", "conversation_id"]] = Field(
        default_factory=lambda: ["run_id", "conversation_id"],
    )
    event_names: list[RunStreamEventType] = Field(
        default_factory=lambda: list(RunStreamEventType),
    )
    disconnect_does_not_end_run: Literal[True] = True
    transport: Literal["sse"] = "sse"
