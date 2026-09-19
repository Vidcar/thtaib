"""Managed and connected deployments (MOD-004). PATH llama is never used.

Issue #62: per-deployment lifecycle is serialized; duplicate starts are
idempotent for a verified-owned process; a healthy endpoint alone does
not prove the newly launched process is owned.
"""

from __future__ import annotations

import socket
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import mmproj_companion
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.process import (
    PROCESS_IDENTITY_MISMATCH,
    PROCESS_IDENTITY_UNPROVEN,
    HttpProbe,
    ProcessSupervisor,
    wait_for_owned_health,
)
from workbench_backend.inference.runtime import RuntimeService
from workbench_backend.inference.schemas import (
    ConnectedDeploymentRequest,
    Deployment,
    DeploymentStatus,
    ImportStatus,
    ManagedDeploymentRequest,
    ManagementScope,
    ModelBundle,
    ProcessIdentity,
    ResourceUsage,
    SmokeResult,
)
from workbench_backend.inference.settings import resolve_bags, startup_cli_args
from workbench_backend.inference.store import RecordStore

_LIVE_MANAGED = {
    DeploymentStatus.starting,
    DeploymentStatus.running,
    DeploymentStatus.unhealthy,
}


class DeploymentService:
    def __init__(
        self,
        store: RecordStore,
        runtime: RuntimeService,
        *,
        processes: ProcessSupervisor | None = None,
        probe: HttpProbe | None = None,
        reconcile_on_init: bool = True,
    ) -> None:
        self.store = store
        self.runtime = runtime
        self.processes = processes or ProcessSupervisor()
        self.probe = probe or HttpProbe()
        self._guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}
        if reconcile_on_init:
            self.reconcile()

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
            server_props=self.probe.props(endpoint) if health.healthy else None,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        return self.store.put_deployment(deployment)

    def start(self, deployment_id: str) -> Deployment:
        with self._lock_for(deployment_id):
            return self._start_locked(deployment_id)

    def stop(self, deployment_id: str) -> Deployment:
        with self._lock_for(deployment_id):
            return self._stop_locked(deployment_id)

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
        with self._lock_for(deployment_id):
            return self._health_locked(deployment_id)

    def smoke(self, deployment_id: str) -> SmokeResult:
        deployment = self._require(deployment_id)
        if not deployment.endpoint:
            raise ManagerError("Deployment has no endpoint", code="no_endpoint", status_code=409)
        ok, detail = self.probe.smoke(deployment.endpoint)
        return SmokeResult(ok=ok, endpoint=deployment.endpoint, detail=detail)

    def reconcile(self) -> list[Deployment]:
        """Re-adopt matching owned processes; clear unowned records without killing."""
        updated: list[Deployment] = []
        for deployment in list(self.store.list_deployments()):
            if deployment.scope != ManagementScope.managed:
                continue
            with self._lock_for(deployment.id):
                current = self._require(deployment.id)
                updated.append(self._reconcile_locked(current))
        return updated

    def live_owned(self) -> list[Deployment]:
        blocking: list[Deployment] = []
        for deployment in self.store.list_deployments():
            if deployment.scope != ManagementScope.managed:
                continue
            if deployment.status not in _LIVE_MANAGED:
                continue
            if self._owned_live(deployment):
                blocking.append(deployment)
            elif deployment.status == DeploymentStatus.starting and deployment.process_identity is None:
                blocking.append(deployment)
        return blocking

    def _start_locked(self, deployment_id: str) -> Deployment:
        deployment = self._require(deployment_id)
        if deployment.scope != ManagementScope.managed:
            raise ManagerError(
                "Connected endpoints cannot be started by Local AI Workbench.",
                code="connected_no_lifecycle",
                status_code=409,
            )
        deployment = self._reconcile_locked(deployment)
        if self._owned_live(deployment):
            return deployment
        bundle = self.store.get_bundle(deployment.bundle_id or "")
        if bundle is None or bundle.status != ImportStatus.complete:
            raise ManagerError(
                "Cannot start a deployment from a missing or unsuccessful bundle.",
                code="bundle_not_deployable",
                status_code=409,
            )
        executable = self.runtime.require_executable()
        argv = managed_argv(executable, bundle, deployment.applied_startup)
        starting = deployment.model_copy(
            update={
                "status": DeploymentStatus.starting,
                "updated_at": utc_now(),
                "error": None,
                "pid": None,
                "process_identity": None,
            }
        )
        self.store.put_deployment(starting)
        identity: ProcessIdentity | None = None
        try:
            identity = self.processes.start(argv, cwd=Path(executable).parent)
            recorded = starting.model_copy(
                update={
                    "pid": identity.pid,
                    "process_identity": identity,
                    "updated_at": utc_now(),
                }
            )
            self.store.put_deployment(recorded)
            port = _endpoint_port(recorded.endpoint)
            verdict, health, owns_listen = wait_for_owned_health(
                self.probe,
                recorded.endpoint or "",
                self.processes,
                identity,
                port=port,
            )
            if verdict != "match" or not self.processes.launched_still_running(identity.pid):
                return self._fail_unowned(
                    recorded,
                    error=(
                        "Launched process exited or lost identity while another "
                        "process may still answer the endpoint. Not recorded as "
                        "a healthy owned deployment."
                    ),
                    identity=identity,
                )
            if health.healthy and owns_listen is False:
                return self._fail_unowned(
                    recorded,
                    error=(
                        "Endpoint is healthy but the launched process does not "
                        "own the listen port. Not recorded as a healthy owned "
                        "deployment."
                    ),
                    identity=identity,
                )
            usage = self.processes.resource_usage(identity)
            status = DeploymentStatus.running if health.healthy else DeploymentStatus.unhealthy
            props = self.probe.props(recorded.endpoint or "") if health.healthy else None
            return self.store.put_deployment(
                recorded.model_copy(
                    update={
                        "status": status,
                        "pid": identity.pid,
                        "process_identity": identity,
                        "health": health,
                        "resource_usage": usage,
                        "server_props": props,
                        "error": None,
                        "updated_at": utc_now(),
                    }
                )
            )
        except Exception as exc:
            return self._fail_unowned(starting, error=str(exc), identity=identity)

    def _stop_locked(self, deployment_id: str) -> Deployment:
        deployment = self._require(deployment_id)
        if deployment.scope != ManagementScope.managed:
            raise ManagerError(
                "Connected endpoints have no destructive lifecycle. Use detach.",
                code="connected_no_lifecycle",
                status_code=409,
            )
        identity = deployment.process_identity
        if identity is None and deployment.pid is not None:
            self._clear_ownership(
                deployment,
                status=DeploymentStatus.stopped,
                error="Unproven process identity; refused termination.",
            )
            raise ManagerError(
                "Refusing to terminate a managed PID without persisted "
                "creation-time and executable identity.",
                code=PROCESS_IDENTITY_UNPROVEN,
                status_code=409,
                details={"deployment_id": deployment.id, "pid": deployment.pid},
            )
        if identity is not None:
            try:
                self.processes.stop(identity)
            except ManagerError as exc:
                if exc.code != PROCESS_IDENTITY_MISMATCH:
                    raise
                self._clear_ownership(
                    deployment,
                    status=DeploymentStatus.stopped,
                    error="Process identity mismatch; refused termination.",
                )
                raise
        return self._clear_ownership(
            deployment,
            status=DeploymentStatus.stopped,
            error=None,
            usage_reason="managed process stopped",
        )

    def _health_locked(self, deployment_id: str) -> Deployment:
        deployment = self._require(deployment_id)
        if not deployment.endpoint:
            raise ManagerError("Deployment has no endpoint", code="no_endpoint", status_code=409)
        if deployment.scope == ManagementScope.managed:
            deployment = self._reconcile_locked(deployment)
            if not self._owned_live(deployment) and deployment.status not in _LIVE_MANAGED:
                report = self.probe.health(deployment.endpoint)
                return self.store.put_deployment(
                    deployment.model_copy(
                        update={
                            "health": report,
                            "resource_usage": ResourceUsage(
                                available=False,
                                reason="managed process is not owned",
                            ),
                            "updated_at": utc_now(),
                        }
                    )
                )
        report = self.probe.health(deployment.endpoint)
        props = deployment.server_props
        if report.healthy and props is None:
            props = self.probe.props(deployment.endpoint)
        if deployment.scope == ManagementScope.connected:
            usage = ResourceUsage(
                available=False,
                reason="connected endpoint — external process is not managed",
            )
            return self.store.put_deployment(
                deployment.model_copy(
                    update={
                        "health": report,
                        "resource_usage": usage,
                        "server_props": props,
                        "status": deployment.status,
                        "updated_at": utc_now(),
                    }
                )
            )
        usage = self.processes.resource_usage(deployment.process_identity)
        if self._owned_live(deployment) and deployment.status in _LIVE_MANAGED:
            status = DeploymentStatus.running if report.healthy else DeploymentStatus.unhealthy
        else:
            status = deployment.status
        return self.store.put_deployment(
            deployment.model_copy(
                update={
                    "health": report,
                    "resource_usage": usage,
                    "server_props": props,
                    "status": status,
                    "updated_at": utc_now(),
                }
            )
        )

    def _reconcile_locked(self, deployment: Deployment) -> Deployment:
        if deployment.scope != ManagementScope.managed:
            return deployment
        identity = deployment.process_identity
        if identity is None:
            if deployment.pid is not None and deployment.status in _LIVE_MANAGED:
                return self._clear_ownership(
                    deployment,
                    status=DeploymentStatus.stopped,
                    error="Unproven process identity after restart; ownership cleared without termination.",
                )
            return deployment
        verdict = self.processes.classify(identity)
        if verdict == "match":
            usage = self.processes.resource_usage(identity)
            status = deployment.status
            if status not in _LIVE_MANAGED:
                status = DeploymentStatus.running
            return self.store.put_deployment(
                deployment.model_copy(
                    update={
                        "status": status,
                        "pid": identity.pid,
                        "process_identity": identity,
                        "resource_usage": usage,
                        "error": None,
                        "updated_at": utc_now(),
                    }
                )
            )
        if verdict == "mismatch":
            return self._clear_ownership(
                deployment,
                status=DeploymentStatus.stopped,
                error="Stale or reused PID / mismatched executable identity; ownership cleared without termination.",
            )
        return self._clear_ownership(
            deployment,
            status=DeploymentStatus.stopped,
            error=None,
            usage_reason="owned process is not running",
        )

    def _owned_live(self, deployment: Deployment) -> bool:
        if deployment.scope != ManagementScope.managed:
            return False
        identity = deployment.process_identity
        if identity is None:
            return False
        return self.processes.classify(identity) == "match"

    def _fail_unowned(
        self,
        deployment: Deployment,
        *,
        error: str,
        identity: ProcessIdentity | None,
    ) -> Deployment:
        if identity is not None:
            try:
                self.processes.stop(identity)
            except ManagerError:
                pass
        return self._clear_ownership(
            deployment,
            status=DeploymentStatus.failed,
            error=error,
        )

    def _clear_ownership(
        self,
        deployment: Deployment,
        *,
        status: DeploymentStatus,
        error: str | None,
        usage_reason: str = "managed process is not owned",
    ) -> Deployment:
        return self.store.put_deployment(
            deployment.model_copy(
                update={
                    "status": status,
                    "pid": None,
                    "process_identity": None,
                    "health": None,
                    "server_props": None,
                    "resource_usage": ResourceUsage(available=False, reason=usage_reason),
                    "error": error,
                    "updated_at": utc_now(),
                }
            )
        )

    def _require(self, deployment_id: str) -> Deployment:
        deployment = self.store.get_deployment(deployment_id)
        if deployment is None:
            raise ManagerError("Unknown deployment", code="deployment_missing", status_code=404)
        return deployment

    def _lock_for(self, deployment_id: str) -> threading.RLock:
        with self._guard:
            lock = self._locks.get(deployment_id)
            if lock is None:
                lock = threading.RLock()
                self._locks[deployment_id] = lock
            return lock

    def _allocate_listen(
        self,
        requested: dict[str, Any],
    ) -> tuple[str, int, dict[str, Any]]:
        host = str(requested.get("host") or "127.0.0.1")
        requested_port = int(requested.get("port") or 8080)
        port = _first_free_port(host, requested_port)
        overrides: dict[str, Any] = {"host": host, "port": port}
        return host, port, overrides


