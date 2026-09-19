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
from collections.abc import Callable
from pathlib import Path

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
