"""Bounded llama-server process logs under the product data-root logs dir.

Managed starts used to discard stdout/stderr to DEVNULL. A start failure
then surfaced only as "Launched process exited". These helpers keep the
streams in ``logs\\llama-server-<deployment>.log`` and rotate so the
directory cannot grow without bound.
"""

from __future__ import annotations

import threading
from pathlib import Path

PROCESS_LOG_MAX_BYTES = 8 * 1024 * 1024
PROCESS_LOG_BACKUPS = 3
PROCESS_LOGS_DIR_MAX_BYTES = 256 * 1024 * 1024
_LOG_PREFIX = "llama-server-"
_LOG_SUFFIX = ".log"


def deployment_log_path(logs_dir: Path, deployment_id: str) -> Path:
    return logs_dir / f"{_LOG_PREFIX}{deployment_id}{_LOG_SUFFIX}"


def rotate_log_file(
    path: Path,
    *,
    max_bytes: int = PROCESS_LOG_MAX_BYTES,
    backups: int = PROCESS_LOG_BACKUPS,
) -> None:
    """Shift ``path`` to ``path.1`` … ``path.N`` when it has reached ``max_bytes``."""

    if backups < 1 or not path.is_file() or path.stat().st_size < max_bytes:
        return
    oldest = Path(f"{path}.{backups}")
    if oldest.exists():
        oldest.unlink()
    for index in range(backups - 1, 0, -1):
        source = Path(f"{path}.{index}")
        if source.exists():
            source.replace(Path(f"{path}.{index + 1}"))
    path.replace(Path(f"{path}.1"))


def prune_logs_dir(logs_dir: Path, *, max_bytes: int = PROCESS_LOGS_DIR_MAX_BYTES) -> None:
    """Delete oldest llama-server log families until the directory is under the cap."""

    if not logs_dir.is_dir():
        return
    members = [item for item in logs_dir.iterdir() if _is_process_log(item)]
    total = sum(item.stat().st_size for item in members if item.is_file())
    if total <= max_bytes:
        return
    members.sort(key=lambda item: (item.stat().st_mtime, item.name))
    for item in members:
        if total <= max_bytes:
            return
        try:
            size = item.stat().st_size
            item.unlink()
        except OSError:
            continue
        total -= size


def _is_process_log(path: Path) -> bool:
    name = path.name
    if not name.startswith(_LOG_PREFIX):
        return False
    return name.endswith(_LOG_SUFFIX) or ".log." in name


class RotatingLogWriter:
    """Append-only writer that rotates the current file and caps the logs directory."""

    def __init__(
        self,
        path: Path,
        *,
        max_bytes: int = PROCESS_LOG_MAX_BYTES,
        backups: int = PROCESS_LOG_BACKUPS,
        dir_max_bytes: int = PROCESS_LOGS_DIR_MAX_BYTES,
    ) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.backups = backups
        self.dir_max_bytes = dir_max_bytes
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        prune_logs_dir(self.path.parent, max_bytes=self.dir_max_bytes)
        rotate_log_file(self.path, max_bytes=self.max_bytes, backups=self.backups)
        self._handle = self.path.open("ab")

    def write(self, data: bytes) -> None:
        if not data:
            return
        with self._lock:
            if self._handle.closed:
                return
            self._handle.write(data)
            self._handle.flush()
            try:
                size = self._handle.tell()
            except OSError:
                size = self.path.stat().st_size if self.path.is_file() else 0
            if size < self.max_bytes:
                return
            self._handle.close()
            rotate_log_file(self.path, max_bytes=0, backups=self.backups)
            prune_logs_dir(self.path.parent, max_bytes=self.dir_max_bytes)
            self._handle = self.path.open("ab")

    def close(self) -> None:
        with self._lock:
            if not self._handle.closed:
                self._handle.close()


def pump_stream_to_log(stream: object, writer: RotatingLogWriter) -> None:
    """Copy a subprocess pipe to ``writer`` until the pipe closes."""

    read = getattr(stream, "read", None)
    if read is None:
        return
    try:
        while True:
            chunk = read(4096)
            if not chunk:
                return
            writer.write(chunk)
    except OSError:
        return
    finally:
        writer.close()
        close = getattr(stream, "close", None)
        if close is not None:
            try:
                close()
            except OSError:
                pass
