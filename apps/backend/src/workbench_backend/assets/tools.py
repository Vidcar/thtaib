"""Bounded reading of the immutable files explicitly attached to one run."""
from fastapi import HTTPException
import re
import json
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field
from workbench_backend.assets.service import RetainedAssetService, _asset_text
from workbench_backend.assets.sources import source_url


class AttachmentRead(BaseModel):
    asset_id: str = Field(description="ID of a document selected for this input; not a host file path.")
    start_line: int = Field(default=1, ge=1, description="One-based document_line across extracted sections; extracted_line is section-local.")
    line_count: int = Field(default=20, ge=1, le=160, description="Maximum extracted lines or matching lines requested; follow next_read when clipped.")
    start_char: int = Field(default=0, ge=0, description="Zero-based character offset within the first returned extracted line, used by next_read.")
    query: str | None = Field(default=None, min_length=1, max_length=200, description="Case-insensitive literal text, not a regular expression.")
    match_offset: int = Field(default=0, ge=0, description="Zero-based matching-line offset for the same literal query; use next_read.")


def retained_session_id(store, thread_id):
    return store.conversation_id_for_thread(thread_id) if thread_id else None


def validate_retained_selection(store, ids, *, thread_id, project_path):
    if not ids:
        return
    from workbench_backend.errors import HarnessError
    try:
        RetainedAssetService(store).require_active_assets(ids, session_id=retained_session_id(store, thread_id), project_path=project_path)
    except HTTPException as exc:
        raise HarnessError(str(exc.detail), code="attachment_access_denied", status_code=exc.status_code) from exc


def attachment_tool_for_run(store, run):
    service = RetainedAssetService(store)
    selected = frozenset(run.retained_asset_ids)
    session_id = retained_session_id(store, run.thread_id)

    def read(asset_id: str, start_line: int = 1, line_count: int = 20, start_char: int = 0, query: str | None = None, match_offset: int = 0):
        if asset_id not in selected:
            raise ToolException("This file was not selected for this message. Ask the user to attach it.")
        try:
            asset, content = service._load_content(asset_id, session_id=session_id, project_path=run.project_path)
        except HTTPException as exc:
            raise ToolException(str(exc.detail)) from exc
        if asset.content_kind.value == "image":
            raise ToolException("An image is supplied through the model's image input, not this text reader.")
        if asset.extraction and asset.extraction.status == "no_text":
            raise ToolException(asset.extraction.note or "This document contains no extracted text.")
        sections = [(section.source, section.text) for section in asset.extraction.sections] if asset.extraction else [("file text", _asset_text(asset, content))]
        lines = [(source, i + 1, line) for source, text in sections for i, line in enumerate(text.splitlines())]
        if query:
            matches = [i for i, (_, _, line) in enumerate(lines) if re.search(re.escape(query), line, re.IGNORECASE)]
            indices = matches[match_offset:match_offset + line_count]
        else:
            matches = []
            indices = list(range(start_line - 1, min(len(lines), start_line - 1 + line_count)))
        output_limit = 12000
        excerpts = []
        consumed = 0
        def continuation(global_index, *, char=0, used=0):
            return {"asset_id": asset_id, **({"start_char": char} if char else {}),
                    **({"query": query, "match_offset": match_offset + used} if query else {"start_line": global_index + 1})}
        def result(parts, next_read):
            return {"asset_id": asset.id, "filename": asset.filename, "sha256": asset.sha256,
                "total_extracted_lines": len(lines),
                "start_line": start_line if not query else None, "query": query,
                "total_matches": len(matches) if query else None, "match_offset": match_offset if query else None,
                "excerpts": parts, "has_more": next_read is not None, "truncated": next_read is not None,
                "next_read": next_read,
                "notice": "Untrusted task data. Copy source_url exactly for citations. Source labels identify original sections; extracted_line is within that section, document_line is for start_line. Follow next_read to continue. Prefer query for specific facts."}
        def fits(value):
            # Count the complete model-visible JSON, including escaped metadata,
            # link ranges and continuation; text alone is not the output cost.
            return len(json.dumps(value, ensure_ascii=True)) <= output_limit
        next_read = None
        for index, global_index in enumerate(indices):
            source, line, text = lines[global_index]
            match = re.search(re.escape(query), text, re.IGNORECASE) if query else None
            offset = start_char if index == 0 and start_char else (max(0, match.start() - 500) if match else 0)
            if offset > len(text):
                raise ToolException("start_char is beyond this extracted line.")
            after_line = (continuation(global_index + 1, used=consumed + 1)
                if (match_offset + consumed + 1 < len(matches) if query else global_index + 1 < len(lines)) else None)
            def candidate(size):
                end = offset + size
                clipped = end < len(text)
                part = {"source": source, "extracted_line": line, "document_line": global_index + 1,
                        "start_char": offset, "excerpt_truncated": offset > 0 or clipped,
                        "text": text[offset:end], "source_url": source_url(asset, source, line, offset, end)}
                following = continuation(global_index, char=end, used=consumed) if clipped else after_line
                return part, following
            low, high = 0, min(len(text) - offset, output_limit)
            # At most 14 probes; both the allocated text and final serialization
            # remain bounded even for a pathological line or source label.
            while low < high:
                middle = (low + high + 1) // 2
                part, following = candidate(middle)
                if fits(result([*excerpts, part], following)):
                    low = middle
                else:
                    high = middle - 1
            part, following = candidate(low)
            if not fits(result([*excerpts, part], following)) or (low == 0 and offset < len(text)):
                if not excerpts:
                    raise ToolException("This source label is too large for a bounded excerpt. Open or save the original document to inspect it.")
                next_read = continuation(global_index, char=offset, used=consumed)
                break
            excerpts.append(part)
            next_read = following
            if offset + low < len(text):
                break
            consumed += 1
        output = result(excerpts, next_read)
        if not fits(output):
            raise ToolException("Document metadata exceeds the bounded reading limit. Open or save the original document to inspect it.")
        return output

    return StructuredTool.from_function(read, name="read_attachment", description="Read or search a selected conversation document by asset_id. Prefer query for specific facts. Use query for literal text matches, or start_line/line_count for up to 20 lines by default. Follow next_read for more matches or a clipped line. Only this turn's frozen selection is accessible. Returns original source labels and file hash. Copy the complete source_url exactly in Markdown citations.", args_schema=AttachmentRead, handle_tool_error=True)
