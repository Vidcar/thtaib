"""HTTP routes for compatibility records. Loopback smoke only."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

from workbench_backend.inference.compatibility import (
    CompatibilityAssessRequest,
    CompatibilityService,
    UserOverrideRequest,
)
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.capabilities import CAPABILITIES, CapabilityEvidence, CapabilityProbeRequest, CapabilityProbeReport, ImageProbeSetup, applicable_capabilities, capability_support, proof_fingerprint, setup_fingerprint
from workbench_backend.inference.capability_context import configuration_probe_context, resolve_probe_bag, selected_configuration
from workbench_backend.inference.bundles import mmproj_companion
from workbench_backend.inference.probes import run_capability_probe
from workbench_backend.inference.schemas import ManagedDeploymentRequest
from workbench_backend.errors import ManagerError

router = APIRouter(prefix="/v1/compatibility")


@router.post("/deployments/{deployment_id}/probes", response_model=CapabilityEvidence)
def probe(request: Request, deployment_id: str, body: CapabilityProbeRequest) -> CapabilityEvidence:
    return run_capability_probe(get_manager(request), deployment_id, body)


@router.get("/deployments/{deployment_id}/probes", response_model=CapabilityProbeReport)
def probe_evidence(request: Request, deployment_id: str, configuration_id: str | None = None,
                   expected_configuration_revision: int | None = None) -> CapabilityProbeReport:
    manager = get_manager(request)
    deployment = manager.get_deployment(deployment_id)
    body = CapabilityProbeRequest(capability="text_stream", configuration_id=configuration_id,
                                  expected_configuration_revision=expected_configuration_revision)
    return _report(manager, deployment, resolve_probe_bag(manager, deployment, body))


@router.get("/configurations/{configuration_id}/probes", response_model=CapabilityProbeReport)
def configuration_evidence(request: Request, configuration_id: str,
                           expected_configuration_revision: int | None = None) -> CapabilityProbeReport:
    manager = get_manager(request)
    deployment = configuration_probe_context(manager, configuration_id, expected_configuration_revision)
    return _report(manager, deployment, deployment.settings.per_request)


@router.post("/configurations/{configuration_id}/probes", response_model=CapabilityEvidence)
def probe_configuration(request: Request, configuration_id: str, body: CapabilityProbeRequest) -> CapabilityEvidence:
    manager = get_manager(request)
    if body.configuration_id not in {None, configuration_id} or body.per_request is not None:
        raise ManagerError("Check the saved setup selected in this model.", code="probe_settings_ambiguous", status_code=422)
    with manager.store.configuration_lock():
        profile = selected_configuration(manager, configuration_id, body.expected_configuration_revision)
        selected = body.model_copy(update={"configuration_id": profile.id,
                                           "expected_configuration_revision": profile.revision})
        deployment = manager.create_managed(ManagedDeploymentRequest(
            bundle_id=profile.bundle_id, profile_id=profile.id, auto_start=False))
    # Reserve the selected revision through readiness and the entire probe.
    # Ordinary text use can continue while this lifecycle reservation is held.
    with manager.reserve_deployment(deployment.id, profile_id=profile.id):
        manager.ensure_deployment_ready(deployment.id)
        return run_capability_probe(manager, deployment.id, selected)


def _report(manager, deployment, bag) -> CapabilityProbeReport:
    bundle = manager.store.get_bundle(deployment.bundle_id) if deployment.bundle_id else None
    projector = mmproj_companion(bundle) if bundle else None
    fingerprint = proof_fingerprint(deployment, bag)
    coordinator = getattr(manager, "capability_checks", None)
    running, capability = coordinator.state(fingerprint) if coordinator else (False, None)
    return CapabilityProbeReport(
        current_fingerprint=setup_fingerprint(deployment, bag),
        evidence=deployment.capability_evidence,
        current_support={name: capability_support(deployment, name, bag) for name in CAPABILITIES},
        applicable_capabilities=applicable_capabilities(deployment, bag),
        automatic_running=running,
        running_capability=capability,
        image_setup=ImageProbeSetup(
            selected_projector=projector.path if projector else None,
            projector_present=Path(projector.path).is_file() if projector else None,
            runtime_support=deployment.server_props.modalities.get("vision") if deployment.server_props else None,
        ),
    )


def get_compatibility(request: Request) -> CompatibilityService:
    return request.app.state.compatibility


def get_manager(request: Request) -> ModelManager:
    return request.app.state.manager


@router.get("/records")
def list_records(request: Request) -> object:
    return get_compatibility(request).list_records()


@router.get("/records/{record_id}")
def get_record(request: Request, record_id: str) -> object:
    return get_compatibility(request).get_record(record_id)


@router.post("/records/{record_id}/overrides")
def add_override(request: Request, record_id: str, body: UserOverrideRequest) -> object:
    return get_compatibility(request).add_user_override(record_id, body)


@router.post("/assess")
def assess(request: Request, body: CompatibilityAssessRequest) -> object:
    service = get_compatibility(request)
    if body.bundle_id:
        bundle = get_manager(request).get_bundle(body.bundle_id)
        return service.assess_bundle(bundle)
    if not body.selector and not body.display_name:
        return service.assess(selector="unfamiliar")
    return service.assess(selector=body.selector, display_name=body.display_name)
