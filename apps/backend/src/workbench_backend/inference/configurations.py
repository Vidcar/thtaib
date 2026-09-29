"""Model configuration identity and default creation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from workbench_backend.errors import ManagerError
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.schemas import (
    Deployment, DeploymentStatus, DuplicateProfileRequest, GgufRuntimeMetadata, ManagementScope,
    ModelBundle, RenameProfileRequest, RunProfile, RuntimeManifest, SettingsBags,
)
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
        startup["kv_unified"] = True
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


def loaded_model_identity(runtime: RuntimeManifest | None, bundle: ModelBundle, bags: SettingsBags,
                          *, hash_external: bool = True) -> str | None:
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
                if not hash_external:
                    return None
                recorded[str(path)] = cached_sha256_file(path) if path.is_file() else "missing"
    payload = {
        "version": 1,
        "runtime": runtime.model_dump(include={"platform", "flavor", "release_tag", "executable", "sha256", "companion_sha256"}) if runtime else None,
        "primary_path": str(Path(bundle.primary_path).resolve()) if bundle.primary_path else None,
        "artifacts": sorted(recorded.items()),
        "startup": startup,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def model_default_values(store: RecordStore, bundle: ModelBundle, *, startup: dict[str, Any] | None = None
                         ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the shared native/template/card baseline without creating overrides."""
    from workbench_backend.inference.configuration_options import (
        bundle_configuration_options, response_default_values,
    )
    from workbench_backend.inference.inspect import read_gguf_runtime_metadata
    from workbench_backend.inference.inspection_cache import cached_inspection

    try:
        metadata, _, _ = cached_inspection(store, bundle, "runtime", GgufRuntimeMetadata,
            lambda: read_gguf_runtime_metadata(Path(bundle.primary_path or "")))
    except (OSError, ValueError, KeyError, TypeError, ManagerError):
        metadata = GgufRuntimeMetadata()
    config = bundle.huggingface_configuration
    startup = startup or {}
    selected_file = startup.get("chat_template_file") or (
        config.template_file if config and not startup.get("chat_template") else None)
    selected_source = "configuration_template" if startup.get("chat_template_file") or startup.get("chat_template") else (
        f"{config.template_origin}_template" if config and config.template_file else None)
    if selected_file:
        path = Path(str(selected_file))
        record = next((item for item in bundle.files if Path(item.path) == path), None)
        try:
            with path.open("rb") as template_stream:
                payload = template_stream.read(2 * 1024 * 1024 + 1)
            if (len(payload) > 2 * 1024 * 1024
                or record is not None and hashlib.sha256(payload).hexdigest() != record.sha256
                or record is None and selected_source != "configuration_template"):
                raise ValueError("selected template differs from the bundle record")
            metadata = metadata.model_copy(update={"chat_template": payload.decode("utf-8")})
        except (OSError, UnicodeError, ValueError):
            metadata = metadata.model_copy(update={"chat_template": None})
    elif startup.get("chat_template"):
        inline = str(startup["chat_template"])
        metadata = metadata.model_copy(update={"chat_template": inline if "{{" in inline or "{%" in inline else None})
    options = bundle_configuration_options(bundle.id, metadata, huggingface_configuration=config,
        selected_template_source=selected_source)
    return {}, response_default_values(options)


def ensure_model_configurations(store: RecordStore) -> None:
    """Create one fresh default for a bundle that has no valid default.

    Existing configurations and accepted deployment snapshots keep their
    identity. Reading a model never rewrites requested settings.
    """
    with store.configuration_lock():
        for bundle in store.list_bundles():
            current = store.get_profile(bundle.default_configuration_id) if bundle.default_configuration_id else None
            if current is not None and current.bundle_id == bundle.id:
                continue
            now = utc_now()
            startup_defaults, response_defaults = model_default_values(store, bundle)
            default_id = f"config_{bundle.id}"
            default = store.get_profile(default_id)
            if default is None:
                default = store.put_profile(RunProfile(
                    id=default_id, bundle_id=bundle.id, display_name="Default",
                    bags=resolve_bags(startup_defaults=startup_defaults, per_request_defaults=response_defaults),
                    settings_schema_version=2,
                    created_at=now, updated_at=now,
                ))
            elif default.bundle_id != bundle.id:
                raise ManagerError("Model configuration ID belongs to another bundle.",
                                   code="configuration_identity_conflict", status_code=409)
            store.put_bundle(bundle.model_copy(update={"default_configuration_id": default.id}))


def require_profile_bundle(store: RecordStore, bundle_id: str | None) -> None:
    if bundle_id is not None and store.get_bundle(bundle_id) is None:
        raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)


def validate_profile_bundle(profile: RunProfile, bundle_id: str) -> None:
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


