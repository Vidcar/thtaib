"""Harness HTTP API: start / observe / cancel one agent task."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentStartRequest
from workbench_backend.agents.tools import enabled_catalogue
from workbench_backend.chat.service import ChatService
from workbench_backend.errors import WorkbenchError
from workbench_backend.event_stream import iter_workbench_events

router = APIRouter(prefix="/v1")


def get_harness(request: Request) -> HarnessService:
    return request.app.state.harness


def get_chat(request: Request) -> ChatService:
    return request.app.state.chat


def resolved_event_target(
    request: Request,
    run_id: str | None = None,
    conversation_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Validate targets before FastAPI starts the SSE producer."""

    if (run_id is None) == (conversation_id is None):
        raise WorkbenchError(
            "Provide exactly one of run_id or conversation_id.",
            code="event_target_required",
            status_code=400,
        )
    if run_id is not None:
        get_harness(request).get_run(run_id)
    if conversation_id is not None:
        get_chat(request).get(conversation_id)
    return run_id, conversation_id


@router.get("/agent-tools")
def list_agent_tools() -> dict[str, list[str]]:
    return {"enabled": enabled_catalogue()}


@router.get("/agent-runs")
def list_agent_runs(request: Request) -> object:
    return get_harness(request).list_runs()


@router.post("/agent-runs")
def start_agent_run(request: Request, body: AgentStartRequest) -> object:
    return get_harness(request).start(body)


@router.get("/agent-runs/{run_id}")
def get_agent_run(request: Request, run_id: str) -> object:
    return get_harness(request).get_run(run_id)


@router.post("/agent-runs/{run_id}/cancel")
def cancel_agent_run(request: Request, run_id: str) -> object:
    return get_harness(request).cancel(run_id)


@router.get("/events", response_class=EventSourceResponse)
def stream_run_events(
    request: Request,
    target: Annotated[tuple[str | None, str | None], Depends(resolved_event_target)],
    last_event_id: Annotated[int | None, Header(alias="Last-Event-ID")] = None,
) -> Iterable[ServerSentEvent]:
    run_id, conversation_id = target
    yield from iter_workbench_events(
        harness=get_harness(request),
        chat=get_chat(request),
        run_id=run_id,
        conversation_id=conversation_id,
        last_event_id=last_event_id,
    )
