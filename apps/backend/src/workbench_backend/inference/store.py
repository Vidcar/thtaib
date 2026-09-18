"""JSON record store under the managed state directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter

from workbench_backend.inference.schemas import (
    Deployment,
    ImportJob,
    ModelBundle,
    RunProfile,
    RuntimeManifest,
)
from workbench_backend.paths import WorkbenchPaths

T = TypeVar("T", bound=BaseModel)


class RecordStore:
    def __init__(self, paths: WorkbenchPaths) -> None:
        self.paths = paths.ensure()
        self.bundles_path = self.paths.state / "bundles.json"
        self.jobs_path = self.paths.state / "import_jobs.json"
        self.profiles_path = self.paths.state / "profiles.json"
        self.deployments_path = self.paths.state / "deployments.json"
        self.runtime_manifest_path = self.paths.runtimes / "runtime-manifest.json"

    def list_bundles(self) -> list[ModelBundle]:
        return self._read_list(self.bundles_path, ModelBundle)

    def put_bundle(self, bundle: ModelBundle) -> ModelBundle:
        return self._upsert(self.bundles_path, ModelBundle, bundle)

    def get_bundle(self, bundle_id: str) -> ModelBundle | None:
        return next((item for item in self.list_bundles() if item.id == bundle_id), None)

    def list_jobs(self) -> list[ImportJob]:
        return self._read_list(self.jobs_path, ImportJob)

    def put_job(self, job: ImportJob) -> ImportJob:
        return self._upsert(self.jobs_path, ImportJob, job)

    def get_job(self, job_id: str) -> ImportJob | None:
        return next((item for item in self.list_jobs() if item.id == job_id), None)

    def list_profiles(self) -> list[RunProfile]:
        return self._read_list(self.profiles_path, RunProfile)

    def put_profile(self, profile: RunProfile) -> RunProfile:
        return self._upsert(self.profiles_path, RunProfile, profile)

    def get_profile(self, profile_id: str) -> RunProfile | None:
        return next((item for item in self.list_profiles() if item.id == profile_id), None)

    def list_deployments(self) -> list[Deployment]:
        return self._read_list(self.deployments_path, Deployment)

    def put_deployment(self, deployment: Deployment) -> Deployment:
        return self._upsert(self.deployments_path, Deployment, deployment)

    def get_deployment(self, deployment_id: str) -> Deployment | None:
        return next(
            (item for item in self.list_deployments() if item.id == deployment_id),
            None,
        )

    def delete_deployment(self, deployment_id: str) -> None:
        remaining = [item for item in self.list_deployments() if item.id != deployment_id]
        self._write_list(self.deployments_path, remaining)

    def read_runtime_manifest(self) -> RuntimeManifest | None:
        if not self.runtime_manifest_path.is_file():
            return None
        return RuntimeManifest.model_validate_json(
            self.runtime_manifest_path.read_text(encoding="utf-8")
        )

    def write_runtime_manifest(self, manifest: RuntimeManifest) -> RuntimeManifest:
        self._write_json(self.runtime_manifest_path, manifest.model_dump(mode="json"))
        return manifest

    def _read_list(self, path: Path, model: type[T]) -> list[T]:
        if not path.is_file():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return TypeAdapter(list[model]).validate_python(raw)

    def _write_list(self, path: Path, items: list[BaseModel]) -> None:
        self._write_json(path, [item.model_dump(mode="json") for item in items])

    def _upsert(self, path: Path, model: type[T], item: T) -> T:
        items = self._read_list(path, model)
        replaced = False
        next_items: list[T] = []
        for existing in items:
            if getattr(existing, "id") == getattr(item, "id"):
                next_items.append(item)
                replaced = True
            else:
                next_items.append(existing)
        if not replaced:
            next_items.append(item)
        self._write_list(path, next_items)
        return item

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
        tmp.replace(path)
