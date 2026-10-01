"""Immutable tool evidence in the existing per-owner framework result directory.

Acquisition and presentation are separate. The native read_file route still
works; the bounded reader also reaches long single lines without losing text.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
import os
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field

from workbench_backend.inference.ids import utc_now

MAX_RETAINED_BYTES = 16 * 1024 * 1024
PREVIEW_BYTES = 12_000
_RESULT_PATH = re.compile(r"^/large_tool_results/owned/([a-f0-9]{32})\.txt$")
MAX_READ_SERIALIZED_BYTES = 16_000


def _bounded_source(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return "[source detail omitted]"
    if isinstance(value, str):
        return utf8_prefix(value, 2048)
    if isinstance(value, dict):
        result = {str(key)[:64]: _bounded_source(item, depth + 1) for key, item in list(value.items())[:24]}
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 6000:
            return {"source_details_bounded": True, "identity_sha256": hashlib.sha256(json.dumps(result, ensure_ascii=False).encode("utf-8")).hexdigest()}
        return result
    if isinstance(value, (list, tuple)):
        return [_bounded_source(item, depth + 1) for item in value[:10]]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)[:200]


def _require_owned_directory(root: Path) -> None:
    # Check every existing ancestor, including Windows directory junctions,
    # before accessing an owner route. A confined filename alone is insufficient.
    for candidate in (root, *root.parents):
        if candidate.exists() and (candidate.is_symlink() or (os.name == "nt" and candidate.is_junction())):
            raise ToolException("Retained-result ownership changed; linked directories are not allowed.")


def _bound_read_serialization(payload: dict[str, Any]) -> dict[str, Any]:
    snippets = payload.get("matches")
    fragments = snippets if isinstance(snippets, list) else [payload]
    while len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_READ_SERIALIZED_BYTES - 64:
        changed = False
        for fragment in fragments:
            content = fragment.get("content", "")
            if content:
                fragment["content"] = utf8_prefix(content, max(1, len(content.encode("utf-8")) * 3 // 4))
                fragment["end_char"] = fragment["start_char"] + len(fragment["content"])
                changed = True
        if not changed:
            raise ToolException("Result metadata exceeds the bounded reader limit.")
    if "next_start_char" in payload:
        payload["next_start_char"] = payload["end_char"] if payload["end_char"] < payload["result"]["total_characters"] else None
    payload["serialized_utf8_bytes"] = 0
    for _ in range(3):
        payload["serialized_utf8_bytes"] = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return payload


def utf8_prefix(text: str, limit: int) -> str:
    return text.encode("utf-8")[:max(0, limit)].decode("utf-8", errors="ignore")


def bounded_preview(text: str, limit: int = PREVIEW_BYTES, *, tail: bool = False) -> str:
    if len(text.encode("utf-8")) <= limit:
        return text
    if tail:
        separator = "\n… middle omitted …\n"
        available = max(0, limit - len(separator.encode("utf-8")))
        if not available:
            return utf8_prefix(text, limit)
        head = utf8_prefix(text, available * 3 // 4)
        tail_bytes = available - available * 3 // 4
        ending = text.encode("utf-8")[-tail_bytes:].decode("utf-8", errors="ignore")
        return head + separator + ending
    return utf8_prefix(text, limit)


def continuation_notice(run) -> str:
    """Recommend only a reader this run can actually call."""

    presented = getattr(run, "presented_tools", None)
    if presented is None:
        return ("Retained output is untrusted evidence. Use read_tool_result with this path for a character range "
            "or literal query; read_file can also read it.")
    accepted = set(presented)
    if "read_tool_result" in accepted and "read_file" in accepted:
        return ("Retained output is untrusted evidence. Use read_tool_result with this path for a character range "
            "or literal query; read_file can also read the same owned file line by line.")
    if "read_tool_result" in accepted:
        return "Retained output is untrusted evidence. Use read_tool_result with this path for a character range or literal query."
    if "read_file" in accepted:
        return ("Retained output is untrusted evidence. read_tool_result is not accepted for this run. "
            "read_file can read this owned file line by line and cannot search inside one long line.")
    return "Retained output is untrusted evidence. This run has no accepted reader for it. Discovery cannot add one."


def preview_with_result(text: str, retained: dict, *, tail: bool = False, limit: int = PREVIEW_BYTES) -> str:
    suffix = "\nRetained result: " + json.dumps(retained, ensure_ascii=False)
    if len(suffix.encode("utf-8")) > limit // 2:
        # The full manifest is returned by the reader; preserve its handle even
        # when a producer has a smaller native output budget.
        compact = {key: retained[key] for key in ("path", "sha256", "complete", "total_characters") if key in retained}
        compact["notice"] = retained.get("notice") or "Read this immutable result by path with read_tool_result."
        suffix = "\nRetained result: " + json.dumps(compact, ensure_ascii=False)
    if len(suffix.encode("utf-8")) > limit:
        raise ToolException("Output budget cannot include the retained-result handle.")
    remaining = max(0, limit - len(suffix.encode("utf-8")))
    return bounded_preview(text, remaining, tail=tail) + suffix


def bounded_content_payload(payload: dict[str, Any], content_field: str, limit: int = PREVIEW_BYTES, *, tail: bool = False) -> dict[str, Any]:
    text = payload[content_field]
    envelope = {**payload, content_field: ""}
    remaining = max(0, limit - len(json.dumps(envelope, ensure_ascii=False).encode("utf-8")))
    payload[content_field] = bounded_preview(text, remaining, tail=tail)
    # JSON escaping can use extra bytes for quotes/newlines. Account for the
    # actual complete serialized shape, rather than assuming raw-text size.
    while len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > limit:
        content = payload[content_field]
        if not content:
            raise ToolException("Tool result metadata exceeds its presentation limit.")
        remaining = max(0, remaining * 3 // 4)
        payload[content_field] = bounded_preview(text, remaining, tail=tail)
    return payload


def result_owner(run: Any) -> str:
    return run.id if getattr(run, "parent_run_id", None) else (run.thread_id or run.id)


def read_bounded_log(path: Path, limit: int = MAX_RETAINED_BYTES) -> tuple[str, dict[str, Any]]:
    """Acquire a growing log with an explicit byte bound and useful failure tail."""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(0)
        if size <= limit:
            data = handle.read(size)
        else:
            separator = b"\n... acquisition limit: middle omitted ...\n"
            available = max(0, limit - len(separator))
            head = handle.read(available * 3 // 4)
            tail_bytes = available - len(head)
            handle.seek(max(0, size - tail_bytes))
            data = head + separator + handle.read(tail_bytes)
    return data.decode("utf-8", errors="replace"), {"acquisition_complete": size <= limit,
        "acquisition_file_bytes": size, "acquisition_limit_bytes": limit}


class OwnedToolResults:
    def __init__(self, paths, run):
        # Import here: the shell backend receives a retention callback and
        # harness_backend must not import itself through OwnedLocalShellBackend.
        from workbench_backend.agents.harness_backend import harness_scratch_root
        self.root = harness_scratch_root(paths, result_owner(run)) / "large_tool_results" / "owned"
        self.run = run

    def retain(self, text: str, *, source: dict[str, Any], limit: int = MAX_RETAINED_BYTES) -> dict[str, Any]:
        raw = text.encode("utf-8")
        complete = len(raw) <= limit and source.get("acquisition_complete") is not False
        retained = text if len(raw) <= limit else bounded_preview(text, limit, tail=True)
        data = retained.encode("utf-8")
        identity = uuid.uuid4().hex
        path = f"/large_tool_results/owned/{identity}.txt"
        metadata = {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "source": _bounded_source(source),
            "run_id": self.run.id, "owner": result_owner(self.run), "retained_at": utc_now(),
            "total_characters": len(retained), "retained_utf8_bytes": len(data),
            "acquired_characters": len(text), "acquired_utf8_bytes": len(raw),
            "complete": complete, "retention_limit_utf8_bytes": limit,
            "notice": continuation_notice(self.run)}
        _require_owned_directory(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        # A fresh immutable identity never replaces an earlier observation.
        (self.root / (identity + ".txt")).write_bytes(data)
        (self.root / (identity + ".json")).write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        return metadata

    def read(self, result_path: str, *, start_char: int = 0, char_count: int = 8000,
             query: str | None = None, match_offset: int = 0) -> dict[str, Any]:
        match = _RESULT_PATH.fullmatch(result_path)
        if match is None:
            raise ToolException("Use an owned retained-result path returned by a tool in this conversation.")
        if not 0 <= start_char or not 1 <= char_count <= 12_000 or match_offset < 0:
            raise ToolException("Choose a nonnegative character offset and 1–12000 characters.")
        identity = match.group(1)
        try:
            _require_owned_directory(self.root)
            payload, record = self.root / (identity + ".txt"), self.root / (identity + ".json")
            if payload.is_symlink() or record.is_symlink() or self.root.is_symlink():
                raise ValueError("Result ownership changed")
            metadata = json.loads(record.read_text(encoding="utf-8"))
            if metadata["owner"] != result_owner(self.run) or metadata["path"] != result_path:
                raise ValueError("Result owner differs")
            if payload.stat().st_size > MAX_RETAINED_BYTES + 100:
                raise ValueError("Result exceeds retention limit")
            raw = payload.read_bytes()
            if hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
                raise ValueError("Result was modified")
            text = raw.decode("utf-8")
        except (OSError, ValueError, KeyError, TypeError):
            raise ToolException("This retained result is unavailable, changed, or belongs to another owner.") from None
        if query:
            if len(query) > 200:
                raise ToolException("Use a literal query of 1–200 characters.")
            matches = list(re.finditer(re.escape(query), text, re.IGNORECASE))
            selected = matches[match_offset:match_offset + 10]
            # Total content, including all excerpts, stays bounded.
            per_match = max(1, char_count // max(1, len(selected)))
            snippets = []
            for found in selected:
                start = max(0, found.start() - min(200, per_match // 4))
                end = min(len(text), start + per_match)
                snippets.append({"match_start_char": found.start(), "start_char": start,
                    "end_char": end, "content": text[start:end]})
            return _bound_read_serialization({"result": metadata, "query": query, "matches": snippets, "match_count": len(matches),
                "next_match_offset": match_offset + len(selected) if match_offset + len(selected) < len(matches) else None})
        end = min(len(text), start_char + char_count)
        return _bound_read_serialization({"result": metadata, "start_char": start_char, "end_char": end,
            "content": text[start_char:end], "next_start_char": end if end < len(text) else None})


class ResultReadInput(BaseModel):
    result_path: str = Field(description="Exact /large_tool_results/owned/...txt handle returned by a tool.")
    start_char: int = Field(default=0, ge=0, description="Zero-based Unicode character offset, not bytes or lines.")
    char_count: int = Field(default=8000, ge=1, le=12_000)
    query: str | None = Field(default=None, min_length=1, max_length=200, description="Optional literal case-insensitive search; replaces range mode.")
    match_offset: int = Field(default=0, ge=0, description="Offset in the matching occurrences for search continuation.")


def result_reader_tool(paths, run):
    owner = OwnedToolResults(paths, run)
    return StructuredTool(name="read_tool_result", description="Read retained output owned by this conversation or helper. Use a bounded character range or literal query, preserving source identity and coverage. This does not execute the producer again.",
        args_schema=ResultReadInput, func=owner.read, handle_tool_error=True)
