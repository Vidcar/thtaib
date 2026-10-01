"""Opt-in inert runtime workflows, imported through the native knowledge owner."""
from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workbench_backend.errors import KnowledgeError
from workbench_backend.knowledge.packages import parse_skill_markdown, parse_skill_requirements, read_skill_package
from workbench_backend.knowledge.schemas import KnowledgeScope, SkillPackageImportRequest, SkillResource

SKILL_IDS = ("project-change", "failure-diagnosis", "windows-execution", "verify-delivery",
    "browser-validation", "desktop-validation", "evidence-research", "delegate-review", "memory-curation")
PACK_ROOT = Path(__file__).parent / "runtime_skills"


class BundledSkill(BaseModel):
    id: str
    name: str
    description: str
    content: str
    sha256: str
    resources: list[SkillResource]
    required_tools: list[str]
    required_connections: list[str]
    requires_project: bool


class BundledSkillInstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: KnowledgeScope = "user"
    scope_id: str | None = None


def bundled_skills() -> list[BundledSkill]:
    results = []
    for slug in SKILL_IDS:
        content, files = read_skill_package(PACK_ROOT / slug)
        name, description = parse_skill_markdown(content)
        results.append(BundledSkill(id=slug, name=name, description=description, content=content,
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            resources=[SkillResource(path=path, size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                for path, raw in sorted(files.items()) if path != "SKILL.md"],
            **parse_skill_requirements(content)))
    return results


def install_bundled_skill(knowledge, slug: str, request: BundledSkillInstallRequest):
    if slug not in SKILL_IDS:
        raise KnowledgeError("This bundled skill does not exist.", code="bundled_skill_missing", status_code=404)
    source = str((PACK_ROOT / slug).resolve())
    # Installation is idempotent and never overwrites a person's edits or
    # selects it for a chat. Existing accepted work keeps its frozen version.
    with knowledge.admission_lock():
        knowledge._require_scope(request.scope, request.scope_id)
        existing = next((entry for entry in knowledge.list_entries()
            if entry.kind == "skill" and (entry.scope, entry.scope_id) == (request.scope, request.scope_id)
            and entry.package_source == source), None)
        if existing is not None:
            return existing
        return knowledge.import_skill(SkillPackageImportRequest(source_path=source,
            scope=request.scope, scope_id=request.scope_id))
