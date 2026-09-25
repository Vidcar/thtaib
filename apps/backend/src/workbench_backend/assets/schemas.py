"""Schemas for immutable retained user files and verified outputs."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RetainedAssetOrigin(str, Enum):
    upload = "upload"
    verified_output = "verified_output"
    capture = "capture"


class RetainedAssetScope(str, Enum):
    session = "session"
    project = "project"


class RetainedAssetStorage(str, Enum):
    application_sqlite = "application.sqlite"


class AssetContentKind(str, Enum):
    text = "text"
    code = "code"
    image = "image"
    document = "document"


class ExtractedSection(BaseModel):
    source: str
    text: str


class AssetExtraction(BaseModel):
    parser: str
    status: Literal["complete", "no_text"] = "complete"
    sections: list[ExtractedSection] = Field(default_factory=list)
    note: str | None = None


class RetainedAsset(BaseModel):
    id: str
    origin: RetainedAssetOrigin
    scope: RetainedAssetScope
    session_id: str
    project_path: str | None = None
    access_scope: str
    storage: RetainedAssetStorage = RetainedAssetStorage.application_sqlite
    filename: str
    content_type: str
    content_kind: AssetContentKind
    encoding: Literal["utf-8", "base64"] = "utf-8"
    image_width: int | None = None
    image_height: int | None = None
    extraction: AssetExtraction | None = None
    size_bytes: int
    sha256: str
    observed_at: str
    source_run_id: str | None = None
    source_tool_call_id: str | None = None
    source_tool_name: str | None = None
    source_target: str | None = None
    mutable_reference: str | None = None
    observation: str | None = None
    deleted_at: str | None = None


class RetainedAssetListFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str | None = None
    project_path: str | None = None
    origin: RetainedAssetOrigin | None = None
    include_deleted: bool = False


class RetainedUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=260)
    content_type: str = Field(min_length=1, max_length=200)
    content_kind: AssetContentKind = AssetContentKind.text
    content_base64: str = Field(min_length=1)


class RegisterVerifiedOutputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    source_tool_call_id: str = Field(min_length=1, max_length=200)
    mutable_reference: str = Field(min_length=1, max_length=4096)
    filename: str | None = Field(default=None, max_length=260)
    content_type: str | None = Field(default=None, max_length=200)
    content_kind: AssetContentKind = AssetContentKind.text


class RetainedAssetPreview(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    preview: str
    truncated: bool = False
    image_data_url: str | None = None
    extraction: AssetExtraction | None = None
    source_status: Literal["retained_only", "unchanged", "changed", "missing", "unavailable"] = "retained_only"


class RetainedAssetContent(BaseModel):
    id: str
    filename: str
    content_type: str
    encoding: Literal["utf-8", "base64"] = "utf-8"
    text: str
    content_base64: str | None = None
    sha256: str
    size_bytes: int
    source_status: Literal["retained_only", "unchanged", "changed", "missing", "unavailable"] = "retained_only"


class RetainedAssetReuseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_ids: list[str] = Field(min_length=1, max_length=32)
    session_id: str | None = Field(default=None, max_length=200)
    project_path: str | None = Field(default=None, max_length=4096)
    allow_cross_session_reuse: bool = False
    max_chars: int = Field(default=1_000_000, ge=1, le=1_000_000)


class RetainedAssetDeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_ids: list[str] = Field(default_factory=list, max_length=100)
    run_ids: list[str] = Field(default_factory=list, max_length=100)
    project_paths: list[str] = Field(default_factory=list, max_length=100)
    branch_ids: list[str] = Field(default_factory=list, max_length=100)
    case_ids: list[str] = Field(default_factory=list, max_length=100)
    asset_ids: list[str] = Field(default_factory=list, max_length=100)


class RetainedAssetDeletionPreview(BaseModel):
    requested_asset_ids: list[str]
    affected_asset_ids: list[str]
    preserved_asset_ids: list[str]
    affected_sessions: list[str]
    retained_sessions: list[str]
    affected_runs: list[str]
    retained_runs: list[str]
    affected_projects: list[str] = Field(default_factory=list)
    retained_projects: list[str] = Field(default_factory=list)
    affected_branches: list[str] = Field(default_factory=list)
    retained_branches: list[str] = Field(default_factory=list)
    affected_cases: list[str] = Field(default_factory=list)
    retained_cases: list[str] = Field(default_factory=list)
    note: str = (
        "Preview only. Shared retained assets are preserved while any "
        "unselected session or run still references them. Project source "
        "files, remote copies, backups and secure erasure are out of scope."
    )
