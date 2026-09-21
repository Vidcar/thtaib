"""In-memory lifecycle admission gate for model manager mutations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import threading

from workbench_backend.errors import ManagerError
from workbench_backend.inference.schemas import Deployment


class LifecycleCoordinator:
    """Serialize run admission against destructive model lifecycle mutations."""

    def __init__(self) -> None:
        self._condition = threading.Condition(threading.RLock())
        self._mutation: str | None = None
        self._mutation_owner: int | None = None
        self._mutation_depth = 0
        self._deployment_refs: dict[str, int] = {}
        self._profile_refs: dict[str, int] = {}
        self._bundle_refs: dict[str, int] = {}

    @contextmanager
    def reserve(self, deployment: Deployment, *, profile_id: str | None = None) -> Iterator[None]:
        deps = self._deps_for(deployment, profile_id=profile_id)
        owner = threading.get_ident()
        with self._condition:
            if self._mutation is not None and self._mutation_owner != owner:
                raise ManagerError(
                    "Model lifecycle change is in progress. Try again after it finishes.",
                    code="model_lifecycle_busy",
                    status_code=409,
                    details={"operation": self._mutation},
                )
            self._add_refs(deps)
        try:
            yield
        finally:
            with self._condition:
                self._drop_refs(deps)
                self._condition.notify_all()

    @contextmanager
    def mutate(
        self,
        operation: str,
        *,
        deployment_ids: set[str] | None = None,
        profile_ids: set[str] | None = None,
        bundle_ids: set[str] | None = None,
    ) -> Iterator[None]:
        deployment_ids = deployment_ids or set()
        profile_ids = profile_ids or set()
        bundle_ids = bundle_ids or set()
        owner = threading.get_ident()
        with self._condition:
            if self._mutation is not None and self._mutation_owner == owner:
                self._mutation_depth += 1
                nested = True
            else:
                nested = False
            if self._mutation is not None:
                if not nested:
                    raise ManagerError(
                        "Another model lifecycle change is already in progress.",
                        code="model_lifecycle_busy",
                        status_code=409,
                        details={"operation": self._mutation},
                    )
            else:
                blockers = self._reservation_blockers(
                    deployment_ids=deployment_ids,
                    profile_ids=profile_ids,
                    bundle_ids=bundle_ids,
                )
                if blockers:
                    raise ManagerError(
                        "Active model work is using this configuration. Stop or wait for it before changing lifecycle state.",
                        code="model_lifecycle_active",
                        status_code=409,
                        details={"blockers": blockers},
                    )
                self._mutation = operation
                self._mutation_owner = owner
                self._mutation_depth = 1
        try:
            yield
        finally:
            with self._condition:
                if self._mutation_owner == owner:
                    self._mutation_depth -= 1
                    if self._mutation_depth <= 0:
                        self._mutation = None
                        self._mutation_owner = None
                        self._mutation_depth = 0
                        self._condition.notify_all()

    def _reservation_blockers(
        self,
        *,
        deployment_ids: set[str],
        profile_ids: set[str],
        bundle_ids: set[str],
    ) -> list[dict[str, str]]:
        blockers: list[dict[str, str]] = []
        for deployment_id in sorted(deployment_ids):
            if self._deployment_refs.get(deployment_id, 0) > 0:
                blockers.append({"kind": "deployment", "id": deployment_id})
        for profile_id in sorted(profile_ids):
            if self._profile_refs.get(profile_id, 0) > 0:
                blockers.append({"kind": "profile", "id": profile_id})
        for bundle_id in sorted(bundle_ids):
            if self._bundle_refs.get(bundle_id, 0) > 0:
                blockers.append({"kind": "bundle", "id": bundle_id})
        return blockers

    def _deps_for(
        self,
        deployment: Deployment,
        *,
        profile_id: str | None,
    ) -> tuple[set[str], set[str], set[str]]:
        profiles = {value for value in (profile_id, deployment.profile_id) if value}
        bundles = {deployment.bundle_id} if deployment.bundle_id else set()
        return {deployment.id}, profiles, bundles

    def _add_refs(self, deps: tuple[set[str], set[str], set[str]]) -> None:
        deployments, profiles, bundles = deps
        for deployment_id in deployments:
            self._deployment_refs[deployment_id] = self._deployment_refs.get(deployment_id, 0) + 1
        for profile_id in profiles:
            self._profile_refs[profile_id] = self._profile_refs.get(profile_id, 0) + 1
        for bundle_id in bundles:
            self._bundle_refs[bundle_id] = self._bundle_refs.get(bundle_id, 0) + 1

    def _drop_refs(self, deps: tuple[set[str], set[str], set[str]]) -> None:
        deployments, profiles, bundles = deps
        for deployment_id in deployments:
            self._decrement(self._deployment_refs, deployment_id)
        for profile_id in profiles:
            self._decrement(self._profile_refs, profile_id)
        for bundle_id in bundles:
            self._decrement(self._bundle_refs, bundle_id)

    @staticmethod
    def _decrement(refs: dict[str, int], key: str) -> None:
        next_count = refs.get(key, 0) - 1
        if next_count > 0:
            refs[key] = next_count
        else:
            refs.pop(key, None)
