"""Setup-specific probe identity, independent of publisher claims and opt-outs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from workbench_backend.inference.schemas import Deployment, SettingsBag

Capability = Literal["text_stream", "tools", "structured_native", "structured_tools", "structured_with_tools", "structured_tools_with_tools", "reasoning", "reasoning_replay", "image", "tool_image"]
ProbeStatus = Literal["passed", "failed", "untested", "inconclusive"]
CAPABILITIES: tuple[Capability, ...] = ("text_stream", "tools", "structured_native", "structured_tools", "structured_with_tools", "structured_tools_with_tools", "reasoning", "reasoning_replay", "image", "tool_image")


class CapabilityProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability: Capability
    per_request: dict[str, Any] | None = None
    configuration_id: str | None = None
    expected_configuration_revision: int | None = Field(default=None, ge=1)


class CapabilityEvidence(BaseModel):
    schema_version: Literal[1] = 1
    id: str
    deployment_id: str
    capability: Capability
    status: ProbeStatus
    fingerprint: str
    setup: dict[str, Any]
    tested_at: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    observations: dict[str, Any] = Field(default_factory=dict)
    note: str = "Evidence applies only to this setup and probe; schema validity is not factual correctness."


class ImageProbeSetup(BaseModel):
    selected_projector: str | None = None
    projector_present: bool | None = None
    runtime_support: bool | None = None


class CapabilityProbeReport(BaseModel):
    current_fingerprint: str
    current_support: dict[Capability, ProbeStatus]
    evidence: list[CapabilityEvidence]
    image_setup: ImageProbeSetup
    applicable_capabilities: list[Capability] = Field(default_factory=list)
    automatic_running: bool = False
    running_capability: Capability | None = None


def setup_identity(deployment: Deployment, per_request: SettingsBag | dict | None = None) -> dict[str, Any]:
    props = deployment.server_props
    settings = deployment.settings.per_request.applied if per_request is None else per_request.applied if isinstance(per_request, SettingsBag) else per_request
    settings = {"max_tokens": -1, **settings}
    return {
        "probe_version": 3,
        "deployment_id": deployment.id,
        "bundle_id": deployment.bundle_id,
        "artifacts": deployment.inference_identity,
        "endpoint": deployment.endpoint,
        "startup": deployment.applied_startup,
        "request": settings,
        "runtime_build": props.build_info if props else None,
        "model": props.model_alias if props else None,
        "model_path": props.model_path if props else None,
        "template": props.chat_template if props else None,
        "template_caps": props.chat_template_caps if props else {},
        "modalities": props.modalities if props else {},
        "context": props.n_ctx if props else None,
        "generation_defaults": props.default_generation_settings if props else {},
        "external_template": _external_template_identity({"chat_template_file":
            deployment.applied_startup.get("chat_template_file") or (
                deployment.inference_identity.get("selected_template_file")
                if not deployment.applied_startup.get("chat_template") else None)}),
        "external_draft_model": _external_draft_identity(deployment),
    }


def _identity_fingerprint(identity: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def setup_fingerprint(deployment: Deployment, per_request: SettingsBag | dict | None = None) -> str:
    return _identity_fingerprint(setup_identity(deployment, per_request))


# Context, cache, placement and MTP change memory, not the checked behaviour.
_PROOF_IGNORED_STARTUP = frozenset({
    "ctx_size", "cache_type_k", "cache_type_v", "kv_offload", "n_gpu_layers",
    "flash_attn", "fit", "parallel", "kv_unified",
    "host", "port", "alias", "threads", "threads_batch", "batch_size", "ubatch_size",
    "op_offload", "mmproj_use_gpu", "load_mode",
})
# Sampling and the answer-length ceiling do not change what the ten checks observed.
_PROOF_IGNORED_REQUEST = frozenset({
    "temperature", "top_k", "top_p", "min_p", "repeat_penalty",
    "presence_penalty", "frequency_penalty", "max_tokens",
})
# A saved Thinking change drops only the two thinking checks.
_THINKING_REQUEST_KEYS = frozenset({"reasoning", "reasoning_effort"})
_THINKING_HISTORY_KEYS = frozenset({"reasoning_preserve"})


def _external_template_identity(startup: dict[str, Any]) -> dict[str, Any] | None:
    """Templates are small; check their bytes without rereading model weights."""
    if not startup.get("chat_template_file"):
        return None
    path = Path(str(startup["chat_template_file"]))
    try:
        with path.open("rb") as stream:
            data = stream.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            return {"path": str(path.resolve()), "state": "too_large"}
        return {"sha256": hashlib.sha256(data).hexdigest()}
    except OSError:
        return {"path": str(path.resolve()), "state": "missing"}


def _external_draft_identity(deployment: Deployment) -> dict[str, Any] | None:
    path = deployment.applied_startup.get("spec_draft_model")
    if not path:
        return None
    from workbench_backend.inference.hashes import observed_file_identity
    return observed_file_identity(Path(str(path)), deployment.inference_identity.get("external_draft_model"))


def _artifact_scope(artifacts: Any) -> dict[str, Any]:
    if not isinstance(artifacts, dict):
        return {}
    runtime = artifacts.get("runtime")
    runtime = ({key: runtime.get(key) for key in ("release", "sha256", "companion_sha256")}
               if isinstance(runtime, dict) else None)
    files = artifacts.get("bundle_files")
    normalized = []
    for item in files if isinstance(files, list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("role") == "companion" and Path(str(item.get("path", ""))).suffix.lower() != ".gguf":
            continue
        normalized.append({"role": item.get("role"), "sha256": item.get("sha256"),
                           **({"path": item.get("path")} if not item.get("sha256") else {})})
    normalized.sort(key=lambda item: json.dumps(item, sort_keys=True))
    return {"runtime": runtime, "bundle_files": normalized}


def proof_scope(identity: dict[str, Any], *, capability: str | None = None) -> dict[str, Any]:
    startup = identity.get("startup") if isinstance(identity.get("startup"), dict) else {}
    # Legacy evidence has no normalized artifact/runtime proof. It stays local
    # to its original exact identity and is never promoted to durable proof.
    if identity.get("probe_version") != 3:
        return identity
    artifacts = _artifact_scope(identity.get("artifacts"))
    runtime = artifacts.get("runtime")
    files = artifacts.get("bundle_files", [])
    reusable = bool(runtime and runtime.get("sha256") and files and all(item.get("sha256") for item in files))
    excluded = {"model", "model_path", "context"}
    if reusable:
        excluded.update({"deployment_id", "bundle_id", "endpoint"})
    scoped = {key: value for key, value in identity.items() if key not in excluded}
    scoped["artifacts"] = artifacts
    draft = scoped.get("external_draft_model")
    if isinstance(draft, dict) and draft.get("sha256"):
        scoped["external_draft_model"] = {"sha256": draft["sha256"]}
    scoped["startup"] = {
        key: value for key, value in startup.items()
        if key not in _PROOF_IGNORED_STARTUP and key != "chat_template_file" and not str(key).startswith("spec_")
    }
    generation = scoped.get("generation_defaults")
    if isinstance(generation, dict):
        def behaviour_defaults(values: dict[str, Any]) -> dict[str, Any]:
            return {key: behaviour_defaults(value) if isinstance(value, dict) else value
                    for key, value in values.items()
                    if key not in _PROOF_IGNORED_STARTUP and key not in {"n_ctx", "n_batch", "n_ubatch", "n_threads"}}
        scoped["generation_defaults"] = behaviour_defaults(generation)
    request = scoped.get("request")
    if isinstance(request, dict):
        drop = set(_PROOF_IGNORED_REQUEST)
        if capability != "reasoning_replay":
            drop |= _THINKING_HISTORY_KEYS
        if capability not in {"reasoning", "reasoning_replay"}:
            drop |= _THINKING_REQUEST_KEYS
        scoped["request"] = {key: value for key, value in request.items() if key not in drop}
    return scoped


def proof_fingerprint(deployment: Deployment, per_request: SettingsBag | dict | None = None) -> str:
    return _identity_fingerprint(proof_scope(setup_identity(deployment, per_request)))


def artifact_proof_scope(identity: dict[str, Any]) -> dict[str, Any]:
    """Hydrate saved evidence for every response setup using these artifacts."""
    scope = proof_scope(identity)
    return {key: value for key, value in scope.items() if key != "request"}


def applicable_capabilities(deployment: Deployment, per_request: SettingsBag | dict | None = None) -> list[Capability]:
    settings = deployment.settings.per_request.applied if per_request is None else per_request.applied if isinstance(per_request, SettingsBag) else per_request
    if deployment.applied_startup.get("embedding") == "on":
        return []
    props = deployment.server_props
    modalities = props.modalities if props else {}
    caps = props.chat_template_caps if props else {}
    vision = modalities.get("vision") is True
    # A projector is a usable image input when an older server does not report
    # modalities. An explicit native rejection takes precedence.
    if modalities.get("vision") is None:
        vision = any(item.get("role") == "companion" and "mmproj" in str(item.get("path", "")).lower()
                     for item in deployment.inference_identity.get("bundle_files", []))
    thinking = (settings.get("reasoning") != "off" and settings.get("reasoning_effort") != "none"
                and caps.get("supports_thinking") is not False)
    preserve = settings.get("reasoning_preserve")
    if type(preserve) is not bool and props:
        kwargs = props.default_generation_settings.get("chat_template_kwargs", {})
        if isinstance(kwargs, dict):
            preserve = kwargs.get("preserve_reasoning", kwargs.get("preserve_thinking"))
        if type(preserve) is not bool:
            from workbench_backend.inference.configuration_options import reasoning_history_descriptor
            from workbench_backend.inference.schemas import GgufRuntimeMetadata
            preserve = reasoning_history_descriptor(GgufRuntimeMetadata(), deployment).default_value
    replay = thinking and caps.get("supports_preserve_reasoning") is True and preserve is True
    return [name for name in CAPABILITIES
            if (name not in {"image", "tool_image"} or vision)
            and (name != "reasoning" or thinking)
            and (name != "reasoning_replay" or replay)]


def capability_support(deployment: Deployment, capability: str, per_request: SettingsBag | dict | None = None) -> ProbeStatus:
    identity = setup_identity(deployment, per_request)
    fingerprint = _identity_fingerprint(identity)
    scoped = _identity_fingerprint(proof_scope(identity, capability=capability))
    for raw in reversed(deployment.capability_evidence):
        if raw.get("capability") != capability:
            continue
        status = raw.get("status")
        if status not in {"passed", "failed", "untested", "inconclusive"}:
            continue
        if raw.get("fingerprint") == fingerprint:
            return status
        setup = raw.get("setup")
        if isinstance(setup, dict) and _identity_fingerprint(proof_scope(setup, capability=capability)) == scoped:
            return status
    return "untested"
