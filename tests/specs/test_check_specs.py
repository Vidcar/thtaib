"""Regression tests for the specification checker against synthetic packs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "scripts"))
import check_specs  # noqa: E402

APPROVAL = "synthetic-test-approval-only"
COMMIT = "a" * 40


class SpecificationCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="spec-check-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in check_specs.CORE_FILES:
            self.write(name, "# Synthetic test fixture\n")
        self.write(".github/CODEOWNERS", "* @synthetic-owner\n")
        self.write("specs/architecture.md", '''# Architecture fixture

<a id="mod-001"></a>
### MOD-001: A synthetic rule

Required fixture behaviour.

**Acceptance:** Exercise the fixture behaviour.
''')
        self.write("specs/decisions/ADR-0004-slim-specification-pack.md", "# Synthetic adoption decision\n")
        self.write("specs/sources/archive.docx", "Synthetic archive bytes, not a Word document.")
        documents = []
        for path in sorted((self.root / "specs").rglob("*.md")):
            name = path.relative_to(self.root).as_posix()
            if name == "specs/architecture.md":
                kind, status = "specification", "accepted"
            elif name.startswith("specs/decisions/ADR-"):
                kind, status = "decision", "accepted"
            elif name.startswith("specs/templates/"):
                kind, status = "template", "informational"
            else:
                kind, status = "guide", "accepted"
            documents.append({"path": name, "kind": kind, "status": status,
                              "approval": None if status == "informational" else APPROVAL})
        self.catalog = {
            "schema_version": 2,
            "adoption": {"state": "accepted",
                         "decision": "specs/decisions/ADR-0004-slim-specification-pack.md",
                         "approval": {"reviewer": "synthetic-test-reviewer", "reference": APPROVAL, "date": "2026-09-19"}},
            "source_archive": {"path": "specs/sources/archive.docx",
                               "sha256": hashlib.sha256((self.root / "specs/sources/archive.docx").read_bytes()).hexdigest()},
            "documents": documents,
            "requirements": [{"id": "MOD-001", "document": "specs/architecture.md", "status": "planned",
                              "code": [], "tests": [], "evidence": []}],
        }
        self.mapping = {"schema_version": 1, "bindings": [{
            "id": "fixture-source", "state": "unbound", "path": None,
            "kind": "file", "owner_spec": "specs/architecture.md", "required_before": "Fixture implementation",
        }]}
        self.save()

    def write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def save(self) -> None:
        self.write("specs/catalog.json", json.dumps(self.catalog, indent=2))
        self.write("specs/repository-map.json", json.dumps(self.mapping, indent=2))

    def errors(self, **kwargs) -> str:
        return "\n".join(check_specs.validate_repo(self.root, **kwargs))

    def document(self, path: str = "specs/architecture.md") -> dict:
        return next(row for row in self.catalog["documents"] if row["path"] == path)

    @property
    def requirement(self) -> dict:
        return self.catalog["requirements"][0]

    def digest(self) -> str:
        block = check_specs.requirement_blocks((self.root / "specs/architecture.md").read_text())["MOD-001"]
        return check_specs.requirement_digest(block)

    def evidence_row(self, **overrides) -> dict:
        row = {"kind": "ci-smoke", "ref": "https://example.test/actions/runs/1", "commit": COMMIT,
               "date": "2026-09-19", "environment": "Synthetic unit-test fixture", "result": "passed",
               "requirement_sha256": self.digest()}
        row.update(overrides)
        return row

    def make_verified_fixture(self, **overrides) -> None:
        self.write("src/fixture.py", "VALUE = 1\n")
        self.write("tests/fixture_test.py", "assert 1 == 1\n")
        self.requirement.update({"status": "verified", "code": ["src/fixture.py"],
                                 "tests": ["tests/fixture_test.py"], "evidence": [self.evidence_row(**overrides)]})
        self.save()

    # Baseline and adoption

    def test_valid_fixture_passes(self):
        self.assertEqual(self.errors(), "")

    def test_pending_adoption_without_approval_passes(self):
        self.catalog["adoption"].update({"state": "pending", "approval": None})
        self.save()
        self.assertEqual(self.errors(), "")

    def test_accepted_adoption_needs_approval_metadata(self):
        self.catalog["adoption"]["approval"] = None
        self.save()
        self.assertIn("requires approval metadata", self.errors())

    def test_invalid_approval_date_fails(self):
        self.catalog["adoption"]["approval"]["date"] = "not-a-date"
        self.save()
        self.assertIn("approval date", self.errors())

    def test_adoption_decision_must_be_accepted(self):
        self.document("specs/decisions/ADR-0004-slim-specification-pack.md")["status"] = "draft"
        self.save()
        self.assertIn("adoption decision itself must be accepted", self.errors())

    def test_old_schema_version_is_rejected(self):
        self.catalog["schema_version"] = 1
        self.save()
        self.assertIn("unsupported manifest schema_version", self.errors())

    # Documents

    def test_accepted_document_needs_approval_reference(self):
        self.document()["approval"] = None
        self.save()
        self.assertIn("needs a real approval reference", self.errors())

    def test_placeholder_approval_fails(self):
        self.document()["approval"] = "REPLACE_WITH_REVIEW"
        self.save()
        self.assertIn("invalid approval", self.errors())

    def test_specification_cannot_be_informational(self):
        self.document().update({"status": "informational", "approval": None})
        self.save()
        self.assertIn("cannot be informational", self.errors())

    def test_new_spec_document_needs_registration(self):
        self.write("specs/new-spec.md", "# Not registered\n")
        self.assertIn("unregistered specification document", self.errors())

    def test_evidence_reports_need_no_registration(self):
        self.write("specs/evidence/2026-09-19-fixture.md", "# Report\n\nBody.\n")
        self.assertEqual(self.errors(), "")

    # Requirement definitions and references

    def test_duplicate_requirement_definition_fails(self):
        path = self.root / "specs/architecture.md"
        path.write_text(path.read_text() + path.read_text(), encoding="utf-8")
        self.assertIn("duplicate requirement definition", self.errors())

    def test_duplicate_catalogue_entry_fails(self):
        self.catalog["requirements"].append(dict(self.requirement))
        self.save()
        self.assertIn("duplicate catalogue requirement", self.errors())

    def test_missing_requirement_row_fails(self):
        self.catalog["requirements"] = []
        self.save()
        self.assertIn("requirement missing from catalogue", self.errors())

    def test_unknown_requirement_reference_fails(self):
        self.write("README.md", "# Fixture\n\nSee MOD-999.\n")
        self.assertIn("unknown requirement reference: MOD-999", self.errors())

    def test_question_deviation_and_hash_names_are_not_requirements(self):
        self.write("README.md", "# Fixture\n\nOQ-001, DEV-001 and a SHA-256 digest.\n")
        self.assertEqual(self.errors(), "")

    def test_requirement_outside_specification_fails(self):
        self.write("specs/commands.md", '<a id="mod-002"></a>\n### MOD-002: Misplaced\n\nText.\n\n**Acceptance:** x.\n')
        self.catalog["requirements"].append({"id": "MOD-002", "document": "specs/commands.md", "status": "planned",
                                             "code": [], "tests": [], "evidence": []})
        self.save()
        self.assertIn("outside a registered specification", self.errors())

    def test_missing_acceptance_check_fails(self):
        path = self.root / "specs/architecture.md"
        path.write_text(path.read_text().replace("**Acceptance:**", "**Notes:**"), encoding="utf-8")
        self.assertIn("has no acceptance check", self.errors())

    def test_mismatched_anchor_fails(self):
        path = self.root / "specs/architecture.md"
        path.write_text(path.read_text().replace('id="mod-001"', 'id="rule-one"'), encoding="utf-8")
        self.assertIn("anchor must match mod-001", self.errors())

    # Links

    def test_broken_file_link_fails(self):
        self.write("README.md", "[Missing](specs/missing.md)\n")
        self.assertIn("broken local link", self.errors())

    def test_broken_fragment_fails(self):
        self.write("README.md", "[Missing anchor](specs/architecture.md#no-such-anchor)\n")
        self.assertIn("missing Markdown anchor", self.errors())

    def test_explicit_and_heading_anchors_pass(self):
        self.write("README.md", "[Rule](specs/architecture.md#mod-001) [Top](specs/architecture.md#architecture-fixture)\n")
        self.assertEqual(self.errors(), "")

    def test_fenced_examples_are_not_live_links_or_ids(self):
        self.write("README.md", "# Fixture\n```text\n[Example](missing.md) MOD-999\n```\n")
        self.assertEqual(self.errors(), "")

    def test_relative_markdown_link_cannot_escape_repository(self):
        self.write("README.md", "[Outside](../outside.md)\n")
        self.assertIn("local link escapes the repository", self.errors())

    # Catalogue shape and pointers

    def test_invalid_status_enum_fails(self):
        self.requirement["status"] = "partial"
        self.save()
        self.assertIn("invalid status", self.errors())

    def test_unknown_json_field_is_not_silently_ignored(self):
        self.requirement["testz"] = []
        self.save()
        self.assertIn("expected keys", self.errors())

    def test_duplicate_json_keys_are_rejected(self):
        self.write("specs/catalog.json", '{"schema_version": 2, "schema_version": 2}')
        self.assertIn("duplicate JSON key", self.errors())

    def test_catalogue_pointer_cannot_escape_repository(self):
        self.requirement["code"] = ["../escape.py"]
        self.save()
        self.assertIn("unsafe or noncanonical", self.errors())

    def test_missing_code_pointer_fails(self):
        self.requirement["code"] = ["src/missing.py"]
        self.save()
        self.assertIn("MOD-001 code: missing file", self.errors())

    def test_changed_source_archive_fails(self):
        self.write("specs/sources/archive.docx", "Changed synthetic source")
        self.assertIn("SHA-256 mismatch", self.errors())

    def test_missing_bound_file_fails(self):
        self.mapping["bindings"][0].update(state="bound", path="missing.py")
        self.save()
        self.assertIn("binding fixture-source: missing file", self.errors())

    def test_unbound_path_cannot_be_guessed(self):
        self.mapping["bindings"][0]["path"] = "future.py"
        self.save()
        self.assertIn("unbound path must be null", self.errors())

    # Evidence and verified claims

    def test_valid_verified_fixture_passes(self):
        self.make_verified_fixture()
        self.assertEqual(self.errors(), "")

    def test_uat_evidence_with_report_path_verifies(self):
        self.write("specs/evidence/2026-09-19-uat.md", "# UAT\n\nReal report body.\n")
        self.make_verified_fixture(kind="uat", ref="specs/evidence/2026-09-19-uat.md")
        self.assertEqual(self.errors(), "")

    def test_manual_evidence_cannot_verify(self):
        self.make_verified_fixture(kind="manual")
        self.assertIn("needs a passing ci-smoke or uat evidence row", self.errors())

    def test_manual_evidence_on_built_row_passes(self):
        self.requirement.update({"status": "built", "evidence": [self.evidence_row(kind="manual", requirement_sha256=None)]})
        self.save()
        self.assertEqual(self.errors(), "")

    def test_verified_claim_needs_code_tests_and_evidence(self):
        self.requirement["status"] = "verified"
        self.save()
        output = self.errors()
        self.assertIn("needs code and tests pointers", output)
        self.assertIn("needs a passing ci-smoke or uat evidence row", output)

    def test_verified_claim_needs_accepted_specification(self):
        self.make_verified_fixture()
        self.document().update({"status": "draft", "approval": None})
        self.save()
        self.assertIn("require an accepted specification", self.errors())

    def test_verified_claim_needs_existing_test_file(self):
        self.make_verified_fixture()
        (self.root / "tests/fixture_test.py").unlink()
        self.assertIn("MOD-001 tests: missing file", self.errors())

    def test_changed_requirement_invalidates_evidence(self):
        self.make_verified_fixture()
        path = self.root / "specs/architecture.md"
        path.write_text(path.read_text().replace("Required fixture behaviour.", "Changed required behaviour."), encoding="utf-8")
        self.assertIn("stale evidence", self.errors())

    def test_failed_live_evidence_cannot_verify(self):
        self.make_verified_fixture(result="failed")
        self.assertIn("non-passing ci-smoke row", self.errors())

    def test_verified_row_needs_digest(self):
        self.make_verified_fixture(requirement_sha256=None)
        self.assertIn("needs requirement_sha256", self.errors())

    def test_invalid_evidence_kind_fails(self):
        self.make_verified_fixture(kind="screenshot")
        self.assertIn("evidence kind must be one of", self.errors())

    def test_missing_evidence_report_fails(self):
        self.make_verified_fixture(kind="uat", ref="specs/evidence/missing.md")
        self.assertIn("evidence ref: missing file", self.errors())

    def test_placeholder_evidence_report_fails(self):
        self.write("specs/evidence/2026-09-19-uat.md", "# REPLACE_WITH_ACTUAL_REPORT\n")
        self.make_verified_fixture(kind="uat", ref="specs/evidence/2026-09-19-uat.md")
        self.assertIn("without template placeholders", self.errors())

    def test_abbreviated_revision_is_rejected(self):
        self.make_verified_fixture(commit="abcd123")
        self.assertIn("full tested Git object ID", self.errors())

    def test_invalid_evidence_date_is_rejected(self):
        self.make_verified_fixture(date="yesterday")
        self.assertIn("evidence date must be ISO", self.errors())

    # Digest helpers

    def test_requirement_hash_includes_fenced_examples(self):
        base = (self.root / "specs/architecture.md").read_text()
        first = check_specs.requirement_blocks(base + '\n```json\n{"value": 1}\n```\n')["MOD-001"]
        second = check_specs.requirement_blocks(base + '\n```json\n{"value": 2}\n```\n')["MOD-001"]
        self.assertNotEqual(check_specs.requirement_digest(first), check_specs.requirement_digest(second))

    def test_digest_normalises_windows_line_endings(self):
        text = (self.root / "specs/architecture.md").read_text()
        unix = check_specs.requirement_blocks(text)["MOD-001"]
        windows = check_specs.requirement_blocks(text.replace("\n", "\r\n"))["MOD-001"]
        self.assertEqual(check_specs.requirement_digest(unix), check_specs.requirement_digest(windows))

    # Base-ref comparison

    def test_baseline_rejects_ambiguous_ref(self):
        self.assertIn("full Git commit", "\n".join(check_specs.compare_baseline(self.root, "main", {"MOD-001"})))

    @patch("check_specs.subprocess.run")
    def test_baseline_detects_removed_ids(self, run):
        old = {"requirements": [{"id": "MOD-001"}, {"id": "MOD-002"}]}
        run.side_effect = [subprocess.CompletedProcess([], 0, "", ""),
                           subprocess.CompletedProcess([], 0, "specs/catalog.json\n", ""),
                           subprocess.CompletedProcess([], 0, json.dumps(old), "")]
        self.assertIn("MOD-002", "\n".join(check_specs.compare_baseline(self.root, "b" * 40, {"MOD-001"})))

    @patch("check_specs.subprocess.run")
    def test_baseline_allows_missing_previous_catalogue(self, run):
        run.side_effect = [subprocess.CompletedProcess([], 0, "", ""),
                           subprocess.CompletedProcess([], 0, "", "")]
        self.assertEqual(check_specs.compare_baseline(self.root, "b" * 40, {"MOD-001"}), [])

    @patch("check_specs.subprocess.run", side_effect=FileNotFoundError("Git missing"))
    def test_missing_git_does_not_silently_skip_requested_comparison(self, run):
        self.assertIn("failed to compare", "\n".join(check_specs.compare_baseline(self.root, "b" * 40, {"MOD-001"})))


if __name__ == "__main__":
    unittest.main()
