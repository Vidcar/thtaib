"""Harness HTTP API: start / observe / cancel one agent task."""

from __future__ import annotations

from fastapi import APIRouter, Request

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentStartRequest
from workbench_backend.agents.tools import enabled_catalogue

router = APIRouter(prefix="/v1")


def get_harness(request: Request) -> HarnessService:
    return request.app.state.harness


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
