"""Hash caching used by model-bundle verification."""

from __future__ import annotations

import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from workbench_backend.inference import hashes


class HashTests(unittest.TestCase):
    def setUp(self) -> None:
        hashes._HASH_CACHE.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "model.gguf"
        self.path.write_bytes(b"one")

    def tearDown(self) -> None:
        hashes._HASH_CACHE.clear()
        self.tmp.cleanup()

    def test_cached_sha256_reuses_digest_while_stat_is_unchanged(self) -> None:
        original = hashes.sha256_file
        with patch.object(hashes, "sha256_file", wraps=original) as wrapped:
            first = hashes.cached_sha256_file(self.path)
            second = hashes.cached_sha256_file(self.path)
        self.assertEqual(first, second)
        self.assertEqual(wrapped.call_count, 1)

    def test_cached_sha256_rehashes_after_same_size_change(self) -> None:
        first = hashes.cached_sha256_file(self.path)
        self.path.write_bytes(b"two")
        second = hashes.cached_sha256_file(self.path)
        self.assertNotEqual(first, second)

    def test_cached_sha256_rehashes_after_replacement(self) -> None:
        first = hashes.cached_sha256_file(self.path)
        replacement = self.path.with_suffix(".tmp")
        replacement.write_bytes(b"two")
        replacement.replace(self.path)
        second = hashes.cached_sha256_file(self.path)
        self.assertNotEqual(first, second)

    def test_parallel_cache_miss_hashes_once(self) -> None:
        original = hashes.sha256_file

        def slow_hash(path: Path) -> str:
            time.sleep(0.05)
            return original(path)

        with patch.object(hashes, "sha256_file", side_effect=slow_hash) as wrapped:
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(hashes.cached_sha256_file, [self.path] * 4))

        self.assertEqual(len(set(results)), 1)
        self.assertEqual(wrapped.call_count, 1)

    def test_file_change_during_hash_retries(self) -> None:
        original = hashes.sha256_file
        calls = 0

        def changing_hash(path: Path) -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                path.write_bytes(b"two")
            return original(path)

        with patch.object(hashes, "sha256_file", side_effect=changing_hash):
            digest = hashes.cached_sha256_file(self.path)

        self.assertEqual(calls, 2)
        self.assertEqual(digest, hashes.sha256_file(self.path))


if __name__ == "__main__":
    unittest.main()
