"""Protocol and exact DLL identity for the native allocation subprocess."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from workbench_backend.inference.hashes import cached_sha256_file, sha256_file

PROTOCOL = 1
RELEASE = "b11045"
COMMIT = "2b1847030"
EXECUTABLE = "workbench-memory-planner.exe" if sys.platform == "win32" else "workbench-memory-planner"
REQUIRED_DLLS = frozenset({"llama.dll", "llama-common.dll", "mtmd.dll", "ggml.dll", "ggml-base.dll"})


def native_fingerprint(directory: Path) -> str:
    """Hash every exact native DLL; stat-aware digests avoid repeat 700MB reads."""
    libraries = sorted(directory.glob("*.dll"))
    if not REQUIRED_DLLS.issubset({path.name for path in libraries}):
        raise ValueError("The exact native allocation libraries are unavailable.")
    digests = {path.name: cached_sha256_file(path) for path in libraries}
    return hashlib.sha256(json.dumps(digests, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def preview_environment() -> dict[str, str]:
    """Saved CLI settings own previews; ambient server/backend knobs cannot.

    Keep OS, driver and visible-device selection, but remove native argument,
    backend override/plugin and remote credential environments. The adapter
    accepts local artifacts and does not invoke service/network facilities.
    """
    return {key: value for key, value in os.environ.items()
            if not key.upper().startswith(("LLAMA_", "GGML_", "MTMD_", "HF_", "HUGGING_FACE_"))}


def planner_manifest_fields(path: Path, runtime_directory: Path) -> dict:
    path = path.resolve()
    if path.parent != runtime_directory.resolve() or not path.is_file():
        raise ValueError("The allocation helper must be installed beside the exact runtime libraries.")
    completed = subprocess.run([str(path), "--workbench-version"], capture_output=True,
        timeout=5, encoding="utf-8", errors="replace", env=preview_environment(),
        cwd=runtime_directory, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    if completed.returncode or len(completed.stdout) + len(completed.stderr) > 16384:
        raise ValueError("The native allocation helper protocol could not be verified.")
    try:
        version = json.loads(completed.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError("The native allocation helper protocol could not be verified.") from exc
    fingerprint = native_fingerprint(runtime_directory)
    if (version.get("protocol") != PROTOCOL or version.get("native_build") != 11045
            or version.get("native_commit") != COMMIT or version.get("native_fingerprint") != fingerprint):
        raise ValueError("The allocation helper and exact pinned runtime do not match.")
    return {"memory_planner_path": str(path), "memory_planner_sha256": sha256_file(path),
            "memory_planner_protocol": PROTOCOL, "memory_planner_native_fingerprint": fingerprint}


def require_planner(manifest) -> Path:
    if (manifest is None or manifest.status != "ready" or manifest.release_tag != RELEASE
            or getattr(manifest, "memory_planner_protocol", None) != PROTOCOL):
        raise ValueError("The pinned native allocation helper is unavailable.")
    path = Path(getattr(manifest, "memory_planner_path", "") or "")
    directory = Path(manifest.executable).resolve().parent
    if (not path.is_file() or path.resolve().parent != directory or
            cached_sha256_file(path) != getattr(manifest, "memory_planner_sha256", None)):
        raise ValueError("The pinned native allocation helper is missing or changed.")
    if native_fingerprint(directory) != getattr(manifest, "memory_planner_native_fingerprint", None):
        raise ValueError("The pinned native allocation libraries changed; the preview is unavailable.")
    return path
