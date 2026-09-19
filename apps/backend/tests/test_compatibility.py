"""MOD-006 compatibility provenance: categories stay separate; unverified ≠ incompatible."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError
from fastapi.testclient import TestClient

from workbench_backend.app import create_app
from workbench_backend.inference.compatibility import (
    CompatibilityProvenance,
    CompatibilityRecord,
    CompatibilityService,
    CompatibilitySubject,
    CompatibilitySupportStatus,
    PROVENANCE_CATEGORIES,
    ProvenanceCategory,
    ProvenanceItem,
    SubjectKind,
)
from workbench_backend.inference.schemas import LocalImportRequest
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from tests.support import write_tiny_gguf


class ProvenanceSeparationTests(unittest.TestCase):
    def test_three_categories_are_named_and_required(self) -> None:
        self.assertEqual(
            PROVENANCE_CATEGORIES,
            ("publisher_guidance", "tested_adjustments", "user_overrides"),
        )
        empty = CompatibilityProvenance()
        dumped = empty.model_dump()
        for name in PROVENANCE_CATEGORIES:
            self.assertIn(name, dumped)
            self.assertEqual(dumped[name], [])

    def test_item_cannot_sit_in_the_wrong_category_list(self) -> None:
        item = ProvenanceItem(
            id="mixed",
            category=ProvenanceCategory.publisher_guidance,
            claim="publisher claim",
        )
        with self.assertRaises(ValidationError):
            CompatibilityProvenance(tested_adjustments=[item])

    def test_unverified_record_cannot_be_marked_incompatible(self) -> None:
        with self.assertRaises(ValidationError):
            CompatibilityRecord(
                id="bad",
                support_status=CompatibilitySupportStatus.unverified,
                subject=CompatibilitySubject(kind=SubjectKind.unfamiliar, selector="x"),
                incompatible=True,
            )


class CompatibilityApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.gguf = write_tiny_gguf(self.root / "incoming" / "unfamiliar-Q4_K_M.gguf")
        self.manager = ModelManager(self.paths)
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        self.app.state.compatibility = CompatibilityService(self.paths)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_three_provenance_record_keeps_categories_separate(self) -> None:
        response = self.client.get("/v1/compatibility/records/compat_three_provenance")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["kind"], "compatibility-record")
        self.assertEqual(body["catalogue_claim"], "not_verified")
        self.assertNotEqual(body["catalogue_claim"], "verified")
        provenance = body["provenance"]
        self.assertEqual(set(provenance), set(PROVENANCE_CATEGORIES))
        publisher_ids = {item["id"] for item in provenance["publisher_guidance"]}
        tested_ids = {item["id"] for item in provenance["tested_adjustments"]}
        override_ids = {item["id"] for item in provenance["user_overrides"]}
        self.assertIn("pub_ctx", publisher_ids)
        self.assertIn("test_ctx", tested_ids)
        self.assertIn("user_temp", override_ids)
        self.assertFalse(publisher_ids & tested_ids)
        self.assertFalse(publisher_ids & override_ids)
        self.assertFalse(tested_ids & override_ids)
        for item in provenance["publisher_guidance"]:
            self.assertEqual(item["category"], "publisher_guidance")
        for item in provenance["tested_adjustments"]:
            self.assertEqual(item["category"], "tested_adjustments")
        for item in provenance["user_overrides"]:
            self.assertEqual(item["category"], "user_overrides")

    def test_user_override_api_does_not_mix_into_publisher_or_tested(self) -> None:
        added = self.client.post(
            "/v1/compatibility/records/compat_three_provenance/overrides",
            json={"claim": "User sets flash_attn to auto"},
        )
        self.assertEqual(added.status_code, 200, added.text)
        body = added.json()
        publisher = [item["claim"] for item in body["provenance"]["publisher_guidance"]]
        tested = [item["claim"] for item in body["provenance"]["tested_adjustments"]]
        overrides = [item["claim"] for item in body["provenance"]["user_overrides"]]
        self.assertNotIn("User sets flash_attn to auto", publisher)
        self.assertNotIn("User sets flash_attn to auto", tested)
        self.assertIn("User sets flash_attn to auto", overrides)
        self.assertTrue((self.paths.state / "compatibility" / "overrides.json").is_file())

    def test_unfamiliar_unverified_model_is_not_known_incompatible(self) -> None:
        job = self.manager.import_local(LocalImportRequest(source_path=str(self.gguf)))
        bundle_id = job.bundle_id or ""
        response = self.client.get(f"/v1/bundles/{bundle_id}/compatibility")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["support_status"], "unverified")
        self.assertNotEqual(body["support_status"], "known_incompatible")
        self.assertFalse(body["incompatible"])
        self.assertFalse(body["excluded"])
        self.assertTrue(body["usable"])
        self.assertTrue(body["unverified_is_not_incompatible"])
        self.assertEqual(body["catalogue_claim"], "not_verified")
        assess = self.client.post(
            "/v1/compatibility/assess",
            json={"selector": "totally-unknown-family"},
        )
        self.assertEqual(assess.status_code, 200, assess.text)
        unknown = assess.json()
        self.assertEqual(unknown["support_status"], "unverified")
        self.assertFalse(unknown["incompatible"])
        self.assertTrue(unknown["usable"])

    def test_known_incompatible_is_distinct_from_unverified(self) -> None:
        known = self.client.post(
            "/v1/compatibility/assess",
            json={"selector": "known-incompatible-fixture"},
        ).json()
        unverified = self.client.post(
            "/v1/compatibility/assess",
            json={"selector": "never-seen-model"},
        ).json()
        self.assertEqual(known["support_status"], "known_incompatible")
        self.assertTrue(known["incompatible"])
        self.assertEqual(unverified["support_status"], "unverified")
        self.assertFalse(unverified["incompatible"])
        self.assertNotEqual(known["support_status"], unverified["support_status"])

    def test_unverified_bundle_is_not_excluded_from_managed_create(self) -> None:
        job = self.manager.import_local(LocalImportRequest(source_path=str(self.gguf)))
        assessment = self.client.get(f"/v1/bundles/{job.bundle_id}/compatibility").json()
        self.assertEqual(assessment["support_status"], "unverified")
        self.assertTrue(assessment["usable"])
        created = self.client.post(
            "/v1/deployments/managed",
            json={"bundle_id": job.bundle_id, "auto_start": False},
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["bundle_id"], job.bundle_id)
        self.assertNotEqual(created.json()["status"], "failed")


if __name__ == "__main__":
    unittest.main()
