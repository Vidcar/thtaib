"""Local context-capture redaction. Not a retrieval index.

The detector is a fixed pattern list. It is incomplete: unknown formats,
obfuscation, and novel credential shapes are missed. A clean scan is not
proof that no secret is present. Do not claim perfect secret detection.
"""

from __future__ import annotations

import json
import re
from typing import Any

from workbench_backend.knowledge.schemas import RedactionMode

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api_key", re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([^\s\"']+)")),
    ("secret", re.compile(r"(?i)((?<!redact_)secret(?:_value)?\s*[=:]\s*)([^\s\"']+)")),
    ("password", re.compile(r"(?i)(password\s*[=:]\s*)([^\s\"']+)")),
    ("token", re.compile(r"(?i)((?<![a-z])token\s*[=:]\s*)([^\s\"']+)")),
    ("bearer", re.compile(r"(?i)(authorization:\s*bearer\s+)([^\s\"']+)")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("hf_token", re.compile(r"\bhf_[A-Za-z0-9]{16,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")),
    ("secret_value", re.compile(r"\bSECRET_VALUE\b")),
)

REDACTION_MARK = "[REDACTED]"

DETECTOR_LIMITATIONS = (
    "Pattern-based detector only (Knowledge capture patterns). "
    "It is incomplete: unknown formats and obfuscation are missed. "
    "A clean scan is not proof that no secret is present. "
    "Tests use synthetic credentials only."
)


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


def text_changes_under_redaction(content: str) -> bool:
    """True when redact_secrets would change the text (unredacted hit)."""

    stored, _, _ = apply_redaction(content, "redact_secrets")
    return stored != content


def redact_structured(value: Any, mode: RedactionMode) -> tuple[Any, bool, list[str]]:
    """Walk JSON-like values and apply the same text redaction to strings."""

    if mode == "discard":
        return None, False, []
    if mode == "retain":
        return value, False, []

    fields: list[str] = []

    def walk(item: Any) -> Any:
        if isinstance(item, str):
            stored, _, names = apply_redaction(item, "redact_secrets")
            fields.extend(names)
            return stored
        if isinstance(item, dict):
            return {key: walk(child) for key, child in item.items()}
        if isinstance(item, list):
            return [walk(child) for child in item]
        if isinstance(item, tuple):
            return [walk(child) for child in item]
        return item

    redacted_value = walk(value)
    unique = list(dict.fromkeys(fields))
    return redacted_value, bool(unique), unique


def structured_has_unredacted_secret(value: Any) -> bool:
    """Walk JSON-like values and test each string on its own."""

    if isinstance(value, str):
        return text_changes_under_redaction(value)
    if isinstance(value, dict):
        return any(structured_has_unredacted_secret(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return any(structured_has_unredacted_secret(child) for child in value)
    return False


def structured_text(value: Any) -> str:
    """Stable scan surface for JSON-like values."""

    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, sort_keys=True)
