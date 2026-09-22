"""Version-bound source references for immutable retained documents."""
from urllib.parse import urlencode
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from workbench_backend.assets.service import _asset_text


class SourceRangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source: str | None = Field(default=None, max_length=4096)
    extracted_line: int = Field(default=1, ge=1)
    start_char: int = Field(default=0, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    session_id: str | None = None
    project_path: str | None = None


class SourceRange(BaseModel):
    asset_id: str
    filename: str
    sha256: str
    source: str
    extracted_line: int
    start_char: int
    end_char: int
    text: str
    truncated: bool
    parser: str | None = None


def source_url(asset, source=None, line=1, start=0, end=None):
    query = {"line": line, "start": start}
    if source is not None:
        query["source"] = source
    if end is not None:
        query["end"] = end
    return f"workbench-source://{asset.id}/{asset.sha256}?{urlencode(query)}"


def read_source(service, asset_id, request):
    asset, raw = service._load_content(asset_id, session_id=request.session_id, project_path=request.project_path)
    if asset.sha256 != request.sha256:
        raise HTTPException(409, "This reference identifies a different retained file version.")
    if asset.content_kind.value == "image":
        raise HTTPException(422, "Use the image viewer for this source.")
    if request.source is None:
        if request.extracted_line != 1:
            raise HTTPException(422, "A full-document reference starts at line 1.")
        text = _asset_text(asset, raw)
        label = "Complete extracted document" if asset.extraction else "Complete file text"
    else:
        sections = {section.source: section.text for section in asset.extraction.sections} if asset.extraction else {"file text": _asset_text(asset, raw)}
        if request.source not in sections:
            raise HTTPException(404, "The referenced source range does not exist in this version.")
        lines = sections[request.source].splitlines()
        if request.extracted_line > len(lines):
            raise HTTPException(404, "The referenced line does not exist in this source.")
        text, label = lines[request.extracted_line - 1], request.source
    end = len(text) if request.end_char is None else request.end_char
    if request.start_char > end or end > len(text):
        raise HTTPException(422, "The referenced character range is outside this source.")
    shown_end = min(end, request.start_char + 12000)
    return SourceRange(asset_id=asset.id, filename=asset.filename, sha256=asset.sha256,
                       source=label, extracted_line=request.extracted_line, start_char=request.start_char,
                       end_char=shown_end, text=text[request.start_char:shown_end], truncated=shown_end < end,
                       parser=asset.extraction.parser if asset.extraction else None)
