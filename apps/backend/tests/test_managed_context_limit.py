"""Managed start rejects a context size outside the model's GGUF length."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.support import write_tiny_gguf
from workbench_backend.errors import ManagerError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import LocalImportRequest, ManagedDeploymentRequest, RunProfile
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.paths import WorkbenchPaths


class ManagedContextLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.manager = ModelManager(self.paths)
        self.bundle_id = self._import(write_tiny_gguf(self.root / "bounded.gguf", context_length=4096))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _import(self, path: Path) -> str:
        job = self.manager.import_local(LocalImportRequest(source_path=str(path)))
        self.assertTrue(job.bundle_id)
        return job.bundle_id or ""

    def _start(self, startup: dict, *, bundle_id: str | None = None, profile_id: str | None = None):
        return self.manager.create_managed(ManagedDeploymentRequest(
            bundle_id=bundle_id or self.bundle_id, profile_id=profile_id, startup=startup, auto_start=False,
        ))

    def test_explicit_context_must_be_inside_the_model_maximum(self) -> None:
        accepted = self._start({"ctx_size": 4096})
        self.assertEqual(accepted.applied_startup["ctx_size"], 4096)
        omitted = self._start({})
        self.assertNotIn("ctx_size", omitted.applied_startup)
        automatic = self._start({"ctx_size": "auto"})
        self.assertNotIn("ctx_size", automatic.applied_startup)
        full = self._start({"ctx_size": 0})
        self.assertEqual(full.applied_startup["ctx_size"], 0)
        for value in (8192, 1.5, True, "big", -1):
            with self.subTest(value=value):
                with self.assertRaises(ManagerError) as failure:
                    self._start({"ctx_size": value})
                self.assertEqual(failure.exception.code, "managed_startup_invalid")

    def test_profile_context_above_the_maximum_is_rejected_on_managed_start(self) -> None:
        now = utc_now()
        profile = RunProfile(id="oversized", display_name="Oversized", bundle_id=self.bundle_id,
            bags=resolve_bags(startup={"ctx_size": 8192}), revision=1, created_at=now, updated_at=now)
        self.manager.store.put_profile(profile)
        with self.assertRaises(ManagerError) as failure:
            self._start({}, profile_id=profile.id)
        self.assertEqual(failure.exception.code, "managed_startup_invalid")
        replaced = self._start({"ctx_size": 2048}, profile_id=profile.id)
        self.assertEqual(replaced.applied_startup["ctx_size"], 2048)
        with self.assertRaises(ManagerError):
            self.manager.deployments.create_managed(ManagedDeploymentRequest(
                bundle_id=self.bundle_id, startup={"ctx_size": 8192}, auto_start=False,
            ))

    def test_unknown_model_maximum_does_not_invent_a_span(self) -> None:
        bundle_id = self._import(write_tiny_gguf(self.root / "unknown.gguf"))
        accepted = self._start({"ctx_size": 1024}, bundle_id=bundle_id)
        self.assertEqual(accepted.applied_startup["ctx_size"], 1024)
        with self.assertRaises(ManagerError) as failure:
            self._start({"ctx_size": 2**31}, bundle_id=bundle_id)
        self.assertEqual(failure.exception.code, "managed_startup_invalid")
