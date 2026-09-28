"""Model configuration identity and default creation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from workbench_backend.errors import ManagerError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import ModelBundle, RunProfile, RuntimeManifest, SettingsBags
from workbench_backend.inference.settings import (
    REQUEST_STARTUP_ALIASES, REQUEST_TEMPLATE_ALIASES, normalize_startup_requested,
    resolve_bags, split_response_startup,
)
from workbench_backend.inference.store import RecordStore


def requested_identity(bags: SettingsBags) -> tuple[dict, dict]:
    """The model owns loading and response settings, never agent instructions."""
    startup = loading_startup_settings(bags)
    response = {key: value for key, value in bags.per_request.requested.items()
                if value is not None and not (key == "reasoning_effort" and value == "default")
                and not (key == "reasoning" and value == "auto")}
    return startup, response


def loading_startup_settings(bags: SettingsBags) -> dict:
    """Canonical loading plan, independent of saved/request response identity.

    Applied settings preserve historical implicit defaults. Request aliases are
    removed only from known native response keys; unrelated template kwargs are
    loading settings and remain part of the identity.
    """
    raw = bags.startup.applied or resolve_bags(startup=bags.startup.requested).startup.applied
    loading, _ = split_response_startup(raw, {})
    startup, _ = normalize_startup_requested(loading)
    if bags.startup.requested.get("port") is None:
        startup.pop("port", None)
    if startup.get("n_gpu_layers") == -1:
        startup["n_gpu_layers"] = "auto"
    # Native server Auto uses four slots and unified KV. Make semantically
    # equivalent historical omitted values compare with fresh explicit plans.
    original_parallel = startup.get("parallel")
    if original_parallel in {None, -1}:
        startup["parallel"] = 4
        startup.setdefault("kv_unified", True)
    else:
        startup.setdefault("kv_unified", False)
    startup.setdefault("fit", "on")
    startup.setdefault("flash_attn", "auto")
    startup.setdefault("cache_type_k", "f16")
    startup.setdefault("cache_type_v", "f16")
    startup.setdefault("kv_offload", True)
    return startup


def has_response_startup_defaults(bags: SettingsBags) -> bool:
    """Old non-neutral children cannot supply another setup's defaults."""
    raw = bags.startup.applied
    if any(key in raw for key in REQUEST_STARTUP_ALIASES):
        return True
    kwargs = raw.get("chat_template_kwargs")
    if isinstance(kwargs, str):
        try:
            kwargs = json.loads(kwargs)
        except ValueError:
            return True
    return isinstance(kwargs, dict) and any(key in kwargs for key in REQUEST_TEMPLATE_ALIASES)


def loaded_model_identity(runtime: RuntimeManifest | None, bundle: ModelBundle, bags: SettingsBags) -> str:
    """Hash exact inference runtime/artifacts and the normalized loading plan."""
    from workbench_backend.inference.bundles import mmproj_companion
    from workbench_backend.inference.hashes import cached_sha256_file

    startup = loading_startup_settings(bags)
    artifacts = [item for item in bundle.files if item.role.value in {"primary_weights", "shard"}]
    projector = mmproj_companion(bundle)
    if projector is not None:
        artifacts.append(projector)
    config = bundle.huggingface_configuration
    if config and config.template_file and not any(startup.get(key) for key in ("chat_template", "chat_template_file")):
        selected = next((item for item in bundle.files if item.path == config.template_file), None)
        if selected is not None:
            artifacts.append(selected)
    recorded = {str(Path(item.path).resolve()): item.sha256 for item in artifacts}
    for key in ("chat_template_file", "spec_draft_model"):
        if startup.get(key):
            path = Path(str(startup[key])).resolve()
            if str(path) not in recorded:
                recorded[str(path)] = cached_sha256_file(path) if path.is_file() else "missing"
    payload = {
        "version": 1,
        "runtime": runtime.model_dump(include={"platform", "flavor", "release_tag", "executable", "sha256", "companion_sha256"}) if runtime else None,
        "primary_path": str(Path(bundle.primary_path).resolve()) if bundle.primary_path else None,
        "artifacts": sorted(recorded.items()),
        "startup": startup,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def upgrade_configuration(profile: RunProfile) -> RunProfile:
    """Preserve effective old saved defaults once without rewriting history."""
    if profile.settings_schema_version >= 2:
        return profile
    requested = dict(profile.bags.startup.requested)
    applied = profile.bags.startup.applied
    for key, legacy in (("n_gpu_layers", -1), ("flash_attn", "on"), ("fit", "on")):
        requested.setdefault(key, applied.get(key, legacy))
    old_parallel = applied.get("parallel", requested.get("parallel"))
    requested.setdefault("parallel", 4 if old_parallel in {None, -1} else old_parallel)
    requested.setdefault("kv_unified", applied.get("kv_unified", old_parallel in {None, -1}))
    if applied.get("n_gpu_layers", requested.get("n_gpu_layers")) == 0:
        # A historical zero-layer setup was weight-only CPU placement. Retain
        # its effective companion/operation defaults during this semantic cutover.
        for key, legacy in (("kv_offload", True), ("op_offload", True), ("mmproj_use_gpu", True), ("spec_draft_ngl", "auto")):
            requested.setdefault(key, applied.get(key, legacy))
    loading, response = split_response_startup(requested, profile.bags.per_request.requested)
    return profile.model_copy(update={
        "bags": resolve_bags(startup=loading, per_request=response, agent=profile.bags.agent.requested,
                             per_request_defaults=profile.bags.per_request.applied),
        "settings_schema_version": 2,
    })


def ensure_model_configurations(store: RecordStore) -> None:
    """Create one fresh default for a bundle that has no valid default.

    Existing saved configurations retain their effective defaults at the
    settings cutover. Historical deployment snapshots and merged profile
    aliases remain separate from this saved configuration authority.
    """
    with store.configuration_lock():
        for profile in store.list_profiles():
            migrated = upgrade_configuration(profile)
            if migrated != profile:
                store.put_profile(migrated)
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
                    settings_schema_version=2,
                    created_at=now, updated_at=now,
                ))
            elif default.bundle_id != bundle.id:
                raise ManagerError("Model configuration ID belongs to another bundle.",
                                   code="configuration_identity_conflict", status_code=409)
            store.put_bundle(bundle.model_copy(update={"default_configuration_id": default.id}))
