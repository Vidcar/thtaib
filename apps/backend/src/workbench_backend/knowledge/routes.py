"""Durable knowledge HTTP API. Thin debug surface only; not Chat or Builder."""

from __future__ import annotations

from fastapi import APIRouter, Request

from workbench_backend.knowledge.schemas import (
    ContextCaptureRequest,
    KnowledgeConfigUpdateRequest,
    KnowledgeCreateRequest,
    KnowledgeEditRequest,
    KnowledgeRevertRequest,
    KnowledgeConfig, KnowledgeEntryView, KnowledgeVersion, KnowledgeLifecycleRequest,
    KnowledgeAutomaticPolicy, KnowledgeScopeOption, KnowledgeProposal, KnowledgeProposalReview,
    SkillPackageImportRequest, SkillResourceView,
)
from workbench_backend.knowledge.service import KnowledgeService
from workbench_backend.inference.schemas import DeletePreview
from workbench_backend.state.dependencies import dependency_preview_for_app

router = APIRouter(prefix="/v1/knowledge")


@router.post("/skills/import", response_model=KnowledgeEntryView)
def import_skill(request: Request, body: SkillPackageImportRequest):
    return get_knowledge(request).import_skill(body)


@router.get("/versions/{version_id}/resource", response_model=SkillResourceView)
def skill_resource(request: Request, version_id: str, path: str):
    return get_knowledge(request).inspect_resource(version_id, path)


def get_knowledge(request: Request) -> KnowledgeService:
    return request.app.state.knowledge


@router.get("/config", response_model=KnowledgeConfig)
def get_config(request: Request) -> object:
    return get_knowledge(request).get_config()


@router.put("/config", response_model=KnowledgeConfig)
def update_config(request: Request, body: KnowledgeConfigUpdateRequest) -> object:
    return get_knowledge(request).update_config(body)


@router.post("/entries", response_model=KnowledgeEntryView)
def create_entry(request: Request, body: KnowledgeCreateRequest) -> object:
    return get_knowledge(request).create(body)


@router.get("/entries", response_model=list[KnowledgeEntryView])
def list_entries(request: Request, include_inactive: bool = False) -> object:
    return get_knowledge(request).list_entries(include_inactive=include_inactive)


@router.get("/entries/{entry_id}", response_model=KnowledgeEntryView)
def get_entry(request: Request, entry_id: str) -> object:
    return get_knowledge(request).get_entry(entry_id)


@router.get("/entries/{entry_id}/versions", response_model=list[KnowledgeVersion])
def list_versions(request: Request, entry_id: str) -> object:
    return get_knowledge(request).list_versions(entry_id)


@router.post("/entries/{entry_id}/edit", response_model=KnowledgeEntryView)
def edit_entry(request: Request, entry_id: str, body: KnowledgeEditRequest) -> object:
    return get_knowledge(request).edit(entry_id, body)


@router.post("/entries/{entry_id}/revert", response_model=KnowledgeEntryView)
def revert_entry(request: Request, entry_id: str, body: KnowledgeRevertRequest) -> object:
    return get_knowledge(request).revert(entry_id, body)


@router.get("/versions/{version_id}", response_model=KnowledgeVersion)
def get_version(request: Request, version_id: str) -> object:
    return get_knowledge(request).get_version(version_id)


@router.patch("/entries/{entry_id}", response_model=KnowledgeEntryView)
def update_entry(request: Request, entry_id: str, body: KnowledgeLifecycleRequest):
    return get_knowledge(request).update_lifecycle(entry_id, body)


@router.delete("/entries/{entry_id}", response_model=KnowledgeEntryView)
def remove_entry(request: Request, entry_id: str):
    return get_knowledge(request).remove_entry(entry_id)


@router.get("/entries/{entry_id}/delete-preview", response_model=DeletePreview)
def entry_delete_preview(request: Request, entry_id: str):
    return dependency_preview_for_app(request.app.state, "knowledge", entry_id)


@router.get("/scopes", response_model=list[KnowledgeScopeOption])
def knowledge_scopes(request: Request):
    return get_knowledge(request).scope_options()


@router.put("/automatic-save-policy", response_model=KnowledgeConfig)
def automatic_save_policy(request: Request, body: KnowledgeAutomaticPolicy):
    return get_knowledge(request).set_automatic_policy(body)


@router.get("/proposals", response_model=list[KnowledgeProposal])
def proposals(request: Request, run_id: str | None = None):
    return get_knowledge(request).list_proposals(run_id=run_id)


@router.post("/proposals/{proposal_id}/review", response_model=KnowledgeProposal)
def review_proposal(request: Request, proposal_id: str, body: KnowledgeProposalReview):
    return get_knowledge(request).review_proposal(proposal_id, body.decision)


@router.post("/captures")
def create_capture(request: Request, body: ContextCaptureRequest) -> object:
    return get_knowledge(request).capture(body)


@router.get("/captures")
def list_captures(request: Request) -> object:
    return get_knowledge(request).list_captures()


@router.get("/captures/{capture_id}")
def get_capture(request: Request, capture_id: str) -> object:
    return get_knowledge(request).get_capture(capture_id)
