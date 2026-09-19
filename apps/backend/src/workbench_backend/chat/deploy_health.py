"""Chat-facing deploy-health report. Reuses stored deployment health (#62)."""

from __future__ import annotations

from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.chat.schemas import ChatDeployHealth
from workbench_backend.inference.connection_errors import (
    DEPLOY_UNHEALTHY,
    DEPLOY_UNHEALTHY_MESSAGE,
    DEPLOY_UNREACHABLE,
    DEPLOY_UNREACHABLE_MESSAGE,
    classify_connection_failure,
)
from workbench_backend.inference.schemas import Deployment, DeploymentStatus

_UNHEALTHY_STATUSES = {
    DeploymentStatus.unhealthy,
    DeploymentStatus.failed,
    DeploymentStatus.stopped,
}


def report_chat_deploy_health(
    deployment: Deployment,
    run: AgentRun | None = None,
) -> ChatDeployHealth:
    """Describe whether live completion can use this bound deployment."""

    stored_unhealthy = deployment.status in _UNHEALTHY_STATUSES or (
        deployment.health is not None and not deployment.health.healthy
    )
    run_unreachable = bool(
        run is not None
        and run.status is AgentRunStatus.failed
        and classify_connection_failure(run.error or "")
    )
    if run_unreachable:
        return ChatDeployHealth(
            deployment_id=deployment.id,
            deployment_status=deployment.status.value,
            healthy=False,
            code=DEPLOY_UNREACHABLE,
            message=DEPLOY_UNREACHABLE_MESSAGE,
            detail=_health_detail(deployment),
        )
    if stored_unhealthy:
        return ChatDeployHealth(
            deployment_id=deployment.id,
            deployment_status=deployment.status.value,
            healthy=False,
            code=DEPLOY_UNHEALTHY,
            message=DEPLOY_UNHEALTHY_MESSAGE,
            detail=_health_detail(deployment),
        )
    healthy: bool | None
    if deployment.status is DeploymentStatus.running:
        healthy = True
    else:
        healthy = None
    return ChatDeployHealth(
        deployment_id=deployment.id,
        deployment_status=deployment.status.value,
        healthy=healthy,
        detail=_health_detail(deployment),
    )


def _health_detail(deployment: Deployment) -> str | None:
    if deployment.health is not None and deployment.health.detail:
        return deployment.health.detail
    return deployment.error
