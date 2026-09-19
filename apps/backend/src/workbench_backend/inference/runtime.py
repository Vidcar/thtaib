"""Managed llama-server pin. PATH fallback is unsupported for UAT claims.

The supported Windows GPU path is llama.cpp b11045 CUDA 13.4 (+ cudart).
NVIDIA absence is a clear error; CPU-only is not installed as a silent
GPU path.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Literal

import httpx

from workbench_backend.errors import ManagerError
from workbench_backend.inference.hardware import NvidiaPresent, nvidia_gpu_present
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.schemas import (
    Deployment,
    DeploymentStatus,
    ManagementScope,
    PinRuntimeRequest,
    RuntimeManifest,
)
from workbench_backend.inference.store import RecordStore
from workbench_backend.paths import WorkbenchPaths

LLAMA_CPP_RELEASE_TAG = "b11045"
WINDOWS_CUDA_ASSET = "llama-b11045-bin-win-cuda-13.4-x64.zip"
WINDOWS_CUDART_ASSET = "cudart-llama-bin-win-cuda-13.4-x64.zip"
WINDOWS_CUDA_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/"
    f"{LLAMA_CPP_RELEASE_TAG}/{WINDOWS_CUDA_ASSET}"
)
WINDOWS_CUDART_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/"
    f"{LLAMA_CPP_RELEASE_TAG}/{WINDOWS_CUDART_ASSET}"
)

PINNED_WINDOWS_CUDA = {
    "release_tag": LLAMA_CPP_RELEASE_TAG,
    "platform": "win-x64",
    "flavor": "cuda-13.4",
    "asset_name": WINDOWS_CUDA_ASSET,
    "source_url": WINDOWS_CUDA_URL,
    "companion_asset_name": WINDOWS_CUDART_ASSET,
    "companion_source_url": WINDOWS_CUDART_URL,
    "executable_name": "llama-server.exe",
}

NVIDIA_ABSENT_MESSAGE = (
    "NVIDIA GPU was not detected. The supported managed Windows runtime is "
    f"CUDA 13.4 llama.cpp {LLAMA_CPP_RELEASE_TAG} "
    f"({WINDOWS_CUDA_ASSET} + {WINDOWS_CUDART_ASSET}). "
    "CPU-only is not installed as a silent GPU path. "
    "PATH llama-server is unsupported."
)

PIN_WHILE_RUNNING_MESSAGE = (
    "Cannot pin the managed runtime while a managed llama-server is running. "
    "Stop the deployment first, or retry with stop_first. "
    "A half-finished pin is not recorded as success."
)


class RuntimeInstaller:
    def download(self, url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, follow_redirects=True, timeout=600.0) as response:
            response.raise_for_status()
            with dest.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)


class RuntimeService:
    def __init__(
        self,
        paths: WorkbenchPaths,
        store: RecordStore,
        *,
        installer: RuntimeInstaller | None = None,
        nvidia_present: NvidiaPresent | None = None,
    ) -> None:
        self.paths = paths.ensure()
        self.store = store
        self.installer = installer or RuntimeInstaller()
        self.nvidia_present = nvidia_present or nvidia_gpu_present

    def current(self) -> RuntimeManifest | None:
        return self.store.read_runtime_manifest()

    def require_executable(self) -> Path:
        manifest = self.current()
        if manifest is None or manifest.status != "ready":
            raise ManagerError(
                "No ready managed runtime is pinned. PATH llama-server is unsupported.",
                code="runtime_unpinned",
                status_code=409,
            )
        executable = Path(manifest.executable)
        if not executable.is_file():
            raise ManagerError(
                "Pinned runtime executable is missing. PATH fallback is unsupported.",
                code="runtime_missing",
                status_code=409,
            )
        return executable

    def running_managed_deployments(self) -> list[Deployment]:
        blocking = {
            DeploymentStatus.starting,
            DeploymentStatus.running,
            DeploymentStatus.unhealthy,
        }
        return [
            deployment
            for deployment in self.store.list_deployments()
            if deployment.scope == ManagementScope.managed and deployment.status in blocking
        ]

    def pin(self, request: PinRuntimeRequest | None = None) -> RuntimeManifest:
        request = request or PinRuntimeRequest()
        if self.running_managed_deployments():
            raise ManagerError(
                PIN_WHILE_RUNNING_MESSAGE,
                code="runtime_pin_busy",
                status_code=409,
            )
        if request.local_executable:
            return self._pin_local(Path(request.local_executable).expanduser())
        return self._pin_windows_cuda()

    def _pin_local(self, executable: Path) -> RuntimeManifest:
        source_dir, resolved = _resolve_local_runtime(executable)
        if source_dir is None or resolved is None or not resolved.is_file():
            manifest = RuntimeManifest(
                platform="local",
                flavor="fixture",
                release_tag="local",
                install_dir=str(source_dir if source_dir is not None else executable),
                executable=str(executable),
                status="failed",
                error=f"local executable is missing: {executable}",
            )
            self.store.write_runtime_manifest(manifest)
            return manifest
        digest = sha256_file(resolved)
        install_dir = self.paths.runtimes / "local-pin"
        try:
            _copy_runtime_directory(source_dir, install_dir)
        except OSError as exc:
            manifest = RuntimeManifest(
                platform="local",
                flavor="managed-local",
                release_tag="local",
                install_dir=str(install_dir),
                executable=str(resolved),
                path_fallback="unsupported",
                status="failed",
                error=str(exc),
            )
            self.store.write_runtime_manifest(manifest)
            return manifest
        relative = resolved.resolve().relative_to(source_dir.resolve())
        target = install_dir / relative
        manifest = RuntimeManifest(
            platform="local",
            flavor="managed-local",
            release_tag="local",
            source_url=None,
            asset_name=resolved.name,
            sha256=digest,
            install_dir=str(install_dir),
            executable=str(target),
            path_fallback="unsupported",
            status="ready",
        )
        return self.store.write_runtime_manifest(manifest)

    def _pin_windows_cuda(self) -> RuntimeManifest:
        spec = PINNED_WINDOWS_CUDA
        install_dir = (
            self.paths.runtimes
            / f"llama.cpp-{spec['release_tag']}-{spec['platform']}-{spec['flavor']}"
        )
        if not self.nvidia_present():
            return self._fail_pin(install_dir, spec, NVIDIA_ABSENT_MESSAGE, "failed")
        archive = self.paths.runtimes / spec["asset_name"]
        companion = self.paths.runtimes / spec["companion_asset_name"]
        try:
            self.installer.download(spec["source_url"], archive)
            self.installer.download(spec["companion_source_url"], companion)
            digest = sha256_file(archive)
            companion_digest = sha256_file(companion)
            if install_dir.exists():
                shutil.rmtree(install_dir)
            install_dir.mkdir(parents=True, exist_ok=True)
            _extract_zip(archive, install_dir)
            _extract_zip(companion, install_dir)
            executable = _find_executable(install_dir, spec["executable_name"])
            if executable is None:
                raise ManagerError(
                    "Windows llama-server.exe was not found in the pinned CUDA archive",
                    code="runtime_exe_missing",
                    status_code=500,
                )
            manifest = RuntimeManifest(
                platform=spec["platform"],
                flavor=spec["flavor"],
                release_tag=spec["release_tag"],
                source_url=spec["source_url"],
                asset_name=spec["asset_name"],
                sha256=digest,
                install_dir=str(install_dir),
                executable=str(executable),
                path_fallback="unsupported",
                status="ready",
                companion_asset_name=spec["companion_asset_name"],
                companion_sha256=companion_digest,
            )
            return self.store.write_runtime_manifest(manifest)
        except ManagerError as exc:
            return self._fail_pin(install_dir, spec, exc.message, "failed")
        except (OSError, InterruptedError) as exc:
            return self._fail_pin(install_dir, spec, str(exc), "interrupted")
        except Exception as exc:
            status: Literal["failed", "interrupted"] = (
                "interrupted" if "interrupt" in str(exc).lower() else "failed"
            )
            return self._fail_pin(install_dir, spec, str(exc), status)

    def _fail_pin(
        self,
        install_dir: Path,
        spec: dict[str, str],
        error: str,
        status: Literal["failed", "interrupted"],
    ) -> RuntimeManifest:
        manifest = RuntimeManifest(
            platform=spec["platform"],
            flavor=spec["flavor"],
            release_tag=spec["release_tag"],
            source_url=spec["source_url"],
            asset_name=spec["asset_name"],
            install_dir=str(install_dir),
            executable="",
            path_fallback="unsupported",
            status=status,
            error=error,
            companion_asset_name=spec.get("companion_asset_name"),
        )
        return self.store.write_runtime_manifest(manifest)


def _resolve_local_runtime(path: Path) -> tuple[Path | None, Path | None]:
    if path.is_dir():
        found = _find_executable(path, "llama-server.exe") or _find_executable(path, "llama-server")
        return path, found
    if path.is_file():
        return path.parent, path
    return path.parent if path.parent.exists() else None, None


def _copy_runtime_directory(source_dir: Path, dest_dir: Path) -> None:
    source = source_dir.resolve()
    dest = dest_dir.resolve()
    if source == dest:
        return
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest)


def _extract_zip(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(dest)


def _find_executable(root: Path, name: str) -> Path | None:
    matches = sorted(root.rglob(name))
    return matches[0] if matches else None
