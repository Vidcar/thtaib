"""Read-only GGUF inspection via gguf-py.

Normal import and inspect paths never open a GGUF for write and never call
GGUFWriter.
"""

from __future__ import annotations

import gc
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
import math
import struct
from pathlib import Path
from threading import RLock
from typing import Any

from gguf import GGUFReader
from gguf.constants import GGMLQuantizationType, GGML_QUANT_SIZES

from workbench_backend.errors import ManagerError
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.hashes import _cache_key
from workbench_backend.inference.schemas import GgufRuntimeMetadata, InspectReport, InspectTensor

OMIT_PREFIXES = ("tokenizer.ggml.tokens", "tokenizer.ggml.scores", "tokenizer.ggml.merges")
MAX_FIELD_CHARS = 4000
READER_MODE = "r"
MAX_METADATA_BYTES = 16 * 1024 * 1024
_DIRECTORY_CACHE: OrderedDict[tuple, tuple["GgufFields", int | None]] = OrderedDict()
_DIRECTORY_LOCK = RLock()


@dataclass(frozen=True)
class GgufTensorMetadata:
    """A directory entry; never maps or reads the tensor's weight bytes."""

    name: str
    shape: tuple[int, ...]
    tensor_type: int
    n_bytes: int | None


class GgufFields(dict[str, Any]):
    """GGUF values with non-wire directory facts for allocation previews."""

    tensors: tuple[GgufTensorMetadata, ...]

    def __init__(self, values=None, *, tensors=()) -> None:
        super().__init__(values or {})
        self.tensors = tuple(tensors)


def tensor_metadata(name: str, shape: tuple[int, ...], kind: int) -> GgufTensorMetadata:
    size = None
    try:
        block, item_size = GGML_QUANT_SIZES[GGMLQuantizationType(kind)]
        if shape and all(0 < item <= 2**40 for item in shape) and shape[0] % block == 0:
            size = math.prod(shape) // block * item_size
    except (ValueError, KeyError):
        pass
    return GgufTensorMetadata(name, shape, kind, size)


class IncompleteMetadata(ValueError):
    pass


def parse_gguf_directory(payload: bytes) -> tuple[dict[str, Any], int | None]:
    """Bounded structural inspection; use gguf's quant block sizes, not guessed bits."""
    offset = 0
    endian = "<"

    def take(size: int) -> bytes:
        nonlocal offset
        if size < 0 or size > MAX_METADATA_BYTES or offset + size > MAX_METADATA_BYTES:
            raise ValueError("GGUF metadata exceeds the inspection budget")
        if offset + size > len(payload):
            raise IncompleteMetadata("More GGUF metadata is required")
        result = payload[offset:offset + size]
        offset += size
        return result

    def number(fmt: str):
        return struct.unpack(endian + fmt, take(struct.calcsize(fmt)))[0]

    def string(*, keep: bool = True):
        size = number("Q")
        raw = take(size)
        return raw.decode("utf-8") if keep else None

    def value(kind: int, *, keep: bool = True):
        formats = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
        if kind in formats:
            result = number(formats[kind])
            return result if keep else None
        if kind == 8:
            return string(keep=keep)
        if kind == 9:
            element, count = number("I"), number("Q")
            if count > MAX_METADATA_BYTES or element == 9:
                raise ValueError("Unsupported GGUF metadata array")
            if element in formats:
                raw = take(struct.calcsize(formats[element]) * count)
                return list(struct.unpack(endian + str(count) + formats[element], raw)) if keep else None
            if keep:
                return [value(element) for _ in range(count)]
            for _ in range(count):
                value(element, keep=False)
            return None
        raise ValueError("Unknown GGUF metadata type")

    if take(4) != b"GGUF":
        raise ValueError("Not a GGUF file")
    raw_version = take(4)
    version = struct.unpack("<I", raw_version)[0]
    if version not in {2, 3}:
        endian = ">"
        version = struct.unpack(">I", raw_version)[0]
    if version not in {2, 3}:
        raise ValueError("Unsupported GGUF version")
    tensor_count, field_count = number("Q"), number("Q")
    if tensor_count > 1000000 or field_count > 1000000:
        raise ValueError("Invalid GGUF directory count")
    fields = GgufFields()
    for _ in range(field_count):
        name = string()
        if len(name) > 1024:
            raise ValueError("Invalid GGUF metadata key")
        kind = number("I")
        keep = not name.startswith("tokenizer.") or name == "tokenizer.chat_template"
        entry = value(kind, keep=keep)
        if keep:
            fields[name] = entry
    total = 0
    known = True
    tensors = []
    for _ in range(tensor_count):
        name = string()
        dimensions = number("I")
        if not 1 <= dimensions <= 4:
            raise ValueError("Invalid GGUF tensor dimensions")
        shape = [number("Q") for _ in range(dimensions)]
        kind, _tensor_offset = number("I"), number("Q")
        tensor = tensor_metadata(name, tuple(shape), kind)
        tensors.append(tensor)
        if tensor.n_bytes is None:
            known = False
        else:
            total += tensor.n_bytes
    fields.tensors = tuple(tensors)
    return fields, total if known else None


