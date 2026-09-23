"""Freeze selected named agents without recursively resolving a helper catalogue."""
from __future__ import annotations

from workbench_backend.agents.setup_schemas import FrozenHelperSelection, SetupConfiguration
from workbench_backend.errors import HarnessError
from workbench_backend.inference.schemas import SettingsBags
from workbench_backend.inference.settings import resolve_bags


def freeze_settings(manager, configuration):
    profile = manager.get_profile(configuration.profile_id) if configuration.profile_id else None
    deployment = manager.get_deployment(configuration.deployment_id) if configuration.deployment_id else None
    bags = profile.bags if profile else deployment.settings if deployment and configuration.inherit_deployment_settings is not False else SettingsBags()
    # Saved model settings can change while work is queued. Capture the inputs,
    # then compare this selected startup with the actual loaded runtime at dispatch.
    frozen = bags.model_copy(deep=True)
    if configuration.startup_overrides:
        selected = {**bags.startup.requested, **configuration.startup_overrides}
        frozen.startup = resolve_bags(startup={key: value for key, value in selected.items() if value is not None}).startup
    return frozen.model_dump(mode="json")


def freeze_helpers(service, agent_ids, *, project_id=None, parent_configuration=None):
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
            overrides=SetupConfiguration.model_validate(inherited))
        snapshots.append(FrozenHelperSelection(agent_id=ident, version_id=version.id, name=version.name,
            role=version.role, configuration=selected.configuration, instruction_layers=selected.instruction_layers,
            settings_snapshot=freeze_settings(service.manager, selected.configuration)))
    return snapshots
