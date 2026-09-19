"""Durable knowledge HTTP API. Thin debug surface only; not Chat or Builder."""

from __future__ import annotations

from fastapi import APIRouter, Request

from workbench_backend.knowledge.schemas import (
    ContextCaptureRequest,
    KnowledgeConfigUpdateRequest,
    KnowledgeCreateRequest,
    KnowledgeEditRequest,
    KnowledgeRevertRequest,
)
from workbench_backend.knowledge.service import KnowledgeService

router = APIRouter(prefix="/v1/knowledge")


def get_knowledge(request: Request) -> KnowledgeService:
    return request.app.state.knowledge


@router.get("/config")
def get_config(request: Request) -> object:
    return get_knowledge(request).get_config()


@router.put("/config")
def update_config(request: Request, body: KnowledgeConfigUpdateRequest) -> object:
    return get_knowledge(request).update_config(body)


@router.post("/entries")
def create_entry(request: Request, body: KnowledgeCreateRequest) -> object:
    return get_knowledge(request).create(body)


@router.get("/entries")
def list_entries(request: Request) -> object:
    return get_knowledge(request).list_entries()


@router.get("/entries/{entry_id}")
def get_entry(request: Request, entry_id: str) -> object:
    return get_knowledge(request).get_entry(entry_id)


@router.get("/entries/{entry_id}/versions")
def list_versions(request: Request, entry_id: str) -> object:
    return get_knowledge(request).list_versions(entry_id)


@router.post("/entries/{entry_id}/edit")
def edit_entry(request: Request, entry_id: str, body: KnowledgeEditRequest) -> object:
    return get_knowledge(request).edit(entry_id, body)


@router.post("/entries/{entry_id}/revert")
def revert_entry(request: Request, entry_id: str, body: KnowledgeRevertRequest) -> object:
    return get_knowledge(request).revert(entry_id, body)


@router.get("/versions/{version_id}")
def get_version(request: Request, version_id: str) -> object:
    return get_knowledge(request).get_version(version_id)


@router.post("/captures")
def create_capture(request: Request, body: ContextCaptureRequest) -> object:
    return get_knowledge(request).capture(body)


@router.get("/captures")
def list_captures(request: Request) -> object:
    return get_knowledge(request).list_captures()


@router.get("/captures/{capture_id}")
def get_capture(request: Request, capture_id: str) -> object:
    return get_knowledge(request).get_capture(capture_id)
