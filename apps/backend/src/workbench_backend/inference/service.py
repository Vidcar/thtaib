"""Model-manager facade used by the FastAPI routes."""

from __future__ import annotations

from collections.abc import Iterator, Callable
from contextlib import contextmanager
from pathlib import Path
import hashlib
import re
import time
import httpx

from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import BundleService
from workbench_backend.inference.import_jobs import ImportJobRunner
from workbench_backend.inference.configuration_options import bundle_configuration_options
from workbench_backend.inference.configurations import (
    deployment_for_configuration, duplicate_saved_profile, migrate_model_configurations,
    find_compatible_deployment, has_response_startup_defaults, list_saved_configurations,
    list_saved_profiles, loaded_model_identity, loading_startup_settings, model_default_values,
    rename_saved_profile, requested_identity, require_profile_bundle, resolved_profile,
    saved_profile, set_bundle_default_configuration, validate_profile_bundle, validate_configuration_name,
)
from workbench_backend.inference.deployments import DeploymentService
from workbench_backend.inference.hf_fetch import HuggingFaceFetcher, PUBLISHER_DIR, REPOSITORY_TEMPLATE_DIR
from workbench_backend.inference.hashes import sha256_file
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
    HuggingFaceConfiguration,
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
    ResponseRecipe,
    ResponseRecipeConfigurationResult,
    RuntimeManifest,
    SettingsBags,
    SmokeResult,
)
from workbench_backend.inference.settings import resolve_bags, split_response_startup, STARTUP_KEYS, PER_REQUEST_KEYS
from workbench_backend.inference.store import RecordStore
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
        from workbench_backend.inference.memory_estimates import MemoryEstimator
        self.memory_estimator = MemoryEstimator(self)
        from workbench_backend.inference.capability_checks import CapabilityCheckCoordinator
        self.capability_checks = CapabilityCheckCoordinator(self)
        self.validate_chat_reconfiguration = None
        if self.store.get_setting("models-workspace-records-version") != "1":
            generated = [profile for profile in self.store.list_profiles()
                if profile.id == f"config_{profile.bundle_id}" or profile.id.startswith("config_import_")]
            protected = {profile.id for profile in generated
                if any(consumer.live for consumer in self._profile_consumers(profile.id))}
            migrate_model_configurations(self.store, protected_profile_ids=protected)

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
        return [self.bundles.verify_bundle(bundle, use_cache=True) for bundle in self.store.list_bundles()]

    def get_bundle(self, bundle_id: str) -> ModelBundle:
        bundle = self.store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)
        return self.bundles.verify_bundle(bundle)

    def rename_bundle(self, bundle_id: str, display_name: str) -> ModelBundle:
        name = display_name.strip()
        if not name:
            raise ManagerError("Name this model.", code="bundle_name_required", status_code=400)
        with self.store.configuration_lock():
            bundle = self.store.get_bundle(bundle_id)
            if bundle is None:
                raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)
            return self.store.put_bundle(bundle.model_copy(update={"display_name": name}))

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

    def select_bundle_chat_template(self, bundle_id: str, origin: str) -> ModelBundle:
        if origin not in {"gguf", "repository", "publisher"}:
            raise ManagerError("Choose the GGUF or an available standalone template.", code="template_choice", status_code=400)
        with self.lifecycle.mutate("select_chat_template", bundle_ids={bundle_id}):
            self._require_no_live_runs(bundle_ids={bundle_id}, code="bundle_active")
            for deployment in self.store.list_deployments():
                if deployment.bundle_id == bundle_id and (deployment.status in {
                    DeploymentStatus.starting, DeploymentStatus.running, DeploymentStatus.unhealthy}
                    or deployment.pid is not None or deployment.process_identity is not None):
                    raise ManagerError("Unload this model before changing its chat template.", code="bundle_active", status_code=409)
            bundle = self.store.get_bundle(bundle_id)
            if bundle is None or bundle.huggingface_configuration is None:
                raise ManagerError("This bundle has no recorded Hugging Face template choices.", code="template_unavailable", status_code=404)
            config = bundle.huggingface_configuration
            if origin == "gguf":
                metadata = self._read_bundle_runtime_metadata(bundle)
                if not metadata.chat_template:
                    raise ManagerError("This GGUF has no embedded chat template.", code="template_unavailable", status_code=409)
                unsupported = dict(config.unsupported)
                if config.template_differs:
                    unsupported["chat_template.jinja"] = ("Standalone template differs from GGUF; "
                        "GGUF is selected until a compatible template choice is made.")
                updated = config.model_copy(update={"template_origin": "gguf", "template_file": None,
                    "unsupported": unsupported})
            else:
                names = ([f"{PUBLISHER_DIR}/chat_template.jinja", f"{PUBLISHER_DIR}/chat_template.from-tokenizer.jinja"]
                    if origin == "publisher" else ["chat_template.jinja", f"{REPOSITORY_TEMPLATE_DIR}/chat_template.from-tokenizer.jinja"])
                record = next((item for name in names for item in bundle.files if item.name == name), None)
                if record is None or (origin == "publisher" and not config.source_verified):
                    raise ManagerError("This template has no verified file in the bundle.", code="template_unavailable", status_code=409)
                path = Path(record.path)
                if not path.is_file() or sha256_file(path) != record.sha256:
                    raise ManagerError("The template file is missing or changed.", code="bundle_template_invalid", status_code=409)
                self._probe_chat_template(bundle, path)
                unsupported = dict(config.unsupported)
                unsupported.pop("chat_template.jinja", None)
                updated = config.model_copy(update={"template_origin": origin, "template_file": str(path),
                    "template_compatible": True, "unsupported": unsupported})
            saved = bundle.model_copy(update={"huggingface_configuration": updated})
            return self.store.put_bundle(saved)

    def _probe_chat_template(self, bundle: ModelBundle, path: Path) -> None:
        probe = self.deployments.create_managed(ManagedDeploymentRequest(bundle_id=bundle.id,
            startup={"chat_template_file": str(path), "ctx_size": 2048}, auto_start=False))
        try:
            running = self.deployments.start(probe.id)
            if running.status != DeploymentStatus.running or not running.endpoint:
                raise ManagerError(running.error or "The publisher template could not start with this model.",
                    code="template_incompatible", status_code=409)
            reported = running.server_props.chat_template if running.server_props else None
            if reported is None or reported.rstrip("\r\n") != path.read_text(encoding="utf-8").rstrip("\r\n"):
                raise ManagerError("The runtime did not load the publisher template for the compatibility check.",
                    code="template_incompatible", status_code=409)
            endpoint = running.endpoint.removesuffix("/v1")
            try:
                template_request = {"messages": [
                    {"role": "user", "content": "Template compatibility check"}],
                    "add_generation_prompt": True}
                if self.deployments._router_enabled():
                    template_request["model"] = probe.id
                response = httpx.post(f"{endpoint}/apply-template", json=template_request, timeout=30)
                response.raise_for_status()
                rendered = response.json().get("prompt")
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                raise ManagerError("The publisher template failed the runtime conversation check.",
                    code="template_incompatible", status_code=409) from exc
            if not isinstance(rendered, str) or "Template compatibility check" not in rendered:
                raise ManagerError("The publisher template did not render the check conversation.",
                    code="template_incompatible", status_code=409)
        finally:
            stopped = self.deployments.stop(probe.id)
            if stopped.process_identity is None and stopped.pid is None:
                self.store.delete_deployment(probe.id)
                if self.deployments._router_enabled():
                    self.deployments.router.refresh_presets()

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
        configuration_id: str | None = None,
        startup: dict | None = None,
        refresh: bool = False,
    ) -> BundleConfigurationOptions:
        deployment = self._deployment_for_bundle_options(bundle_id, deployment_id)
        verified, metadata, cached, inspected_at = self._inspected_bundle_for_options(bundle_id, refresh=refresh)
        profile = self._profile_for_bundle_options(bundle_id, configuration_id)
        selected_bags, selected_startup = self._selected_startup_for_options(verified, profile, deployment, startup)
        metadata, template_source = self._metadata_for_selected_template(verified, metadata, selected_startup)
        return self._bundle_configuration_options_result(
            verified, metadata, deployment, selected_bags, selected_startup, template_source, cached, inspected_at,
            configuration_id=configuration_id, startup=startup,
        )

    def _deployment_for_bundle_options(self, bundle_id: str, deployment_id: str | None) -> Deployment | None:
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
        return deployment

    def _inspected_bundle_for_options(
        self, bundle_id: str, *, refresh: bool,
    ) -> tuple[ModelBundle, GgufRuntimeMetadata, bool, str]:
        bundle = self.store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)
        verified = self.bundles.verify_bundle(bundle, use_cache=True)
        if refresh:
            from workbench_backend.inference.inspect import invalidate_gguf_metadata
            for item in verified.files:
                if item.role.value in {"primary_weights", "shard"}:
                    invalidate_gguf_metadata(Path(item.path))
        metadata, cached, inspected_at = cached_inspection(self.store, verified, "runtime", GgufRuntimeMetadata,
            lambda: self._read_bundle_runtime_metadata(verified), refresh=refresh)
        return verified, metadata, cached, inspected_at

    def _profile_for_bundle_options(self, bundle_id: str, configuration_id: str | None) -> RunProfile | None:
        profile = self.get_profile(configuration_id) if configuration_id else None
        if profile is not None and profile.bundle_id != bundle_id:
            raise ManagerError("Configuration belongs to another model.", code="profile_bundle_mismatch", status_code=400)
        return profile

    def _selected_startup_for_options(
        self, verified: ModelBundle, profile: RunProfile | None, deployment: Deployment | None, startup: dict | None,
    ) -> tuple[SettingsBags, dict]:
        requested = dict(profile.bags.startup.requested if profile else deployment.settings.startup.requested if deployment else {})
        for key, value in (startup or {}).items():
            if value is None:
                requested.pop(key, None)
            else:
                requested[key] = value
        initial_startup = model_default_values(self.store, verified, startup=requested)[0]
        selected_bags = resolve_bags(startup=requested, startup_defaults=initial_startup)
        return selected_bags, selected_bags.startup.applied

    def _metadata_for_selected_template(
        self, verified: ModelBundle, metadata: GgufRuntimeMetadata, selected_startup: dict,
    ) -> tuple[GgufRuntimeMetadata, str]:
        configuration = verified.huggingface_configuration
        template_source = "gguf_template"
        selected_file = selected_startup.get("chat_template_file")
        if not selected_file and not selected_startup.get("chat_template") and configuration and configuration.template_file:
            selected_file = configuration.template_file
            template_source = f"{configuration.template_origin}_template"
        elif selected_file:
            template_source = "configuration_template"
        if selected_file:
            path = Path(str(selected_file))
            record = next((item for item in verified.files if Path(item.path).resolve() == path.resolve()), None)
            try:
                with path.open("rb") as template_stream:
                    payload = template_stream.read(2 * 1024 * 1024 + 1)
                if (len(payload) > 2 * 1024 * 1024
                        or record is not None and hashlib.sha256(payload).hexdigest() != record.sha256
                        or template_source != "configuration_template" and record is None):
                    raise ValueError("selected template differs from the verified record")
                metadata = metadata.model_copy(update={"chat_template": payload.decode("utf-8")})
            except (OSError, UnicodeError, ValueError) as exc:
                raise ManagerError("The selected chat template is missing or changed.", code="bundle_template_invalid", status_code=409) from exc
        elif selected_startup.get("chat_template"):
            inline = str(selected_startup["chat_template"])
            # Named native templates require native evaluation. Do not describe
            # the bundle's unrelated embedded template as the selected one.
            metadata = metadata.model_copy(update={"chat_template": inline if "{{" in inline or "{%" in inline else None})
            template_source = "configuration_template"
        return metadata, template_source

    def _bundle_configuration_options_result(
        self,
        verified: ModelBundle,
        metadata: GgufRuntimeMetadata,
        deployment: Deployment | None,
        selected_bags: SettingsBags,
        selected_startup: dict,
        template_source: str,
        cached: bool,
        inspected_at: str,
        *,
        configuration_id: str | None,
        startup: dict | None,
    ) -> BundleConfigurationOptions:
        descriptor_deployment = deployment
        if deployment is not None and (configuration_id is not None or startup is not None):
            exact = (not has_response_startup_defaults(deployment.settings)
                and deployment.loaded_model_identity is not None
                and deployment.loaded_model_identity == loaded_model_identity(self.runtime.current(), verified, selected_bags))
            if not exact:
                descriptor_deployment = None
        result = bundle_configuration_options(
            verified.id,
            metadata,
            deployment=descriptor_deployment,
            huggingface_configuration=verified.huggingface_configuration,
            selected_template_source=template_source,
        )
        result.context_size.applied = selected_startup.get("ctx_size")
        if deployment is not None and descriptor_deployment is None:
            result.deployment_id = deployment.id
            result.context_size.observed = deployment.server_props.n_ctx if deployment.server_props else None
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

    def get_deployment_configuration_options(self, deployment_id: str) -> BundleConfigurationOptions:
        deployment = self.get_deployment(deployment_id)
        if deployment.bundle_id:
            return self.get_bundle_configuration_options(deployment.bundle_id, deployment_id=deployment.id)
        return bundle_configuration_options(None, GgufRuntimeMetadata(), deployment=deployment)

    def list_profiles(self) -> list[RunProfile]:
        return list_saved_profiles(self.store)

    def list_model_configurations(self, bundle_id: str) -> list[RunProfile]:
        return list_saved_configurations(self.store, bundle_id)

    def get_model_card(self, bundle_id: str) -> dict[str, str]:
        """Return only the selected bundle's verified, pinned root README."""
        bundle = self.store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown model.", code="bundle_missing", status_code=404)
        from workbench_backend.inference.hf_configuration import read_bundle_model_card

        card, _ = read_bundle_model_card(bundle, self.bundles.hf)
        return {"bundle_id": bundle.id, "repo_id": card.repo_id, "revision": card.revision,
            "sha256": card.sha256, "markdown": card.markdown, "origin": card.origin}

    def refresh_response_recipes(self, bundle_id: str) -> ModelBundle:
        """Refresh only a pinned model card; weights and saved setups stay untouched."""
        bundle = self.store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown model.", code="bundle_missing", status_code=404)
        source = bundle.source
        if source.kind.value != "huggingface" or not source.repo_id or not source.resolved_revision:
            raise ManagerError("Only revision-pinned Hugging Face models can refresh response recipes.",
                code="recipe_source", status_code=400)
        from workbench_backend.inference.hf_configuration import read_bundle_model_card
        from workbench_backend.inference.hf_recipes import parse_model_card_recipes
        card, local_note = read_bundle_model_card(bundle, self.bundles.hf)
        recipes = parse_model_card_recipes(card.markdown, repo_id=card.repo_id,
            revision=card.revision, sha256=card.sha256)
        with self.store.configuration_lock():
            current = self.store.get_bundle(bundle_id)
            if current is None or current.source != source:
                raise ManagerError("Model source changed while refreshing its card. Try again.",
                    code="recipe_source_changed", status_code=409)
            config = current.huggingface_configuration or HuggingFaceConfiguration()
            unsupported = dict(config.unsupported)
            if local_note:
                unsupported["README.md"] = f"{local_note} Recipes were read from the pinned repository."
            else:
                unsupported.pop("README.md", None)
            updated = config.model_copy(update={"response_recipes": [ResponseRecipe.model_validate(item) for item in recipes],
                "metadata_refreshed_at": utc_now(), "unsupported": unsupported})
            return self.store.put_bundle(current.model_copy(update={"huggingface_configuration": updated}))

    def create_response_recipe_configurations(
        self, bundle_id: str, recipe_ids: list[str], default_recipe_id: str | None = None,
    ) -> ResponseRecipeConfigurationResult:
        from workbench_backend.inference.recipe_configurations import create_recipe_configurations
        result = create_recipe_configurations(self.store, bundle_id, recipe_ids, default_recipe_id)
        recipe_profiles = {profile.recipe_origin.recipe_id: profile for profile in self.store.list_profiles()
            if profile.bundle_id == bundle_id and profile.recipe_origin is not None}
        for job in self.store.list_jobs():
            if job.bundle_id != bundle_id or not job.configuration_error:
                continue
            if all(recipe_id in recipe_profiles for recipe_id in job.recipe_ids) and (
                not job.default_recipe_id or result.bundle.default_configuration_id == recipe_profiles[job.default_recipe_id].id
            ):
                self.store.put_job(job.model_copy(update={"configuration_error": None, "updated_at": utc_now()}))
        return result

    def canonical_configuration(self, configuration_id: str) -> RunProfile:
        return self.get_profile(configuration_id)

    def save_model_configuration(self, bundle_id: str, request: ModelConfigurationWriteRequest) -> RunProfile:
        with self.store.configuration_lock():
            self._require_profile_bundle(bundle_id)
            existing = self.canonical_configuration(request.configuration_id) if request.configuration_id else None
            if existing is not None:
                self._validate_profile_bundle(existing, bundle_id)
            name = validate_configuration_name(self.store, request.display_name, bundle_id, excluding=existing.id if existing else None)
            first_saved = not any(profile.bundle_id == bundle_id for profile in self.store.list_profiles())
            # Optional model-authored guidance is a visible input source. An
            # ordinary response/settings save must not erase it implicitly.
            agent = request.agent if "agent" in request.model_fields_set else (
                dict(existing.bags.agent.requested) if existing is not None else {})
            if set(agent) - {"system_prompt"}:
                raise ManagerError("Model instructions support only system_prompt; choose tools and access in an Agent setup.",
                    code="configuration_agent_instructions", status_code=400)
            if "system_prompt" in agent and not isinstance(agent["system_prompt"], str):
                raise ManagerError("Model instructions must be text. Use an empty instruction bag to reset them.",
                    code="configuration_agent_instructions", status_code=400)
            recipe_origin = existing.recipe_origin if existing else None
            if "recipe_origin" in request.model_fields_set:
                if request.recipe_origin is not None:
                    from workbench_backend.inference.recipe_configurations import validate_recipe_origin
                    recipe_origin = validate_recipe_origin(self.get_bundle(bundle_id), request.recipe_origin)
                else:
                    recipe_origin = None
            body = ProfileWriteRequest(**{**request.model_dump(exclude={"configuration_id", "make_default", "recipe_origin"}),
                "display_name": name, "bundle_id": bundle_id, "agent": agent})
            if request.configuration_id:
                profile = self.update_profile(existing.id, body)
            else:
                profile = self.create_profile(body)
            if profile.recipe_origin != recipe_origin:
                profile = self.store.put_profile(profile.model_copy(update={"recipe_origin": recipe_origin}))
            if request.make_default or first_saved:
                self.set_default_configuration(bundle_id, profile.id)
            return profile

    def set_default_configuration(self, bundle_id: str, configuration_id: str) -> ModelBundle:
        return set_bundle_default_configuration(self.store, bundle_id, configuration_id)

    def configuration_deployment(self, configuration_id: str) -> Deployment | None:
        return deployment_for_configuration(self.store, self.runtime.current(), configuration_id)

    def compatible_deployment(self, bundle_id: str, bags: SettingsBags, *, require_named_origin: bool = False) -> Deployment | None:
        """Find an exact native plan without using setup or response identity."""
        return find_compatible_deployment(self.store, self.runtime.current(), bundle_id, bags, require_named_origin=require_named_origin)

    def get_profile(self, profile_id: str) -> RunProfile:
        return saved_profile(self.store, profile_id)

    def _resolved_profile(self, profile: RunProfile) -> RunProfile:
        """Resolve the shared current baseline without rewriting saved overrides."""
        return resolved_profile(self.store, profile)

    def create_profile(self, request: ProfileWriteRequest) -> RunProfile:
        self._require_profile_bundle(request.bundle_id)
        loading, response = split_response_startup(request.startup, request.per_request)
        bundle = self.store.get_bundle(request.bundle_id) if request.bundle_id else None
        initial_startup, defaults = model_default_values(self.store, bundle, startup=loading) if bundle else ({}, None)
        bags = resolve_bags(startup=loading, startup_defaults=initial_startup,
            per_request=response, agent=request.agent, per_request_defaults=defaults)
        self._validate_configuration_bags(request.bundle_id, bags)
        now = utc_now()
        profile = RunProfile(
            id=new_id("profile"),
            display_name=request.display_name,
            bundle_id=request.bundle_id,
            bags=bags,
            settings_schema_version=2,
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
        loading, response = split_response_startup(request.startup, request.per_request)
        bundle = self.store.get_bundle(request.bundle_id) if request.bundle_id else None
        initial_startup, defaults = model_default_values(self.store, bundle, startup=loading) if bundle else ({}, None)
        bags = resolve_bags(startup=loading, startup_defaults=initial_startup,
            per_request=response, agent=request.agent, per_request_defaults=defaults)
        self._validate_configuration_bags(request.bundle_id, bags)
        updated = existing.model_copy(
            update={
                "display_name": request.display_name,
                "bundle_id": request.bundle_id,
                "bags": bags,
                "settings_schema_version": 2,
                "updated_at": utc_now(),
                "revision": existing.revision + 1,
            }
        )
        return self.store.put_profile(updated)

    def _validate_configuration_bags(self, bundle_id: str | None, bags: SettingsBags) -> None:
        invalid = [key for key in bags.startup.unsupported if key in STARTUP_KEYS]
        invalid.extend(key for key in bags.per_request.unsupported if key in PER_REQUEST_KEYS)
        if invalid:
            raise ManagerError("Correct invalid model control values before saving.", code="configuration_values_invalid", status_code=422,
                               details={"keys": sorted(set(invalid))})
        if not bundle_id:
            return
        options = self.get_bundle_configuration_options(bundle_id, startup=bags.startup.requested)
        architecture = options.metadata.get("architecture") or ""
        if architecture == "deepseek4" and bags.startup.applied.get("cache_type_k", "f16") != bags.startup.applied.get("cache_type_v", "f16"):
            raise ManagerError("This model requires matching K and V cache precision.", code="configuration_cache_invalid", status_code=422)
        for key in ("reasoning", "reasoning_effort", "reasoning_preserve"):
            value = bags.per_request.applied.get(key)
            # b11045 server-common.cpp consumes top-level effort=none, disables
            # Thinking and erases the effort kwarg before the template runs.
            if value is None or value in {"auto", "default"} or key == "reasoning_effort" and value == "none":
                continue
            descriptor = options.per_request_defaults[key]
            if descriptor.supported is False or (descriptor.accepted_values is not None and value not in descriptor.accepted_values):
                raise ManagerError("The selected template does not support this Thinking choice.", code="configuration_thinking_invalid", status_code=422,
                                   details={"key": key, "supported": descriptor.accepted_values})

    def rename_profile(self, profile_id: str, request: RenameProfileRequest | str) -> RunProfile:
        return rename_saved_profile(self.store, profile_id, request)

    def duplicate_profile(
        self,
        profile_id: str,
        request: DuplicateProfileRequest | None = None,
    ) -> RunProfile:
        return duplicate_saved_profile(self.store, profile_id, request)

    def profile_delete_preview(self, profile_id: str) -> DeletePreview:
        with self.store.configuration_lock():
            profile = self.get_profile(profile_id)
            consumers = self._profile_consumers(profile.id)
            blockers = [consumer for consumer in consumers if consumer.live]
            return DeletePreview(
                target_kind="profile",
                target_id=profile.id,
                target_label=profile.display_name,
                blockers=blockers,
                consumers=consumers,
                retained=[
                    "Historical deployments, Chat conversations, Lab cases and runs keep their saved profile id/configuration."
                ],
            )

    def delete_profile(self, profile_id: str) -> DeletePreview:
        with self.lifecycle.mutate("delete_profile", profile_ids={profile_id}):
            with self.store.configuration_lock():
                preview = self.profile_delete_preview(profile_id)
                if any(blocker.live for blocker in preview.blockers):
                    raise self._blocked_error("profile_delete_blocked", preview.blockers)
                if preview.blockers:
                    raise self._blocked_error("profile_delete_blocked", preview.blockers)
                self.store.delete_profile(profile_id)
                for bundle in self.store.list_bundles():
                    if bundle.default_configuration_id == profile_id:
                        self.store.put_bundle(bundle.model_copy(update={"default_configuration_id": None}))
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
                if self.deployments._router_enabled():
                    self._require_no_live_runs(deployment_ids=deployment_ids, code="runtime_pin_busy")
                    self.release_lab_deployments()
                    self.deployments.router.stop_router()
                else:
                    for deployment in running:
                        self.deployments.stop(deployment.id)
            return self.runtime.pin(request)

    def reconcile_deployments(self) -> list[Deployment]:
        return self.deployments.reconcile()

    def create_managed(self, request: ManagedDeploymentRequest) -> Deployment:
        bundle = self._require_deployable_bundle(request.bundle_id, use_cache=True)
        if request.profile_id:
            profile = self.get_profile(request.profile_id)
            self._validate_profile_bundle(profile, request.bundle_id)
        # Preparing a future immutable record is a configuration operation, not
        # a lifecycle mutation. It must remain possible during generation.
        with self.store.configuration_lock():
            profile = self.get_profile(request.profile_id) if request.profile_id else None
            startup = dict(profile.bags.startup.requested) if profile else {}
            for key, value in request.startup.items():
                if value is None:
                    startup.pop(key, None)
                else:
                    startup[key] = value
            initial_startup, response_defaults = model_default_values(self.store, bundle, startup=startup)
            wanted = resolve_bags(startup=startup, startup_defaults=initial_startup,
                per_request_defaults=response_defaults, per_request=profile.bags.per_request.requested if profile else {},
                agent=profile.bags.agent.requested if profile else {})
            from workbench_backend.inference.deployments import _require_valid_managed_startup
            _require_valid_managed_startup(wanted.startup)
            invalid_response = [key for key in wanted.per_request.unsupported if key in PER_REQUEST_KEYS]
            if invalid_response:
                raise ManagerError("Correct invalid response controls before preparing this setup.", code="configuration_values_invalid", status_code=422,
                                   details={"keys": invalid_response})
            existing = self.compatible_deployment(request.bundle_id, wanted, require_named_origin=profile is not None)
            if existing is None:
                existing = self.deployments.create_managed(request.model_copy(update={"auto_start": False}))
                existing = self.store.put_deployment(existing.model_copy(update={
                    "loaded_model_identity": loaded_model_identity(self.runtime.current(), bundle, existing.settings),
                }))
        return self.start_deployment(existing.id, configuration_id=request.profile_id) if request.auto_start else existing

    def attach_connected(self, request: ConnectedDeploymentRequest) -> Deployment:
        return self.deployments.attach_connected(request)

    def list_deployments(self) -> list[Deployment]:
        if self.deployments._router_enabled():
            self.deployments.router.status()
        return self.store.list_deployments()

    def managed_model_runtime(self) -> dict[str, object]:
        return self.deployments.router.status()

    def set_max_loaded_models(self, value: int) -> dict[str, object]:
        managed_ids = {item.id for item in self.store.list_deployments()
                       if item.scope == ManagementScope.managed}
        with self.lifecycle.mutate("set_max_loaded_models", deployment_ids=managed_ids):
            self._require_no_live_runs(deployment_ids=managed_ids, code="deployment_active")
            return self.deployments.router.set_max_loaded_models(value)

    def get_deployment(self, deployment_id: str) -> Deployment:
        deployment = self.store.get_deployment(deployment_id)
        if deployment is None:
            raise ManagerError(
                "Unknown deployment",
                code="deployment_missing",
                status_code=404,
            )
        return deployment

    def start_deployment(self, deployment_id: str, *, configuration_id: str | None = None) -> Deployment:
        deployment = self.get_deployment(deployment_id)
        if deployment.bundle_id:
            self._require_deployable_bundle(deployment.bundle_id)
        self._require_current_loaded_identity(deployment)
        ready = self.deployments.start(deployment_id)
        self.capability_checks.start(ready.id, configuration_id or deployment.profile_id)
        return ready

    def prepare_lab_deployment(self, configuration_id: str, startup: dict, *, owner: str,
                               concurrent: bool, deployment_id: str | None = None,
                               cancelled: Callable[[], bool] | None = None) -> Deployment:
        """Borrow only overflow residency, using the existing managed launcher.

        b11045 fixes router capacity at process start. Overflow therefore uses
        DeploymentService's existing identity-verified managed child path; it
        never restarts the router or edits its saved limit. Admission and slot
        observation are serialized with other application lifecycle callers.
        """
        with self.lifecycle.mutate("prepare_lab_deployment"):
            if deployment_id is None:
                profile = self.get_profile(configuration_id)
                if not profile.bundle_id:
                    raise ManagerError("Lab requires an installed model configuration.", code="lab_model_required", status_code=422)
                deployment = self.create_managed(ManagedDeploymentRequest(bundle_id=profile.bundle_id,
                    profile_id=profile.id, startup=startup, auto_start=False))
            else:
                deployment = self.get_deployment(deployment_id)
            residency = self.managed_model_runtime()
            resident = set(residency["loaded_deployment_ids"]) | set(residency["loading_deployment_ids"])
            if concurrent and deployment.id not in resident and len(resident) >= int(residency["max_loaded_models"]):
                # Never lend an ordinary record to another owner. A fresh record
                # carries immutable launch settings and survives crash recovery.
                deployment = self.store.put_deployment(deployment.model_copy(update={
                    "id": new_id("deployment"), "benchmark_owner": owner,
                    "router_preset_id": None, "endpoint": None, "pid": None,
                    "process_identity": None, "status": DeploymentStatus.stopped, "health": None,
                    "server_props": None, "resource_usage": None, "error": None,
                    "created_at": utc_now(), "updated_at": utc_now(),
                }, deep=True))
            loaded = self.ensure_deployment_ready(deployment.id, **({"cancelled": cancelled} if cancelled else {}))
            if not loaded.benchmark_owner:
                self.deployments.router.hold_for_lab(owner, loaded.id)
            return loaded

    def release_lab_deployments(self, owner: str | None = None) -> None:
        """Release exactly marked overflow children, also after an interrupted run."""
        self.deployments.router.release_lab_holds(owner)
        for deployment in self.store.list_deployments():
            if not deployment.benchmark_owner or owner is not None and deployment.benchmark_owner != owner:
                continue
            # Overflow has its own process and is deliberately unavailable for
            # ordinary configuration binding. Same-bundle Chat on the router
            # must not prevent releasing this distinct child.
            with self.lifecycle.mutate("release_lab_deployment", deployment_ids={deployment.id}):
                self._require_no_live_runs(deployment_ids={deployment.id}, code="deployment_active")
                with self.deployments._lock_for(deployment.id):
                    try:
                        self.deployments._stop_locked(deployment.id)
                    except ManagerError as exc:
                        current = self.store.get_deployment(deployment.id)
                        if (exc.code != "process_identity_mismatch" or current is None
                                or current.process_identity is not None or current.pid is not None):
                            raise
                        # The supervisor proved that this PID no longer belongs
                        # to the benchmark and cleared its stale identity. Never
                        # kill the replacement process or block app recovery.
                self.store.delete_deployment(deployment.id)

    def _require_current_loaded_identity(self, deployment: Deployment) -> None:
        if deployment.scope != ManagementScope.managed or deployment.loaded_model_identity is None or not deployment.bundle_id:
            return
        bundle = self.store.get_bundle(deployment.bundle_id)
        if bundle is not None and loaded_model_identity(self.runtime.current(), bundle, deployment.settings) != deployment.loaded_model_identity:
            raise ManagerError("This model's runtime or files changed after its setup was prepared. Select the saved setup again to prepare the current model.",
                               code="loaded_model_identity_changed", status_code=409,
                               details={"deployment_id": deployment.id, "bundle_id": deployment.bundle_id})

    def stop_deployment(self, deployment_id: str) -> Deployment:
        deployment = self.get_deployment(deployment_id)
        with self.capability_checks.suspend(deployment_id, deployment.bundle_id), self.lifecycle.mutate(
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

    def stop_owned_deployments_for_quit(self) -> None:
        """Stop residency after desktop maintenance has joined execution owners.

        Paused inputs retain their frozen configuration for a later restart;
        unlike an ordinary model change, Quit does not edit that configuration.
        Keep this purpose on the existing lifecycle owner so every lower-level
        guard rechecks active work without granting concurrent callers a bypass.
        """
        self.capability_checks.stop_all()
        managed = [item for item in self.store.list_deployments() if item.scope == ManagementScope.managed]
        deployment_ids = {item.id for item in managed}
        profile_ids = {item.profile_id for item in managed if item.profile_id}
        bundle_ids = {item.bundle_id for item in managed if item.bundle_id}
        with self.lifecycle.mutate("desktop_quit", deployment_ids=deployment_ids,
                                   profile_ids=profile_ids, bundle_ids=bundle_ids):
            self._require_no_live_runs(deployment_ids=deployment_ids, profile_ids=profile_ids,
                                       bundle_ids=bundle_ids, code="deployment_active")
            for deployment in managed:
                self.stop_deployment(deployment.id)
            if self.deployments._router_enabled():
                self.deployments.router.stop_router()

    def stop_legacy_owned_deployment(self, deployment_id: str) -> Deployment:
        """Safely stop a verified older per-model process during local cutover."""
        deployment = self.get_deployment(deployment_id)
        with self.lifecycle.mutate("stop_legacy_owned_deployment", deployment_ids={deployment.id},
                                   profile_ids={deployment.profile_id} if deployment.profile_id else set(),
                                   bundle_ids={deployment.bundle_id} if deployment.bundle_id else set()):
            self._require_no_live_runs(deployment_ids={deployment.id}, code="deployment_active")
            return self.deployments.stop_legacy_owned(deployment.id)

    def detach_deployment(self, deployment_id: str) -> Deployment:
        deployment = self.get_deployment(deployment_id)
        with self.lifecycle.mutate("detach_deployment", deployment_ids={deployment.id}):
            self._require_no_live_runs(deployment_ids={deployment.id}, code="deployment_active")
            return self.deployments.detach(deployment_id)

    def ensure_deployment_ready(self, deployment_id: str, *, cancelled: Callable[[], bool] | None = None) -> Deployment:
        cancellation = {"cancelled": cancelled} if cancelled else {}
        if cancelled is not None and cancelled():
            raise ManagerError("Lab loading was stopped.", code="deployment_load_cancelled", status_code=409)
        deployment = self.get_deployment(deployment_id)
        if deployment.reconfiguration and deployment.reconfiguration.get("phase") == "recovery_required":
            raise ManagerError("Reload this model to restore its previous configuration.", code="reconfigure_recovery_required", status_code=409)
        if deployment.scope == ManagementScope.connected:
            if not deployment.endpoint:
                raise ManagerError("Deployment has no endpoint", code="no_endpoint", status_code=409)
            return deployment
        self._require_current_loaded_identity(deployment)
        if self.deployments._router_enabled() and not deployment.benchmark_owner:
            if deployment.bundle_id:
                # A resident preset already uses verified weight bytes. Recheck
                # its file identity on each turn without hashing the full GGUF.
                self._require_deployable_bundle(deployment.bundle_id, use_cache=True)
            # The selected preset may have been evicted since the last turn.
            # Ask the native scheduler to load it again, even if the saved
            # deployment record still says running. A cache hit is insufficient
            # at that launch boundary, so the router verifies fully before load.
            def verify_before_load() -> None:
                if deployment.bundle_id:
                    self._require_deployable_bundle(deployment.bundle_id)

            return self._wait_deployment_ready(
                deployment.id, first=self.deployments.start(
                    deployment.id, verify_before_load=verify_before_load,
                    **cancellation,
                ),
                timeout_seconds=180.0,
                **cancellation,
            )
        if (
            deployment.status == DeploymentStatus.running
            and deployment.endpoint
            and (deployment.health is None or deployment.health.healthy)
        ):
            return self._wait_deployment_ready(deployment.id, first=deployment, **cancellation)
        if deployment.bundle_id:
            self._require_deployable_bundle(deployment.bundle_id)
        if deployment.status in {DeploymentStatus.stopped, DeploymentStatus.failed} or not deployment.endpoint:
            deployment = self.deployments.start(deployment.id, **cancellation)
        return self._wait_deployment_ready(deployment.id, first=deployment, **cancellation)

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
        with self.capability_checks.suspend(deployment_id, deployment.bundle_id), self.lifecycle.mutate(
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
            ready = self.deployments.start(deployment.id)
        self.capability_checks.start(ready.id, ready.profile_id)
        return ready

    def _guard_reconfigure(self, deployment: Deployment, request: ReconfigureDeploymentRequest) -> None:
        if deployment.reconfiguration and deployment.reconfiguration.get("phase") == "recovery_required":
            raise ManagerError("Reload this model to restore its previous configuration first.", code="reconfigure_recovery_required", status_code=409)
        self._require_no_live_deployment_dependencies(deployment, "deployment_active")
        if request.expected_updated_at is not None and request.expected_updated_at != deployment.updated_at:
            raise ManagerError("Model state changed. Refresh before applying.", code="deployment_revision_conflict", status_code=409)
        if deployment.scope != ManagementScope.managed:
            raise ManagerError("This model is controlled by an external server.", code="connected_no_lifecycle", status_code=409)

    def _profile_for_reconfigure(self, deployment: Deployment, request: ReconfigureDeploymentRequest):
        profile = self.canonical_configuration(request.model_configuration_id) if request.model_configuration_id else None
        if profile is not None:
            if profile.bundle_id != deployment.bundle_id:
                raise ManagerError("Configuration belongs to another model.", code="profile_bundle_mismatch", status_code=400)
            if request.expected_configuration_revision is not None and request.expected_configuration_revision != profile.revision:
                raise ManagerError("The selected configuration changed. Refresh before applying.", code="configuration_revision_conflict", status_code=409)
        return profile

    def _bags_for_reconfigure(self, deployment: Deployment, request: ReconfigureDeploymentRequest, bundle, profile):
        requested = {} if request.replace_startup else dict(deployment.requested_startup)
        for key, value in request.startup.items():
            if value is None:
                requested.pop(key, None)
            else:
                requested[key] = value
        initial_startup, response_defaults = model_default_values(self.store, bundle, startup=requested)
        bags = resolve_bags(startup=requested, startup_defaults=initial_startup, per_request_defaults=response_defaults,
            per_request=profile.bags.per_request.requested if profile else deployment.settings.per_request.requested,
            agent=profile.bags.agent.requested if profile else deployment.settings.agent.requested)
        return requested, bags

    def _guard_shrinking_conversation_context(self, deployment: Deployment, request: ReconfigureDeploymentRequest, requested: dict, profile, bags) -> None:
        old_context = deployment.server_props.n_ctx if deployment.server_props else deployment.applied_startup.get("ctx_size")
        new_context = bags.startup.applied.get("ctx_size")
        if request.conversation_id and (new_context is None or not old_context or new_context < old_context):
            with open_application_store(self.paths) as app_store:
                conversation = app_store.get_conversation(request.conversation_id)
            if conversation is None or conversation.deployment_id != deployment.id:
                raise ManagerError("This conversation does not use the selected model.", code="context_conversation_mismatch", status_code=409)
            if self.validate_chat_reconfiguration is not None:
                self.validate_chat_reconfiguration(request.conversation_id, deployment.id, requested, profile.id if profile else deployment.profile_id)
            elif conversation.run_ids or conversation.transcript:
                raise ManagerError("Conversation compatibility cannot be checked. Retry after opening Chat.",
                    code="context_compatibility_unavailable", status_code=409)

    def _store_identical_running_launch(self, deployment: Deployment, request: ReconfigureDeploymentRequest, requested: dict, bags, profile) -> tuple[Deployment | None, Deployment]:
        # Response settings belong to requests, not the loaded process. An
        # explicit configuration switch with the identical frozen launch
        # reuses that child without rewriting its snapshot. Keep every
        # busy/revision/identity check above and require observed ownership;
        # equal settings on an unhealthy or unowned process are not enough.
        def same_frozen_launch(current: Deployment) -> bool:
            selected = loading_startup_settings(bags)
            return (current.applied_startup == current.settings.startup.applied
                and not has_response_startup_defaults(current.settings)
                and selected == loading_startup_settings(current.settings)
                and (profile is None or loading_startup_settings(profile.bags) == selected))

        if (same_frozen_launch(deployment) and deployment.status == DeploymentStatus.running
            and deployment.health and deployment.health.healthy and deployment.process_identity
            and self.deployments.processes.classify(deployment.process_identity) == "match"):
            identity = deployment.process_identity
            deployment = self.deployments.health(deployment.id)
            if (deployment.status == DeploymentStatus.running and deployment.health and deployment.health.healthy
                and deployment.process_identity == identity
                and self.deployments.processes.classify(identity) == "match"
                and same_frozen_launch(deployment)):
                # Same argv keeps the process. Context Auto is still stored
                # on the request. Response-only keys leave this snapshot.
                loading_request, _ = split_response_startup(requested, {})
                stored_request, _ = split_response_startup(deployment.requested_startup, {})
                if loading_request != stored_request:
                    overrides = dict(request.startup) if request.replace_startup else {**deployment.startup_overrides, **request.startup}
                    return self.store.put_deployment(deployment.model_copy(update={
                        "requested_startup": requested,
                        "startup_overrides": overrides,
                        "settings": deployment.settings.model_copy(update={
                            "startup": deployment.settings.startup.model_copy(update={"requested": dict(requested)}),
                        }),
                        "updated_at": utc_now(),
                    })), deployment
                return deployment, deployment
        return None, deployment

    def _replace_managed_process(self, deployment: Deployment, request: ReconfigureDeploymentRequest, requested: dict, bags, profile, bundle) -> Deployment:
        # Preflight changed fixed ports while the old process remains usable.
        if requested.get("port") is not None and (requested.get("port") != deployment.applied_startup.get("port") or requested.get("host", "127.0.0.1") != deployment.applied_startup.get("host", "127.0.0.1")):
            self.deployments._allocate_listen(bags.startup.applied, fixed=True)
        prior = deployment.model_dump(mode="json", exclude={"reconfiguration", "capability_evidence", "inference_identity"})
        journal = {"phase": "applying", "previous": prior, "requested_startup": requested, "started_at": utc_now()}
        self.store.put_deployment(deployment.model_copy(update={"reconfiguration": journal}))
        stopped = self.deployments.stop(deployment.id)
        pending = stopped.model_copy(update={"requested_startup": requested, "applied_startup": bags.startup.applied,
            "startup_overrides": dict(request.startup) if request.replace_startup else {**deployment.startup_overrides, **request.startup}, "settings": bags,
            "profile_id": profile.id if profile else deployment.profile_id,
            "profile_snapshot": profile.bags.model_copy(deep=True) if profile else deployment.profile_snapshot,
            "configuration_revision": profile.revision if profile else deployment.configuration_revision,
            "loaded_model_identity": loaded_model_identity(self.runtime.current(), bundle, bags),
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

    def reconfigure_deployment(self, deployment_id: str, request: ReconfigureDeploymentRequest) -> Deployment:
        """Change an idle owned process, committing only after verified readiness."""
        from workbench_backend.inference.deployments import _require_valid_managed_startup, managed_argv

        deployment = self.get_deployment(deployment_id)
        with self.capability_checks.suspend(deployment_id, deployment.bundle_id), self.lifecycle.mutate("reconfigure_deployment", deployment_ids={deployment.id},
            bundle_ids={deployment.bundle_id} if deployment.bundle_id else set()):
            deployment = self.get_deployment(deployment_id)
            self._guard_reconfigure(deployment, request)
            bundle = self._require_deployable_bundle(deployment.bundle_id or "")
            profile = self._profile_for_reconfigure(deployment, request)
            requested, bags = self._bags_for_reconfigure(deployment, request, bundle, profile)
            _require_valid_managed_startup(bags.startup)
            executable = self.runtime.require_executable()
            managed_argv(executable, bundle, bags.startup.applied)
            self._guard_shrinking_conversation_context(deployment, request, requested, profile, bags)
            reused, deployment = self._store_identical_running_launch(deployment, request, requested, bags, profile)
            ready = reused if reused is not None else self._replace_managed_process(deployment, request, requested, bags, profile, bundle)
        self.capability_checks.start(ready.id, profile.id if profile else ready.profile_id)
        return ready

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
        cancelled: Callable[[], bool] | None = None,
    ) -> Deployment:
        deadline = time.monotonic() + timeout_seconds
        deployment = first or self.get_deployment(deployment_id)
        while True:
            if cancelled is not None and cancelled():
                raise ManagerError("Lab loading was stopped.", code="deployment_load_cancelled", status_code=409)
            if deployment.scope != ManagementScope.managed:
                return deployment
            if deployment.status == DeploymentStatus.running and deployment.endpoint:
                if deployment.health is None or deployment.health.healthy:
                    self.capability_checks.start(deployment.id, deployment.profile_id)
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
        bundle = self.store.get_bundle(deployment.bundle_id or "")
        initial_startup = model_default_values(self.store, bundle, startup=pending_requested_startup)[0] if bundle else {}
        current = resolve_bags(
            startup=pending_requested_startup,
            startup_defaults=initial_startup,
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
                self.store.delete_bundle_capability_evidence(bundle_id, deployment_ids)
            self.store.delete_bundle(bundle_id)
            return preview

    def _require_deployable_bundle(self, bundle_id: str, *, use_cache: bool = False) -> ModelBundle:
        stored = self.store.get_bundle(bundle_id)
        if stored is None:
            raise ManagerError(
                "A complete, on-disk bundle is required. A failed or interrupted "
                "download is not a successful deployment.",
                code="bundle_not_deployable",
                status_code=409,
            )
        bundle = self.bundles.verify_bundle(stored, use_cache=use_cache)
        if bundle.status.value != "complete" or not bundle.disk_matches:
            raise ManagerError(
                "A complete, on-disk bundle is required. A failed or interrupted "
                "download is not a successful deployment.",
                code="bundle_not_deployable",
                status_code=409,
            )
        return bundle

    def _require_profile_bundle(self, bundle_id: str | None) -> None:
        require_profile_bundle(self.store, bundle_id)

    def _validate_profile_bundle(self, profile: RunProfile, bundle_id: str) -> None:
        validate_profile_bundle(profile, bundle_id)

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
                runs = app_store.list_runs_operational()
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

    def _chat_consumers(self, *, profile_id: str | None = None, profile_ids: set[str] | None = None, deployment_ids: set[str] | None = None, ignore_paused: bool = False) -> list[LifecycleConsumer]:
        profiles = set(profile_ids or ()) | ({profile_id} if profile_id else set())
        deployments = deployment_ids or set()
        try:
            with open_application_store(self.paths) as app_store:
                conversations = app_store.list_conversations(include_archived=True)
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
                if ignore_paused and item.status == "paused":
                    continue
                frozen = item.frozen_config or item.intended_config or {}
                if (frozen.get("deployment_id", conversation.deployment_id) in deployments
                    or frozen.get("embedding_deployment_id", conversation.embedding_deployment_id) in deployments
                    or frozen.get("profile_id", conversation.profile_id) in profiles
                    or frozen.get("model_configuration_id") in profiles
                    or any(helper.configuration.deployment_id in deployments or helper.configuration.profile_id in profiles
                        for helper in item.helper_snapshots or [])):
                    consumers.append(LifecycleConsumer(kind="chat_queue", id=item.id, label=conversation.title or conversation.id, live=True))
        return consumers

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
            ), *self._chat_consumers(deployment_ids=deployment_ids, profile_ids=profile_ids,
                                    ignore_paused=self.lifecycle.owns_mutation("desktop_quit"))]
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
