"""Full pinned cards are selected by bundle and never applied as settings on view."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench_backend.errors import ManagerError, manager_error_handler
from workbench_backend.inference.hf_recipes import MAX_CARD_BYTES
from workbench_backend.inference.routes import router
from workbench_backend.inference.schemas import (
    BundleFile, BundleSource, BundleSourceKind, FileRole, ModelBundle,
)
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths


REVISION = "a" * 40
CARD = "# Card A\n\n## Recommended sampling settings\n- Thinking mode for general tasks: temperature=1.0, top_p=0.95\n"


class ModelCardViewTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = Path(__file__).resolve().parents[3] / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        root = Path(self.tmp.name)
        self.manager = ModelManager(WorkbenchPaths(root / "app"))
        self.card = root / "README.md"
        self.card.write_bytes(CARD.encode("utf-8"))
        self.digest = hashlib.sha256(CARD.encode("utf-8")).hexdigest()
        self.bundle = self._bundle("bundle_a", "owner/model-a", self.card)
        self.manager.store.put_bundle(self.bundle)
        app = FastAPI()
        app.state.manager = self.manager
        app.include_router(router)
        app.add_exception_handler(ManagerError, manager_error_handler)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.tmp.cleanup()

    def _bundle(self, bundle_id: str, repo_id: str, card: Path | None) -> ModelBundle:
        # The deliberately absent GGUF proves card reads and refresh never open weights.
        files = [BundleFile(role=FileRole.primary_weights, name="absent.gguf",
            path=str(Path(self.tmp.name) / "absent.gguf"), sha256="0" * 64, size_bytes=100)]
        if card is not None:
            payload = card.read_bytes()
            files.append(BundleFile(role=FileRole.companion, name=card.name, path=str(card),
                sha256=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload)))
        return ModelBundle(id=bundle_id, display_name=bundle_id,
            source=BundleSource(kind=BundleSourceKind.huggingface,
                repo_id=repo_id, resolved_revision=REVISION), files=files,
            primary_path=str(Path(self.tmp.name) / "absent.gguf"), created_at="2026-09-25T00:00:00Z")

    def test_route_uses_selected_bundle_and_does_not_write_records(self) -> None:
        second_card = Path(self.tmp.name) / "other" / "README.md"
        second_card.parent.mkdir()
        second_card.write_text("# Other model", encoding="utf-8")
        other = self._bundle("bundle_b", "owner/model-b", second_card)
        self.manager.store.put_bundle(other)
        before = (self.manager.store.get_bundle(self.bundle.id), self.manager.store.get_bundle(other.id))
        with patch.object(self.manager.bundles.hf, "inspect") as inspect, patch.object(
            self.manager.bundles.hf, "read_pinned_card") as remote, patch.object(
            self.manager.bundles.hf, "download", side_effect=AssertionError("weights downloaded")):
            response = self.client.get("/v1/bundles/bundle_b/model-card")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"bundle_id": "bundle_b", "repo_id": "owner/model-b",
                "revision": REVISION, "sha256": hashlib.sha256(b"# Other model").hexdigest(),
                "markdown": "# Other model", "origin": "saved"})
            inspect.assert_not_called()
            remote.assert_not_called()
        self.assertEqual((self.manager.store.get_bundle(self.bundle.id),
            self.manager.store.get_bundle(other.id)), before)
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/v1/bundles/{bundle_id}/model-card", schema["paths"])
        self.assertEqual(set(schema["components"]["schemas"]["ModelCardResponse"]["required"]),
            {"bundle_id", "repo_id", "revision", "sha256", "markdown", "origin"})

    def test_corrupt_or_wrong_size_local_card_falls_back_to_recorded_checksum(self) -> None:
        for damage in ("changed hash", "changed size"):
            with self.subTest(damage=damage):
                if damage == "changed hash":
                    self.card.write_bytes(CARD.replace("1.0", "0.5").encode("utf-8"))
                    # Same byte count, so only the checksum can catch this.
                    bundle = self.bundle
                else:
                    self.card.write_bytes(CARD.encode("utf-8"))
                    record = self.bundle.files[1].model_copy(update={"size_bytes": len(CARD) + 1})
                    bundle = self.bundle.model_copy(update={"files": [self.bundle.files[0], record]})
                self.manager.store.put_bundle(bundle)
                with patch.object(self.manager.bundles.hf, "read_pinned_card",
                    return_value=(CARD, self.digest)) as remote, patch.object(
                    self.manager.bundles.hf, "download", side_effect=AssertionError("weights downloaded")):
                    response = self.client.get("/v1/bundles/bundle_a/model-card")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["origin"], "fetched")
                remote.assert_called_once_with("owner/model-a", REVISION,
                    filename="README.md", expected_sha256=self.digest)

    def test_missing_record_discovers_only_root_card_at_pinned_revision(self) -> None:
        missing = self._bundle("bundle_a", "owner/model-a", None)
        self.manager.store.put_bundle(missing)
        listing = SimpleNamespace(resolved_revision=REVISION,
            guidance_files=["nested/README.md", "readme.md"])
        with patch.object(self.manager.bundles.hf, "inspect", return_value=listing) as inspect, patch.object(
            self.manager.bundles.hf, "read_pinned_card", return_value=(CARD, self.digest)) as remote:
            response = self.client.get("/v1/bundles/bundle_a/model-card")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["origin"], "fetched")
        inspect.assert_called_once_with(repo_id="owner/model-a", revision=REVISION)
        remote.assert_called_once_with("owner/model-a", REVISION,
            filename="readme.md", expected_sha256=None)
        self.assertEqual(self.manager.store.get_bundle("bundle_a").files, missing.files)

    def test_unavailable_or_mismatched_pinned_card_is_rejected(self) -> None:
        self.card.write_text("tampered", encoding="utf-8")
        with patch.object(self.manager.bundles.hf, "read_pinned_card",
            side_effect=ManagerError("Pinned card unavailable.", code="hf_offline", status_code=503)):
            response = self.client.get("/v1/bundles/bundle_a/model-card")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "hf_offline")
        with patch.object(self.manager.bundles.hf, "read_pinned_card",
            return_value=(CARD, "f" * 64)):
            response = self.client.get("/v1/bundles/bundle_a/model-card")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "hf_card_checksum")

    def test_missing_root_card_and_changed_listing_revision_are_rejected(self) -> None:
        missing = self._bundle("bundle_a", "owner/model-a", None)
        self.manager.store.put_bundle(missing)
        for listing, status, code in (
            (SimpleNamespace(resolved_revision=REVISION, guidance_files=["nested/README.md"]), 404, "recipe_card_missing"),
            (SimpleNamespace(resolved_revision="b" * 40, guidance_files=["README.md"]), 409, "recipe_source_changed"),
        ):
            with self.subTest(code=code), patch.object(self.manager.bundles.hf, "inspect",
                return_value=listing), patch.object(self.manager.bundles.hf, "read_pinned_card") as remote:
                response = self.client.get("/v1/bundles/bundle_a/model-card")
                self.assertEqual((response.status_code, response.json()["code"]), (status, code))
                remote.assert_not_called()

    def test_size_limit_and_refresh_share_verified_reader_without_weights(self) -> None:
        self.card.write_bytes(b"x" * (MAX_CARD_BYTES + 1))
        with patch.object(self.manager.bundles.hf, "read_pinned_card",
            return_value=(CARD, self.digest)) as remote, patch.object(
            self.manager.bundles.hf, "download", side_effect=AssertionError("weights downloaded")):
            response = self.client.get("/v1/bundles/bundle_a/model-card")
            refreshed = self.manager.refresh_response_recipes(self.bundle.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(remote.call_count, 2)
        self.assertEqual(refreshed.files, self.bundle.files)
        self.assertEqual(len(refreshed.huggingface_configuration.response_recipes), 1)
        self.assertIn("size", refreshed.huggingface_configuration.unsupported["README.md"])

    def test_non_huggingface_and_unknown_bundle_have_clear_errors(self) -> None:
        self.manager.store.put_bundle(self.bundle.model_copy(update={"source": BundleSource(
            kind=BundleSourceKind.local, original_path="somewhere")}))
        response = self.client.get("/v1/bundles/bundle_a/model-card")
        self.assertEqual((response.status_code, response.json()["code"]), (400, "model_card_source"))
        response = self.client.get("/v1/bundles/unknown/model-card")
        self.assertEqual((response.status_code, response.json()["code"]), (404, "bundle_missing"))

    def test_moving_revision_is_not_presented_as_a_pinned_card(self) -> None:
        source = self.bundle.source.model_copy(update={"resolved_revision": "main"})
        self.manager.store.put_bundle(self.bundle.model_copy(update={"source": source}))
        with patch.object(self.manager.bundles.hf, "read_pinned_card") as remote:
            response = self.client.get("/v1/bundles/bundle_a/model-card")
        self.assertEqual((response.status_code, response.json()["code"]), (409, "model_card_revision"))
        remote.assert_not_called()


if __name__ == "__main__":
    unittest.main()
