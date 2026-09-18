"""Read-only GGUF inspection via gguf-py (MOD-002).

Normal import and inspect paths never open a GGUF for write and never call
GGUFWriter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gguf import GGUFReader

from workbench_backend.errors import ManagerError
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.schemas import InspectReport, InspectTensor

OMIT_PREFIXES = ("tokenizer.ggml.tokens", "tokenizer.ggml.scores", "tokenizer.ggml.merges")
MAX_FIELD_CHARS = 4000
READER_MODE = "r"


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)


def inspect_gguf_file(path: Path, *, bundle_id: str) -> InspectReport:
    if not path.is_file():
        raise ManagerError(
            f"GGUF file is missing: {path}",
            code="gguf_missing",
            status_code=404,
        )
    digest = sha256_file(path)
    reader = GGUFReader(str(path), READER_MODE)
    fields: dict[str, Any] = {}
    omitted: list[str] = []
    for name, field in reader.fields.items():
        if name.startswith("GGUF."):
            continue
        if any(name.startswith(prefix) for prefix in OMIT_PREFIXES):
            omitted.append(name)
            continue
        rendered = _jsonable(field.contents())
        text = str(rendered)
        if len(text) > MAX_FIELD_CHARS:
            omitted.append(name)
            continue
        fields[name] = rendered

    tensors = [
        InspectTensor(
            name=tensor.name,
            shape=[int(dim) for dim in list(tensor.shape)],
            n_elements=int(tensor.n_elements),
            n_bytes=int(tensor.n_bytes),
            tensor_type=str(tensor.tensor_type.name)
            if hasattr(tensor.tensor_type, "name")
            else str(tensor.tensor_type),
        )
        for tensor in reader.tensors
    ]
    return InspectReport(
        bundle_id=bundle_id,
        file_path=str(path),
        sha256=digest,
        reader="gguf.GGUFReader",
        reader_mode="r",
        metadata_edited=False,
        architecture=_as_str(fields.get("general.architecture")),
        name=_as_str(fields.get("general.name")),
        quantization_version=_as_int(fields.get("general.quantization_version")),
        file_type=_as_int(fields.get("general.file_type")),
        fields=fields,
        omitted_fields=omitted,
        tensors=tensors,
    )


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
