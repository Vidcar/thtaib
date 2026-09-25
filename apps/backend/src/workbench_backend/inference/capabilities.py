"""Setup-specific probe identity, independent of publisher claims and opt-outs."""

from __future__ import annotations

import hashlib
import json
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


def setup_identity(deployment: Deployment, per_request: SettingsBag | dict | None = None) -> dict[str, Any]:
    props = deployment.server_props
    settings = deployment.settings.per_request.applied if per_request is None else per_request.applied if isinstance(per_request, SettingsBag) else per_request
    return {
        "probe_version": 2,
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
    }


def setup_fingerprint(deployment: Deployment, per_request: SettingsBag | dict | None = None) -> str:
    return hashlib.sha256(json.dumps(setup_identity(deployment, per_request), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def capability_support(deployment: Deployment, capability: str, per_request: SettingsBag | dict | None = None) -> ProbeStatus:
    fingerprint = setup_fingerprint(deployment, per_request)
    for raw in reversed(deployment.capability_evidence):
        if raw.get("capability") == capability and raw.get("fingerprint") == fingerprint:
            status = raw.get("status")
            if status in {"passed", "failed", "untested", "inconclusive"}:
                return status
    return "untested"
