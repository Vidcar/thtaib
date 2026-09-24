"""Conservative extraction of response recipes from a pinned model card.

Model cards contain prose, examples, and sometimes copied upstream guidance.
Only labelled sampling recommendations become selectable recipes. Nothing in
this module turns a recommendation into an active request default.
"""

from __future__ import annotations

import math
import re
from typing import Any


MAX_CARD_BYTES = 2 * 1024 * 1024

# (minimum, maximum, inclusive minimum, integral value). Bounds are narrower
# than arbitrary user-request pass-through because these are imported values.
_SAMPLING_FIELDS: dict[str, tuple[float, float, bool, bool]] = {
    "temperature": (0, 100, True, False),
    "top_p": (0, 1, False, False),
    "top_k": (0, 1_000_000, True, True),
    "min_p": (0, 1, True, False),
    "typical_p": (0, 1, False, False),
    "repetition_penalty": (0, 100, False, False),
    "repeat_penalty": (0, 100, False, False),
    "presence_penalty": (-2, 2, True, False),
    "frequency_penalty": (-2, 2, True, False),
}


def normalize_sampling_value(key: str, value: Any) -> int | float | None:
    """Validate a publisher/card sampler without accepting bool or NaN.

    The key may be a Hugging Face name such as ``repetition_penalty`` or its
    llama.cpp request equivalent. Callers map that key after validation.
    """
    spec = _SAMPLING_FIELDS.get(key)
    if spec is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    minimum, maximum, inclusive_minimum, integral = spec
    if (isinstance(value, float) and not math.isfinite(value)) or value < minimum or (value == minimum and not inclusive_minimum) or value > maximum:
        return None
    if integral:
        return int(value) if isinstance(value, int) or value.is_integer() else None
    return value


_MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_HTML_HEADING = re.compile(r"^\s*<h[1-6][^>]*>(.+?)</h[1-6]>\s*$", re.I)
_BOLD_HEADING = re.compile(r"^\s*(?:<b>|<strong>)(.+?)(?:</b>|</strong>)\s*$", re.I)
_MARKDOWN_BOLD_HEADING = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")
_BULLET = re.compile(r"^\s*[-*]\s+(.{3,160}?):\s*(.+?)\s*$")
_ASSIGNMENT = re.compile(r"^([a-z][a-z0-9_]*)\s*=\s*(\S+)$", re.I)
_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$", re.I)


def _heading(line: str) -> str | None:
    for pattern in (_MARKDOWN_HEADING, _HTML_HEADING, _BOLD_HEADING, _MARKDOWN_BOLD_HEADING):
        match = pattern.match(line)
        if match:
            return re.sub(r"<[^>]+>", "", match[1]).strip().rstrip(":").strip()
    return None


def _is_recommendation_heading(value: str) -> bool:
    lowered = value.casefold()
    subject = re.search(r"\b(?:model|sampling|generation)\s+(?:default\s+)?(?:settings|parameters|recommendations?)\b", lowered)
    recommendation = re.search(r"\b(?:suggested|recommended|recommendations?)\b", lowered)
    return bool(subject and recommendation)


def _label(label: str) -> tuple[str, str] | None:
    lowered = label.casefold()
    if "non-thinking" in lowered or "non thinking" in lowered or "instruct" in lowered:
        return "Non-thinking", "off"
    if "thinking" not in lowered:
        return None
    if "coding" in lowered or "code" in lowered or "precise" in lowered:
        return "Precise coding", "on"
    if "general" in lowered:
        return "General thinking", "on"
    return "Thinking", "on"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:48]


def _recipe_line(line: str) -> tuple[str, str, dict[str, int | float], list[str]] | None:
    match = _BULLET.match(line)
    if not match:
        return None
    labelled = _label(match[1])
    if labelled is None:
        return None
    settings: dict[str, int | float] = {}
    notes: list[str] = []
    for raw in match[2].split(","):
        part = raw.strip().strip("` ")
        assignment = _ASSIGNMENT.fullmatch(part)
        if not assignment:
            # A partly parsed recommendation is unsafe to offer as a recipe.
            return None
        key, literal = assignment[1].casefold(), assignment[2].rstrip("`.;")
        if key not in _SAMPLING_FIELDS:
            # A selectable recipe must not imply that an unsupported part of
            # the card's recommended combination will be applied.
            return None
        if not _NUMBER.fullmatch(literal):
            return None
        try:
            parsed_value = float(literal)
        except (ValueError, OverflowError):
            return None
        value = normalize_sampling_value(key, parsed_value)
        if value is None:
            return None
        canonical = "repeat_penalty" if key == "repetition_penalty" else key
        if canonical in settings and settings[canonical] != value:
            return None
        settings[canonical] = value
    if len(settings) < 2:
        return None
    return labelled[0], labelled[1], settings, notes


def parse_model_card_recipes(
    card_text: str, *, repo_id: str, revision: str, sha256: str,
) -> list[dict[str, Any]]:
    """Return only unambiguous, selectable response recipes from a README.

    The caller verifies the README's hash against the bundle file record. The
    card revision and hash are part of each ID so an old selection cannot be
    silently applied to a new version of the card.
    """
    if (not isinstance(card_text, str) or len(card_text.encode("utf-8")) > MAX_CARD_BYTES
        or not re.fullmatch(r"[0-9a-f]{40}", revision, re.I)
        or not re.fullmatch(r"[0-9a-f]{64}", sha256, re.I)):
        return []
    recipes: dict[str, dict[str, Any]] = {}
    ambiguous: set[str] = set()
    section: str | None = None
    for line in card_text.splitlines():
        heading = _heading(line)
        if heading is not None:
            section = heading if _is_recommendation_heading(heading) else None
            continue
        if section is None:
            continue
        bullet = _BULLET.match(line)
        labelled = _label(bullet[1]) if bullet else None
        parsed = _recipe_line(line)
        if parsed is None:
            if labelled is not None:
                # Another recommendation for the same mode is present but
                # cannot be applied in full. Suppress even an earlier valid
                # bullet rather than choosing one version arbitrarily.
                ambiguous.add(labelled[0].casefold())
            continue
        name, reasoning, settings, notes = parsed
        candidate_id = f"card-{revision[:12]}-{sha256[:12]}-{_slug(section)}-{_slug(name)}"
        candidate = {
            "id": candidate_id,
            "name": name,
            "per_request": settings,
            "reasoning": reasoning,
            "source_repo_id": repo_id,
            "source_revision": revision,
            "card_sha256": sha256,
            "section": section,
            "notes": notes,
        }
        # A card can restate identical guidance in multiple sections. Keep one
        # recipe. If it gives different values for the same labelled mode,
        # neither recommendation is safe to select automatically.
        mode_key = name.casefold()
        previous = recipes.get(mode_key)
        if previous is None:
            recipes[mode_key] = candidate
        elif (previous["per_request"], previous["reasoning"]) != (settings, reasoning):
            ambiguous.add(mode_key)
    return [recipe for key, recipe in recipes.items() if key not in ambiguous]
