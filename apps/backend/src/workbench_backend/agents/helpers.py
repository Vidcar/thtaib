"""Freeze selected named agents without recursively resolving a helper catalogue."""
from __future__ import annotations

from workbench_backend.agents.setup_schemas import FrozenHelperSelection, SetupConfiguration
from workbench_backend.errors import HarnessError
from workbench_backend.inference.schemas import Deployment, ManagedDeploymentRequest, SettingsBags
from workbench_backend.inference.settings import PER_REQUEST_KEYS, resolve_bag, resolve_bags, split_response_startup
from workbench_backend.inference.response_budget import freeze_output_policy


def freeze_settings(manager, configuration):
    profile = manager.get_profile(configuration.profile_id) if configuration.profile_id else None
    deployment = manager.get_deployment(configuration.deployment_id) if configuration.deployment_id else None
    bags = profile.bags if profile else deployment.settings if deployment and configuration.inherit_deployment_settings is not False else SettingsBags()
    # Saved model settings can change while work is queued. Capture the inputs,
    # then compare this selected startup with the actual loaded runtime at dispatch.
    frozen = bags.model_copy(deep=True)
    if deployment is not None and configuration.inherit_deployment_settings is False:
        # Opting out of response/agent defaults does not reset the actual launch.
        frozen.startup = deployment.settings.startup.model_copy(deep=True)
    response_overrides = dict(configuration.per_request_overrides or {})
    if configuration.startup_overrides:
        selected = {**frozen.startup.requested, **configuration.startup_overrides}
        loading, response_overrides = split_response_startup(selected, response_overrides)
        frozen.startup = resolve_bags(startup={key: value for key, value in loading.items() if value is not None}).startup
    if response_overrides:
        requested = {**frozen.per_request.requested, **response_overrides}
        defaults = {key: value for key, value in frozen.per_request.applied.items()
            if key not in frozen.per_request.requested}
        frozen.per_request = resolve_bag({key: value for key, value in requested.items() if value is not None},
            PER_REQUEST_KEYS, defaults=defaults)
    bundle_id = configuration.bundle_id or (profile.bundle_id if profile else deployment.bundle_id if deployment else None)
    default_thinking = None
    if bundle_id and hasattr(manager, "get_bundle_configuration_options"):
        compatible = getattr(manager, "compatible_deployment", None)
        exact = compatible(bundle_id, frozen) if callable(compatible) else None
        options = manager.get_bundle_configuration_options(bundle_id, deployment_id=exact.id if exact else None,
            startup=frozen.startup.requested)
        thinking = options.per_request_defaults.get("reasoning")
        if thinking is not None and thinking.default_value in ("on", "off"):
            default_thinking = thinking.default_value == "on"
    elif deployment is not None and deployment.scope.value == "connected":
        from workbench_backend.inference.configuration_options import bundle_configuration_options
        from workbench_backend.inference.schemas import GgufRuntimeMetadata
        thinking = bundle_configuration_options(None, GgufRuntimeMetadata(), deployment=deployment).per_request_defaults["reasoning"]
        if thinking.default_source == "server_properties" and thinking.default_value in ("on", "off"):
            default_thinking = thinking.default_value == "on"
    frozen.per_request = freeze_output_policy(frozen.per_request, default_thinking=default_thinking)
    frozen.per_request.recipe_origin = profile.recipe_origin.model_copy(deep=True) if profile and profile.recipe_origin else None
    model_store = getattr(manager, "store", None)
    runtime = getattr(manager, "runtime", None)
    bundle = model_store.get_bundle(bundle_id) if model_store is not None and bundle_id else None
    manifest = runtime.current() if runtime is not None else None
    if bundle is not None and manifest is not None:
        from workbench_backend.inference.configurations import loaded_model_identity
        frozen.accepted_loading_identity = loaded_model_identity(manifest, bundle, frozen)
    return frozen.model_dump(mode="json")


def require_accepted_model_identity(deployment: Deployment, settings: SettingsBags | None) -> None:
    """A resumed role retains the exact model plan accepted for that role."""
    if (settings is not None and settings.accepted_loading_identity and deployment.loaded_model_identity
            and settings.accepted_loading_identity != deployment.loaded_model_identity):
        raise HarnessError("The loaded model differs from this accepted task's exact model plan. Restore that plan or deliberately retry with new choices.",
            code="accepted_model_identity_changed", status_code=409)


