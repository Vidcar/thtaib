"""Substantial synthetic diagnostic history for operational regressions."""

from workbench_backend.agents.schemas import AgentRun, ModelRequestCapture
from workbench_backend.inference.ids import utc_now


def synthetic_large_run(id: str = "run_large", **overrides) -> AgentRun:
    now = utc_now()
    content = ("Synthetic captured model context for responsiveness checks. " * 4096)[:220 * 1024]
    values = dict(
        id=id, deployment_id="deployment_synthetic", task="Synthetic long tool run",
        status="running", thread_id="thread_large", source_surface="agent-run",
        enabled_tools=["read_file", "browser_snapshot"],
        presented_tools=["read_file", "browser_snapshot"], created_at=now, updated_at=now,
        model_requests=[ModelRequestCapture(at=now, instructions=content) for _ in range(50)],
    )
    values.update(overrides)
    return AgentRun(**values)
