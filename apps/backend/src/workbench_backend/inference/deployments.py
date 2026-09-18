"""Managed and connected deployments (MOD-004). PATH llama is never used."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from workbench_backend.errors import ManagerError
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.process import HttpProbe, ProcessSupervisor, wait_for_health
from workbench_backend.inference.runtime import RuntimeService
from workbench_backend.inference.schemas import (
    ConnectedDeploymentRequest,
    Deployment,
    DeploymentStatus,
    ImportStatus,
    ManagedDeploymentRequest,
    ManagementScope,
    ResourceUsage,
    SmokeResult,
)
from workbench_backend.inference.settings import resolve_bags, startup_cli_args
from workbench_backend.inference.store import RecordStore


class DeploymentService:
    def __init__(
        self,
        store: RecordStore,
        runtime: RuntimeService,
        *,
        processes: ProcessSupervisor | None = None,
        probe: HttpProbe | None = None,
    ) -> None:
        self.store = store
        self.runtime = runtime
        self.processes = processes or ProcessSupervisor()
        self.probe = probe or HttpProbe()

    def create_managed(self, request: ManagedDeploymentRequest) -> Deployment:
        bundle = self.store.get_bundle(request.bundle_id)
        if bundle is None or bundle.status != ImportStatus.complete or not bundle.disk_matches:
            raise ManagerError(
                "A complete, on-disk bundle is required. A failed or interrupted "
                "download is not a successful deployment.",
                code="bundle_not_deployable",
                status_code=409,
            )
        profile = None
        if request.profile_id:
            profile = self.store.get_profile(request.profile_id)
            if profile is None:
                raise ManagerError(
                    "Unknown profile",
                    code="profile_missing",
                    status_code=404,
                )
        requested_startup = dict(profile.bags.startup.requested) if profile else {}
        requested_startup.update(request.startup)
        per_request = profile.bags.per_request.requested if profile else {}
        agent = profile.bags.agent.requested if profile else {}
        host, port, overrides = self._allocate_listen(requested_startup)
        bags = resolve_bags(
            startup=requested_startup,
            per_request=per_request,
            agent=agent,
            startup_overrides=overrides,
        )
        deployment = Deployment(
            id=new_id("deploy"),
            display_name=f"managed:{bundle.display_name}",
            scope=ManagementScope.managed,
            status=DeploymentStatus.stopped,
            bundle_id=bundle.id,
            profile_id=request.profile_id,
            endpoint=f"http://{host}:{port}/v1",
            requested_startup=requested_startup,
            applied_startup=bags.startup.applied,
            settings=bags,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.store.put_deployment(deployment)
        if request.auto_start:
            return self.start(deployment.id)
        return deployment

    def attach_connected(self, request: ConnectedDeploymentRequest) -> Deployment:
        endpoint = request.endpoint.rstrip("/")
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ManagerError(
                "Connected endpoint must be an http(s) URL",
                code="connected_endpoint_invalid",
                status_code=400,
            )
        health = self.probe.health(endpoint)
        status = DeploymentStatus.running if health.healthy else DeploymentStatus.unhealthy
        deployment = Deployment(
            id=new_id("deploy"),
            display_name=request.display_name or f"connected:{parsed.netloc}",
            scope=ManagementScope.connected,
            status=status,
            endpoint=endpoint,
            health=health,
            resource_usage=ResourceUsage(
                available=False,
                reason="connected endpoint — external process is not managed",
            ),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        return self.store.put_deployment(deployment)

    def start(self, deployment_id: str) -> Deployment:
        deployment = self._require(deployment_id)
        if deployment.scope != ManagementScope.managed:
            raise ManagerError(
                "Connected endpoints cannot be started by Local AI Workbench.",
                code="connected_no_lifecycle",
                status_code=409,
            )
        bundle = self.store.get_bundle(deployment.bundle_id or "")
        if bundle is None or bundle.status != ImportStatus.complete:
            raise ManagerError(
                "Cannot start a deployment from a missing or unsuccessful bundle.",
                code="bundle_not_deployable",
                status_code=409,
            )
        executable = self.runtime.require_executable()
        model_path = bundle.primary_path
        if not model_path or not Path(model_path).is_file():
            raise ManagerError(
                "Bundle primary GGUF is missing on disk",
                code="bundle_file_missing",
                status_code=409,
            )
        argv = [str(executable), "-m", model_path, *startup_cli_args(deployment.applied_startup)]
        starting = deployment.model_copy(
            update={"status": DeploymentStatus.starting, "updated_at": utc_now(), "error": None}
        )
        self.store.put_deployment(starting)
        pid: int | None = None
        try:
            pid = self.processes.start(argv, cwd=Path(executable).parent)
            health = wait_for_health(self.probe, starting.endpoint or "")
            usage = self.processes.resource_usage(pid)
            status = DeploymentStatus.running if health.healthy else DeploymentStatus.unhealthy
            return self.store.put_deployment(
                starting.model_copy(
                    update={
                        "status": status,
                        "pid": pid,
                        "health": health,
                        "resource_usage": usage,
                        "updated_at": utc_now(),
                    }
                )
            )
        except Exception as exc:
            if pid is not None:
                self.processes.stop(pid)
            return self.store.put_deployment(
                starting.model_copy(
                    update={
                        "status": DeploymentStatus.failed,
                        "pid": None,
                        "error": str(exc),
                        "updated_at": utc_now(),
                    }
                )
            )

    def stop(self, deployment_id: str) -> Deployment:
        deployment = self._require(deployment_id)
        if deployment.scope != ManagementScope.managed:
            raise ManagerError(
                "Connected endpoints have no destructive lifecycle. Use detach.",
                code="connected_no_lifecycle",
                status_code=409,
            )
        if deployment.pid is not None:
            self.processes.stop(deployment.pid)
        return self.store.put_deployment(
            deployment.model_copy(
                update={
                    "status": DeploymentStatus.stopped,
                    "pid": None,
                    "health": None,
                    "resource_usage": ResourceUsage(
                        available=False,
                        reason="managed process stopped",
                    ),
                    "updated_at": utc_now(),
                }
            )
        )

    def detach(self, deployment_id: str) -> Deployment:
        deployment = self._require(deployment_id)
        if deployment.scope != ManagementScope.connected:
            raise ManagerError(
                "Detach applies to connected endpoints. Stop a managed deployment first.",
                code="detach_managed",
                status_code=409,
            )
        self.store.delete_deployment(deployment.id)
        return deployment.model_copy(update={"status": DeploymentStatus.stopped, "updated_at": utc_now()})

    def health(self, deployment_id: str) -> Deployment:
        deployment = self._require(deployment_id)
        if not deployment.endpoint:
            raise ManagerError("Deployment has no endpoint", code="no_endpoint", status_code=409)
        report = self.probe.health(deployment.endpoint)
        usage = (
            self.processes.resource_usage(deployment.pid)
            if deployment.scope == ManagementScope.managed
            else ResourceUsage(
                available=False,
                reason="connected endpoint — external process is not managed",
            )
        )
        if deployment.scope == ManagementScope.managed and deployment.status in {
            DeploymentStatus.running,
            DeploymentStatus.unhealthy,
            DeploymentStatus.starting,
        }:
            status = DeploymentStatus.running if report.healthy else DeploymentStatus.unhealthy
        else:
            status = deployment.status
        return self.store.put_deployment(
            deployment.model_copy(
                update={
                    "health": report,
                    "resource_usage": usage,
                    "status": status,
                    "updated_at": utc_now(),
                }
            )
        )

    def smoke(self, deployment_id: str) -> SmokeResult:
        deployment = self._require(deployment_id)
        if not deployment.endpoint:
            raise ManagerError("Deployment has no endpoint", code="no_endpoint", status_code=409)
        ok, detail = self.probe.smoke(deployment.endpoint)
        return SmokeResult(ok=ok, endpoint=deployment.endpoint, detail=detail)

    def _require(self, deployment_id: str) -> Deployment:
        deployment = self.store.get_deployment(deployment_id)
        if deployment is None:
            raise ManagerError("Unknown deployment", code="deployment_missing", status_code=404)
        return deployment

    def _allocate_listen(
        self,
        requested: dict[str, Any],
    ) -> tuple[str, int, dict[str, Any]]:
        host = str(requested.get("host") or "127.0.0.1")
        requested_port = int(requested.get("port") or 8080)
        port = _first_free_port(host, requested_port)
        overrides: dict[str, Any] = {"host": host, "port": port}
        return host, port, overrides


def _first_free_port(host: str, start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise ManagerError(
        "No free listen port found",
        code="no_free_port",
        status_code=409,
    )
