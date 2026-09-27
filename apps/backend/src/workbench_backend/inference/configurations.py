"""Model configuration identity and default creation."""

from __future__ import annotations

from workbench_backend.errors import ManagerError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import RunProfile, SettingsBags
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.inference.store import RecordStore


def requested_identity(bags: SettingsBags) -> tuple[dict, dict]:
    """The model owns loading and response settings, never agent instructions."""
    startup = resolve_bags(startup=bags.startup.requested).startup.applied
    if bags.startup.requested.get("port") is None:
        startup.pop("port", None)
    response = {key: value for key, value in bags.per_request.requested.items()
                if value is not None and not (key == "reasoning_effort" and value == "default")
                and not (key == "reasoning" and value == "auto")}
    return startup, response


def ensure_model_configurations(store: RecordStore) -> None:
    """Create one fresh default for a bundle that has no valid default.

    Historical deployment snapshots and merged profile aliases are not model
    configuration sources. Disposable old data is reset at development cutover
    rather than migrated here.
    """
    with store.configuration_lock():
        for bundle in store.list_bundles():
            current = store.get_profile(bundle.default_configuration_id) if bundle.default_configuration_id else None
            if current is not None and current.bundle_id == bundle.id:
                continue
            now = utc_now()
            publisher_defaults = (bundle.huggingface_configuration.generation_defaults
                                  if bundle.huggingface_configuration else None)
            default_id = f"config_{bundle.id}"
            default = store.get_profile(default_id)
            if default is None:
                default = store.put_profile(RunProfile(
                    id=default_id, bundle_id=bundle.id, display_name="Default",
                    bags=resolve_bags(per_request_defaults=publisher_defaults),
                    created_at=now, updated_at=now,
                ))
            elif default.bundle_id != bundle.id:
                raise ManagerError("Model configuration ID belongs to another bundle.",
                                   code="configuration_identity_conflict", status_code=409)
            store.put_bundle(bundle.model_copy(update={"default_configuration_id": default.id}))
