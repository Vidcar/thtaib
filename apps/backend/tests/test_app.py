"""Scaffold and model-manager API checks for the Local AI Workbench backend."""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
import threading
from types import SimpleNamespace
from pathlib import Path

from fastapi.testclient import TestClient

from workbench_backend.app import PRODUCT_NAME, SURFACE, create_app
from workbench_backend.inference.hf_fetch import HuggingFaceDownload, describe_repository
from workbench_backend.inference.schemas import PinRuntimeRequest
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from support import OfflineProbe, close_workbench_sqlite, workbench_client, write_tiny_gguf, wait_for_import


class FakeHF:
    def __init__(self, *, files: dict[str, bytes] | None = None, error: Exception | None = None) -> None:
        self.files = files or {}
        self.error = error

    def inspect(self, *, repo_id: str, revision: str = "main"):
        return describe_repository(repo_id, SimpleNamespace(sha="1" * 40, siblings=[SimpleNamespace(rfilename=name, size=len(payload)) for name, payload in self.files.items()]))

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
            app = create_app(data_root=Path(tmp))
            client = TestClient(app)
            try:
                response = client.get("/health")
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["status"], "ok")
                self.assertEqual(body["product"], PRODUCT_NAME)
                self.assertEqual(body["surface"], SURFACE)
            finally:
                close_workbench_sqlite(app, client)

    def test_openapi_is_not_published(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(data_root=Path(tmp))
            anonymous = TestClient(app)
            authorized = workbench_client(app)
            try:
                self.assertEqual(anonymous.get("/openapi.json").status_code, 401)
                self.assertEqual(anonymous.get("/docs").status_code, 401)
                self.assertEqual(authorized.get("/openapi.json").status_code, 404)
                self.assertEqual(authorized.get("/docs").status_code, 404)
            finally:
                close_workbench_sqlite(app, anonymous, authorized)


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
        self.client = workbench_client(self.app)

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def test_paths_use_models_runtimes_state(self) -> None:
        body = self.client.get("/v1/paths").json()
        self.assertEqual(body["models"], str(self.paths.models))
        self.assertEqual(body["runtimes"], str(self.paths.runtimes))
        self.assertEqual(body["state"], str(self.paths.state))
        self.assertEqual(body["cases"], str(self.paths.cases))
        self.assertEqual(body["snapshots"], str(self.paths.snapshots))
        self.assertEqual(body["knowledge"], str(self.paths.knowledge))
        self.assertEqual(body["logs"], str(self.paths.logs))
        self.assertEqual(body["application_db"], str(self.paths.application_db))
        self.assertEqual(body["checkpoints_db"], str(self.paths.checkpoints_db))
        self.assertNotEqual(body["application_db"], body["checkpoints_db"])
        self.assertIn("LocalAIWorkbench", body["windows_layout"])
        self.assertIn("application.sqlite", body["windows_layout"])
        self.assertIn("checkpoints.sqlite", body["windows_layout"])
        self.assertIn("logs", body["windows_layout"])

    def test_local_import_and_inspect_via_api(self) -> None:
        response = self.client.post(
            "/v1/imports/local",
            json={"source_path": str(self.gguf), "display_name": "tiny"},
        )
        self.assertEqual(response.status_code, 202)
        job = wait_for_import(self.client, response.json())
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
        self.manager.bundles.hf = FakeHF(files={self.gguf.name: self.gguf.read_bytes()}, error=RuntimeError("network down"))
        # The subprocess transport itself is covered by import-worker tests.
        # Keep this API failure check deterministic at its download boundary.
        def failed_transfer(job, request):
            return self.manager.bundles.import_huggingface(request, job=job)
        with patch.object(self.manager.imports, "_run_huggingface_subprocess", side_effect=failed_transfer):
            response = self.client.post(
                "/v1/imports/huggingface",
                json={"repo_id": "org/missing", "revision": "abc"},
            )
            self.assertEqual(response.status_code, 202)
            job = wait_for_import(self.client, response.json())
        self.assertEqual(job["status"], "failed")
        self.assertIsNone(job["bundle_id"])
        response = self.client.post(
            "/v1/deployments/managed",
            json={"bundle_id": "bundle_does_not_exist", "auto_start": False},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "bundle_not_deployable")

    def test_import_returns_durable_id_before_copy_finishes(self) -> None:
        entered, release = threading.Event(), threading.Event()
        original = self.manager.bundles.import_local
        def blocked(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise AssertionError("Test did not release import worker")
            return original(*args, **kwargs)
        try:
            with patch.object(self.manager.bundles, "import_local", side_effect=blocked):
                response = self.client.post("/v1/imports/local", json={"source_path": str(self.gguf)})
                self.assertEqual(response.status_code, 202)
                self.assertTrue(entered.wait(2))
                job = response.json()
                durable = self.manager.store.get_job(job["id"])
                self.assertIsNotNone(durable)
                self.assertIn(durable.status.value, {"pending", "running"})
                self.assertEqual(self.manager.store.list_bundles(), [])
                release.set()
                self.assertEqual(wait_for_import(self.client, job)["status"], "complete")
        finally:
            release.set()

    def test_connected_endpoint_rejects_stop(self) -> None:
        self.manager.deployments.probe = OfflineProbe()
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
