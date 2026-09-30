"""Resolve a saved setup once before checking or presenting capability proof."""

from __future__ import annotations

from typing import Any
from pathlib import Path

from workbench_backend.errors import ManagerError
from workbench_backend.inference.capabilities import CapabilityProbeRequest, proof_scope, setup_identity
from workbench_backend.inference.configurations import loading_startup_settings
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import Deployment, DeploymentStatus, ManagementScope, ServerProperties, SettingsBag
from workbench_backend.inference.settings import PER_REQUEST_KEYS, resolve_bag


def selected_configuration(manager: Any, configuration_id: str, expected_revision: int | None = None):
    profile = manager.get_profile(configuration_id)
    if expected_revision is not None and profile.revision != expected_revision:
        raise ManagerError("This setup changed elsewhere. Refresh before checking it.",
                           code="configuration_revision_conflict", status_code=409)
    if not profile.bundle_id:
        raise ManagerError("Capability checks require an installed model setup.",
                           code="configuration_bundle_required", status_code=422)
    return profile


def resolve_probe_bag(manager: Any, deployment: Deployment, request: CapabilityProbeRequest) -> SettingsBag:
    if request.configuration_id:
        if request.per_request is not None:
            raise ManagerError("Check the saved setup or response overrides, not both together.",
                               code="probe_settings_ambiguous", status_code=422)
        profile = selected_configuration(manager, request.configuration_id, request.expected_configuration_revision)
        if profile.bundle_id != deployment.bundle_id:
            raise ManagerError("This setup belongs to another model.", code="profile_bundle_mismatch", status_code=409)
        if loading_startup_settings(profile.bags) != loading_startup_settings(deployment.settings):
            raise ManagerError("Load this saved setup before checking it.", code="probe_loading_mismatch", status_code=409)
        return profile.bags.per_request
    if request.expected_configuration_revision is not None:
        raise ManagerError("Select the saved setup whose revision is being checked.",
                           code="probe_configuration_required", status_code=422)
    return deployment.settings.per_request if request.per_request is None else resolve_bag(request.per_request, PER_REQUEST_KEYS)


def require_current_probe_template(deployment: Deployment) -> None:
    """Do not attach current disk bytes to a process using an earlier template."""
    path = deployment.applied_startup.get("chat_template_file") or (
        deployment.inference_identity.get("selected_template_file")
        if not deployment.applied_startup.get("chat_template") else None)
    if not path:
        return
    try:
        with Path(str(path)).open("rb") as stream:
            data = stream.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("template too large")
        template = data.decode("utf-8").rstrip("\r\n")
    except (OSError, UnicodeError, ValueError) as exc:
        raise ManagerError("This setup's template is missing or changed. Load the saved setup again before checking it.",
                           code="probe_template_changed", status_code=409) from exc
    props = deployment.server_props
    if props is None or props.chat_template is None or props.chat_template.rstrip("\r\n") != template:
        raise ManagerError("This process uses an earlier template. Load the saved setup again before checking it.",
                           code="probe_template_changed", status_code=409)


def configuration_probe_context(manager: Any, configuration_id: str, expected_revision: int | None = None) -> Deployment:
    """Present stored proof while unloaded; this read never launches a model."""
    profile = selected_configuration(manager, configuration_id, expected_revision)
    bundle = manager.store.get_bundle(profile.bundle_id)
    if bundle is None:
        raise ManagerError("This setup's installed model is missing.", code="bundle_missing", status_code=404)
    selected = profile.bags.startup.applied

    def behaviour_startup(startup: dict) -> dict:
        return proof_scope({"probe_version": 3, "startup": startup}).get("startup", {})

    candidates = [item for item in manager.store.list_deployments()
                  if item.bundle_id == bundle.id and item.server_props is not None
                  and behaviour_startup(item.applied_startup) == behaviour_startup(selected)]
    candidate = max(candidates, key=lambda item: item.updated_at, default=None)
    now = utc_now()
    deployment = candidate.model_copy(deep=True) if candidate else Deployment(
        id=f"saved:{configuration_id}", display_name=profile.display_name,
        scope=ManagementScope.managed, status=DeploymentStatus.stopped,
        bundle_id=bundle.id, created_at=now, updated_at=now,
    )
    deployment.settings = profile.bags
    deployment.applied_startup = dict(selected)
    deployment.profile_id = profile.id
    runtime = manager.store.read_runtime_manifest()
    deployment.inference_identity = {
        "runtime": ({"release": runtime.release_tag, "sha256": runtime.sha256,
                     "companion_sha256": runtime.companion_sha256} if runtime else None),
        "bundle_files": [{"path": item.path, "sha256": item.sha256, "role": item.role.value}
                         for item in [*bundle.files, *bundle.shards, *bundle.companions]],
    }
    if (bundle.huggingface_configuration and bundle.huggingface_configuration.template_file
            and not any(selected.get(key) for key in ("chat_template", "chat_template_file"))):
        deployment.inference_identity["selected_template_file"] = bundle.huggingface_configuration.template_file
    if selected.get("spec_draft_model"):
        from workbench_backend.inference.hashes import observed_file_identity
        path = Path(str(selected["spec_draft_model"]))
        draft = observed_file_identity(path)
        if not draft.get("sha256"):
            for item in reversed(manager.store.list_capability_evidence()):
                setup = item.get("setup")
                recorded = setup.get("external_draft_model") if isinstance(setup, dict) else None
                if isinstance(recorded, dict) and recorded.get("signature") == draft.get("signature"):
                    draft = observed_file_identity(path, recorded)
                    break
        deployment.inference_identity["external_draft_model"] = draft
    if deployment.server_props is None:
        # A deployment record is disposable; the persisted observation still
        # describes the exact native template that was checked. Reconstruct only
        # a candidate, then require its complete scope to match current inputs.
        for item in reversed(manager.store.list_capability_evidence()):
            recorded = item.get("setup")
            if not isinstance(recorded, dict) or recorded.get("probe_version") != 3:
                continue
            proposed = deployment.model_copy(deep=True)
            proposed.server_props = ServerProperties(
                fetched=item["tested_at"], source_url="stored-capability-proof",
                build_info=recorded.get("runtime_build"), chat_template=recorded.get("template"),
                chat_template_caps=recorded.get("template_caps", {}), modalities=recorded.get("modalities", {}),
                default_generation_settings=recorded.get("generation_defaults", {}),
            )
            if proof_scope(setup_identity(proposed, profile.bags.per_request)) == proof_scope(recorded):
                deployment = proposed
                break
    scope = proof_scope(setup_identity(deployment, profile.bags.per_request))
    deployment.capability_evidence = [item for item in manager.store.list_capability_evidence()
        if isinstance(item.get("setup"), dict) and proof_scope(item["setup"]) == scope]
    return deployment
