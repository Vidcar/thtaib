"""STATE-005 / AGT-004: materialize selected memory and skill versions.

Official Deep Agents 0.7.15 owns always-load (``memory=`` / MemoryMiddleware)
and progressive disclosure (``skills=`` / SkillsMiddleware). This module is
thin glue: it writes derived files onto the existing CompositeBackend and
returns the official kwargs. It is not a second knowledge store and not RAG.

Sources consulted 2026-09-20 for pinned ``deepagents==0.7.15``:

- ``deepagents/graph.py`` (``create_deep_agent(..., memory=, skills=)``)
- ``deepagents/middleware/memory.py`` (file sources; missing file skipped)
- ``deepagents/middleware/skills.py`` (directories of ``SKILL.md``; invalid
  frontmatter skipped; ``name`` must match the directory)
- ``deepagents/backends/composite.py`` (``upload_files`` / longest prefix)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml
from pydantic import BaseModel

from workbench_backend.errors import HarnessError
from workbench_backend.knowledge.schemas import KnowledgeKind, KnowledgeVersion

MEMORIES_PREFIX = "/memories/"
SKILLS_PREFIX = "/skills/"
SKILLS_SOURCE = "/skills/"
SKILL_MARKDOWN_NAME = "SKILL.md"
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024
SKILL_MATERIALIZE_INVALID = "skill_materialize_invalid"
SKILL_NAME_COLLISION = "skill_name_collision"
KNOWLEDGE_MATERIALIZE_FAILED = "knowledge_materialize_failed"
MEMORY_EDIT_GAP = "memory edits are run-local; not durable knowledge"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_INVALID_SLUG_CHARS = re.compile(r"[^a-z0-9-]+")


class MaterializedKnowledgeFact(BaseModel):
    version_id: str
    kind: KnowledgeKind
    path: str


@dataclass(frozen=True)
class KnowledgeMaterializePlan:
    facts: list[MaterializedKnowledgeFact] = field(default_factory=list)
    uploads: list[tuple[str, bytes]] = field(default_factory=list)
    memory_sources: list[str] = field(default_factory=list)
    skills_sources: list[str] = field(default_factory=list)

    @property
    def has_memory(self) -> bool:
        return bool(self.memory_sources)

    @property
    def has_skills(self) -> bool:
        return bool(self.skills_sources)

    @property
    def has_knowledge_routes(self) -> bool:
        return self.has_memory or self.has_skills


def knowledge_routes_selected(
    memory_version_refs: list[str] | None = None,
    skill_version_refs: list[str] | None = None,
) -> bool:
    return bool(memory_version_refs or skill_version_refs)


def memory_file_path(scope: str, entry_id: str) -> str:
    return f"{MEMORIES_PREFIX}{scope}/{entry_id}.md"


def skill_file_path(slug: str) -> str:
    return f"{SKILLS_PREFIX}{slug}/{SKILL_MARKDOWN_NAME}"


def skill_slug_from_entry_id(entry_id: str) -> str:
    """Hyphenate an entry id into an Agent Skills directory/name slug.

    0.7.15 SkillsMiddleware warns (and still loads) when ``name`` has
    underscores or does not match the directory. Glue hyphenates so a
    selected skill is not silently dropped, and fails closed if the result
    is not a valid slug.
    """

    lowered = (entry_id or "").strip().lower().replace("_", "-")
    cleaned = _INVALID_SLUG_CHARS.sub("-", lowered)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    slug = cleaned.strip("-")
    valid, error = _validate_skill_slug(slug)
    if not valid:
        raise HarnessError(
            f"Selected skill entry {entry_id!r} cannot be materialized as "
            f"SKILL.md: {error}.",
            code=SKILL_MATERIALIZE_INVALID,
            status_code=400,
            details={"entry_id": entry_id, "slug": slug},
        )
    return slug


def wrap_skill_markdown(slug: str, body: str, display_name: str | None) -> str:
    """Write Agent Skills frontmatter so 0.7.15 does not skip the file.

    Existing valid frontmatter is kept except ``name``, which is forced to
    the directory slug. ``description`` is taken from existing frontmatter,
    then ``display_name``, then the first body line, capped at 1024.
    """

    rest = body or ""
    extra: dict[str, Any] = {}
    existing_description: str | None = None
    match = _FRONTMATTER_RE.match(rest)
    if match:
        try:
            parsed = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            parsed = None
        if isinstance(parsed, dict):
            extra = {key: value for key, value in parsed.items() if key not in {"name", "description"}}
            raw_description = str(parsed.get("description") or "").strip()
            existing_description = raw_description or None
            rest = rest[match.end() :]
    description = _skill_description(existing_description, display_name, rest)
    payload: dict[str, Any] = {"name": slug, "description": description}
    payload.update(extra)
    dumped = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{dumped}\n---\n\n{rest.lstrip('\n')}"


def plan_knowledge_materialization(
    versions: list[KnowledgeVersion],
    display_names: dict[str, str | None] | None = None,
) -> KnowledgeMaterializePlan:
    """Build derived ``/memories/`` and ``/skills/`` files for selected versions.

    Protected instructions are not materialized; they stay in
    ``system_prompt=``. Fail closed on an unsanitizable slug or a selected
    skill name collision so SkillsMiddleware cannot silently drop one.
    """

    names = display_names or {}
    facts: list[MaterializedKnowledgeFact] = []
    uploads: list[tuple[str, bytes]] = []
    memory_sources: list[str] = []
    skill_slugs: dict[str, str] = {}
    for version in versions:
        if version.kind == "memory":
            path = memory_file_path(version.scope, version.entry_id)
            facts.append(
                MaterializedKnowledgeFact(
                    version_id=version.id,
                    kind="memory",
                    path=path,
                )
            )
            uploads.append((path, version.content.encode("utf-8")))
            memory_sources.append(path)
            continue
        if version.kind != "skill":
            continue
        slug = skill_slug_from_entry_id(version.entry_id)
        owner = skill_slugs.get(slug)
        if owner is not None:
            raise HarnessError(
                f"Selected skills {owner!r} and {version.entry_id!r} materialize "
                f"to the same SKILL.md slug {slug!r}.",
                code=SKILL_NAME_COLLISION,
                status_code=400,
                details={"slug": slug, "entry_ids": [owner, version.entry_id]},
            )
        skill_slugs[slug] = version.entry_id
        path = skill_file_path(slug)
        wrapped = wrap_skill_markdown(slug, version.content, names.get(version.entry_id))
        facts.append(
            MaterializedKnowledgeFact(
                version_id=version.id,
                kind="skill",
                path=path,
            )
        )
        uploads.append((path, wrapped.encode("utf-8")))
    skills_sources = [SKILLS_SOURCE] if skill_slugs else []
    return KnowledgeMaterializePlan(
        facts=facts,
        uploads=uploads,
        memory_sources=memory_sources,
        skills_sources=skills_sources,
    )


def official_agent_kwargs(plan: KnowledgeMaterializePlan) -> dict[str, list[str]]:
    """Return ``memory=`` / ``skills=`` only when that kind is selected.

    0.7.15 constructs the middleware whenever the list is not ``None``,
    including ``[]``. Do not pass an empty list.
    """

    kwargs: dict[str, list[str]] = {}
    if plan.memory_sources:
        kwargs["memory"] = list(plan.memory_sources)
    if plan.skills_sources:
        kwargs["skills"] = list(plan.skills_sources)
    return kwargs


def materialize_onto_backend(backend: Any, plan: KnowledgeMaterializePlan) -> None:
    """Upload derived files. Fail closed if official download would skip them."""

    if not plan.uploads:
        return
    upload_files = getattr(backend, "upload_files", None)
    if upload_files is None:
        raise HarnessError(
            "Knowledge routes need a backend that implements upload_files.",
            code=KNOWLEDGE_MATERIALIZE_FAILED,
            status_code=409,
        )
    responses = upload_files(list(plan.uploads))
    failed: list[str] = []
    for path, response in zip((item[0] for item in plan.uploads), responses, strict=False):
        error = getattr(response, "error", None)
        if error:
            failed.append(f"{path}: {error}")
    if failed:
        raise HarnessError(
            "Selected knowledge versions could not be materialized onto the "
            f"harness backend: {'; '.join(failed)}.",
            code=KNOWLEDGE_MATERIALIZE_FAILED,
            status_code=409,
            details={"failed": failed},
        )


def is_knowledge_route_path(virtual_path: str) -> bool:
    normalized = _normalize_virtual_path(virtual_path)
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in (MEMORIES_PREFIX, SKILLS_PREFIX)
    )


def is_memory_route_path(virtual_path: str) -> bool:
    normalized = _normalize_virtual_path(virtual_path)
    return normalized == MEMORIES_PREFIX.rstrip("/") or normalized.startswith(MEMORIES_PREFIX)


def _normalize_virtual_path(virtual_path: str) -> str:
    if not virtual_path:
        return "/"
    return virtual_path if virtual_path.startswith("/") else f"/{virtual_path.lstrip('/')}"


def _validate_skill_slug(slug: str) -> tuple[bool, str]:
    if not slug:
        return False, "name is required"
    if len(slug) > MAX_SKILL_NAME_LENGTH:
        return False, "name exceeds 64 characters"
    if slug.startswith("-") or slug.endswith("-") or "--" in slug:
        return False, "name must be lowercase alphanumeric with single hyphens only"
    for char in slug:
        if char == "-":
            continue
        if (char.isalpha() and char.islower()) or char.isdigit():
            continue
        return False, "name must be lowercase alphanumeric with single hyphens only"
    return True, ""


def _skill_description(
    existing: str | None,
    display_name: str | None,
    body: str,
) -> str:
    candidates = (
        (existing or "").strip(),
        (display_name or "").strip(),
        _first_description_line(body),
    )
    for candidate in candidates:
        if candidate:
            return candidate[:MAX_SKILL_DESCRIPTION_LENGTH]
    raise HarnessError(
        "Selected skill has no description after wrapping SKILL.md.",
        code=SKILL_MATERIALIZE_INVALID,
        status_code=400,
    )


def _first_description_line(body: str) -> str:
    for line in (body or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        return stripped
    return ""
