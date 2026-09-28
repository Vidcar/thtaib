"""Concurrent diagnostics and atomic knowledge configuration publication."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from workbench_backend.knowledge.schemas import KnowledgeConfig
from workbench_backend.knowledge.store import KnowledgeStore
from workbench_backend.paths import WorkbenchPaths


class KnowledgeStoreConcurrencyTests(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.paths = WorkbenchPaths(Path(fixture.name)).ensure()
        self.store = KnowledgeStore(self.paths)

    def test_concurrent_first_diagnostics_are_read_only(self):
        ready = threading.Barrier(8, timeout=4)

        def read():
            store = KnowledgeStore(self.paths)
            ready.wait()
            return store.read_config()

        with patch.object(KnowledgeStore, "write_config", side_effect=AssertionError("read wrote defaults")), \
                ThreadPoolExecutor(max_workers=8) as workers:
            results = [future.result(timeout=6) for future in [workers.submit(read) for _ in range(8)]]
        self.assertEqual(results, [KnowledgeConfig()] * 8)
        self.assertFalse(self.store.config_path.exists())

    def test_overlapping_writes_publish_whole_records_from_distinct_temporaries(self):
        self.store._write_json(self.store.config_path, {"original": True})
        ready = threading.Barrier(2, timeout=4)
        original_replace = Path.replace
        temporary_paths = []
        payloads = [{"writer": ident, "record": str(ident) * 32768} for ident in range(2)]

        def replace(path, target):
            self.assertEqual(path.parent, self.store.config_path.parent)
            if path not in temporary_paths:
                self.assertEqual(json.loads(Path(target).read_text(encoding="utf-8")), {"original": True})
                temporary_paths.append(path)
                ready.wait()
            return original_replace(path, target)

        with patch.object(Path, "replace", replace), ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(KnowledgeStore(self.paths)._write_json, self.store.config_path, value) for value in payloads]
            for future in futures:
                future.result(timeout=6)
        self.assertEqual(len(set(temporary_paths)), 2)
        self.assertIn(json.loads(self.store.config_path.read_text(encoding="utf-8")), payloads)
        self.assertFalse(any(self.paths.knowledge.glob("*.tmp")))

    def test_failed_publication_preserves_previous_record_and_removes_temporary(self):
        self.store._write_json(self.store.config_path, {"original": True})
        with patch.object(Path, "replace", side_effect=PermissionError("blocked replacement")), \
                self.assertRaises(PermissionError):
            self.store._write_json(self.store.config_path, {"new": True})
        self.assertEqual(json.loads(self.store.config_path.read_text(encoding="utf-8")), {"original": True})
        self.assertFalse(any(self.paths.knowledge.glob("*.tmp")))

    def test_persistent_windows_sharing_failure_is_bounded_and_preserves_record(self):
        self.store._write_json(self.store.config_path, {"original": True})
        blocked = PermissionError("locked destination")
        blocked.winerror = 32
        with patch.object(Path, "replace", side_effect=blocked) as replace, \
                patch("workbench_backend.knowledge.store.time.sleep") as backoff, \
                self.assertRaises(PermissionError):
            self.store._write_json(self.store.config_path, {"new": True})
        self.assertEqual(replace.call_count, 10)
        self.assertEqual(backoff.call_count, 9)
        self.assertEqual(json.loads(self.store.config_path.read_text(encoding="utf-8")), {"original": True})
        self.assertFalse(any(self.paths.knowledge.glob("*.tmp")))
