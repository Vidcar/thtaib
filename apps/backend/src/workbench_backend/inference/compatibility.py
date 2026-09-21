"""MOD-006 compatibility records with separate provenance categories.

Unverified is not incompatible and is not a supported-capability claim.
Compatibility records remain distinct from observed capability evidence.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from workbench_backend.errors import ManagerError
from workbench_backend.inference.ids import new_id
from workbench_backend.inference.schemas import ModelBundle
from workbench_backend.paths import WorkbenchPaths

PACK_RECORDS_DIR = Path(__file__).resolve().parents[1] / "managed" / "compatibility"

PROVENANCE_CATEGORIES: tuple[str, str, str] = (
    "publisher_guidance",
    "tested_adjustments",
    "user_overrides",
)

UNVERIFIED_NOTE = (
    "Unverified is not incompatible and is not a supported-capability claim. "
    "Testing is not a prerequisite to model use."
)


class CompatibilitySupportStatus(str, Enum):
    unverified = "unverified"
    known_incompatible = "known_incompatible"
    tested = "tested"


class SubjectKind(str, Enum):
    unfamiliar = "unfamiliar"
    model_family = "model_family"
    bundle = "bundle"


class ProvenanceCategory(str, Enum):
    publisher_guidance = "publisher_guidance"
    tested_adjustments = "tested_adjustments"
    user_overrides = "user_overrides"


class CompatibilitySubject(BaseModel):
    kind: SubjectKind
    selector: str
    display_name: str | None = None


class ProvenanceItem(BaseModel):
    id: str
    category: ProvenanceCategory
    claim: str
    source: str | None = None
    evidence_ref: str | None = None
    note: str | None = None


class CompatibilityProvenance(BaseModel):
    publisher_guidance: list[ProvenanceItem] = Field(default_factory=list)
    tested_adjustments: list[ProvenanceItem] = Field(default_factory=list)
    user_overrides: list[ProvenanceItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def categories_stay_separate(self) -> CompatibilityProvenance:
        _assert_category(self.publisher_guidance, ProvenanceCategory.publisher_guidance)
        _assert_category(self.tested_adjustments, ProvenanceCategory.tested_adjustments)
        _assert_category(self.user_overrides, ProvenanceCategory.user_overrides)
        return self


class CompatibilityRecord(BaseModel):
    schema_version: Literal[1] = 1
    kind: Literal["compatibility-record"] = "compatibility-record"
    id: str
    record_version: int = 1
    product: Literal["Local AI Workbench"] = "Local AI Workbench"
    support_status: CompatibilitySupportStatus
    subject: CompatibilitySubject
    requirements: list[str] = Field(default_factory=list)
    supported_capabilities: list[str] = Field(default_factory=list)
    supported_controls: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    validation_evidence: list[str] = Field(default_factory=list)
    provenance: CompatibilityProvenance = Field(default_factory=CompatibilityProvenance)
    excluded: bool = False
    incompatible: bool = False
    catalogue_claim: Literal["not_verified"] = "not_verified"
    note: str = UNVERIFIED_NOTE

    @model_validator(mode="after")
    def unverified_is_never_incompatible(self) -> CompatibilityRecord:
        if self.support_status is CompatibilitySupportStatus.unverified:
            if self.incompatible or self.excluded:
                raise ValueError("Unverified records must not be marked incompatible or excluded.")
        if self.support_status is CompatibilitySupportStatus.known_incompatible:
            object.__setattr__(self, "incompatible", True)
        elif self.support_status is not CompatibilitySupportStatus.known_incompatible:
            object.__setattr__(self, "incompatible", False)
        return self


class CompatibilityAssessment(BaseModel):
    support_status: CompatibilitySupportStatus
    incompatible: bool
    excluded: bool
    usable: bool
    unverified_is_not_incompatible: Literal[True] = True
    provenance_categories: list[str] = Field(default_factory=lambda: list(PROVENANCE_CATEGORIES))
    provenance: CompatibilityProvenance
    record: CompatibilityRecord
    catalogue_claim: Literal["not_verified"] = "not_verified"
    note: str = UNVERIFIED_NOTE


class CompatibilityAssessRequest(BaseModel):
    bundle_id: str | None = None
    selector: str | None = None
    display_name: str | None = None


class UserOverrideRequest(BaseModel):
    claim: str
    source: str | None = "user"
    note: str | None = None


class CompatibilityService:
    """Load pack records and LocalAppData user overrides. Categories stay separate."""

    def __init__(self, paths: WorkbenchPaths, *, pack_dir: Path | None = None) -> None:
        self.paths = paths.ensure()
        self.pack_dir = pack_dir or PACK_RECORDS_DIR
        self.overrides_path = self.paths.state / "compatibility" / "overrides.json"

    def list_records(self) -> list[CompatibilityRecord]:
        records = [_load_pack_record(path) for path in _pack_record_paths(self.pack_dir)]
        return [self._with_local_overrides(record) for record in records]

    def get_record(self, record_id: str) -> CompatibilityRecord:
        for record in self.list_records():
            if record.id == record_id:
                return record
        raise ManagerError(
            "Unknown compatibility record",
            code="compatibility_missing",
            status_code=404,
        )

    def assess_bundle(self, bundle: ModelBundle) -> CompatibilityAssessment:
        return self.assess(
            selector=bundle.id,
            display_name=bundle.display_name,
            extra_selectors=(bundle.id, bundle.display_name),
        )

    def assess(
        self,
        *,
        selector: str | None = None,
        display_name: str | None = None,
        extra_selectors: tuple[str, ...] = (),
    ) -> CompatibilityAssessment:
        needles = {
            value.strip().lower()
            for value in (selector, display_name, *extra_selectors)
            if value and value.strip()
        }
        match = None
        for record in self.list_records():
            candidates = {
                record.subject.selector.lower(),
                (record.subject.display_name or "").lower(),
                record.id.lower(),
            }
            if needles & {item for item in candidates if item}:
                match = record
                break
        if match is None:
            match = _unverified_record(selector=selector or display_name or "unfamiliar")
        return _assessment_for(match)

    def add_user_override(self, record_id: str, request: UserOverrideRequest) -> CompatibilityRecord:
        record = self.get_record(record_id)
        if record.id.startswith("compat_unverified_synth_"):
            raise ManagerError(
                "Synthesized unverified assessments are not stored pack records.",
                code="compatibility_override_unbound",
                status_code=409,
            )
        item = ProvenanceItem(
            id=new_id("cpo"),
            category=ProvenanceCategory.user_overrides,
            claim=request.claim,
            source=request.source,
            note=request.note or "User override. Not publisher guidance and not a tested adjustment.",
        )
        stored = self._read_overrides()
        stored.setdefault(record_id, []).append(item.model_dump(mode="json"))
        self._write_overrides(stored)
        return self.get_record(record_id)

    def _with_local_overrides(self, record: CompatibilityRecord) -> CompatibilityRecord:
        extras = self._read_overrides().get(record.id, [])
        if not extras:
            return record
        merged = list(record.provenance.user_overrides)
        seen = {item.id for item in merged}
        for raw in extras:
            item = ProvenanceItem.model_validate(raw)
            if item.category is not ProvenanceCategory.user_overrides:
                continue
            if item.id in seen:
                continue
            merged.append(item)
            seen.add(item.id)
        return record.model_copy(
            update={
                "provenance": record.provenance.model_copy(update={"user_overrides": merged}),
                "record_version": record.record_version + len(extras),
            }
        )

    def _read_overrides(self) -> dict[str, list[dict[str, Any]]]:
        if not self.overrides_path.is_file():
            return {}
        raw = json.loads(self.overrides_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[dict[str, Any]]] = {}
        for key, value in raw.items():
            if isinstance(value, list):
                out[str(key)] = [item for item in value if isinstance(item, dict)]
        return out

    def _write_overrides(self, payload: dict[str, list[dict[str, Any]]]) -> None:
        self.overrides_path.parent.mkdir(parents=True, exist_ok=True)
        self.overrides_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _assert_category(items: list[ProvenanceItem], expected: ProvenanceCategory) -> None:
    for item in items:
        if item.category is not expected:
            raise ValueError(
                f"Provenance item {item.id} has category {item.category.value} "
                f"in the {expected.value} list. Categories must stay separate."
            )


def _pack_record_paths(pack_dir: Path) -> list[Path]:
    if not pack_dir.is_dir():
        return []
    return sorted(
        path
        for path in pack_dir.iterdir()
        if path.suffix == ".json" and not path.name.endswith(".schema.json")
    )


def _load_pack_record(path: Path) -> CompatibilityRecord:
    return CompatibilityRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _unverified_record(*, selector: str) -> CompatibilityRecord:
    return CompatibilityRecord(
        id=f"compat_unverified_synth_{selector}",
        support_status=CompatibilitySupportStatus.unverified,
        subject=CompatibilitySubject(
            kind=SubjectKind.unfamiliar,
            selector=selector,
            display_name=selector,
        ),
        excluded=False,
        incompatible=False,
        note=UNVERIFIED_NOTE,
    )


def _assessment_for(record: CompatibilityRecord) -> CompatibilityAssessment:
    incompatible = record.support_status is CompatibilitySupportStatus.known_incompatible
    excluded = bool(record.excluded) and incompatible
    if record.support_status is CompatibilitySupportStatus.unverified:
        incompatible = False
        excluded = False
    return CompatibilityAssessment(
        support_status=record.support_status,
        incompatible=incompatible,
        excluded=excluded,
        usable=not excluded,
        provenance=record.provenance,
        record=record,
        note=record.note,
    )
