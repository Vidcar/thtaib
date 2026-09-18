"""Regression tests against independent synthetic packs, not product features."""
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


class SpecificationCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="spec-check-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in check_specs.CORE_FILES:
            self.write(name, "# Synthetic test fixture\n")
        self.write("specs/architecture.md", '''# Architecture fixture

<a id="mod-001"></a>
### MOD-001: A synthetic rule

Required fixture behaviour.

**Acceptance:** Exercise the fixture behaviour.
''')
        self.write("specs/sources/archive.docx", "Synthetic archive bytes, not a Word document.")
        documents = []
        for path in sorted((self.root / "specs").rglob("*.md")):
            name = path.relative_to(self.root).as_posix()
            documents.append({
                "path": name,
                "kind": "specification" if name == "specs/architecture.md" else "guide",
                "basis": "pack-proposal", "owner": "Unit-test fixture owner",
                "status": "draft", "approval_reference": None,
            })
        self.catalog = {
            "schema_version": 1,
            "adoption": {"state": "pending", "decision": "specs/decisions/ADR-0001-adopt-specification-pack.md", "approval": None},
            "source_archive": {"path": "specs/sources/archive.docx", "sha256": hashlib.sha256((self.root / "specs/sources/archive.docx").read_bytes()).hexdigest()},
            "documents": documents,
            "requirements": [{"id": "MOD-001", "document": "specs/architecture.md", "implementation_status": "unassessed", "code": [], "tests": [], "evidence": []}],
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

    def accept_doc(self, path: str = "specs/architecture.md") -> None:
        for row in self.catalog["documents"]:
            if row["path"] == path:
                row["status"] = "accepted"
                row["approval_reference"] = "synthetic-test-approval-only"

    def make_verified_fixture(self) -> None:
        self.accept_doc()
        self.write("src/fixture.py", "VALUE = 1\n")
        self.write("tests/fixture_test.py", "assert 1 == 1\n")
        self.write("specs/evidence/fixture-report.md", "# Synthetic evidence fixture\n\nOnly for checker unit testing.\n")
        block = check_specs.requirement_blocks((self.root / "specs/architecture.md").read_text())["MOD-001"]
        self.catalog["requirements"][0].update({
            "implementation_status": "verified",
            "code": ["src/fixture.py"], "tests": ["tests/fixture_test.py"],
            "evidence": [{"path": "specs/evidence/fixture-report.md", "code_revision": "a" * 40,
                          "requirement_sha256": check_specs.requirement_digest(block),
                          "environment": "Synthetic unit-test fixture", "result": "passed"}],
        })
        self.save()

    def make_adopted_fixture(self) -> None:
        self.catalog["adoption"].update({"state": "accepted", "approval": {
            "reviewer": "synthetic-test-reviewer", "reference": "synthetic-approval-reference",
            "date": "2026-09-18"}})
        self.accept_doc(self.catalog["adoption"]["decision"])
        self.write(".github/CODEOWNERS", "* @synthetic-test-reviewer\n")
        self.save()

    def test_valid_unadopted_fixture(self):
        self.assertEqual(self.errors(), "")

    def test_strict_adoption_fails_before_approval(self):
        self.assertIn("approval has not been recorded", self.errors(require_adopted=True))

    def test_adopted_fixture_passes_structure_only(self):
        self.make_adopted_fixture()
        self.assertEqual(self.errors(require_adopted=True), "")

    def test_accepted_adoption_needs_active_ownership_file(self):
        self.make_adopted_fixture()
        (self.root / ".github/CODEOWNERS").unlink()
        self.assertIn("adoption ownership: missing file", self.errors())

    def test_placeholder_owners_fail(self):
        self.make_adopted_fixture()
        self.write(".github/CODEOWNERS", "* @REPLACE_WITH_MAINTAINER\n")
        self.assertIn("placeholder owners", self.errors())

    def test_invalid_approval_date_fails(self):
        self.make_adopted_fixture()
        self.catalog["adoption"]["approval"]["date"] = "not-a-date"
        self.save()
        self.assertIn("approval date", self.errors())

    def test_duplicate_requirement_definition_fails(self):
        path = self.root / "specs/architecture.md"
        path.write_text(path.read_text() + path.read_text(), encoding="utf-8")
        self.assertIn("duplicate requirement definition", self.errors())

    def test_duplicate_catalogue_entry_fails(self):
        self.catalog["requirements"].append(dict(self.catalog["requirements"][0]))
        self.save()
        self.assertIn("duplicate catalogue requirement", self.errors())

    def test_missing_requirement_row_fails(self):
        self.catalog["requirements"] = []
        self.save()
        self.assertIn("requirement missing from catalogue", self.errors())

    def test_unknown_requirement_reference_fails(self):
        self.write("README.md", "# Fixture\n\nSee MOD-999.\n")
        self.assertIn("unknown requirement reference: MOD-999", self.errors())

    def test_technical_hash_name_is_not_a_requirement(self):
        self.write("README.md", "# Fixture\n\nThe archive has a SHA-256 digest.\n")
        self.assertEqual(self.errors(), "")

    def test_broken_file_link_fails(self):
        self.write("README.md", "[Missing](specs/missing.md)\n")
        self.assertIn("broken local link", self.errors())

    def test_broken_fragment_fails(self):
        self.write("README.md", "[Missing anchor](specs/architecture.md#no-such-anchor)\n")
        self.assertIn("missing Markdown anchor", self.errors())

    def test_valid_explicit_anchor_passes(self):
        self.write("README.md", "[Rule](specs/architecture.md#mod-001)\n")
        self.assertEqual(self.errors(), "")

    def test_fenced_examples_are_not_live_links_or_ids(self):
        self.write("README.md", "# Fixture\n```text\n[Example](missing.md) MOD-999\n```\n")
        self.assertEqual(self.errors(), "")

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

    def test_missing_acceptance_check_fails(self):
        path = self.root / "specs/architecture.md"
        path.write_text(path.read_text().replace("**Acceptance:**", "**Notes:**"), encoding="utf-8")
        self.assertIn("has no acceptance check", self.errors())

    def test_missing_bound_file_fails(self):
        self.mapping["bindings"][0].update(state="bound", path="missing.py")
        self.save()
        self.assertIn("binding fixture-source: missing file", self.errors())

    def test_unbound_path_cannot_be_guessed(self):
        self.mapping["bindings"][0]["path"] = "future.py"
        self.save()
        self.assertIn("unbound path must be null", self.errors())

    def test_catalogue_pointer_cannot_escape_repository(self):
        self.catalog["requirements"][0]["code"] = ["../escape.py"]
        self.save()
        self.assertIn("unsafe or noncanonical", self.errors())

    def test_relative_markdown_link_cannot_escape_repository(self):
        self.write("README.md", "[Outside](../outside.md)\n")
        self.assertIn("local link escapes the repository", self.errors())

    def test_changed_source_archive_fails(self):
        self.write("specs/sources/archive.docx", "Changed synthetic source")
        self.assertIn("SHA-256 mismatch", self.errors())

    def test_new_spec_document_needs_registration(self):
        self.write("specs/new-spec.md", "# Not registered\n")
        self.assertIn("unregistered specification document", self.errors())

    def test_invalid_metadata_enum_fails(self):
        self.catalog["requirements"][0]["implementation_status"] = "looks-good"
        self.save()
        self.assertIn("invalid implementation_status", self.errors())

    def test_unknown_json_field_is_not_silently_ignored(self):
        self.catalog["requirements"][0]["testz"] = []
        self.save()
        self.assertIn("expected keys", self.errors())

    def test_duplicate_json_keys_are_rejected(self):
        self.write("specs/catalog.json", '{"schema_version": 1, "schema_version": 2}')
        self.assertIn("duplicate JSON key", self.errors())

    def test_valid_verified_metadata_fixture_passes(self):
        self.make_verified_fixture()
        self.assertEqual(self.errors(), "")

    def test_verified_claim_needs_real_code_tests_and_evidence(self):
        self.accept_doc()
        self.catalog["requirements"][0]["implementation_status"] = "verified"
        self.save()
        self.assertIn("needs code, tests and passing evidence", self.errors())

    def test_verified_claim_needs_accepted_specification(self):
        self.make_verified_fixture()
        for row in self.catalog["documents"]:
            if row["path"] == "specs/architecture.md":
                row["status"] = "draft"
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

    def test_failed_evidence_cannot_verify_a_requirement(self):
        self.make_verified_fixture()
        self.catalog["requirements"][0]["evidence"][0]["result"] = "failed"
        self.save()
        self.assertIn("non-passing evidence", self.errors())

    def test_placeholder_evidence_report_fails(self):
        self.make_verified_fixture()
        self.write("specs/evidence/fixture-report.md", "# REPLACE_WITH_ACTUAL_REPORT\n")
        self.assertIn("without template placeholders", self.errors())

    def test_abbreviated_revision_is_rejected(self):
        self.make_verified_fixture()
        self.catalog["requirements"][0]["evidence"][0]["code_revision"] = "abcd123"
        self.save()
        self.assertIn("full tested Git object ID", self.errors())

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
    def test_baseline_allows_first_import(self, run):
        run.side_effect = [subprocess.CompletedProcess([], 0, "", ""),
                           subprocess.CompletedProcess([], 0, "", "")]
        self.assertEqual(check_specs.compare_baseline(self.root, "b" * 40, {"MOD-001"}), [])

    @patch("check_specs.subprocess.run", side_effect=FileNotFoundError("Git missing"))
    def test_missing_git_does_not_silently_skip_requested_comparison(self, run):
        self.assertIn("failed to compare", "\n".join(check_specs.compare_baseline(self.root, "b" * 40, {"MOD-001"})))


if __name__ == "__main__":
    unittest.main()
