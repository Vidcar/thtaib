"""Model configurations reuse profiles; deployments remain loaded snapshots."""
from __future__ import annotations

from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import RunProfile, SettingsBags
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.inference.store import RecordStore


def requested_identity(bags: SettingsBags) -> tuple[dict, dict, dict]:
    startup = resolve_bags(startup=bags.startup.requested).startup.applied
    if bags.startup.requested.get("port") is None:
        startup.pop("port", None)
    response = {key: value for key, value in bags.per_request.requested.items() if value is not None
        and not (key == "reasoning_effort" and value == "default") and not (key == "reasoning" and value == "auto")}
    return (startup, response, bags.agent.requested)


def ensure_model_configurations(store: RecordStore) -> None:
    """Idempotent in-place migration, preserving every deployment and old ID.

    Deterministic recovered IDs make a crash between JSON writes safe to retry.
    No process, chat, model file, or historical snapshot is changed.
    """
    with store.configuration_lock():
        for bundle in store.list_bundles():
            if bundle.default_configuration_id and store.get_profile(bundle.default_configuration_id):
                continue
            profiles = [p for p in store.list_profiles() if p.bundle_id == bundle.id]
            deployments = sorted(
                [d for d in store.list_deployments() if d.bundle_id == bundle.id and d.scope.value == "managed"],
                key=lambda d: (bool(d.status.value == "running" and d.process_identity and d.health and d.health.healthy), d.updated_at),
                reverse=True,
            )
            default = None
            for index, deployment in enumerate(deployments):
                bags = resolve_bags(startup=deployment.requested_startup,
                    per_request=deployment.settings.per_request.requested,
                    agent=deployment.settings.agent.requested)
                profile = next((p for p in profiles if requested_identity(p.bags) == requested_identity(bags)), None)
                if profile is None:
                    profile = RunProfile(id=f"config_{deployment.id}", bundle_id=bundle.id,
                        display_name="Default" if index == 0 else f"Saved variant {index + 1}",
                        bags=bags, created_at=utc_now(), updated_at=utc_now())
                    profile = store.put_profile(profile)
                    profiles.append(profile)
                if default is None:
                    default = profile
            if default is None:
                default = max(profiles, key=lambda p: p.updated_at) if profiles else store.put_profile(
                    RunProfile(id=f"config_{bundle.id}", display_name="Default", bundle_id=bundle.id,
                        bags=resolve_bags(), created_at=utc_now(), updated_at=utc_now()))
            store.put_bundle(bundle.model_copy(update={"default_configuration_id": default.id}))