def managed_argv(executable: Path | str, bundle: ModelBundle, applied_startup: dict[str, Any]) -> list[str]:
    """Build the llama-server argv for a managed start.

    Passes the primary GGUF with ``-m`` and, when the bundle recorded a
    classified ``mmproj`` companion, that projector with ``--mmproj`` so a
    vision-capable bundle can start through the managed path. Both files
    must exist on disk; a missing file is a clear failure, not a start.
    """
    model_path = bundle.primary_path
    if not model_path or not Path(model_path).is_file():
        raise ManagerError(
            "Bundle primary GGUF is missing on disk",
            code="bundle_file_missing",
            status_code=409,
        )
    argv = [str(executable), "-m", model_path]
    projector = mmproj_companion(bundle)
    if projector is not None:
        if not Path(projector.path).is_file():
            raise ManagerError(
                f"Bundle mmproj companion is missing on disk: {projector.name}",
                code="bundle_file_missing",
                status_code=409,
            )
        argv.extend(["--mmproj", projector.path])
    argv.extend(startup_cli_args(applied_startup))
    return argv


def _endpoint_port(endpoint: str | None) -> int | None:
    if not endpoint:
        return None
    parsed = urlparse(endpoint)
    if parsed.port:
        return int(parsed.port)
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    return None


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
