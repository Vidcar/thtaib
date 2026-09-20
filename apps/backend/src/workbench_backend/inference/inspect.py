"""Read-only GGUF inspection via gguf-py (MOD-002).

Normal import and inspect paths never open a GGUF for write and never call
GGUFWriter.
"""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Any

from gguf import GGUFReader

from workbench_backend.errors import ManagerError
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.schemas import GgufRuntimeMetadata, InspectReport, InspectTensor

OMIT_PREFIXES = ("tokenizer.ggml.tokens", "tokenizer.ggml.scores", "tokenizer.ggml.merges")
MAX_FIELD_CHARS = 4000
READER_MODE = "r"


class _RuntimeMetadataReader(GGUFReader):
    """gguf-py KV reader for UI runtime controls.

    The pinned ``gguf.GGUFReader`` owns GGUF header, endian and metadata
    parsing. Its ``__init__`` currently calls private ``_build_tensor_info``
    and then ``_build_tensors``; some real models use newer tensor type enums
    than this package knows. Runtime controls only need metadata, so this
    subclass keeps gguf-py parsing and suppresses only tensor construction.
    """

    def _build_tensors(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _InspectReader(GGUFReader):
    """Full gguf-py reader that closes its mmap if tensor parsing fails."""

    def _build_tensors(self, *args: Any, **kwargs: Any) -> None:
        try:
            return super()._build_tensors(*args, **kwargs)
        except ValueError:
            _close_reader(self)
            raise


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
    try:
        reader = _InspectReader(str(path), READER_MODE)
    except ValueError as exc:
        reason = str(exc)
        gc.collect()
        raise ManagerError(
            "This model's file format cannot be fully inspected by the installed reader. Model setup may still be available.",
            code="gguf_inspect_unsupported",
            status_code=409,
            details={"reason": reason},
        ) from None
    try:
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
    finally:
        _close_reader(reader)
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


def read_gguf_runtime_metadata(path: Path) -> GgufRuntimeMetadata:
    """Read the small GGUF fields needed for runtime controls without hashing the file."""

    if not path.is_file():
        raise ManagerError(
            f"GGUF file is missing: {path}",
            code="gguf_missing",
            status_code=404,
        )
    reader = _RuntimeMetadataReader(str(path), READER_MODE)
    try:
        fields = {
            name: _jsonable(field.contents())
            for name, field in reader.fields.items()
            if name in {"general.architecture", "general.name"} or name.endswith((".context_length", ".block_count"))
        }
    finally:
        _close_reader(reader)
    architecture = _as_str(fields.get("general.architecture"))
    prefix = f"{architecture}." if architecture else None
    context_length = _as_int(fields.get(f"{prefix}context_length")) if prefix else None
    block_count = _as_int(fields.get(f"{prefix}block_count")) if prefix else None
    return GgufRuntimeMetadata(
        architecture=architecture,
        name=_as_str(fields.get("general.name")),
        context_length=context_length if context_length is not None and context_length > 0 else None,
        block_count=block_count if block_count is not None and block_count > 0 else None,
    )


def _close_reader(reader: GGUFReader) -> None:
    mmap = getattr(getattr(reader, "data", None), "_mmap", None)
    if mmap is not None:
        mmap.close()


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
