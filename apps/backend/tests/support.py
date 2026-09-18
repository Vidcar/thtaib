"""Shared test helpers for the model manager."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from gguf import GGUFWriter


def write_tiny_gguf(path: Path, *, name: str = "tiny-test") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = GGUFWriter(str(path), "llama")
    writer.add_name(name)
    writer.add_quantization_version(2)
    writer.add_file_type(0)
    writer.add_tensor("token_embd.weight", np.zeros((2, 2), dtype=np.float32))
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
    return path
