"""Apply STATE-005 context-capture policy to diagnostic copies (Issue #64).

Conversation transcripts, LangGraph checkpoints, and operational run event
history are not discarded here. Those follow a separate operational retention
policy so execution recovery is not silently broken.

Safe provenance (tool names, knowledge version refs, capture gaps, timestamps)
is retained when diagnostic bodies are discarded or expired.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any

from workbench_backend.agents.schemas import AgentRun, ModelRequestCapture
from workbench_backend.agents.setup_schemas import InputSourceRow
from workbench_backend.knowledge.redaction import redact_structured
from workbench_backend.knowledge import redaction
from workbench_backend.knowledge.schemas import ContextCaptureSettings
from workbench_backend.knowledge.store import KnowledgeStore
from workbench_backend.paths import WorkbenchPaths

POLICY_DISCARD_GAP = "diagnostic content discarded by Knowledge capture policy"
POLICY_EXPIRED_GAP = "diagnostic content expired by Knowledge capture retention"
POLICY_VERSION = 3


def capture_settings_for_paths(paths: WorkbenchPaths) -> ContextCaptureSettings:
    return KnowledgeStore(paths).read_config().context_captures


def apply_run_diagnostic_policy(
    run: AgentRun,
    settings: ContextCaptureSettings,
    *,
    now: datetime | None = None,
) -> AgentRun:
    """Normalize changed captures without copying operational run state."""

    moment = now or datetime.now(timezone.utc).replace(microsecond=0)
    captures = [apply_capture_policy(item, settings, now=moment) for item in run.model_requests]
    if all(before is after for before, after in zip(run.model_requests, captures, strict=True)):
        return run
    return run.model_copy(update={"model_requests": captures})


def apply_capture_policy(
    capture: ModelRequestCapture,
    settings: ContextCaptureSettings,
    *,
    now: datetime | None = None,
) -> ModelRequestCapture:
    """Apply retain / redact_secrets / discard and retention expiry."""

    moment = now or datetime.now(timezone.utc).replace(microsecond=0)
    expires_at = _expires_at(capture, settings, moment)
    expired = expires_at is not None and expires_at <= moment
    fingerprint = _privacy_fingerprint(capture, settings, expires_at, expired)
    if capture.privacy_fingerprint == fingerprint:
        return capture
    discarded_mode = settings.redaction_mode == "discard"
    drop_content = discarded_mode or expired
    gaps = _policy_gaps(capture.capture_gaps, discarded_mode, expired)

    if drop_content:
        updated = capture.model_copy(
            update={
                "instructions": None,
                "messages": [],
                "generation_settings": {},
                "retrieved_material": [],
                "http_payload": None,
                "http_payloads": [],
                "failure": None,
                "tool_schemas": [],
                "input_sources": [source.model_copy(update={"content": None, "path": None,
                    "title": source.kind, "origin": "Captured source", "reason": "Diagnostic content unavailable.",
                    "history_hint": None, "required_tools": [], "required_connections": []}) for source in capture.input_sources],
                "capture_gaps": gaps,
                "redaction_mode": settings.redaction_mode,
                "retention_seconds": settings.retention_seconds,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "retained": False,
                "redacted": capture.redacted,
                "discarded": discarded_mode,
                "expired": expired,
                "redacted_fields": list(capture.redacted_fields),
            }
        )
        return _with_fingerprint(updated, settings, expires_at, expired)

    # Reapplying a changed policy must not erase prior redaction provenance just
    # because the already-redacted text contains no remaining detector hit.
    redacted_fields: list[str] = list(capture.redacted_fields)
    instructions, redacted_fields = _redact_text(capture.instructions, redacted_fields)
    messages, redacted_fields = _redact_value(capture.messages, redacted_fields)
    generation_settings, redacted_fields = _redact_value(
        capture.generation_settings, redacted_fields
    )
    retrieved_material, redacted_fields = _redact_value(
        capture.retrieved_material, redacted_fields
    )
    http_payload, redacted_fields = _redact_value(capture.http_payload, redacted_fields)
    http_payloads, redacted_fields = _redact_value(capture.http_payloads, redacted_fields)
    failure, redacted_fields = _redact_value(capture.failure, redacted_fields)
    if capture.input_sources or capture.tool_schemas:
        inputs, redacted_fields = _redact_value({"sources": [source.model_dump(mode="json") for source in capture.input_sources],
            "tools": capture.tool_schemas}, redacted_fields)
        source_values, tool_schemas = inputs["sources"], inputs["tools"]
    else:
        source_values, tool_schemas = [], []
    unique = list(dict.fromkeys(redacted_fields))
    updated = capture.model_copy(
        update={
            "instructions": instructions,
            "messages": messages if isinstance(messages, list) else [],
            "generation_settings": generation_settings
            if isinstance(generation_settings, dict)
            else {},
            "retrieved_material": retrieved_material
            if isinstance(retrieved_material, list)
            else [],
            "http_payload": http_payload if isinstance(http_payload, dict) else None,
            "http_payloads": http_payloads if isinstance(http_payloads, list) else [],
            "failure": failure if isinstance(failure, dict) else None,
            "input_sources": [InputSourceRow.model_validate(source) for source in source_values] if isinstance(source_values, list) else [],
            "tool_schemas": tool_schemas if isinstance(tool_schemas, list) else [],
            "capture_gaps": gaps,
            "redaction_mode": settings.redaction_mode,
            "retention_seconds": settings.retention_seconds,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "retained": True,
            "redacted": bool(unique),
            "discarded": False,
            "expired": False,
            "redacted_fields": unique,
        }
    )
    return _with_fingerprint(updated, settings, expires_at, expired)


def _privacy_fingerprint(
    capture: ModelRequestCapture,
    settings: ContextCaptureSettings,
    expires_at: datetime | None,
    expired: bool,
) -> str:
    # Hash the current content on every entry: a retained fingerprint alone
    # cannot certify an object whose nested dictionaries were edited in place.
    canonical = {
        "capture": capture.model_dump(mode="json", exclude={"privacy_fingerprint"}),
        "policy": settings.model_dump(mode="json"),
        "policy_version": POLICY_VERSION,
        "detector_version": redaction.DETECTOR_VERSION,
        "detector_patterns": [(name, pattern.pattern, pattern.flags) for name, pattern in redaction.SECRET_PATTERNS],
        "expires_at": expires_at.isoformat() if expires_at else None,
        "expired": expired,
    }
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _with_fingerprint(
    capture: ModelRequestCapture,
    settings: ContextCaptureSettings,
    expires_at: datetime | None,
    expired: bool,
) -> ModelRequestCapture:
    capture.privacy_fingerprint = _privacy_fingerprint(capture, settings, expires_at, expired)
    return capture


def _expires_at(
    capture: ModelRequestCapture,
    settings: ContextCaptureSettings,
    now: datetime,
) -> datetime | None:
    if settings.retention_seconds is None:
        return None
    created = _parse_time(capture.at) or now
    return created + timedelta(seconds=settings.retention_seconds)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _policy_gaps(existing: list[str], discarded: bool, expired: bool) -> list[str]:
    gaps = [item for item in existing if item not in {POLICY_DISCARD_GAP, POLICY_EXPIRED_GAP}]
    if discarded and POLICY_DISCARD_GAP not in gaps:
        gaps.append(POLICY_DISCARD_GAP)
    if expired and POLICY_EXPIRED_GAP not in gaps:
        gaps.append(POLICY_EXPIRED_GAP)
    return gaps


def _redact_text(
    value: str | None, fields: list[str]
) -> tuple[str | None, list[str]]:
    if value is None:
        return None, fields
    stored, _, names = redact_structured(value, "redact_secrets")
    fields.extend(names)
    return stored if isinstance(stored, str) else None, fields


def _redact_value(value: Any, fields: list[str]) -> tuple[Any, list[str]]:
    stored, _, names = redact_structured(value, "redact_secrets")
    fields.extend(names)
    return stored, fields
