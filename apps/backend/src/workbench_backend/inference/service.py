"""Model-manager facade used by the FastAPI routes."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import time

from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import BundleService
from workbench_backend.inference.import_jobs import ImportJobRunner
from workbench_backend.inference.configuration_options import bundle_configuration_options
from workbench_backend.inference.configurations import ensure_model_configurations, requested_identity
from workbench_backend.inference.deployments import DeploymentService
from workbench_backend.inference.hf_fetch import HuggingFaceFetcher
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.inspect import inspect_gguf_file, read_gguf_runtime_metadata
from workbench_backend.inference.inspection_cache import cached_inspection
from workbench_backend.inference.lifecycle import LifecycleCoordinator
from workbench_backend.inference.process import HttpProbe, ProcessSupervisor
from workbench_backend.inference.hardware import NvidiaPresent
from workbench_backend.inference.runtime import RuntimeInstaller, RuntimeService
from workbench_backend.inference.schemas import (
    ConnectedDeploymentRequest,
    BundleConfigurationOptions,
    DeleteFilePlan,
    DeletePreview,
    Deployment,
    DeploymentProfileChanges,
    DeploymentStatus,
    DuplicateProfileRequest,
    HuggingFaceImportRequest,
    ImportJob,
    InspectReport,
    GgufRuntimeMetadata,
    LifecycleConsumer,
    LocalImportRequest,
    ManagedDeploymentRequest,
    ManagementScope,
    ModelBundle,
    BundleProjectors,
    PinRuntimeRequest,
    ProfileWriteRequest,
    ModelConfigurationWriteRequest,
    ReconfigureDeploymentRequest,
    RenameProfileRequest,
    RunProfile,
    RuntimeManifest,
    SettingsBags,
    SmokeResult,
)
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.inference.store import RecordStore
from workbench_backend.lab.store import LabStore
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.migrate import open_application_store


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
        self.lifecycle = LifecycleCoordinator()
        self.imports = ImportJobRunner(
            self.paths,
            self.store,
            self.bundles,
            lifecycle=self.lifecycle,
            require_repair_allowed=self._require_repair_allowed,
        )
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
            lifecycle=self.lifecycle,
            require_no_live_dependencies=self._require_no_live_deployment_dependencies,
        )

    def describe_paths(self) -> dict[str, str]:
        return self.paths.as_public_dict()

    def _require_repair_allowed(self, bundle_id: str) -> None:
        self._require_no_live_runs(bundle_ids={bundle_id}, code="bundle_active")
        for deployment in self.store.list_deployments():
            if deployment.bundle_id == bundle_id and deployment.status in {DeploymentStatus.starting, DeploymentStatus.running, DeploymentStatus.unhealthy}:
                raise ManagerError("Unload this model before repairing its files.", code="bundle_active", status_code=409)

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
        ensure_model_configurations(self.store)
        return [self.bundles.verify_bundle(bundle, use_cache=True) for bundle in self.store.list_bundles()]

    def get_bundle(self, bundle_id: str) -> ModelBundle:
        bundle = self.store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)
        return self.bundles.verify_bundle(bundle)

    def bundle_projectors(self, bundle_id: str) -> BundleProjectors:
        bundle = self.store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)
        return self.bundles.projector_candidates(bundle)

    def select_bundle_projector(self, bundle_id: str, path: str | None) -> ModelBundle:
        with self.lifecycle.mutate("select_projector", bundle_ids={bundle_id}):
            self._require_no_live_runs(bundle_ids={bundle_id}, code="bundle_active")
            for deployment in self.store.list_deployments():
                if deployment.bundle_id == bundle_id and (
                    deployment.status in {DeploymentStatus.starting, DeploymentStatus.running, DeploymentStatus.unhealthy}
                    or deployment.pid is not None or deployment.process_identity is not None
                ):
                    raise ManagerError("Unload this model before changing its image companion.", code="bundle_active", status_code=409)
            bundle = self.store.get_bundle(bundle_id)
            if bundle is None:
                raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)
            if bundle.status.value != "complete":
                raise ManagerError("Complete the model installation before selecting its image companion.", code="bundle_not_deployable", status_code=409)
            return self.bundles.select_projector(bundle, path)

    def inspect_bundle(self, bundle_id: str, *, refresh: bool = False) -> InspectReport:
        bundle = self.store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)
        bundle = self.bundles.verify_bundle(bundle, use_cache=not refresh)
        report, _, _ = cached_inspection(self.store, bundle, "full", InspectReport,
            lambda: inspect_gguf_file(self.bundles.inspectable_file(bundle), bundle_id=bundle.id), refresh=refresh)
        return report

    def get_bundle_configuration_options(
        self,
        bundle_id: str,
        *,
        deployment_id: str | None = None,
        refresh: bool = False,
    ) -> BundleConfigurationOptions:
        deployment = self.get_deployment(deployment_id) if deployment_id else None
        if deployment is not None and deployment.bundle_id != bundle_id:
            raise ManagerError(
                "Deployment does not belong to the requested bundle.",
                code="deployment_bundle_mismatch",
                status_code=400,
                details={
                    "bundle_id": bundle_id,
                    "deployment_id": deployment.id,
                    "deployment_bundle_id": deployment.bundle_id,
                },
            )
        bundle = self.store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)
        verified = self.bundles.verify_bundle(bundle, use_cache=True)
        metadata, cached, inspected_at = cached_inspection(self.store, verified, "runtime", GgufRuntimeMetadata,
            lambda: self._read_bundle_runtime_metadata(verified), refresh=refresh)
        result = bundle_configuration_options(
            verified.id,
            metadata,
            deployment=deployment,
        )
        result.metadata.update(inspection_cached=cached, inspected_at=inspected_at)
        return result

    def _read_bundle_runtime_metadata(self, bundle: ModelBundle) -> GgufRuntimeMetadata:
        primary = self.bundles.inspectable_file(bundle)
        metadata = read_gguf_runtime_metadata(primary)
        # The MTP head can live in the last shard rather than the primary file.
        for item in bundle.files:
            if item.role.value == "shard" and Path(item.path) != primary:
                shard = read_gguf_runtime_metadata(Path(item.path))
                if shard.has_mtp_tensors:
                    metadata.has_mtp_tensors = True
        return metadata

    def list_profiles(self) -> list[RunProfile]:
        ensure_model_configurations(self.store)
        return [self._resolved_profile(profile) for profile in self.store.list_profiles()]

    def list_model_configurations(self, bundle_id: str) -> list[RunProfile]:
        self._require_profile_bundle(bundle_id)
        return [profile for profile in self.list_profiles() if profile.bundle_id == bundle_id]

    def save_model_configuration(self, bundle_id: str, request: ModelConfigurationWriteRequest) -> RunProfile:
        with self.store.configuration_lock():
            self.list_model_configurations(bundle_id)
            body = ProfileWriteRequest(**{**request.model_dump(exclude={"configuration_id", "make_default"}), "bundle_id": bundle_id})
            if request.configuration_id:
                existing = self.get_profile(request.configuration_id)
                self._validate_profile_bundle(existing, bundle_id)
                profile = self.update_profile(existing.id, body)
            else:
                profile = self.create_profile(body)
            if request.make_default:
                self.set_default_configuration(bundle_id, profile.id)
            return profile

    def set_default_configuration(self, bundle_id: str, configuration_id: str) -> ModelBundle:
        with self.store.configuration_lock():
            bundle = self.store.get_bundle(bundle_id)
            if bundle is None:
                raise ManagerError("Unknown model", code="bundle_missing", status_code=404)
            profile = self.get_profile(configuration_id)
            if profile.bundle_id != bundle_id:
                raise ManagerError("Configuration belongs to another model.", code="profile_bundle_mismatch", status_code=400)
            return self.store.put_bundle(bundle.model_copy(update={"default_configuration_id": profile.id}))

    def configuration_deployment(self, configuration_id: str) -> Deployment | None:
        profile = self.get_profile(configuration_id)
        matches = [d for d in self.store.list_deployments() if d.bundle_id == profile.bundle_id
            and (d.profile_id == profile.id or requested_identity(d.settings) == requested_identity(profile.bags))]
        return max(matches, key=lambda d: (d.status == DeploymentStatus.running and bool(d.health and d.health.healthy and d.process_identity),
            d.status != DeploymentStatus.failed, d.updated_at), default=None)

    def get_profile(self, profile_id: str) -> RunProfile:
        profile = self.store.get_profile(profile_id)
        if profile is None:
            raise ManagerError("Unknown profile", code="profile_missing", status_code=404)
        return self._resolved_profile(profile)

    def _resolved_profile(self, profile: RunProfile) -> RunProfile:
        """Re-resolve requested keys so pre-correction profiles show retired notes."""

        return profile.model_copy(
            update={
                "bags": resolve_bags(
                    startup=profile.bags.startup.requested,
                    per_request=profile.bags.per_request.requested,
                    agent=profile.bags.agent.requested,
                )
            }
        )

    def create_profile(self, request: ProfileWriteRequest) -> RunProfile:
        self._require_profile_bundle(request.bundle_id)
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
        with self.store.configuration_lock():
            return self._update_profile_locked(profile_id, request)

    def _update_profile_locked(self, profile_id: str, request: ProfileWriteRequest) -> RunProfile:
        self._require_profile_bundle(request.bundle_id)
        existing = self.get_profile(profile_id)
        if request.expected_revision is not None and request.expected_revision != existing.revision:
            raise ManagerError("This configuration changed elsewhere. Refresh before saving.", code="configuration_revision_conflict", status_code=409)
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
                "revision": existing.revision + 1,
            }
        )
        return self.store.put_profile(updated)

    def rename_profile(self, profile_id: str, request: RenameProfileRequest | str) -> RunProfile:
        display_name = request if isinstance(request, str) else request.display_name
        existing = self.get_profile(profile_id)
        return self.store.put_profile(
            existing.model_copy(update={"display_name": display_name, "updated_at": utc_now(), "revision": existing.revision + 1})
        )

    def duplicate_profile(
        self,
        profile_id: str,
        request: DuplicateProfileRequest | None = None,
    ) -> RunProfile:
        existing = self.get_profile(profile_id)
        now = utc_now()
        display_name = request.display_name if request and request.display_name else f"{existing.display_name} copy"
        duplicate = existing.model_copy(
            update={
                "id": new_id("profile"),
                "display_name": display_name,
                "created_at": now,
                "updated_at": now,
                "revision": 1,
            },
            deep=True,
        )
        return self.store.put_profile(duplicate)

    def profile_delete_preview(self, profile_id: str) -> DeletePreview:
        profile = self.get_profile(profile_id)
        consumers = self._profile_consumers(profile.id)
        blockers = [consumer for consumer in consumers if consumer.live]
        return DeletePreview(
            target_kind="profile",
            target_id=profile.id,
            blockers=blockers,
            consumers=consumers,
            retained=[
                "Historical deployments, Chat conversations, Lab cases and runs keep their saved profile id/configuration."
            ],
        )

    def delete_profile(self, profile_id: str) -> DeletePreview:
        with self.lifecycle.mutate("delete_profile", profile_ids={profile_id}):
            preview = self.profile_delete_preview(profile_id)
            if preview.blockers:
                raise self._blocked_error("profile_delete_blocked", preview.blockers)
            if any(bundle.default_configuration_id == profile_id for bundle in self.store.list_bundles()):
                raise ManagerError("Choose another default before deleting this configuration.", code="default_configuration_required", status_code=409)
            self.store.delete_profile(profile_id)
            return preview

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
        deployment_ids = {deployment.id for deployment in self.store.list_deployments()}
        with self.lifecycle.mutate("pin_runtime", deployment_ids=deployment_ids):
            self.deployments.reconcile()
            running = self.deployments.live_owned()
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

    def reconcile_deployments(self) -> list[Deployment]:
        return self.deployments.reconcile()

    def create_managed(self, request: ManagedDeploymentRequest) -> Deployment:
        self._require_deployable_bundle(request.bundle_id)
        if request.profile_id:
            profile = self.get_profile(request.profile_id)
            self._validate_profile_bundle(profile, request.bundle_id)
        with self.lifecycle.mutate(
            "create_managed",
            profile_ids={request.profile_id} if request.profile_id else set(),
            bundle_ids={request.bundle_id},
        ):
            profile = self.get_profile(request.profile_id) if request.profile_id else None
            startup = dict(profile.bags.startup.requested) if profile else {}
            for key, value in request.startup.items():
                if value is None:
                    startup.pop(key, None)
                else:
                    startup[key] = value
            wanted = resolve_bags(startup=startup, per_request=profile.bags.per_request.requested if profile else {},
                agent=profile.bags.agent.requested if profile else {})
            candidates = [d for d in self.store.list_deployments() if d.bundle_id == request.bundle_id
                and d.scope == ManagementScope.managed and d.profile_id == request.profile_id
                and requested_identity(d.settings) == requested_identity(wanted)]
            if candidates:
                existing = max(candidates, key=lambda d: (d.status == DeploymentStatus.running and bool(d.health and d.health.healthy), d.updated_at))
                return self.deployments.start(existing.id) if request.auto_start else existing
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
        deployment = self.get_deployment(deployment_id)
        if deployment.bundle_id:
            self._require_deployable_bundle(deployment.bundle_id)
        return self.deployments.start(deployment_id)

    def stop_deployment(self, deployment_id: str) -> Deployment:
        deployment = self.get_deployment(deployment_id)
        with self.lifecycle.mutate(
            "stop_deployment",
            deployment_ids={deployment.id},
            profile_ids={deployment.profile_id} if deployment.profile_id else set(),
            bundle_ids={deployment.bundle_id} if deployment.bundle_id else set(),
        ):
            self._require_no_live_runs(
                deployment_ids={deployment.id},
                profile_ids={deployment.profile_id} if deployment.profile_id else set(),
                bundle_ids={deployment.bundle_id} if deployment.bundle_id else set(),
                code="deployment_active",
            )
            return self.deployments.stop(deployment_id)

    def detach_deployment(self, deployment_id: str) -> Deployment:
        deployment = self.get_deployment(deployment_id)
        with self.lifecycle.mutate("detach_deployment", deployment_ids={deployment.id}):
            self._require_no_live_runs(deployment_ids={deployment.id}, code="deployment_active")
            return self.deployments.detach(deployment_id)

    def ensure_deployment_ready(self, deployment_id: str) -> Deployment:
        deployment = self.get_deployment(deployment_id)
        if deployment.reconfiguration and deployment.reconfiguration.get("phase") == "recovery_required":
            raise ManagerError("Reload this model to restore its previous configuration.", code="reconfigure_recovery_required", status_code=409)
        if deployment.scope == ManagementScope.connected:
            if not deployment.endpoint:
                raise ManagerError("Deployment has no endpoint", code="no_endpoint", status_code=409)
            return deployment
        if (
            deployment.status == DeploymentStatus.running
            and deployment.endpoint
            and (deployment.health is None or deployment.health.healthy)
        ):
            return self._wait_deployment_ready(deployment.id, first=deployment)
        if deployment.bundle_id:
            self._require_deployable_bundle(deployment.bundle_id)
        if deployment.status in {DeploymentStatus.stopped, DeploymentStatus.failed} or not deployment.endpoint:
            deployment = self.deployments.start(deployment.id)
        return self._wait_deployment_ready(deployment.id, first=deployment)

    @contextmanager
    def reserve_deployment(
        self,
        deployment_id: str,
        *,
        profile_id: str | None = None,
    ) -> Iterator[Deployment]:
        deployment = self.get_deployment(deployment_id)
        if profile_id:
            profile = self.get_profile(profile_id)
            if deployment.bundle_id:
                self._validate_profile_bundle(profile, deployment.bundle_id)
        with self.lifecycle.reserve(deployment, profile_id=profile_id):
            yield deployment

    def reload_deployment(self, deployment_id: str) -> Deployment:
        deployment = self.get_deployment(deployment_id)
        with self.lifecycle.mutate(
            "reload_deployment",
            deployment_ids={deployment.id},
            profile_ids={deployment.profile_id} if deployment.profile_id else set(),
            bundle_ids={deployment.bundle_id} if deployment.bundle_id else set(),
        ):
            self._require_no_live_runs(
                deployment_ids={deployment.id},
                profile_ids={deployment.profile_id} if deployment.profile_id else set(),
                bundle_ids={deployment.bundle_id} if deployment.bundle_id else set(),
                code="deployment_active",
            )
            if deployment.scope != ManagementScope.managed:
                raise ManagerError(
                    "Connected endpoints cannot be reloaded by Local AI Workbench.",
                    code="connected_no_lifecycle",
                    status_code=409,
                )
            # Reload launches the recorded files again. Verify them strictly
            # before stopping an otherwise usable owned process.
            self._require_deployable_bundle(deployment.bundle_id or "")
            self.deployments.stop(deployment.id)
            if deployment.reconfiguration and deployment.reconfiguration.get("phase") == "recovery_required":
                prior = deployment.reconfiguration.get("previous")
                if isinstance(prior, dict):
                    restored = Deployment.model_validate(prior).model_copy(update={"pid": None, "process_identity": None,
                        "health": None, "server_props": None, "status": DeploymentStatus.stopped,
                        "reconfiguration": None, "updated_at": utc_now()})
                    self.store.put_deployment(restored)
            return self.deployments.start(deployment.id)

    def reconfigure_deployment(self, deployment_id: str, request: ReconfigureDeploymentRequest) -> Deployment:
        """Change an idle owned process, committing only after verified readiness."""
        from workbench_backend.inference.deployments import _require_valid_managed_startup, managed_argv

        deployment = self.get_deployment(deployment_id)
        with self.lifecycle.mutate("reconfigure_deployment", deployment_ids={deployment.id},
            bundle_ids={deployment.bundle_id} if deployment.bundle_id else set()):
            deployment = self.get_deployment(deployment_id)
            if deployment.reconfiguration and deployment.reconfiguration.get("phase") == "recovery_required":
                raise ManagerError("Reload this model to restore its previous configuration first.", code="reconfigure_recovery_required", status_code=409)
            self._require_no_live_deployment_dependencies(deployment, "deployment_active")
            if request.expected_updated_at is not None and request.expected_updated_at != deployment.updated_at:
                raise ManagerError("Model state changed. Refresh before applying.", code="deployment_revision_conflict", status_code=409)
            if deployment.scope != ManagementScope.managed:
                raise ManagerError("This model is controlled by an external server.", code="connected_no_lifecycle", status_code=409)
            bundle = self._require_deployable_bundle(deployment.bundle_id or "")
            requested = dict(deployment.requested_startup)
            for key, value in request.startup.items():
                if value is None:
                    requested.pop(key, None)
                else:
                    requested[key] = value
            bags = resolve_bags(startup=requested, per_request=deployment.settings.per_request.requested, agent=deployment.settings.agent.requested)
            _require_valid_managed_startup(bags.startup)
            executable = self.runtime.require_executable()
            managed_argv(executable, bundle, bags.startup.applied)
            old_context = deployment.server_props.n_ctx if deployment.server_props else deployment.applied_startup.get("ctx_size")
            new_context = bags.startup.applied.get("ctx_size")
            if request.conversation_id and (new_context is None or not old_context or new_context < old_context):
                with open_application_store(self.paths) as app_store:
                    conversation = app_store.get_conversation(request.conversation_id)
                if conversation is None or conversation.deployment_id != deployment.id:
                    raise ManagerError("This conversation does not use the selected model.", code="context_conversation_mismatch", status_code=409)
                if conversation.run_ids or conversation.transcript:
                    raise ManagerError("Start a new chat to reduce context. This session keeps its retained model history.", code="context_history_requires_new_chat", status_code=409,
                        details={"deployment_id": deployment.id, "applied_context": old_context, "requested_context": new_context})
            # Preflight changed fixed ports while the old process remains usable.
            if requested.get("port") is not None and (requested.get("port") != deployment.applied_startup.get("port") or requested.get("host", "127.0.0.1") != deployment.applied_startup.get("host", "127.0.0.1")):
                self.deployments._allocate_listen(bags.startup.applied, fixed=True)
            prior = deployment.model_dump(mode="json", exclude={"reconfiguration", "capability_evidence", "inference_identity"})
            journal = {"phase": "applying", "previous": prior, "requested_startup": requested, "started_at": utc_now()}
            self.store.put_deployment(deployment.model_copy(update={"reconfiguration": journal}))
            stopped = self.deployments.stop(deployment.id)
            pending = stopped.model_copy(update={"requested_startup": requested, "applied_startup": bags.startup.applied,
                "startup_overrides": {**deployment.startup_overrides, **request.startup}, "settings": bags,
                "server_props": None, "reconfiguration": journal, "updated_at": utc_now()})
            self.store.put_deployment(pending)
            failure = None
            try:
                result = self.deployments.start(deployment.id)
                if result.status == DeploymentStatus.running and result.health and result.health.healthy:
                    return self.store.put_deployment(result.model_copy(update={"reconfiguration": None}))
                failure = result.error or "The changed model did not become ready."
            except Exception as exc:
                failure = str(exc)
            current = self.get_deployment(deployment.id)
            if current.process_identity is not None:
                try:
                    self.deployments.stop(current.id)
                except Exception as exc:
                    journal.update(phase="recovery_required", error=failure, recovery_error=str(exc))
                    self.store.put_deployment(current.model_copy(update={"reconfiguration": journal}))
                    raise ManagerError("The changed model failed and needs recovery before another load.", code="reconfigure_recovery_required", status_code=409, details={"deployment_id": current.id}) from exc
            restored = Deployment.model_validate(prior).model_copy(update={"pid": None, "process_identity": None,
                "health": None, "server_props": None, "status": DeploymentStatus.stopped, "reconfiguration": journal})
            self.store.put_deployment(restored)
            try:
                if deployment.status == DeploymentStatus.running:
                    restored = self.deployments.start(restored.id)
                recovered = restored.status == deployment.status or restored.status == DeploymentStatus.running
            except Exception as exc:
                recovered = False
                journal["recovery_error"] = str(exc)
            journal.update(phase="rolled_back" if recovered else "recovery_required", error=failure)
            self.store.put_deployment(self.get_deployment(deployment.id).model_copy(update={"reconfiguration": journal}))
            raise ManagerError("Could not apply model settings. " + ("The previous configuration was restored." if recovered else "The previous configuration is saved; recovery is needed."),
                code="reconfigure_failed", status_code=409, details={"deployment_id": deployment.id, "recovered": recovered, "cause": failure})

    def deployment_health(self, deployment_id: str) -> Deployment:
        return self.deployments.health(deployment_id)

    def deployment_smoke(self, deployment_id: str) -> SmokeResult:
        return self.deployments.smoke(deployment_id)

    def _wait_deployment_ready(
        self,
        deployment_id: str,
        *,
        first: Deployment | None = None,
        timeout_seconds: float = 20.0,
    ) -> Deployment:
        deadline = time.monotonic() + timeout_seconds
        deployment = first or self.get_deployment(deployment_id)
        while True:
            if deployment.scope != ManagementScope.managed:
                return deployment
            if deployment.status == DeploymentStatus.running and deployment.endpoint:
                if deployment.health is None or deployment.health.healthy:
                    return deployment
            if deployment.status in {DeploymentStatus.failed, DeploymentStatus.stopped}:
                raise ManagerError(
                    "Managed deployment did not become ready.",
                    code="deployment_not_ready",
                    status_code=409,
                    details={
                        "deployment_id": deployment.id,
                        "status": deployment.status.value,
                        "error": deployment.error,
                    },
                )
            if time.monotonic() >= deadline:
                raise ManagerError(
                    "Timed out waiting for managed deployment readiness.",
                    code="deployment_start_timeout",
                    status_code=409,
                    details={
                        "deployment_id": deployment.id,
                        "status": deployment.status.value,
                    },
                )
            time.sleep(0.1)
            deployment = self.deployments.health(deployment.id)

    def deployment_profile_changes(self, deployment_id: str) -> DeploymentProfileChanges:
        deployment = self.get_deployment(deployment_id)
        if not deployment.profile_id:
            return DeploymentProfileChanges(deployment_id=deployment.id)
        profile = self.get_profile(deployment.profile_id)
        frozen = deployment.profile_snapshot or deployment.settings
        current_profile_startup = dict(profile.bags.startup.requested)
        pending_requested_startup = dict(current_profile_startup)
        for key, value in deployment.startup_overrides.items():
            if value is None:
                pending_requested_startup.pop(key, None)
            else:
                pending_requested_startup[key] = value
        current = resolve_bags(
            startup=pending_requested_startup,
            per_request=profile.bags.per_request.requested,
            agent=profile.bags.agent.requested,
            startup_overrides={
                key: deployment.applied_startup[key]
                for key in ("host", "port")
                if key in deployment.applied_startup
            },
        )
        pending: dict[str, dict[str, object]] = {}
        keys = sorted(set(deployment.settings.startup.applied) | set(current.startup.applied))
        for key in keys:
            active = deployment.settings.startup.applied.get(key)
            profile_value = current.startup.applied.get(key)
            if active != profile_value:
                pending[key] = {"active": active, "profile": profile_value}
        return DeploymentProfileChanges(
            deployment_id=deployment.id,
            profile_id=profile.id,
            has_pending_startup_changes=bool(pending),
            pending_startup=pending,
            has_pending_per_request_changes=profile.bags.per_request.requested
            != frozen.per_request.requested,
            has_pending_agent_changes=profile.bags.agent.requested != frozen.agent.requested,
        )

    def bundle_delete_preview(self, bundle_id: str, *, permanent: bool = False) -> DeletePreview:
        # Deletion needs recorded ownership and current file paths, not a full
        # multi-gigabyte integrity scan of weights which will be removed.
        bundle = self.store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)
        consumers = self._bundle_consumers(bundle.id)
        related_jobs = self.imports.bundle_jobs(bundle)
        consumers.extend(LifecycleConsumer(kind="import_job", id=job.id, label=job.display_name or job.id,
            live=self.imports.job_is_active(job),
            retained=not permanent) for job in related_jobs)
        related_ids = {job.id for job in related_jobs}
        for job in self.store.list_active_jobs():
            if job.id in related_ids or not job.source_path:
                continue
            source = Path(job.source_path).resolve()
            if any(Path(file.path).resolve() == source or Path(file.path).resolve().is_relative_to(source)
                   for file in [*bundle.files, *bundle.shards, *bundle.companions]):
                consumers.append(LifecycleConsumer(kind="import_job", id=job.id, label="Import is reading this model's files", live=True))
        if permanent:
            consumers = [consumer.model_copy(update={"retained": False}) if consumer.kind in {"profile", "deployment"} else consumer for consumer in consumers]
        blockers = [consumer for consumer in consumers if consumer.live]
        files = self._bundle_delete_files(bundle, permanent=permanent)
        if permanent:
            files.extend(DeleteFilePlan(path=str(path), size_bytes=self._current_file_size(path), removable=True)
                         for path in self.imports.bundle_staging_files(bundle))
            blockers.extend(LifecycleConsumer(kind="file", id=file.path,
                label=f"{file.reason}: {file.path}", live=True) for file in files if not file.removable)
        return DeletePreview(
            target_kind="bundle",
            target_id=bundle.id,
            blockers=blockers,
            consumers=consumers,
            files=files,
            removable_bytes=sum(file.size_bytes for file in files if file.removable),
            retained=[
                "Historical conversations and runs remain with unavailable model references; they are not switched to another model.",
                "Unrelated files and download caches still used by other models or imports are retained.",
            ] if permanent else [
                "External imported originals and shared companion paths outside the managed models directory are retained.",
                "Historical consumers keep unavailable references instead of switching models.",
            ],
        )

    def delete_bundle(self, bundle_id: str, *, permanent: bool = False) -> DeletePreview:
        initial = self.bundle_delete_preview(bundle_id, permanent=permanent)
        deployment_ids = {consumer.id for consumer in initial.consumers if consumer.kind == "deployment"}
        profile_ids = {consumer.id for consumer in initial.consumers if consumer.kind == "profile"}
        with self.imports._job_lock, self.lifecycle.mutate(
            "delete_bundle",
            deployment_ids=deployment_ids,
            profile_ids=profile_ids,
            bundle_ids={bundle_id},
        ):
            preview = self.bundle_delete_preview(bundle_id, permanent=permanent)
            if preview.blockers:
                raise self._blocked_error("bundle_delete_blocked", preview.blockers)
            bundle = self.store.get_bundle(bundle_id)
            for file in preview.files:
                if file.removable:
                    try:
                        Path(file.path).unlink(missing_ok=True)
                    except OSError as exc:
                        raise ManagerError("Could not delete a model file. Close applications using it and retry. The model record was kept so you can retry.",
                            code="bundle_delete_failed", status_code=409, details={"path": file.path}) from exc
            self._cleanup_empty_managed_dirs(preview.files, bundle)
            if permanent:
                self.imports.purge_bundle_jobs(bundle)
                for consumer in preview.consumers:
                    if consumer.kind == "profile":
                        self.store.delete_profile(consumer.id)
                    elif consumer.kind == "deployment":
                        self.store.delete_deployment(consumer.id)
            self.store.delete_bundle(bundle_id)
            return preview

    def _require_deployable_bundle(self, bundle_id: str) -> ModelBundle:
        stored = self.store.get_bundle(bundle_id)
        if stored is None:
            raise ManagerError(
                "A complete, on-disk bundle is required. A failed or interrupted "
                "download is not a successful deployment.",
                code="bundle_not_deployable",
                status_code=409,
            )
        bundle = self.bundles.verify_bundle(stored)
        if bundle.status.value != "complete" or not bundle.disk_matches:
            raise ManagerError(
                "A complete, on-disk bundle is required. A failed or interrupted "
                "download is not a successful deployment.",
                code="bundle_not_deployable",
                status_code=409,
            )
        return bundle

    def _require_profile_bundle(self, bundle_id: str | None) -> None:
        if bundle_id is not None and self.store.get_bundle(bundle_id) is None:
            raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)

    def _validate_profile_bundle(self, profile: RunProfile, bundle_id: str) -> None:
        if profile.bundle_id is not None and profile.bundle_id != bundle_id:
            raise ManagerError(
                "Profile is bound to a different bundle.",
                code="profile_bundle_mismatch",
                status_code=400,
                details={
                    "profile_id": profile.id,
                    "profile_bundle_id": profile.bundle_id,
                    "bundle_id": bundle_id,
                },
            )

    def _profile_consumers(self, profile_id: str) -> list[LifecycleConsumer]:
        consumers: list[LifecycleConsumer] = []
        for deployment in self.store.list_deployments():
            if deployment.profile_id != profile_id:
                continue
            live = deployment.status in {
                DeploymentStatus.starting,
                DeploymentStatus.running,
                DeploymentStatus.unhealthy,
            } or (deployment.status == DeploymentStatus.failed and (deployment.pid is not None or deployment.process_identity is not None))
            consumers.append(
                LifecycleConsumer(
                    kind="deployment",
                    id=deployment.id,
                    label=deployment.display_name,
                    live=live,
                )
            )
        consumers.extend(self._run_consumers(profile_ids={profile_id}))
        consumers.extend(self._chat_consumers(profile_id=profile_id))
        consumers.extend(self._lab_consumers(profile_id=profile_id))
        return consumers

    def _bundle_consumers(self, bundle_id: str) -> list[LifecycleConsumer]:
        consumers: list[LifecycleConsumer] = []
        deployment_ids: set[str] = set()
        profile_ids: set[str] = set()
        for profile in self.store.list_profiles():
            if profile.bundle_id == bundle_id:
                profile_ids.add(profile.id)
                consumers.append(
                    LifecycleConsumer(kind="profile", id=profile.id, label=profile.display_name)
                )
        for deployment in self.store.list_deployments():
            if deployment.bundle_id == bundle_id:
                deployment_ids.add(deployment.id)
                if deployment.profile_id:
                    profile_ids.add(deployment.profile_id)
                live = deployment.status in {
                    DeploymentStatus.starting,
                    DeploymentStatus.running,
                    DeploymentStatus.unhealthy,
                } or (deployment.status == DeploymentStatus.failed and (deployment.pid is not None or deployment.process_identity is not None))
                consumers.append(
                    LifecycleConsumer(
                        kind="deployment",
                        id=deployment.id,
                        label=deployment.display_name,
                        live=live,
                    )
                )
        consumers.extend(self._run_consumers(deployment_ids=deployment_ids, profile_ids=profile_ids))
        consumers.extend(self._chat_consumers(profile_ids=profile_ids, deployment_ids=deployment_ids))
        consumers.extend(self._lab_consumers(profile_ids=profile_ids, deployment_ids=deployment_ids))
        return consumers

    def _run_consumers(
        self,
        *,
        deployment_ids: set[str] | None = None,
        profile_ids: set[str] | None = None,
    ) -> list[LifecycleConsumer]:
        deployment_ids = deployment_ids or set()
        profile_ids = profile_ids or set()
        try:
            with open_application_store(self.paths) as app_store:
                runs = app_store.list_runs()
        except Exception as exc:
            raise ManagerError("Could not check active model work. Retry after the local state store is available.", code="model_dependencies_unavailable", status_code=503) from exc
        consumers: list[LifecycleConsumer] = []
        for run in runs:
            helper_uses_model = any(helper.configuration.deployment_id in deployment_ids
                or helper.configuration.profile_id in profile_ids for helper in getattr(run, "helper_snapshots", []) or [])
            if run.deployment_id not in deployment_ids and run.embedding_deployment_id not in deployment_ids and (run.profile_id or "") not in profile_ids and not helper_uses_model:
                continue
            consumers.append(
                LifecycleConsumer(
                    kind="agent_run",
                    id=run.id,
                    label=run.source_surface,
                    live=is_run_lifecycle_live(run.status),
                )
            )
        return consumers

    def _chat_consumers(self, *, profile_id: str | None = None, profile_ids: set[str] | None = None, deployment_ids: set[str] | None = None) -> list[LifecycleConsumer]:
        profiles = set(profile_ids or ()) | ({profile_id} if profile_id else set())
        deployments = deployment_ids or set()
        try:
            with open_application_store(self.paths) as app_store:
                conversations = app_store.list_conversations()
        except Exception as exc:
            raise ManagerError("Could not check saved conversations. Retry after the local state store is available.", code="model_dependencies_unavailable", status_code=503) from exc
        consumers = [
            LifecycleConsumer(
                kind="chat",
                id=conversation.id,
                label=conversation.thread_id,
                live=False,
            )
            for conversation in conversations
            if conversation.profile_id in profiles or conversation.deployment_id in deployments or conversation.embedding_deployment_id in deployments
        ]
        for conversation in conversations:
            for item in conversation.queue:
                frozen = item.frozen_config or item.intended_config or {}
                if (frozen.get("deployment_id", conversation.deployment_id) in deployments
                    or frozen.get("embedding_deployment_id", conversation.embedding_deployment_id) in deployments
                    or frozen.get("profile_id", conversation.profile_id) in profiles
                    or frozen.get("model_configuration_id") in profiles
                    or any(helper.configuration.deployment_id in deployments or helper.configuration.profile_id in profiles
                        for helper in item.helper_snapshots or [])):
                    consumers.append(LifecycleConsumer(kind="chat_queue", id=item.id, label=conversation.title or conversation.id, live=True))
        return consumers

    def _lab_consumers(self, *, profile_id: str | None = None, profile_ids: set[str] | None = None, deployment_ids: set[str] | None = None) -> list[LifecycleConsumer]:
        profiles = set(profile_ids or ()) | ({profile_id} if profile_id else set())
        deployments = deployment_ids or set()
        try:
            cases = LabStore(self.paths).list_cases()
        except Exception as exc:
            raise ManagerError("Could not check saved Lab cases. Retry after the local state store is available.", code="model_dependencies_unavailable", status_code=503) from exc
        return [
            LifecycleConsumer(kind="lab_case", id=case.id, label=case.task[:80], live=False)
            for case in cases
            if case.profile_id in profiles or case.deployment_id in deployments or case.embedding_deployment_id in deployments
        ]

    def _require_no_live_runs(
        self,
        *,
        deployment_ids: set[str] | None = None,
        profile_ids: set[str] | None = None,
        bundle_ids: set[str] | None = None,
        code: str,
    ) -> None:
        deployment_ids = set(deployment_ids or set())
        profile_ids = set(profile_ids or set())
        for deployment in self.store.list_deployments():
            if bundle_ids and deployment.bundle_id in bundle_ids:
                deployment_ids.add(deployment.id)
                if deployment.profile_id:
                    profile_ids.add(deployment.profile_id)
        blockers = [
            consumer
            for consumer in [*self._run_consumers(
                deployment_ids=deployment_ids,
                profile_ids=profile_ids,
            ), *self._chat_consumers(deployment_ids=deployment_ids, profile_ids=profile_ids)]
            if consumer.live
        ]
        if blockers:
            raise self._blocked_error(code, blockers)

    def _require_no_live_deployment_dependencies(self, deployment: Deployment, code: str) -> None:
        self._require_no_live_runs(
            deployment_ids={deployment.id},
            profile_ids={deployment.profile_id} if deployment.profile_id else set(),
            bundle_ids={deployment.bundle_id} if deployment.bundle_id else set(),
            code=code,
        )

    def _bundle_delete_files(self, bundle: ModelBundle, *, permanent: bool = False) -> list[DeleteFilePlan]:
        all_files = [*bundle.files, *bundle.shards, *bundle.companions]
        unique: dict[str, DeleteFilePlan] = {}
        managed_bundle_root = Path(bundle.managed_root).resolve() if bundle.managed_root else None
        referenced_paths = {
            self._path_key(Path(file.path))
            for other in self.store.list_bundles()
            if other.id != bundle.id
            for file in [*other.files, *other.shards, *other.companions]
        }
        for file in all_files:
            path = Path(file.path)
            removable = False
            reason = None
            in_managed_bundle = False
            root_is_owned_bundle = (
                managed_bundle_root is not None and managed_bundle_root.name == bundle.id
            )
            if managed_bundle_root is not None:
                try:
                    path.resolve().relative_to(managed_bundle_root)
                    in_managed_bundle = True
                except ValueError:
                    in_managed_bundle = False
            linked = any(candidate.is_symlink() or candidate.is_junction() for candidate in (path, *path.parents))
            if linked:
                reason = "linked_path"
            elif path.exists() and not path.is_file():
                reason = "not_a_regular_file"
            elif self._path_key(path) in referenced_paths:
                reason = "shared_reference"
            elif permanent:
                removable = True
            elif file.ownership != "managed" or not in_managed_bundle or not root_is_owned_bundle:
                reason = "external_original"
            else:
                removable = True
            unique[file.path] = DeleteFilePlan(
                path=file.path,
                size_bytes=self._current_file_size(path),
                removable=removable,
                reason=reason,
            )
        return list(unique.values())

    def _current_file_size(self, path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def _path_key(self, path: Path) -> str:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path.absolute()
        return str(resolved).casefold()

    def _cleanup_empty_managed_dirs(self, files: list[DeleteFilePlan], bundle: ModelBundle) -> None:
        if not bundle.managed_root:
            return
        managed_root = Path(bundle.managed_root).resolve()
        if managed_root.name != bundle.id:
            return
        for file in files:
            if not file.removable:
                continue
            path = Path(file.path).parent
            while path != managed_root:
                try:
                    path.resolve().relative_to(managed_root)
                except ValueError:
                    break
                try:
                    path.rmdir()
                except OSError:
                    break
                path = path.parent
        try:
            managed_root.rmdir()
        except OSError:
            pass

    def _blocked_error(self, code: str, blockers: list[LifecycleConsumer]) -> ManagerError:
        return ManagerError(
            "Active or blocking consumers still reference this model configuration.",
            code=code,
            status_code=409,
            details={"blockers": [blocker.model_dump(mode="json") for blocker in blockers]},
        )


def manager_from_env(data_root: Path | None = None) -> ModelManager:
    return ModelManager(WorkbenchPaths(data_root))