def resolved_profile(store: RecordStore, profile: RunProfile) -> RunProfile:
    """Resolve the shared current baseline without rewriting saved overrides."""
    bundle = store.get_bundle(profile.bundle_id) if profile.bundle_id else None
    initial_startup, response_defaults = model_default_values(store, bundle,
        startup=profile.bags.startup.requested) if bundle else ({}, None)
    return profile.model_copy(
        update={
            "bundle_name": bundle.display_name if bundle else None,
            "bags": resolve_bags(
                startup=profile.bags.startup.requested,
                startup_defaults=initial_startup,
                per_request=profile.bags.per_request.requested,
                agent=profile.bags.agent.requested,
                per_request_defaults=response_defaults,
            )
        }
    )


def saved_profile(store: RecordStore, profile_id: str) -> RunProfile:
    profile = store.get_profile(profile_id)
    if profile is None:
        raise ManagerError("Unknown profile", code="profile_missing", status_code=404)
    return resolved_profile(store, profile)


def list_saved_profiles(store: RecordStore) -> list[RunProfile]:
    ensure_model_configurations(store)
    defaults = {bundle.default_configuration_id for bundle in store.list_bundles()}
    profiles = [resolved_profile(store, profile) for profile in store.list_profiles()]
    profiles.sort(key=lambda profile: (profile.id in defaults, profile.updated_at, profile.id), reverse=True)
    return profiles


def list_saved_configurations(store: RecordStore, bundle_id: str) -> list[RunProfile]:
    require_profile_bundle(store, bundle_id)
    return [profile for profile in list_saved_profiles(store) if profile.bundle_id == bundle_id]


def set_bundle_default_configuration(store: RecordStore, bundle_id: str, configuration_id: str) -> ModelBundle:
    with store.configuration_lock():
        bundle = store.get_bundle(bundle_id)
        if bundle is None:
            raise ManagerError("Unknown model", code="bundle_missing", status_code=404)
        profile = saved_profile(store, configuration_id)
        if profile.bundle_id != bundle_id:
            raise ManagerError("Configuration belongs to another model.", code="profile_bundle_mismatch", status_code=400)
        return store.put_bundle(bundle.model_copy(update={"default_configuration_id": profile.id}))


def rename_saved_profile(store: RecordStore, profile_id: str, request: RenameProfileRequest | str) -> RunProfile:
    display_name = request if isinstance(request, str) else request.display_name
    existing = saved_profile(store, profile_id)
    return store.put_profile(
        existing.model_copy(update={"display_name": display_name, "updated_at": utc_now(), "revision": existing.revision + 1})
    )


def duplicate_saved_profile(
    store: RecordStore,
    profile_id: str,
    request: DuplicateProfileRequest | None = None,
) -> RunProfile:
    existing = saved_profile(store, profile_id)
    now = utc_now()
    display_name = request.display_name if request and request.display_name else f"{existing.display_name} copy"
    duplicate = existing.model_copy(
        update={
            "id": new_id("profile"),
            "display_name": display_name,
            "created_at": now,
            "updated_at": now,
            "revision": 1,
            "recipe_origin": None,
        },
        deep=True,
    )
    return store.put_profile(duplicate)


def find_compatible_deployment(
    store: RecordStore,
    runtime: RuntimeManifest | None,
    bundle_id: str,
    bags: SettingsBags,
) -> Deployment | None:
    """Find an exact native plan without using setup or response identity."""
    bundle = store.get_bundle(bundle_id)
    if bundle is None:
        return None
    selected_identity = loaded_model_identity(runtime, bundle, bags)
    matches = []
    for deployment in store.list_deployments():
        if deployment.scope != ManagementScope.managed or deployment.bundle_id != bundle_id or has_response_startup_defaults(deployment.settings):
            continue
        if deployment.loaded_model_identity is not None:
            compatible = deployment.loaded_model_identity == selected_identity
        else:
            # Only cold historical records may be bound to the current
            # runtime. A live old record has no proven runtime identity.
            compatible = deployment.status == DeploymentStatus.stopped and loaded_model_identity(runtime, bundle, deployment.settings) == selected_identity
        if compatible:
            matches.append(deployment)
    return max(matches, key=lambda d: (d.status == DeploymentStatus.running and bool(d.health and d.health.healthy and d.process_identity),
        d.status != DeploymentStatus.failed, d.updated_at), default=None)


def deployment_for_configuration(
    store: RecordStore,
    runtime: RuntimeManifest | None,
    configuration_id: str,
) -> Deployment | None:
    profile = saved_profile(store, configuration_id)
    return find_compatible_deployment(store, runtime, profile.bundle_id or "", profile.bags)
