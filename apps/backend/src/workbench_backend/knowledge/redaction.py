"""Local context-capture redaction. Not a retrieval index."""

from __future__ import annotations

import re

from workbench_backend.knowledge.schemas import RedactionMode

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api_key", re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)(\S+)")),
    ("secret", re.compile(r"(?i)((?<!redact_)secret(?:_value)?\s*[=:]\s*)(\S+)")),
    ("password", re.compile(r"(?i)(password\s*[=:]\s*)(\S+)")),
    ("token", re.compile(r"(?i)((?<![a-z])token\s*[=:]\s*)(\S+)")),
    ("bearer", re.compile(r"(?i)(authorization:\s*bearer\s+)(\S+)")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("hf_token", re.compile(r"\bhf_[A-Za-z0-9]{16,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")),
    ("secret_value", re.compile(r"\bSECRET_VALUE\b")),
)

REDACTION_MARK = "[REDACTED]"


def apply_redaction(content: str, mode: RedactionMode) -> tuple[str | None, bool, list[str]]:
    """Return (stored_content, redacted, redacted_fields)."""

    if mode == "discard":
        return None, False, []
    if mode == "retain":
        return content, False, []

    redacted_fields: list[str] = []
    next_text = content
    for name, pattern in SECRET_PATTERNS:
        if name in {"private_key", "hf_token", "openai_key", "secret_value"}:
            replaced, count = pattern.subn(REDACTION_MARK, next_text)
        else:
            replaced, count = pattern.subn(rf"\1{REDACTION_MARK}", next_text)
        if count:
            redacted_fields.append(name)
            next_text = replaced
    return next_text, bool(redacted_fields), redacted_fields
