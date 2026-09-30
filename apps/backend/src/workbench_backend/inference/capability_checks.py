"""Background checks owned by the backend, independent of Models navigation."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from contextlib import contextmanager
from typing import Any

from workbench_backend.errors import ManagerError
from workbench_backend.inference.capabilities import Capability, CapabilityProbeRequest, applicable_capabilities, proof_fingerprint
from workbench_backend.inference.capability_context import resolve_probe_bag, selected_configuration
from workbench_backend.inference.schemas import DeploymentStatus, ManagementScope

log = logging.getLogger(__name__)


@dataclass
class _Checks:
    deployment_id: str
    bundle_id: str | None = None
    stop: threading.Event = field(default_factory=threading.Event)
    capability: Capability | None = None
    thread: threading.Thread | None = None


class CapabilityCheckCoordinator:
    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self._lock = threading.RLock()
        self._workers: dict[str, _Checks] = {}
        self._suspended_deployments: dict[str, int] = {}
        self._suspended_bundles: dict[str, int] = {}
        self._closed = False

    def start(self, deployment_id: str, configuration_id: str | None = None) -> None:
        """Queue only missing applicable proof after a healthy named setup load."""
        deployment = self.manager.get_deployment(deployment_id)
        configuration_id = configuration_id or deployment.profile_id
        if (not configuration_id or deployment.benchmark_owner or deployment.scope != ManagementScope.managed
                or deployment.status != DeploymentStatus.running or not deployment.endpoint
                or deployment.health is None or not deployment.health.healthy):
            return
        try:
            profile = selected_configuration(self.manager, configuration_id)
            request = CapabilityProbeRequest(capability="text_stream", configuration_id=profile.id,
                                             expected_configuration_revision=profile.revision)
            bag = resolve_probe_bag(self.manager, deployment, request)
        except ManagerError:
            # Deleted, changed or deliberately detached setups are never
            # silently redirected to a different response recipe.
            return
        capabilities = applicable_capabilities(deployment, bag)
        fingerprint = proof_fingerprint(deployment, bag)
        from workbench_backend.inference.capabilities import capability_support
        if not any(capability_support(deployment, name, bag) == "untested" for name in capabilities):
            return
        with self._lock:
            if (self._closed or fingerprint in self._workers
                    or self._suspended_deployments.get(deployment_id)
                    or self._suspended_bundles.get(deployment.bundle_id or "")):
                return
            work = _Checks(deployment_id=deployment_id, bundle_id=deployment.bundle_id)
            thread = threading.Thread(target=self._run, args=(fingerprint, work, request, capabilities),
                                      name="model-capability-checks", daemon=True)
            work.thread = thread
            self._workers[fingerprint] = work
            thread.start()

    def _run(self, fingerprint: str, work: _Checks, request: CapabilityProbeRequest,
             capabilities: list[Capability]) -> None:
        from workbench_backend.inference.probes import run_capability_probe
        try:
            for name in capabilities:
                if work.stop.is_set():
                    break
                with self._lock:
                    work.capability = name
                run_capability_probe(self.manager, work.deployment_id,
                    request.model_copy(update={"capability": name}), only_missing=True, cancelled=work.stop.is_set)
        except ManagerError:
            # Shutdown/lifecycle changes leave not-started checks untested.
            # The next healthy load may retry them.
            pass
        except Exception:
            log.exception("Automatic model capability checks stopped")
        finally:
            with self._lock:
                self._workers.pop(fingerprint, None)

    def state(self, fingerprint: str) -> tuple[bool, Capability | None]:
        with self._lock:
            work = self._workers.get(fingerprint)
            return (work is not None, work.capability if work else None)

    def cancel(self, deployment_id: str) -> None:
        with self._lock:
            for work in self._workers.values():
                if work.deployment_id == deployment_id:
                    work.stop.set()

    @contextmanager
    def suspend(self, deployment_id: str, bundle_id: str | None = None):
        """Drain automatic owners before lifecycle mutation; keep real run guards."""
        keys = [(self._suspended_deployments, deployment_id)]
        if bundle_id:
            keys.append((self._suspended_bundles, bundle_id))
        with self._lock:
            for counts, key in keys:
                counts[key] = counts.get(key, 0) + 1
            workers = [work for work in self._workers.values()
                       if work.deployment_id == deployment_id or (bundle_id and work.bundle_id == bundle_id)]
            for work in workers:
                work.stop.set()
        try:
            self._drain(workers)
            yield
        finally:
            with self._lock:
                for counts, key in keys:
                    counts[key] -= 1
                    if not counts[key]:
                        del counts[key]

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self.stop_all()

    def stop_all(self) -> None:
        """Drain checks for Quit while allowing admission if Quit is aborted."""
        with self._lock:
            workers = list(self._workers.values())
            for work in workers:
                work.stop.set()
        self._drain(workers)

    @staticmethod
    def _drain(workers: list[_Checks]) -> None:
        deadline = time.monotonic() + 60
        for work in workers:
            if work.thread is not None and work.thread is not threading.current_thread():
                work.thread.join(timeout=max(0, deadline - time.monotonic()))
                if work.thread.is_alive():
                    raise ManagerError("A model check is still finishing. Retry after it stops.",
                                       code="model_check_active", status_code=409)
