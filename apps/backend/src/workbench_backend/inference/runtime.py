"""Managed llama-server pin. PATH fallback is unsupported for UAT claims."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Literal

import httpx

from workbench_backend.errors import ManagerError
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.schemas import PinRuntimeRequest, RuntimeManifest
from workbench_backend.inference.store import RecordStore
from workbench_backend.paths import WorkbenchPaths

PINNED_WINDOWS = {
    "release_tag": "b11045",
    "platform": "win-x64",
    "flavor": "cpu",
    "asset_name": "llama-b11045-bin-win-cpu-x64.zip",
    "source_url": (
        "https://github.com/ggml-org/llama.cpp/releases/download/"
        "b11045/llama-b11045-bin-win-cpu-x64.zip"
    ),
    "executable_name": "llama-server.exe",
}

class RuntimeInstaller:
    def download(self, url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as response:
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
    ) -> None:
        self.paths = paths.ensure()
        self.store = store
        self.installer = installer or RuntimeInstaller()

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

    def pin(self, request: PinRuntimeRequest | None = None) -> RuntimeManifest:
        request = request or PinRuntimeRequest()
        if request.local_executable:
            return self._pin_local(Path(request.local_executable).expanduser())
        return self._pin_windows()

    def _pin_local(self, executable: Path) -> RuntimeManifest:
        if not executable.is_file():
            manifest = RuntimeManifest(
                platform="local",
                flavor="fixture",
                release_tag="local",
                install_dir=str(executable.parent),
                executable=str(executable),
                status="failed",
                error=f"local executable is missing: {executable}",
            )
            self.store.write_runtime_manifest(manifest)
            return manifest
        digest = sha256_file(executable)
        install_dir = self.paths.runtimes / "local-pin"
        install_dir.mkdir(parents=True, exist_ok=True)
        target = install_dir / executable.name
        if executable.resolve() != target.resolve():
            shutil.copy2(executable, target)
        manifest = RuntimeManifest(
            platform="local",
            flavor="managed-local",
            release_tag="local",
            source_url=None,
            asset_name=executable.name,
            sha256=digest,
            install_dir=str(install_dir),
            executable=str(target),
            path_fallback="unsupported",
            status="ready",
        )
        return self.store.write_runtime_manifest(manifest)

    def _pin_windows(self) -> RuntimeManifest:
        spec = PINNED_WINDOWS
        install_dir = (
            self.paths.runtimes
            / f"llama.cpp-{spec['release_tag']}-{spec['platform']}-{spec['flavor']}"
        )
        archive = self.paths.runtimes / spec["asset_name"]
        try:
            self.installer.download(spec["source_url"], archive)
            digest = sha256_file(archive)
            if install_dir.exists():
                shutil.rmtree(install_dir)
            install_dir.mkdir(parents=True, exist_ok=True)
            _extract_zip(archive, install_dir)
            executable = _find_executable(install_dir, spec["executable_name"])
            if executable is None:
                raise ManagerError(
                    "Windows llama-server.exe was not found in the pinned archive",
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
        )
        return self.store.write_runtime_manifest(manifest)


def _extract_zip(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(dest)


def _find_executable(root: Path, name: str) -> Path | None:
    matches = sorted(root.rglob(name))
    return matches[0] if matches else None
