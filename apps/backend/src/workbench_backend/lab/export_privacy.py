"""Shareable case-export sanitization (LAB-003 / Issue #64).

Uses the same Knowledge capture detector as context captures. The detector
is incomplete; a clean flag is not proof that no secret is present.
"""

from __future__ import annotations

from pathlib import Path

from workbench_backend.errors import LabError
from workbench_backend.knowledge.redaction import (
    DETECTOR_LIMITATIONS,
    apply_redaction,
    redact_structured,
    structured_has_unredacted_secret,
    text_changes_under_redaction,
)
from workbench_backend.lab.schemas import CaseExport, LabCase, SnapshotManifest

EXPORT_NOTE = (
    "Shareable export applies the Knowledge capture detector to task text, "
    "fixtures, ordinary included files, and the returned payload. Filename "
    "exclusions are not sufficient. The detector is incomplete."
)


def build_case_export(case: LabCase, snapshot: SnapshotManifest) -> CaseExport:
    """Sanitize or block a shareable export. Never return scan-clean + secrets."""

    files = _included_text_files(snapshot)
    original_hits = _scan_surfaces(case, snapshot, files)
    sanitized_case, case_fields = _sanitize_case(case)
    sanitized_files, file_fields = _sanitize_files(files)
    payload = CaseExport(
        case=sanitized_case,
        snapshot=snapshot,
        secret_scan_clean=not original_hits,
        export_status="clean" if not original_hits else "sanitized",
        sanitized_fields=list(dict.fromkeys([*case_fields, *file_fields])),
        exported_files=sanitized_files,
        detector_limitations=DETECTOR_LIMITATIONS,
        note=EXPORT_NOTE,
    )
    residual = _residual_hits(payload)
    if residual:
        raise LabError(
            "Case export blocked: detectable unsafe content remained after sanitization.",
            code="export_blocked",
            status_code=409,
            details={
                "export_status": "blocked",
                "hits": residual,
                "detector_limitations": DETECTOR_LIMITATIONS,
            },
        )
    return payload


def _included_text_files(snapshot: SnapshotManifest) -> dict[str, str]:
    tree = Path(snapshot.tree_path)
    files: dict[str, str] = {}
    if not tree.is_dir():
        return files
    for item in snapshot.included_files:
        path = tree / item.path
        if path.is_file():
            files[item.path] = path.read_text(encoding="utf-8", errors="replace")
    return files


def _scan_surfaces(
    case: LabCase,
    snapshot: SnapshotManifest,
    files: dict[str, str],
) -> list[str]:
    hits: list[str] = []
    if case.task and text_changes_under_redaction(case.task):
        hits.append("task")
    if case.system_prompt and text_changes_under_redaction(case.system_prompt):
        hits.append("system_prompt")
    if structured_has_unredacted_secret(case.tool_fixtures):
        hits.append("tool_fixtures")
    if structured_has_unredacted_secret(case.model_dump()):
        if "case" not in hits:
            hits.append("case")
    if structured_has_unredacted_secret(snapshot.model_dump()):
        hits.append("snapshot_manifest")
    for path, content in files.items():
        if text_changes_under_redaction(content):
            hits.append(f"snapshot_file:{path}")
    return hits


def _sanitize_case(case: LabCase) -> tuple[LabCase, list[str]]:
    fields: list[str] = []
    if case.task and text_changes_under_redaction(case.task):
        fields.append("task")
    if case.system_prompt and text_changes_under_redaction(case.system_prompt):
        fields.append("system_prompt")
    if structured_has_unredacted_secret(case.tool_fixtures):
        fields.append("tool_fixtures")
    payload = case.model_dump()
    sanitized, changed, _ = redact_structured(payload, "redact_secrets")
    if changed and "case" not in fields:
        fields.append("case")
    if not isinstance(sanitized, dict):
        return case, fields
    return LabCase.model_validate(sanitized), list(dict.fromkeys(fields))


def _sanitize_files(files: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    sanitized: dict[str, str] = {}
    fields: list[str] = []
    for path, content in files.items():
        stored, changed, _ = apply_redaction(content, "redact_secrets")
        sanitized[path] = stored if isinstance(stored, str) else ""
        if changed:
            fields.append(f"snapshot_file:{path}")
    return sanitized, fields


def _residual_hits(payload: CaseExport) -> list[str]:
    hits: list[str] = []
    if structured_has_unredacted_secret(payload.case.model_dump()):
        hits.append("case")
    if structured_has_unredacted_secret(payload.snapshot.model_dump()):
        hits.append("snapshot_manifest")
    for path, content in payload.exported_files.items():
        if text_changes_under_redaction(content):
            hits.append(f"snapshot_file:{path}")
    if structured_has_unredacted_secret(payload.sanitized_fields):
        hits.append("sanitized_fields")
    return hits
