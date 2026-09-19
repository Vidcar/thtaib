"""Apply STATE-005 context-capture policy to diagnostic copies (Issue #64).

Conversation transcripts, LangGraph checkpoints, and operational run event
history are not discarded here. Those follow a separate operational retention
policy so execution recovery is not silently broken.

Safe provenance (tool names, knowledge version refs, capture gaps, timestamps)
is retained when diagnostic bodies are discarded or expired.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from workbench_backend.agents.schemas import AgentRun, ModelRequestCapture
from workbench_backend.knowledge.redaction import redact_structured
from workbench_backend.knowledge.schemas import ContextCaptureSettings
from workbench_backend.knowledge.store import KnowledgeStore
from workbench_backend.paths import WorkbenchPaths

POLICY_DISCARD_GAP = "diagnostic content discarded by Knowledge capture policy"
POLICY_EXPIRED_GAP = "diagnostic content expired by Knowledge capture retention"


def capture_settings_for_paths(paths: WorkbenchPaths) -> ContextCaptureSettings:
    return KnowledgeStore(paths).read_config().context_captures


def apply_run_diagnostic_policy(
    run: AgentRun,
    settings: ContextCaptureSettings,
    *,
    now: datetime | None = None,
) -> AgentRun:
    """Return a copy whose model_requests follow the Knowledge capture policy."""

    moment = now or datetime.now(timezone.utc).replace(microsecond=0)
    updated = run.model_copy(deep=True)
    updated.model_requests = [
        apply_capture_policy(item, settings, now=moment) for item in updated.model_requests
    ]
    return updated


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
    discarded_mode = settings.redaction_mode == "discard"
    drop_content = discarded_mode or expired
    gaps = _policy_gaps(capture.capture_gaps, discarded_mode, expired)

    if drop_content:
        return capture.model_copy(
            update={
                "instructions": None,
                "messages": [],
                "generation_settings": {},
                "retrieved_material": [],
                "http_payload": None,
                "capture_gaps": gaps,
                "redaction_mode": settings.redaction_mode,
                "retention_seconds": settings.retention_seconds,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "retained": False,
                "redacted": False,
                "discarded": discarded_mode,
                "expired": expired,
                "redacted_fields": [],
            }
        )

    redacted_fields: list[str] = []
    instructions, redacted_fields = _redact_text(capture.instructions, redacted_fields)
    messages, redacted_fields = _redact_value(capture.messages, redacted_fields)
    generation_settings, redacted_fields = _redact_value(
        capture.generation_settings, redacted_fields
    )
    retrieved_material, redacted_fields = _redact_value(
        capture.retrieved_material, redacted_fields
    )
    http_payload, redacted_fields = _redact_value(capture.http_payload, redacted_fields)
    unique = list(dict.fromkeys(redacted_fields))
    return capture.model_copy(
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
