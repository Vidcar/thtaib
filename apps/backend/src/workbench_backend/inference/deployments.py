"""Managed and connected deployments (MOD-004). PATH llama is never used.

Issue #62: per-deployment lifecycle is serialized; duplicate starts are
idempotent for a verified-owned process; a healthy endpoint alone does
not prove the newly launched process is owned.
"""

from __future__ import annotations

import socket
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import mmproj_companion
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.lifecycle import LifecycleCoordinator
from workbench_backend.inference.process import (
    PROCESS_IDENTITY_MISMATCH,
    PROCESS_IDENTITY_UNPROVEN,
    HttpProbe,
    ProcessSupervisor,
    wait_for_owned_health,
)
from workbench_backend.inference.process_logs import deployment_log_path
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
    SettingsBags,
    SmokeResult,
)
from workbench_backend.inference.settings import (
    resolve_bags,
    resolve_declared_startup,
    startup_cli_args,
)
from workbench_backend.inference.store import RecordStore

_LIVE_MANAGED = {
    DeploymentStatus.starting,
    DeploymentStatus.running,
    DeploymentStatus.unhealthy,
}

LEGACY_IDENTITY_DETACHED_MESSAGE = (
    "Deployment was detached after restart because its process identity could not be "
    "verified. No process was stopped."
)
PROCESS_IDENTITY_MISMATCH_DETACHED_MESSAGE = (
    "Deployment was detached because the recorded process identity no longer matched "
    "the running process. No process was stopped."
)


