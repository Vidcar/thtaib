"""MOD-001 bundle import and MOD-002 inspect isolation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench_backend.inference.hf_fetch import HuggingFaceDownload
from workbench_backend.inference import bundles as bundle_module
from workbench_backend.inference import hashes
from workbench_backend.inference.inspect import inspect_gguf_file
from workbench_backend.inference.schemas import HuggingFaceImportRequest, LocalImportRequest
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from support import write_tiny_gguf


class FakeHF:
    def __init__(self, *, files: dict[str, bytes] | None = None, error: Exception | None = None) -> None:
        self.files = files or {}
        self.error = error
        self.calls: list[dict[str, object]] = []

    def download(self, *, repo_id: str, revision: str, dest: Path, allow_patterns: list[str] | None):
        self.calls.append(
            {
                "repo_id": repo_id,
                "revision": revision,
                "dest": dest,
                "allow_patterns": allow_patterns,
            }
        )
        if self.error is not None:
            raise self.error
        dest.mkdir(parents=True, exist_ok=True)
        for name, payload in self.files.items():
            (dest / name).write_bytes(payload)
        return HuggingFaceDownload(
            repo_id=repo_id,
            requested_revision=revision,
            resolved_revision="cafebabedead",
            local_dir=dest,
        )


class BundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.source_dir = self.root / "incoming"
        self.primary = write_tiny_gguf(self.source_dir / "demo-Q4_K_M.gguf", name="demo")
        (self.source_dir / "demo.mmproj").write_text("companion", encoding="utf-8")
        shard = write_tiny_gguf(self.source_dir / "demo-00001-of-00002.gguf", name="demo-shard")
        self.shard = shard
        self.hf = FakeHF()
        self.manager = ModelManager(self.paths, hf=self.hf)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_local_import_records_quant_shards_companions_and_hashes(self) -> None:
        job = self.manager.import_local(
            LocalImportRequest(source_path=str(self.source_dir), display_name="demo")
        )
        self.assertEqual(job.status.value, "complete")
        bundle = self.manager.get_bundle(job.bundle_id or "")
        self.assertEqual(bundle.quantization, "Q4_K_M")
        self.assertTrue(bundle.disk_matches)
        self.assertGreaterEqual(len(bundle.companions), 1)
        self.assertGreaterEqual(len(bundle.shards), 1)
        for recorded in bundle.files:
            path = Path(recorded.path)
            self.assertTrue(path.is_file())
            self.assertTrue(path.is_relative_to(self.paths.models))
            self.assertEqual(path.stat().st_size, recorded.size_bytes)

    def test_list_bundles_caches_after_first_check_and_skips_unchanged_write(self) -> None:
        job = self.manager.import_local(
            LocalImportRequest(source_path=str(self.source_dir), display_name="demo")
        )
        self.assertEqual(job.status.value, "complete")
        bundle = self.manager.store.get_bundle(job.bundle_id or "")
        self.assertIsNotNone(bundle)

        with (
            patch.object(hashes, "sha256_file", wraps=hashes.sha256_file) as wrapped_hash,
            patch.object(self.manager.store, "put_bundle", wraps=self.manager.store.put_bundle) as wrapped_put,
        ):
            self.manager.list_bundles()
            self.manager.list_bundles()

        self.assertEqual(wrapped_hash.call_count, len(bundle.files))
        self.assertEqual(wrapped_put.call_count, 0)

    def test_get_bundle_uses_full_hash_each_time(self) -> None:
        job = self.manager.import_local(
            LocalImportRequest(source_path=str(self.source_dir), display_name="demo")
        )
        bundle = self.manager.store.get_bundle(job.bundle_id or "")
        self.assertIsNotNone(bundle)

        with patch.object(bundle_module, "sha256_file", wraps=bundle_module.sha256_file) as wrapped_hash:
            self.manager.get_bundle(job.bundle_id or "")
            self.manager.get_bundle(job.bundle_id or "")

        self.assertEqual(wrapped_hash.call_count, len(bundle.files) * 2)

    def test_reuse_under_models_keeps_same_record_format(self) -> None:
        first = self.manager.import_local(LocalImportRequest(source_path=str(self.primary)))
        first_bundle = self.manager.get_bundle(first.bundle_id or "")
        reuse = self.manager.import_local(
            LocalImportRequest(source_path=first_bundle.primary_path or "")
        )
        reused = self.manager.get_bundle(reuse.bundle_id or "")
        self.assertEqual(reused.source.kind.value, "local")
        self.assertEqual({item.role.value for item in reused.files}, {item.role.value for item in first_bundle.files})
        self.assertTrue(Path(reused.primary_path or "").is_relative_to(self.paths.models))

    def test_hf_import_pins_resolved_revision(self) -> None:
        self.hf.files = {
            self.primary.name: self.primary.read_bytes(),
            "demo.mmproj": b"mm",
        }
        job = self.manager.import_huggingface(
            HuggingFaceImportRequest(repo_id="org/demo", revision="main")
        )
        self.assertEqual(job.status.value, "complete")
        bundle = self.manager.get_bundle(job.bundle_id or "")
        self.assertEqual(bundle.source.kind.value, "huggingface")
        self.assertEqual(bundle.source.requested_revision, "main")
        self.assertEqual(bundle.source.resolved_revision, "cafebabedead")
        self.assertEqual(self.hf.calls[0]["revision"], "main")

    def test_interrupted_download_has_no_bundle(self) -> None:
        self.hf.error = InterruptedError("download interrupted")
        job = self.manager.import_huggingface(
            HuggingFaceImportRequest(repo_id="org/demo", revision="deadbeef")
        )
        self.assertEqual(job.status.value, "interrupted")
        self.assertIsNone(job.bundle_id)
        self.assertEqual(self.manager.list_bundles(), [])

    def test_inspect_does_not_edit_metadata(self) -> None:
        job = self.manager.import_local(LocalImportRequest(source_path=str(self.primary)))
        bundle = self.manager.get_bundle(job.bundle_id or "")
        original = Path(bundle.primary_path or "").read_bytes()
        report = inspect_gguf_file(Path(bundle.primary_path or ""), bundle_id=bundle.id)
        self.assertEqual(report.reader_mode, "r")
        self.assertFalse(report.metadata_edited)
        self.assertEqual(report.name, "demo")
        self.assertEqual(Path(bundle.primary_path or "").read_bytes(), original)
        again = self.manager.inspect_bundle(bundle.id)
        self.assertEqual(again.sha256, report.sha256)
        self.assertEqual(Path(bundle.primary_path or "").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
