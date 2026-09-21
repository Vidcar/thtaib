"""Content hashes for recorded files. Records link to files; they do not store weights."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from pathlib import Path
from threading import RLock
from collections.abc import Callable
from workbench_backend.errors import ManagerError

CHUNK_SIZE = 1024 * 1024
FINGERPRINT_SIZE = 64 * 1024
_CACHE_MAX = 64
_HASH_CACHE: OrderedDict[tuple[str, int, int, int, int, int, str], str] = OrderedDict()
_HASH_CACHE_LOCK = RLock()
_HASH_IO_LOCK = RLock()


def _fingerprint(path: Path, size: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read(FINGERPRINT_SIZE))
        if size > FINGERPRINT_SIZE:
            handle.seek(max(size - FINGERPRINT_SIZE, 0))
            digest.update(handle.read(FINGERPRINT_SIZE))
    return digest.hexdigest()


def _cache_key(path: Path) -> tuple[str, int, int, int, int, int, str]:
    stat = path.stat()
    return (
        str(path.resolve()),
        stat.st_size,
        stat.st_mtime_ns,
        stat.st_ctime_ns,
        stat.st_dev,
        stat.st_ino,
        _fingerprint(path, stat.st_size),
    )


def sha256_file(path: Path, cancel_check: Callable[[], bool] | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            if cancel_check is not None and cancel_check():
                raise ManagerError("Import was stopped before it was made ready.", code="import_cancelled", status_code=409)
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def cached_sha256_file(path: Path) -> str:
    """Return a SHA-256 digest, reusing it only while a lightweight file key matches."""

    for _ in range(2):
        key = _cache_key(path)
        with _HASH_CACHE_LOCK:
            cached = _HASH_CACHE.get(key)
            if cached is not None:
                _HASH_CACHE.move_to_end(key)
                return cached

        with _HASH_IO_LOCK:
            key = _cache_key(path)
            with _HASH_CACHE_LOCK:
                cached = _HASH_CACHE.get(key)
                if cached is not None:
                    _HASH_CACHE.move_to_end(key)
                    return cached

            digest = sha256_file(path)
            if key != _cache_key(path):
                continue

            with _HASH_CACHE_LOCK:
                _HASH_CACHE[key] = digest
                _HASH_CACHE.move_to_end(key)
                while len(_HASH_CACHE) > _CACHE_MAX:
                    _HASH_CACHE.popitem(last=False)
            return digest
    raise OSError(f"File changed while hashing: {path}")
