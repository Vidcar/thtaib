"""Deliberate companion selection never implies verified vision or file ownership."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gguf import GGUFWriter

from tests.support import close_workbench_sqlite, offline_workbench_client, write_tiny_gguf
from workbench_backend.app import create_app
from workbench_backend.inference.capabilities import CapabilityEvidence, setup_fingerprint
from workbench_backend.inference.deployments import managed_argv
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import Deployment, DeploymentStatus, LocalImportRequest, ManagementScope, ServerProperties


def write_projector(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = GGUFWriter(str(path), "clip")
    writer.add_name("Matching fixture family")
    writer.add_string("clip.projector_type", "fixture")
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.close()
    return path


class ProjectorSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.app = create_app(data_root=self.root / "data")
        self.client = offline_workbench_client(self.app)
        self.manager = self.app.state.manager
        self.primary = write_tiny_gguf(self.root / "source" / "model.gguf")
        job = self.manager.import_local(LocalImportRequest(source_path=str(self.primary), copy_files=False))
        self.bundle_id = job.bundle_id
        self.projector = write_projector(self.primary.parent / "mmproj-F16.gguf")
        now = utc_now()
        self.deployment = Deployment(id="projector-deployment", display_name="Fixture", scope=ManagementScope.managed,
            status=DeploymentStatus.stopped, bundle_id=self.bundle_id, created_at=now, updated_at=now)
        self.manager.store.put_deployment(self.deployment)

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.temporary.cleanup()

    def select(self, path):
        return self.client.put(f"/v1/bundles/{self.bundle_id}/projector", json={"path": str(path) if path else None})

    def test_discovery_selection_restart_identity_and_explicit_text_only(self):
        response = self.client.get(f"/v1/bundles/{self.bundle_id}/projectors")
        self.assertEqual(response.status_code, 200, response.text)
        available = response.json()
        self.assertIsNone(available["selected_path"])
        self.assertEqual(len(available["candidates"]), 1)
        self.assertEqual(available["candidates"][0]["metadata_name"], "Matching fixture family")
        self.assertEqual(available["candidates"][0]["compatibility"], "unverified")
        before = setup_fingerprint(self.manager.get_deployment(self.deployment.id))
        response = self.select(self.projector)
        self.assertEqual(response.status_code, 200, response.text)
        selected = self.manager.get_bundle(self.bundle_id)
        self.assertEqual(selected.companions[0].ownership, "external")
        self.assertEqual(len(selected.files), 1, "original import manifest stays intact")
        argv = managed_argv("llama-server", selected, {})
        self.assertEqual(argv[argv.index("--mmproj") + 1], str(self.projector.resolve()))
        after = setup_fingerprint(self.manager.get_deployment(self.deployment.id))
        self.assertNotEqual(before, after)
        report = self.client.get(f"/v1/compatibility/deployments/{self.deployment.id}/probes").json()
        self.assertEqual(report["image_setup"]["selected_projector"], str(self.projector.resolve()))
        self.assertTrue(report["image_setup"]["projector_present"])
        self.assertIsNone(report["image_setup"]["runtime_support"])
        self.assertEqual(report["current_support"]["image"], "untested")
        response = self.select(None)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("--mmproj", managed_argv("llama-server", self.manager.get_bundle(self.bundle_id), {}))
        self.assertTrue(self.projector.exists(), "text-only selection never deletes the original")

    def test_running_failed_owned_and_reserved_deployments_block_selection(self):
        for status, pid in ((DeploymentStatus.running, None), (DeploymentStatus.failed, 123)):
            self.manager.store.put_deployment(self.deployment.model_copy(update={"status": status, "pid": pid}))
            self.assertEqual(self.select(self.projector).status_code, 409)
        self.manager.store.put_deployment(self.deployment)
        with self.manager.reserve_deployment(self.deployment.id):
            self.assertEqual(self.select(self.projector).status_code, 409)
        self.assertEqual(self.select(self.projector).status_code, 200)

    def test_selected_external_companion_remains_part_of_cached_integrity(self):
        self.assertEqual(self.select(self.projector).status_code, 200)
        self.assertTrue(self.manager.list_bundles()[0].disk_matches)
        self.projector.write_bytes(b"changed projector")
        self.assertFalse(self.manager.list_bundles()[0].disk_matches)

    def test_named_weights_cannot_be_misidentified_as_projector(self):
        wrong = write_tiny_gguf(self.primary.parent / "mmproj-wrong.gguf")
        response = self.select(wrong)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.manager.get_bundle(self.bundle_id).companions, [])

    def test_saved_probe_history_exposes_stale_setup_and_survives_restart(self):
        deployment = self.manager.get_deployment(self.deployment.id)
        old = CapabilityEvidence(id="before-projector", deployment_id=deployment.id, capability="image", status="passed",
            fingerprint=setup_fingerprint(deployment), setup={}, tested_at=utc_now())
        self.manager.store.put_capability_evidence(old.model_dump(mode="json"))
        self.assertEqual(self.select(self.projector).status_code, 200)
        report = self.client.get(f"/v1/compatibility/deployments/{deployment.id}/probes").json()
        self.assertEqual(report["evidence"][0]["id"], old.id)
        self.assertNotEqual(report["current_fingerprint"], old.fingerprint)
        self.assertEqual(report["current_support"]["image"], "untested")


if __name__ == "__main__":
    unittest.main()
