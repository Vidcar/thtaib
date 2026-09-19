"""Scaffold and model-manager API checks for the Local AI Workbench backend."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from workbench_backend.app import PRODUCT_NAME, SURFACE, create_app
from workbench_backend.inference.hf_fetch import HuggingFaceDownload
from workbench_backend.inference.schemas import PinRuntimeRequest
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from support import write_tiny_gguf


class FakeHF:
    def __init__(self, *, files: dict[str, bytes] | None = None, error: Exception | None = None) -> None:
        self.files = files or {}
        self.error = error

    def download(self, *, repo_id: str, revision: str, dest: Path, allow_patterns: list[str] | None):
        if self.error is not None:
            raise self.error
        dest.mkdir(parents=True, exist_ok=True)
        for name, payload in self.files.items():
            target = dest / name
            target.write_bytes(payload)
        return HuggingFaceDownload(
            repo_id=repo_id,
            requested_revision=revision,
            resolved_revision="abc123def456",
            local_dir=dest,
        )


class HealthEndpointTests(unittest.TestCase):
    def test_health_returns_managed_inference_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(data_root=Path(tmp)))
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["status"], "ok")
            self.assertEqual(body["product"], PRODUCT_NAME)
            self.assertEqual(body["surface"], SURFACE)

    def test_openapi_is_not_published(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(data_root=Path(tmp)))
            self.assertEqual(client.get("/openapi.json").status_code, 404)
            self.assertEqual(client.get("/docs").status_code, 404)


class ModelManagerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.gguf = write_tiny_gguf(self.root / "incoming" / "tiny-Q4_K_M.gguf")
        self.manager = ModelManager(
            self.paths,
            hf=FakeHF(files={self.gguf.name: self.gguf.read_bytes()}),
        )
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_paths_use_models_runtimes_state(self) -> None:
        body = self.client.get("/v1/paths").json()
        self.assertEqual(body["models"], str(self.paths.models))
        self.assertEqual(body["runtimes"], str(self.paths.runtimes))
        self.assertEqual(body["state"], str(self.paths.state))
        self.assertEqual(body["cases"], str(self.paths.cases))
        self.assertEqual(body["snapshots"], str(self.paths.snapshots))
        self.assertEqual(body["knowledge"], str(self.paths.knowledge))
        self.assertIn("LocalAIWorkbench", body["windows_layout"])

    def test_local_import_and_inspect_via_api(self) -> None:
        job = self.client.post(
            "/v1/imports/local",
            json={"source_path": str(self.gguf), "display_name": "tiny"},
        ).json()
        self.assertEqual(job["status"], "complete")
        bundle = self.client.get(f"/v1/bundles/{job['bundle_id']}").json()
        self.assertTrue(bundle["disk_matches"])
        self.assertTrue(Path(bundle["primary_path"]).is_relative_to(self.paths.models))
        inspect = self.client.get(f"/v1/bundles/{bundle['id']}/inspect").json()
        self.assertEqual(inspect["reader_mode"], "r")
        self.assertFalse(inspect["metadata_edited"])
        self.assertEqual(inspect["name"], "tiny-test")

    def test_settings_preview_separates_bags(self) -> None:
        body = self.client.post(
            "/v1/settings/preview",
            json={
                "startup": {"ctx_size": 2048, "made_up_flag": True},
                "per_request": {"temperature": 0.2, "nope": 1},
                "agent": {"tools_enabled": False, "secret_loop": 9},
            },
        ).json()
        self.assertEqual(body["startup"]["applied"]["ctx_size"], 2048)
        self.assertIn("made_up_flag", body["startup"]["unsupported"])
        self.assertIn("nope", body["per_request"]["unsupported"])
        self.assertIn("secret_loop", body["agent"]["unsupported"])
        self.assertNotEqual(body["startup"]["applied"], body["per_request"]["applied"])

    def test_failed_hf_import_is_not_a_deployment(self) -> None:
        self.manager.bundles.hf = FakeHF(error=RuntimeError("network down"))
        job = self.client.post(
            "/v1/imports/huggingface",
            json={"repo_id": "org/missing", "revision": "abc"},
        ).json()
        self.assertEqual(job["status"], "failed")
        self.assertIsNone(job["bundle_id"])
        response = self.client.post(
            "/v1/deployments/managed",
            json={"bundle_id": "bundle_does_not_exist", "auto_start": False},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "bundle_not_deployable")

    def test_connected_endpoint_rejects_stop(self) -> None:
        deployment = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9", "display_name": "external"},
        ).json()
        self.assertEqual(deployment["scope"], "connected")
        stopped = self.client.post(f"/v1/deployments/{deployment['id']}/stop")
        self.assertEqual(stopped.status_code, 409)
        self.assertEqual(stopped.json()["code"], "connected_no_lifecycle")

    def test_runtime_pin_local_writes_manifest(self) -> None:
        runtime_dir = self.root / "fake-runtime"
        runtime_dir.mkdir()
        fixture = runtime_dir / "fake-server"
        fixture.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fixture.chmod(0o755)
        sibling = runtime_dir / "cudart64_134.dll"
        sibling.write_bytes(b"fake-cudart")
        manifest = self.client.post(
            "/v1/runtime/pin",
            json=PinRuntimeRequest(local_executable=str(fixture)).model_dump(),
        ).json()
        self.assertEqual(manifest["status"], "ready")
        self.assertEqual(manifest["path_fallback"], "unsupported")
        self.assertTrue(Path(manifest["executable"]).is_file())
        self.assertTrue((Path(manifest["install_dir"]) / "cudart64_134.dll").is_file())
        self.assertTrue((self.paths.runtimes / "runtime-manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
