"""MOD-001 bundle import and MOD-002 inspect isolation."""

from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from workbench_backend.inference.hf_fetch import HuggingFaceDownload
from workbench_backend.inference import bundles as bundle_module
from workbench_backend.inference import hashes
from workbench_backend.inference.inspect import inspect_gguf_file
from workbench_backend.inference.schemas import (
    BundleFile,
    BundleSource,
    BundleSourceKind,
    FileRole,
    HuggingFaceImportRequest,
    ImportStatus,
    LocalImportRequest,
    ModelBundle,
)
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
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
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
        self.hf = FakeHF()
        self.manager = ModelManager(self.paths, hf=self.hf)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_local_import_records_quant_shards_companions_and_hashes(self) -> None:
        self.primary.unlink()
        write_tiny_gguf(self.source_dir / "demo-Q4_K_M-00001-of-00002.gguf", name="demo-shard-1")
        write_tiny_gguf(self.source_dir / "demo-Q4_K_M-00002-of-00002.gguf", name="demo-shard-2")
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

    def test_quantization_uses_weight_file_even_when_projector_sorts_first(self) -> None:
        projector = self.source_dir / 'a-mmproj-BF16.gguf'
        write_tiny_gguf(projector, name='fixture projector')
        job = self.manager.import_local(LocalImportRequest(source_path=str(self.source_dir)))
        self.assertEqual(job.status, ImportStatus.complete)
        bundle = self.manager.store.get_bundle(job.bundle_id)
        self.assertEqual(bundle.files[0].name, projector.name)
        self.assertEqual(bundle.quantization, 'Q4_K_M')
        self.assertEqual(bundle_module.detect_quantization(['Ternary-Bonsai-2-27B-PTQ1_0.gguf']), 'PTQ1_0')
        unknown = self.root / 'unknown-precision'
        write_tiny_gguf(unknown / 'weights.gguf', name='weights')
        write_tiny_gguf(unknown / 'a-mmproj-F16.gguf', name='projector')
        job = self.manager.import_local(LocalImportRequest(source_path=str(unknown)))
        self.assertEqual(self.manager.get_bundle(job.bundle_id).quantization, None)

    def test_cached_verification_corrects_saved_projector_label_without_hashing(self) -> None:
        write_tiny_gguf(self.source_dir / 'a-mmproj-BF16.gguf', name='fixture projector')
        job = self.manager.import_local(LocalImportRequest(source_path=str(self.source_dir)))
        bundle = self.manager.get_bundle(job.bundle_id)
        self.manager.store.put_bundle(bundle.model_copy(update={'quantization': 'BF16'}))
        with patch.object(bundle_module, 'sha256_file', side_effect=AssertionError('unnecessary full hash')), \
             patch.object(bundle_module, 'cached_sha256_file', side_effect=AssertionError('unnecessary cached hash')):
            corrected = self.manager.list_bundles()[0]
        self.assertEqual(corrected.quantization, 'Q4_K_M')
        self.assertEqual(self.manager.store.get_bundle(job.bundle_id).quantization, 'Q4_K_M')
        self.assertEqual(corrected.files, bundle.files)
        self.assertEqual(corrected.companions, bundle.companions)
        self.assertEqual(corrected.primary_path, bundle.primary_path)

    def test_local_import_preserves_relative_paths_and_file_identity(self) -> None:
        nested = self.root / "nested-source"
        primary = write_tiny_gguf(nested / "weights" / "demo-Q4_K_M.gguf", name="nested-demo")
        (nested / "config" / "tokenizer.json").parent.mkdir(parents=True, exist_ok=True)
        (nested / "config" / "tokenizer.json").write_text("{}", encoding="utf-8")
        (nested / "extra" / "tokenizer.json").parent.mkdir(parents=True, exist_ok=True)
        (nested / "extra" / "tokenizer.json").write_text("{}", encoding="utf-8")

        job = self.manager.import_local(LocalImportRequest(source_path=str(nested)))

        self.assertEqual(job.status.value, "complete")
        bundle = self.manager.get_bundle(job.bundle_id or "")
        names = {item.name for item in bundle.files}
        self.assertIn("weights/demo-Q4_K_M.gguf", names)
        self.assertIn("config/tokenizer.json", names)
        self.assertIn("extra/tokenizer.json", names)
        self.assertEqual(Path(bundle.primary_path or "").read_bytes(), primary.read_bytes())

    def test_local_import_rejects_multiple_weights_variants(self) -> None:
        write_tiny_gguf(self.source_dir / "demo-Q5_K_M.gguf", name="other")

        job = self.manager.import_local(LocalImportRequest(source_path=str(self.source_dir)))

        self.assertEqual(job.status.value, "failed")
        self.assertIn("multiple GGUF weights variants", job.error or "")
        self.assertEqual(self.manager.list_bundles(), [])

    def test_local_import_rejects_multiple_mmproj_ggufs(self) -> None:
        write_tiny_gguf(self.source_dir / "vision.mmproj.gguf", name="projector-1")
        write_tiny_gguf(self.source_dir / "audio.mmproj.gguf", name="projector-2")

        job = self.manager.import_local(LocalImportRequest(source_path=str(self.source_dir)))

        self.assertEqual(job.status.value, "failed")
        self.assertIn("multiple multimodal projector", job.error or "")
        self.assertEqual(self.manager.list_bundles(), [])

    def test_local_import_rejects_mixed_projector_hint_ggufs(self) -> None:
        write_tiny_gguf(self.source_dir / "vision.mmproj.gguf", name="projector-1")
        write_tiny_gguf(self.source_dir / "vision.projector.gguf", name="projector-2")

        job = self.manager.import_local(LocalImportRequest(source_path=str(self.source_dir)))

        self.assertEqual(job.status.value, "failed")
        self.assertIn("multiple multimodal projector", job.error or "")
        self.assertEqual(self.manager.list_bundles(), [])

    def test_mmproj_companion_rejects_legacy_ambiguous_projectors(self) -> None:
        bundle = ModelBundle(
            id="bundle-old",
            display_name="old",
            source=BundleSource(kind=BundleSourceKind.local),
            files=[],
            companions=[
                BundleFile(
                    role=FileRole.companion,
                    name="vision.mmproj.gguf",
                    path=str(self.source_dir / "vision.mmproj.gguf"),
                    sha256="a",
                    size_bytes=1,
                ),
                BundleFile(
                    role=FileRole.companion,
                    name="vision.projector.gguf",
                    path=str(self.source_dir / "vision.projector.gguf"),
                    sha256="b",
                    size_bytes=1,
                ),
            ],
            created_at="2026-09-20T00:00:00Z",
            status=ImportStatus.complete,
        )

        with self.assertRaisesRegex(Exception, "multiple multimodal projector"):
            bundle_module.mmproj_companion(bundle)

    def test_local_import_rejects_incomplete_shards(self) -> None:
        shard_source = self.root / "shard-source"
        write_tiny_gguf(shard_source / "demo-Q4_K_M-00001-of-00002.gguf", name="demo-shard-1")

        job = self.manager.import_local(LocalImportRequest(source_path=str(shard_source)))

        self.assertEqual(job.status.value, "failed")
        self.assertIn("incomplete GGUF shard set", job.error or "")
        self.assertEqual(self.manager.list_bundles(), [])

    def test_local_import_rejects_mixed_shard_sets(self) -> None:
        shard_source = self.root / "mixed-shard-source"
        write_tiny_gguf(shard_source / "demo-Q4_K_M-00001-of-00002.gguf", name="demo-shard-1")
        write_tiny_gguf(shard_source / "demo-Q4_K_M-00002-of-00002.gguf", name="demo-shard-2")
        write_tiny_gguf(shard_source / "other-Q4_K_M-00001-of-00002.gguf", name="other-shard-1")
        write_tiny_gguf(shard_source / "other-Q4_K_M-00002-of-00002.gguf", name="other-shard-2")

        job = self.manager.import_local(LocalImportRequest(source_path=str(shard_source)))

        self.assertEqual(job.status.value, "failed")
        self.assertIn("mixed GGUF shard sets", job.error or "")
        self.assertEqual(self.manager.list_bundles(), [])

    def test_local_import_rejects_same_shard_names_under_different_dirs(self) -> None:
        shard_source = self.root / "duplicate-name-shards"
        write_tiny_gguf(shard_source / "a" / "demo-Q4_K_M-00001-of-00002.gguf", name="demo-shard-1")
        write_tiny_gguf(shard_source / "b" / "demo-Q4_K_M-00002-of-00002.gguf", name="demo-shard-2")

        job = self.manager.import_local(LocalImportRequest(source_path=str(shard_source)))

        self.assertEqual(job.status.value, "failed")
        self.assertIn("mixed GGUF shard sets", job.error or "")
        self.assertEqual(self.manager.list_bundles(), [])

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
            listed = self.manager.list_bundles()
            self.assertIsNotNone(listed[0].default_configuration_id)
            self.assertEqual(wrapped_put.call_count, 1)  # one-time configuration migration
            wrapped_put.reset_mock()
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
            ".cache/huggingface/download/model.gguf.metadata": b"metadata",
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
        self.assertNotIn(".cache/huggingface/download/model.gguf.metadata", {item.name for item in bundle.files})
        staging = self.hf.calls[0]["dest"]
        self.assertIsInstance(staging, Path)
        self.assertTrue(staging.exists())

    def test_hf_import_reuses_existing_verified_bundle(self) -> None:
        self.hf.files = {
            self.primary.name: self.primary.read_bytes(),
            "demo.mmproj": b"mm",
        }
        with patch.object(bundle_module.shutil, "copy2", wraps=bundle_module.shutil.copy2) as wrapped_copy:
            first = self.manager.import_huggingface(
                HuggingFaceImportRequest(repo_id="org/demo", revision="main")
            )
            first_bundle = self.manager.get_bundle(first.bundle_id or "")
            copy_count = wrapped_copy.call_count
            second = self.manager.import_huggingface(
                HuggingFaceImportRequest(repo_id="org/demo", revision="main")
            )

        self.assertEqual(first.status.value, "complete")
        self.assertEqual(second.status.value, "complete")
        self.assertEqual(second.bundle_id, first.bundle_id)
        self.assertEqual(wrapped_copy.call_count, copy_count)
        self.assertEqual(len(self.manager.list_bundles()), 1)
        self.assertEqual(Path(self.manager.get_bundle(second.bundle_id or "").primary_path or ""), Path(first_bundle.primary_path or ""))

    def test_hf_import_does_not_reuse_damaged_bundle_record(self) -> None:
        self.hf.files = {
            self.primary.name: self.primary.read_bytes(),
            "demo.mmproj": b"mm",
        }
        first = self.manager.import_huggingface(
            HuggingFaceImportRequest(repo_id="org/demo", revision="main")
        )
        first_bundle = self.manager.get_bundle(first.bundle_id or "")
        Path(first_bundle.primary_path or "").unlink()

        second = self.manager.import_huggingface(
            HuggingFaceImportRequest(repo_id="org/demo", revision="main")
        )

        self.assertEqual(second.status.value, "complete")
        self.assertNotEqual(second.bundle_id, first.bundle_id)
        bundles = self.manager.list_bundles()
        self.assertEqual(len(bundles), 2)
        self.assertFalse(next(bundle for bundle in bundles if bundle.id == first.bundle_id).disk_matches)
        self.assertTrue(next(bundle for bundle in bundles if bundle.id == second.bundle_id).disk_matches)

    def test_concurrent_hf_imports_reuse_one_completed_bundle(self) -> None:
        self.hf.files = {
            self.primary.name: self.primary.read_bytes(),
            "demo.mmproj": b"mm",
        }
        request = HuggingFaceImportRequest(repo_id="org/demo", revision="main")

        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = list(pool.map(lambda _index: self.manager.import_huggingface(request), range(2)))

        self.assertEqual([job.status.value for job in jobs], ["complete", "complete"])
        self.assertEqual(jobs[0].bundle_id, jobs[1].bundle_id)
        self.assertEqual(len(self.manager.list_bundles()), 1)

    def test_interrupted_download_has_no_bundle(self) -> None:
        self.hf.error = InterruptedError("download interrupted")
        job = self.manager.import_huggingface(
            HuggingFaceImportRequest(repo_id="org/demo", revision="deadbeef")
        )
        self.assertEqual(job.status.value, "interrupted")
        self.assertIsNone(job.bundle_id)
        self.assertEqual(self.manager.list_bundles(), [])
        staging = self.hf.calls[0]["dest"]
        self.assertIsInstance(staging, Path)
        self.assertTrue(staging.exists())

        retry = self.manager.import_huggingface(
            HuggingFaceImportRequest(repo_id="org/demo", revision="deadbeef")
        )
        self.assertEqual(self.hf.calls[1]["dest"], staging)
        self.assertEqual(retry.status.value, "interrupted")

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
