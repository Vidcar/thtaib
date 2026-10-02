"""A known quantization token remains visible when a version dot precedes it."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workbench_backend.inference.bundles import detect_quantization

from tests.support import write_tiny_gguf


class QuantizationTokenTests(unittest.TestCase):
    def test_known_token_after_a_dot_stays_known_and_unknown_names_stay_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = write_tiny_gguf(Path(temporary) / "Qwen3.5-0.8B.Q4_K_M.gguf", name="qwen")
        self.assertEqual(detect_quantization([path.name]), "Q4_K_M")
        self.assertIsNone(detect_quantization(["custom-weights.gguf"]))


if __name__ == "__main__":
    unittest.main()