class DeploymentService:
    def __init__(
        self,
        store: RecordStore,
        runtime: RuntimeService,
        *,
        processes: ProcessSupervisor | None = None,
        probe: HttpProbe | None = None,
        reconcile_on_init: bool = True,
        lifecycle: LifecycleCoordinator | None = None,
        require_no_live_dependencies: Callable[[Deployment, str], None] | None = None,
    ) -> None:
        self.store = store
        self.runtime = runtime
        self.processes = processes or ProcessSupervisor()
        self.probe = probe or HttpProbe()
        self._guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}
        self.lifecycle = lifecycle or LifecycleCoordinator()
        self.require_no_live_dependencies = require_no_live_dependencies
        if reconcile_on_init:
            self.reconcile()

    def create_managed(self, request: ManagedDeploymentRequest) -> Deployment:
        with self.lifecycle.mutate(
            "create_managed",
            profile_ids={request.profile_id} if request.profile_id else set(),
            bundle_ids={request.bundle_id},
        ):
            return self._create_managed_checked(request)

    def _create_managed_checked(self, request: ManagedDeploymentRequest) -> Deployment:
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
            if profile.bundle_id is not None and profile.bundle_id != request.bundle_id:
                raise ManagerError(
                    "Profile is bound to a different bundle.",
                    code="profile_bundle_mismatch",
                    status_code=400,
                    details={
                        "profile_id": profile.id,
                        "profile_bundle_id": profile.bundle_id,
                        "bundle_id": request.bundle_id,
                    },
                )
        requested_startup = dict(profile.bags.startup.requested) if profile else {}
        for key, value in (request.startup or {}).items():
            if value is None:
                requested_startup.pop(key, None)
            else:
                requested_startup[key] = value
        per_request = profile.bags.per_request.requested if profile else {}
        agent = profile.bags.agent.requested if profile else {}
        bags = resolve_bags(
            startup=requested_startup,
            per_request=per_request,
            agent=agent,
        )
        _require_valid_managed_startup(bags.startup)
        # A stopped record does not reserve an OS port. Recheck at launch.
        host = str(bags.startup.applied.get("host") or "127.0.0.1")
        port = int(bags.startup.applied.get("port") or 8080)
        overrides = {"host": host, "port": port}
        bags = resolve_bags(
            startup=requested_startup,
            per_request=per_request,
            agent=agent,
            startup_overrides=overrides,
        )
        _require_valid_managed_startup(bags.startup)
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
            startup_overrides=dict(request.startup or {}),
            profile_snapshot=profile.bags.model_copy(deep=True) if profile else None,
            configuration_revision=profile.revision if profile else None,
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
        startup = resolve_declared_startup(request.startup)
        deployment = Deployment(
            id=new_id("deploy"),
            display_name=request.display_name or f"connected:{parsed.netloc}",
            scope=ManagementScope.connected,
            status=status,
            endpoint=endpoint,
            requested_startup=dict(request.startup or {}),
            applied_startup=startup.applied,
            settings=SettingsBags(startup=startup),
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
        deployment = self._require(deployment_id)
        with self.lifecycle.reserve(deployment):
            with self._lock_for(deployment_id):
                # Serialize port selection through listen ownership verification.
                # The OS port is not reserved merely by saving a deployment.
                with self._guard:
                    return self._start_locked(deployment_id)

    def stop(self, deployment_id: str) -> Deployment:
        deployment = self._require(deployment_id)
        with self.lifecycle.mutate(
            "stop_deployment",
            deployment_ids={deployment.id},
            profile_ids={deployment.profile_id} if deployment.profile_id else set(),
            bundle_ids={deployment.bundle_id} if deployment.bundle_id else set(),
        ):
            self._require_no_live_dependencies(deployment, "deployment_active")
            with self._lock_for(deployment_id):
                return self._stop_locked(deployment_id)

    def detach(self, deployment_id: str) -> Deployment:
        deployment = self._require(deployment_id)
        with self.lifecycle.mutate("detach_deployment", deployment_ids={deployment.id}):
            with self._lock_for(deployment_id):
                current = self._require(deployment_id)
                self._require_no_live_dependencies(current, "deployment_active")
                return self._detach_checked(current)

    def _detach_checked(self, deployment: Deployment) -> Deployment:
        if deployment.scope != ManagementScope.connected:
            raise ManagerError(
                "Detach applies to connected endpoints. Stop a managed deployment first.",
                code="detach_managed",
                status_code=409,
        )
        self.store.delete_deployment(deployment.id)
        return deployment.model_copy(update={"status": DeploymentStatus.stopped, "updated_at": utc_now()})

    def _require_no_live_dependencies(self, deployment: Deployment, code: str) -> None:
        if self.require_no_live_dependencies is not None:
            self.require_no_live_dependencies(deployment, code)

    def health(self, deployment_id: str) -> Deployment:
        with self._lock_for(deployment_id):
            return self._health_locked(deployment_id)

    def smoke(self, deployment_id: str) -> SmokeResult:
        deployment = self._require(deployment_id)
        with self.lifecycle.reserve(deployment):
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
                current = self._reconcile_locked(current)
                if current.reconfiguration and current.reconfiguration.get("phase") == "applying":
                    current = self.store.put_deployment(current.model_copy(update={"reconfiguration": {
                        **current.reconfiguration, "phase": "recovery_required",
                        "error": "The application restarted while settings were being applied. Reload to restore the previous configuration."}}))
                updated.append(current)
        return updated

    def live_owned(self) -> list[Deployment]:
        blocking: list[Deployment] = []
        for deployment in self.store.list_deployments():
            if deployment.scope != ManagementScope.managed:
                continue
            if deployment.status == DeploymentStatus.failed and (deployment.pid is not None or deployment.process_identity is not None):
                blocking.append(deployment)
                continue
            if deployment.status not in _LIVE_MANAGED and not (
                deployment.status == DeploymentStatus.failed
                and (deployment.pid is not None or deployment.process_identity is not None)
            ):
                continue
            if self._owned_live(deployment):
                blocking.append(deployment)
            elif deployment.status == DeploymentStatus.starting and deployment.process_identity is None:
                blocking.append(deployment)
        return blocking

    def _start_locked(self, deployment_id: str) -> Deployment:
        deployment = self._require(deployment_id)
        if deployment.reconfiguration and deployment.reconfiguration.get("phase") == "recovery_required":
            raise ManagerError("Reload this model to restore the previous configuration before using it.", code="reconfigure_recovery_required", status_code=409)
        if deployment.scope != ManagementScope.managed:
            raise ManagerError(
                "Connected endpoints cannot be started by Local AI Workbench.",
                code="connected_no_lifecycle",
                status_code=409,
            )
        if deployment.status == DeploymentStatus.failed and (
            deployment.pid is not None or deployment.process_identity is not None
        ):
            raise ManagerError(
                "Deployment has retained process identity after a failed lifecycle cleanup. "
                "Stop or unload it before starting again.",
                code="deployment_lifecycle_blocked",
                status_code=409,
                details={"deployment_id": deployment.id, "pid": deployment.pid},
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
        requested_bags = resolve_bags(startup=deployment.requested_startup)
        _require_valid_managed_startup(requested_bags.startup)
        host, port, startup_overrides = self._allocate_listen(
            requested_bags.startup.applied,
            fixed=deployment.requested_startup.get("port") is not None,
        )
        bags = resolve_bags(
            startup=deployment.requested_startup,
            per_request=deployment.settings.per_request.requested,
            agent=deployment.settings.agent.requested,
            startup_overrides=startup_overrides,
        )
        _require_valid_managed_startup(bags.startup)
        if bags.startup.applied != deployment.applied_startup or bags != deployment.settings:
            deployment = self.store.put_deployment(
                deployment.model_copy(
                    update={
                        "applied_startup": bags.startup.applied,
                        "settings": bags,
                        "endpoint": f"http://{host}:{port}/v1",
                        "updated_at": utc_now(),
                    }
                )
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
        cleanup_deployment = starting
        try:
            identity = self.processes.start(
                argv,
                cwd=Path(executable).parent,
                log_path=deployment_log_path(self.runtime.paths.logs, starting.id),
            )
            recorded = starting.model_copy(
                update={
                    "pid": identity.pid,
                    "process_identity": identity,
                    "updated_at": utc_now(),
                }
            )
            self.store.put_deployment(recorded)
            cleanup_deployment = recorded
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
            return self._fail_unowned(cleanup_deployment, error=str(exc), identity=identity)

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
                error=LEGACY_IDENTITY_DETACHED_MESSAGE,
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
                    self.store.put_deployment(
                        deployment.model_copy(
                            update={
                                "status": DeploymentStatus.failed,
                                "error": exc.message,
                                "resource_usage": ResourceUsage(
                                    available=False,
                                    reason="managed process stop failed",
                                ),
                                "updated_at": utc_now(),
                            }
                        )
                    )
                    raise
                self._clear_ownership(
                    deployment,
                    status=DeploymentStatus.stopped,
                    error=PROCESS_IDENTITY_MISMATCH_DETACHED_MESSAGE,
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
        props = self.probe.props(deployment.endpoint) if report.healthy else None
        if deployment.scope == ManagementScope.connected:
            usage = ResourceUsage(
                available=False,
                reason="connected endpoint — external process is not managed",
            )
            status = DeploymentStatus.running if report.healthy else DeploymentStatus.unhealthy
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
        if deployment.status == DeploymentStatus.failed and (deployment.pid is not None or identity is not None):
            return deployment
        if identity is None:
            if deployment.pid is not None and deployment.status in _LIVE_MANAGED:
                return self._clear_ownership(
                    deployment,
                    status=DeploymentStatus.stopped,
                    error=LEGACY_IDENTITY_DETACHED_MESSAGE,
                )
            if deployment.status == DeploymentStatus.starting:
                return self._clear_ownership(
                    deployment,
                    status=DeploymentStatus.failed,
                    error=(
                        "Deployment was starting without process identity after restart. "
                        "No process was stopped; start it again to create a verified owned process."
                    ),
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
                error=PROCESS_IDENTITY_MISMATCH_DETACHED_MESSAGE,
            )
        if verdict == "unproven":
            return self.store.put_deployment(
                deployment.model_copy(
                    update={
                        "status": DeploymentStatus.failed,
                        "pid": identity.pid,
                        "process_identity": identity,
                        "resource_usage": ResourceUsage(
                            available=False,
                            reason="managed process identity could not be verified",
                        ),
                        "error": (
                            "Deployment process identity could not be verified. "
                            "No process was stopped; stop or unload it before starting again."
                        ),
                        "updated_at": utc_now(),
                    }
                )
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
        verdict = self.processes.classify(identity)
        if verdict == "match":
            return True
        return verdict == "unproven" and deployment.status in {*_LIVE_MANAGED, DeploymentStatus.failed}

    def _fail_unowned(
        self,
        deployment: Deployment,
        *,
        error: str,
        identity: ProcessIdentity | None,
    ) -> Deployment:
        retained = deployment
        if identity is not None and deployment.process_identity is None:
            retained = deployment.model_copy(
                update={"pid": identity.pid, "process_identity": identity}
            )
        if identity is not None:
            try:
                self.processes.stop(identity)
            except ManagerError as exc:
                return self.store.put_deployment(
                    retained.model_copy(
                        update={
                            "status": DeploymentStatus.failed,
                            "error": f"{error}; cleanup failed: {exc.message}",
                            "updated_at": utc_now(),
                        }
                    )
                )
        return self._clear_ownership(
            retained,
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
        *,
        fixed: bool = False,
    ) -> tuple[str, int, dict[str, Any]]:
        host = str(requested.get("host") or "127.0.0.1")
        try:
            requested_port = int(requested.get("port") or 8080)
        except (TypeError, ValueError) as exc:
            raise ManagerError(
                "Invalid managed startup setting: port must be an integer.",
                code="managed_startup_invalid",
                status_code=400,
                details={"unsupported": ["port"], "retired": []},
            ) from exc
        if fixed and not _port_available(host, requested_port):
            conflict = next((item for item in self.store.list_deployments()
                if item.endpoint and _endpoint_port(item.endpoint) == requested_port
                and item.process_identity is not None), None)
            owner = conflict.display_name if conflict else "another application"
            raise ManagerError(
                f"Port {requested_port} is already in use by {owner}. Choose Automatic or another port.",
                code="managed_port_conflict", status_code=409,
                details={"port": requested_port, "deployment_id": conflict.id if conflict else None},
            )
        port = requested_port if fixed else _first_free_port(host, requested_port)
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


def _require_valid_managed_startup(startup: Any) -> None:
    unsupported = list(getattr(startup, "unsupported", []) or [])
    retired = list(getattr(startup, "retired", []) or [])
    if not unsupported and not retired:
        return
    retired_keys = [note.key for note in retired]
    keys = [*unsupported, *retired_keys]
    raise ManagerError(
        "Invalid managed startup settings: "
        f"{', '.join(keys)}. Correct or remove these settings before starting llama-server.",
        code="managed_startup_invalid",
        status_code=400,
        details={"unsupported": unsupported, "retired": retired_keys},
    )


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
    for port in range(start, min(start + 50, 65536)):
        if _port_available(host, port):
            return port
    raise ManagerError(
        "No free listen port found",
        code="no_free_port",
        status_code=409,
    )


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # SO_REUSEADDR on Windows permits binding an occupied port. Do not use it.
        try:
            sock.bind((host, port))
        except OSError:
            return False
        return True
