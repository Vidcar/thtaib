"""Model-manager facade used by the FastAPI routes."""

from __future__ import annotations

from pathlib import Path

from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import BundleService
from workbench_backend.inference.deployments import DeploymentService
from workbench_backend.inference.hf_fetch import HuggingFaceFetcher
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.inspect import inspect_gguf_file
from workbench_backend.inference.process import HttpProbe, ProcessSupervisor
from workbench_backend.inference.hardware import NvidiaPresent
from workbench_backend.inference.runtime import RuntimeInstaller, RuntimeService
from workbench_backend.inference.schemas import (
    ConnectedDeploymentRequest,
    Deployment,
    HuggingFaceImportRequest,
    ImportJob,
    InspectReport,
    LocalImportRequest,
    ManagedDeploymentRequest,
    ModelBundle,
    PinRuntimeRequest,
    ProfileWriteRequest,
    RunProfile,
    RuntimeManifest,
    SettingsBags,
    SmokeResult,
)
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.inference.store import RecordStore
from workbench_backend.paths import WorkbenchPaths


class ModelManager:
    def __init__(
        self,
        paths: WorkbenchPaths,
        *,
        hf: HuggingFaceFetcher | None = None,
        installer: RuntimeInstaller | None = None,
        processes: ProcessSupervisor | None = None,
        probe: HttpProbe | None = None,
        nvidia_present: NvidiaPresent | None = None,
    ) -> None:
        self.paths = paths.ensure()
        self.store = RecordStore(self.paths)
        self.bundles = BundleService(self.paths, self.store, hf=hf)
        self.runtime = RuntimeService(
            self.paths,
            self.store,
            installer=installer,
            nvidia_present=nvidia_present,
        )
        self.deployments = DeploymentService(
            self.store,
            self.runtime,
            processes=processes,
            probe=probe,
        )

    def describe_paths(self) -> dict[str, str]:
        return self.paths.as_public_dict()

    def import_local(self, request: LocalImportRequest) -> ImportJob:
        return self.bundles.import_local(request)

    def import_huggingface(self, request: HuggingFaceImportRequest) -> ImportJob:
        return self.bundles.import_huggingface(request)

    def list_jobs(self) -> list[ImportJob]:
        return self.store.list_jobs()

    def get_job(self, job_id: str) -> ImportJob:
        job = self.store.get_job(job_id)
        if job is None:
            raise ManagerError("Unknown import job", code="job_missing", status_code=404)
        return job

    def list_bundles(self) -> list[ModelBundle]:
        return [self.bundles.verify_bundle(bundle) for bundle in self.store.list_bundles()]

    def get_bundle(self, bundle_id: str) -> ModelBundle:
        bundle = self.store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)
        return self.bundles.verify_bundle(bundle)

    def inspect_bundle(self, bundle_id: str) -> InspectReport:
        bundle = self.get_bundle(bundle_id)
        return inspect_gguf_file(self.bundles.inspectable_file(bundle), bundle_id=bundle.id)

    def list_profiles(self) -> list[RunProfile]:
        return self.store.list_profiles()

    def get_profile(self, profile_id: str) -> RunProfile:
        profile = self.store.get_profile(profile_id)
        if profile is None:
            raise ManagerError("Unknown profile", code="profile_missing", status_code=404)
        return profile

    def create_profile(self, request: ProfileWriteRequest) -> RunProfile:
        now = utc_now()
        profile = RunProfile(
            id=new_id("profile"),
            display_name=request.display_name,
            bundle_id=request.bundle_id,
            bags=resolve_bags(
                startup=request.startup,
                per_request=request.per_request,
                agent=request.agent,
            ),
            created_at=now,
            updated_at=now,
        )
        return self.store.put_profile(profile)

    def update_profile(self, profile_id: str, request: ProfileWriteRequest) -> RunProfile:
        existing = self.get_profile(profile_id)
        updated = existing.model_copy(
            update={
                "display_name": request.display_name,
                "bundle_id": request.bundle_id,
                "bags": resolve_bags(
                    startup=request.startup,
                    per_request=request.per_request,
                    agent=request.agent,
                ),
                "updated_at": utc_now(),
            }
        )
        return self.store.put_profile(updated)

    def resolve_preview(
        self,
        *,
        startup: dict,
        per_request: dict,
        agent: dict,
    ) -> SettingsBags:
        return resolve_bags(startup=startup, per_request=per_request, agent=agent)

    def current_runtime(self) -> RuntimeManifest | None:
        return self.runtime.current()

    def pin_runtime(self, request: PinRuntimeRequest | None = None) -> RuntimeManifest:
        request = request or PinRuntimeRequest()
        running = self.runtime.running_managed_deployments()
        if running:
            if not request.stop_first:
                raise ManagerError(
                    "Cannot pin the managed runtime while a managed llama-server is running. "
                    "Stop the deployment first, or retry with stop_first. "
                    "A half-finished pin is not recorded as success.",
                    code="runtime_pin_busy",
                    status_code=409,
                )
            for deployment in running:
                self.deployments.stop(deployment.id)
        return self.runtime.pin(request)

    def create_managed(self, request: ManagedDeploymentRequest) -> Deployment:
        return self.deployments.create_managed(request)

    def attach_connected(self, request: ConnectedDeploymentRequest) -> Deployment:
        return self.deployments.attach_connected(request)

    def list_deployments(self) -> list[Deployment]:
        return self.store.list_deployments()

    def get_deployment(self, deployment_id: str) -> Deployment:
        deployment = self.store.get_deployment(deployment_id)
        if deployment is None:
            raise ManagerError(
                "Unknown deployment",
                code="deployment_missing",
                status_code=404,
            )
        return deployment

    def start_deployment(self, deployment_id: str) -> Deployment:
        return self.deployments.start(deployment_id)

    def stop_deployment(self, deployment_id: str) -> Deployment:
        return self.deployments.stop(deployment_id)

    def detach_deployment(self, deployment_id: str) -> Deployment:
        return self.deployments.detach(deployment_id)

    def deployment_health(self, deployment_id: str) -> Deployment:
        return self.deployments.health(deployment_id)

    def deployment_smoke(self, deployment_id: str) -> SmokeResult:
        return self.deployments.smoke(deployment_id)


def manager_from_env(data_root: Path | None = None) -> ModelManager:
    return ModelManager(WorkbenchPaths(data_root))