def invalidate_gguf_metadata(path: Path) -> None:
    """An explicit refresh invalidates just this file's cached directory."""
    identity = str(path.resolve())
    with _DIRECTORY_LOCK:
        for key in list(_DIRECTORY_CACHE):
            if key[0] == identity:
                del _DIRECTORY_CACHE[key]


class _RuntimeMetadataReader(GGUFReader):
    """gguf-py KV reader for UI runtime controls.

    The pinned ``gguf.GGUFReader`` owns GGUF header, endian and metadata
    parsing. Its ``__init__`` currently calls private ``_build_tensor_info``
    and then ``_build_tensors``; some real models use newer tensor type enums
    than this package knows. Runtime controls only need metadata, so this
    subclass keeps gguf-py parsing and suppresses only tensor construction.
    """

    def _build_tensors(self, _offset: int, fields: list[Any]) -> None:
        # Preserve names/shapes without constructing tensors or decoding newer types.
        self.tensor_metadata = tuple(
            tensor_metadata(bytes(field.parts[1]).decode("utf-8", errors="replace"),
                            tuple(int(value) for value in field.parts[3]), int(field.parts[4][0]))
            for field in fields
        )
        self.has_mtp_tensors = any(
            tensor.name.endswith(".nextn.eh_proj.weight") for tensor in self.tensor_metadata
        )


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
    fields, _ = read_gguf_directory(path)
    architecture = _as_str(fields.get("general.architecture"))
    prefix = f"{architecture}." if architecture else None
    context_length = _as_int(fields.get(f"{prefix}context_length")) if prefix else None
    block_count = _as_int(fields.get(f"{prefix}block_count")) if prefix else None
    return GgufRuntimeMetadata(
        architecture=architecture,
        name=_as_str(fields.get("general.name")),
        context_length=context_length if context_length is not None and context_length > 0 else None,
        block_count=block_count if block_count is not None and block_count > 0 else None,
        chat_template=_as_str(fields.get("tokenizer.chat_template")),
        nextn_predict_layers=_as_int(fields.get(f"{prefix}nextn_predict_layers")) if prefix else None,
        has_mtp_tensors=any(tensor.name.endswith(".nextn.eh_proj.weight") for tensor in fields.tensors),
    )


def read_gguf_directory(path: Path, *, refresh: bool = False) -> tuple[GgufFields, int | None]:
    """Cache detached metadata by lightweight file identity, not whole-file hashes."""
    if refresh:
        invalidate_gguf_metadata(path)
    identity = _cache_key(path)
    with _DIRECTORY_LOCK:
        cached = _DIRECTORY_CACHE.get(identity)
        if cached is not None:
            _DIRECTORY_CACHE.move_to_end(identity)
            return deepcopy(cached)
        # The stock reader builds many numpy objects for a large vocabulary even
        # when tensors are disabled. The existing bounded directory parser skips
        # those token arrays; ordinary previews do not need their contents.
        try:
            with path.open("rb") as handle:
                fields, weights = parse_gguf_directory(handle.read(MAX_METADATA_BYTES))
        except (IncompleteMetadata, ValueError) as exc:
            if not isinstance(exc, IncompleteMetadata) and "exceeds the inspection budget" not in str(exc):
                raise
            # Large metadata remains usable through the installed upstream reader.
            reader = _RuntimeMetadataReader(str(path), READER_MODE)
            try:
                fields = GgufFields({
                    name: _jsonable(field.contents()) for name, field in reader.fields.items()
                    if not name.startswith(("GGUF.", "tokenizer.")) or name == "tokenizer.chat_template"
                }, tensors=reader.tensor_metadata)
                weights = (sum(tensor.n_bytes for tensor in fields.tensors)
                           if all(tensor.n_bytes is not None for tensor in fields.tensors) else None)
            finally:
                _close_reader(reader)
        if _cache_key(path) != identity:
            raise ValueError("Model files changed during metadata inspection. Refresh to retry.")
        cached = fields, weights
        _DIRECTORY_CACHE[identity] = cached
        while len(_DIRECTORY_CACHE) > 32:
            _DIRECTORY_CACHE.popitem(last=False)
        return deepcopy(cached)


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
