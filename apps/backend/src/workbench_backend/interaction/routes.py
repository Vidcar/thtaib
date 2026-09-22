"""Authenticated stock HttpAgentServerAdapter HTTP endpoints."""
from __future__ import annotations

import json
from typing import Literal

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, format_sse_event
from pydantic import BaseModel, ConfigDict, ValidationError

from workbench_backend.errors import WorkbenchError
from workbench_backend.interaction.service import InteractionService, fields, invalid

router = APIRouter(prefix="/v1/agent-interaction")


class InteractionRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_surface: Literal["chat", "agent"]
    conversation_id: str | None = None
    run_id: str | None = None


class InteractionBinding(BaseModel):
    thread_id: str


def service(request: Request) -> InteractionService:
    return request.app.state.interaction


@router.post("/threads")
def register(body: InteractionRegistration, request: Request) -> InteractionBinding:
    return InteractionBinding(**service(request).register(body.model_dump(exclude_none=True)))


@router.post("/threads/{thread_id}/commands")
def command(thread_id: str, body: dict, request: Request) -> JSONResponse:
    try:
        result = service(request).command(thread_id, body)
    except WorkbenchError as exc:
        return JSONResponse({"type": "error", "id": body.get("id"), "error": exc.code,
                             "message": str(exc)}, status_code=exc.status_code)
    except (ValidationError, ValueError, TypeError) as exc:
        return JSONResponse({"type": "error", "id": body.get("id"), "error": "invalid_request",
                             "message": "Invalid command parameters."}, status_code=400)
    return JSONResponse({"type": "success", "id": body["id"], "result": result})


@router.get("/threads/{thread_id}/state")
def state(thread_id: str, request: Request) -> dict:
    return service(request).state(thread_id)


@router.post("/threads/{thread_id}/history")
def history(thread_id: str, body: dict, request: Request) -> list[dict]:
    # The SDK uses this for discovery hydration. Only the current display
    # projection is supported; editing/forking graph checkpoints is not exposed.
    fields(body, {"limit"}, "history")
    limit = body.get("limit", 1)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise invalid("Invalid history limit.")
    return [service(request).state(thread_id)]


@router.post("/threads/{thread_id}/stream/events")
def stream(thread_id: str, body: dict, request: Request) -> EventSourceResponse:
    interaction = service(request)
    options = interaction.subscription(thread_id, body)
    cursor = options.get("since", 0)

    async def produce():
        nonlocal cursor
        idle = 0
        while not await request.is_disconnected():
            # Display-only edits hide prior display events, never graph state.
            # Their first values record is the new authoritative display.
            cutover = interaction.binding(thread_id)["snapshot"].get("workbench", {}).get("display_cutover_seq", 0)
            if cursor < cutover - 1:
                cursor = cutover - 1
            page, _high_water, gap = interaction.store.interaction_page(thread_id, cursor)
            if gap:
                # Released SDKs do not interpret a special gap control frame.
                # Resynchronize via ordinary upstream values/lifecycle events
                # and an explicit application recovery notice. Never rerun.
                cursor = interaction.resynchronize(thread_id)
                continue
            for item in page:
                cursor = item["seq"]
                if interaction.matches(item, options):
                    if item["method"] == "values" and not item["params"].get("namespace"):
                        item["params"]["data"] = interaction.display_values(item["params"]["data"])
                    yield format_sse_event(data_str=json.dumps(item), event="message", id=str(cursor))
            if page:
                idle = 0
                continue
            # No transient queue: replay and live tail share the same durable
            # cursor. A disconnect closes observation without cancelling work.
            await anyio.sleep(0.1)
            idle += 1
            if idle >= 100:
                yield format_sse_event(comment="keepalive")
                idle = 0

    return EventSourceResponse(produce())
