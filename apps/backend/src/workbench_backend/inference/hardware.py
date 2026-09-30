"""Host GPU detection for the supported Windows CUDA runtime pin.

A missing NVIDIA GPU is a clear error. It is not permission to install a
CPU-only archive and call it the GPU path. PATH llama-server stays
unsupported.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import csv
import math
from collections.abc import Callable
from pathlib import Path

import psutil

from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import HardwareDeviceMemory, HardwareMemoryObservation

NvidiaPresent = Callable[[], bool]


def nvidia_gpu_present() -> bool:
    """Return True when an NVIDIA GPU is visible on this host."""
    if _nvidia_smi_lists_gpu():
        return True
    return sys.platform == "win32" and _windows_nvidia_driver_present()


def _nvidia_smi_lists_gpu() -> bool:
    candidates: list[str] = []
    found = shutil.which("nvidia-smi")
    if found:
        candidates.append(found)
    if sys.platform == "win32":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        bundled = program_files / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe"
        if bundled.is_file():
            candidates.append(str(bundled))
    seen: set[str] = set()
    for executable in candidates:
        if executable in seen:
            continue
        seen.add(executable)
        try:
            completed = subprocess.run(  # noqa: S603 - vendor nvidia-smi path only
                [executable, "-L"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        output = f"{completed.stdout or ''}{completed.stderr or ''}"
        if completed.returncode == 0 and "GPU" in output:
            return True
    return False


def _windows_nvidia_driver_present() -> bool:
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    return (system_root / "System32" / "nvcuda.dll").is_file()


class HardwareObserver:
    """Short-lived telemetry cache; unavailable memory never becomes zero."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cached: HardwareMemoryObservation | None = None
        self._checked = 0.0
        self._gpu_success = 0.0

    def observe(self, *, refresh: bool = False, max_age: float = 5.0) -> HardwareMemoryObservation:
        with self._lock:
            now = time.monotonic()
            if self._cached is not None and not refresh and now - self._checked < max_age:
                return self._cached.model_copy(deep=True)
            reasons: list[str] = []
            devices: list[HardwareDeviceMemory] = []
            gpu_budget_incomplete = False
            executable = shutil.which("nvidia-smi")
            if executable is None and sys.platform == "win32":
                candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe"
                executable = str(candidate) if candidate.is_file() else None
            if executable:
                try:
                    completed = subprocess.run([executable, "--query-gpu=uuid,name,memory.total,memory.free,memory.used", "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, timeout=2, check=False, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                    if completed.returncode or len(completed.stdout) > 16384:
                        raise ValueError("GPU memory telemetry unavailable")
                    rows = list(csv.reader(completed.stdout.splitlines()))
                    gpu_budget_incomplete = len(rows) > 16
                    for row in rows[:16]:
                        if len(row) not in (4, 5):
                            gpu_budget_incomplete = True
                            continue
                        identity, name, total, free = (part.strip() for part in row[:4])
                        used = row[4].strip() if len(row) == 5 else "N/A"
                        if not identity or not name:
                            gpu_budget_incomplete = True
                            continue
                        def size(value: str) -> int | None:
                            try:
                                parsed = float(value)
                                return int(parsed * 1024 * 1024) if math.isfinite(parsed) and 0 <= parsed < 1024 * 1024 else None
                            except (ValueError, OverflowError):
                                return None
                        total_bytes = size(total)
                        if total_bytes == 0:
                            total_bytes = None
                        available_bytes, used_bytes = size(free), size(used)
                        if total_bytes is None or available_bytes is not None and available_bytes > total_bytes:
                            available_bytes = None
                        if total_bytes is None or used_bytes is not None and used_bytes > total_bytes:
                            used_bytes = None
                        devices.append(HardwareDeviceMemory(id=identity, name=name, total_bytes=total_bytes,
                            available_bytes=available_bytes, used_bytes=used_bytes))
                    if not devices:
                        raise ValueError("GPU memory telemetry unavailable")
                    self._gpu_success = now
                except (OSError, subprocess.TimeoutExpired, ValueError):
                    reasons.append("GPU memory could not be observed; retry to refresh.")
            else:
                reasons.append("NVIDIA memory telemetry is unavailable on this machine.")
            stale = gpu_budget_incomplete
            if not devices and self._cached and self._cached.gpu_devices:
                # Previous facts stay visibly dated, never masquerade as a fresh budget.
                devices = self._cached.gpu_devices
                stale = True
            gpu_stale = stale or not devices or any(device.used_bytes is None or device.total_bytes is None for device in devices)
            gpu_observed_at = self._cached.gpu_observed_at if gpu_stale and self._cached else None
            if not gpu_stale:
                gpu_observed_at = utc_now()
            total = available = None
            try:
                memory = psutil.virtual_memory()
                total, available = int(memory.total), int(memory.available)
                if total <= 0 or not 0 <= available <= total:
                    raise ValueError("RAM memory telemetry is invalid")
            except (OSError, RuntimeError, ValueError, OverflowError, psutil.Error):
                total = available = None
                reasons.append("RAM memory could not be observed.")
            ram_stale = total is None or available is None
            ram_observed_at = self._cached.ram_observed_at if ram_stale and self._cached else None
            if not ram_stale:
                ram_observed_at = utc_now()
            observed_at = self._cached.observed_at if stale and self._cached else utc_now()
            observation = HardwareMemoryObservation(observed_at=observed_at, source="nvidia-smi + psutil",
                gpu_devices=devices, ram_total_bytes=total, ram_available_bytes=available, reasons=reasons,
                stale=stale or bool(devices and now - self._gpu_success > 15),
                gpu_observed_at=gpu_observed_at, gpu_stale=gpu_stale,
                ram_observed_at=ram_observed_at, ram_stale=ram_stale)
            self._cached, self._checked = observation, time.monotonic()
            return observation.model_copy(deep=True)