def prepare_frozen_model(manager, configuration, settings, *, error_type=HarnessError):
    """Prepare one frozen loading plan without loading or editing its setup.

    Chat, direct runs and helpers use the same record selection. Response values
    remain in the acceptance snapshot; a reused child's setup never supplies them.
    """
    from workbench_backend.inference.configurations import loaded_model_identity, requested_identity

    bags = SettingsBags.model_validate(settings)
    selected = manager.store.get_deployment(configuration.deployment_id or "")
    if selected is not None and configuration.bundle_id is None and selected.bundle_id:
        configuration = configuration.model_copy(update={"bundle_id": selected.bundle_id})
    if selected is not None and selected.scope.value == "connected":
        return configuration
    if bags.accepted_loading_identity and configuration.bundle_id:
        bundle = manager.store.get_bundle(configuration.bundle_id)
        current_identity = loaded_model_identity(manager.runtime.current(), bundle, bags) if bundle else None
        if current_identity != bags.accepted_loading_identity:
            raise error_type("The model files or engine changed after this task was accepted. Deliberately update its model choices before retrying.",
                code="accepted_model_identity_changed", status_code=409)
    wanted = requested_identity(bags)[0]
    compatible = getattr(manager, "compatible_deployment", None)
    if callable(compatible) and configuration.bundle_id:
        selected = compatible(configuration.bundle_id, bags)
    elif selected is None or requested_identity(selected.settings)[0] != wanted:
        candidates = [item for item in manager.store.list_deployments()
            if item.scope.value == "managed" and item.bundle_id == configuration.bundle_id
            and requested_identity(item.settings)[0] == wanted]
        selected = next((item for item in candidates if item.status.value == "running" and item.health and item.health.healthy),
            candidates[0] if candidates else None)
    if selected is None:
        if configuration.bundle_id is None:
            raise error_type("The saved model is unavailable. Choose another model.", code="deploy_missing", status_code=409)
        profile = manager.get_profile(configuration.profile_id) if configuration.profile_id else None
        startup = {key: None for key in profile.bags.startup.requested} if profile else {}
        startup.update(bags.startup.requested)
        selected = manager.create_managed(ManagedDeploymentRequest(bundle_id=configuration.bundle_id,
            profile_id=configuration.profile_id, startup=startup, auto_start=False))
    return configuration.model_copy(update={"deployment_id": selected.id})


def freeze_helpers(service, agent_ids, *, project_id=None, parent_configuration=None, latest_knowledge=False,
        connection_snapshot=None):
    snapshots = []
    for ident in dict.fromkeys(agent_ids or []):
        view = service.get_setup(ident)
        if not view.active:
            raise HarnessError(f"Helper {view.name} was removed. Choose another helper.", code="helper_unavailable", status_code=409)
        version = service.get_version(view.current_version_id, require_active=True)
        inherited = {}
        # An agent without its own model uses the model already selected for this chat.
        if parent_configuration is not None and not any(getattr(version.configuration, key) for key in ("deployment_id", "bundle_id", "model_configuration_id")):
            for key in ("deployment_id", "bundle_id", "model_configuration_id", "profile_id", "inherit_deployment_settings", "startup_overrides"):
                value = getattr(parent_configuration, key, None)
                if value is not None:
                    inherited[key] = value
        inherited.update(helper_agent_ids=[], review={"enabled": False})
        selected = service.resolve(project_id=project_id, agent_setup_version_id=version.id,
            overrides=SetupConfiguration.model_validate(inherited), helper_role=True,
            prepare_model=False, read_only=True, latest_knowledge=latest_knowledge)
        connections = None
        if connection_snapshot is not None:
            config = selected.configuration
            inherited_ids = (parent_configuration.connection_ids or []) if parent_configuration is not None else []
            ids = config.connection_ids if config.connection_ids is not None else inherited_ids
            if parent_configuration is not None:
                ids = [ident for ident in ids if ident in inherited_ids]
            tools_enabled = config.presented_tools != [] and (
                parent_configuration is None or parent_configuration.presented_tools != [])
            connections = connection_snapshot(ids, tools_enabled=tools_enabled,
                allow_unready=bool(config.input_policy and config.input_policy.tool_loading == "when_needed"))
            selected = selected.model_copy(update={"configuration": config.model_copy(
                update={"connection_ids": list(ids) if tools_enabled else []})})
        snapshots.append(FrozenHelperSelection(agent_id=ident, version_id=version.id, name=version.name,
            role=version.role, configuration=selected.configuration, instruction_layers=selected.instruction_layers,
            settings_snapshot=freeze_settings(service.manager, selected.configuration), connection_snapshots=connections))
    return snapshots
