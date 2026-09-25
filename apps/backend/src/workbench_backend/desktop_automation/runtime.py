"""Acquire the optional, pinned Microsoft WinApp CLI worker.

The CLI is not fetched during agent tool dispatch. An authenticated setup action
can call ``install``; ordinary runs only use an already verified installation.
The package checksum is pinned to Microsoft's v0.7.0 GitHub release asset.
"""

from __future__ import annotations

import hashlib
import os
import platform
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

from workbench_backend.paths import WorkbenchPaths

WINAPP_VERSION = "0.7.0"
_RELEASE_BASE = "https://github.com/microsoft/winappCli/releases/download/v0.7.0"
_RELEASES = {
    "x64": (
        "winappcli-x64.zip",
        "236e35173f85a88a62cb030bdc07db6590fb7790514d530a050482a0da80313b",
    ),
    "arm64": (
        "winappcli-arm64.zip",
        "37532ac2a7fd50234230b3aa21605133491a289cb585fe6340442e2eb97956b5",
    ),
}
_MAX_ARCHIVE_BYTES = 110_000_000
_MAX_EXPANDED_BYTES = 500_000_000


class WinAppRuntimeError(RuntimeError):
    """The optional pinned worker is unavailable or failed validation."""


def _architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "x64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    raise WinAppRuntimeError(f"WinApp CLI v{WINAPP_VERSION} has no worker for {machine or 'this architecture'}.")


class WinAppCliRuntime:
    def __init__(self, paths: WorkbenchPaths, *, binary_override: Path | None = None) -> None:
        self.paths = paths
        self.binary_override = binary_override.resolve() if binary_override else None

    @property
    def root(self) -> Path:
        return self.paths.runtimes / "winappcli" / WINAPP_VERSION / _architecture()

    def command_path(self) -> Path:
        if os.name != "nt":
            raise WinAppRuntimeError("Windows window testing is available only on Windows.")
        path = self.binary_override or self.root / "winapp.exe"
        if not path.is_file():
            raise WinAppRuntimeError("The optional WinApp CLI 0.7.0 worker is not installed.")
        try:
            completed = subprocess.run(
                [str(path), "--version"], capture_output=True, text=True,
                timeout=20, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env={**os.environ, "WINAPP_CLI_TELEMETRY_OPTOUT": "1"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WinAppRuntimeError("The WinApp CLI worker could not be started.") from exc
        if completed.returncode != 0 or completed.stdout.strip().splitlines()[-1:] != [WINAPP_VERSION]:
            raise WinAppRuntimeError(f"The WinApp CLI worker must be version {WINAPP_VERSION}.")
        return path

    def available(self) -> bool:
        try:
            self.command_path()
        except WinAppRuntimeError:
            return False
        return True

    def install(self) -> Path:
        """Install from a checked release archive; never overwrite an existing runtime."""
        if os.name != "nt":
            raise WinAppRuntimeError("Windows window testing is available only on Windows.")
        if self.binary_override is not None:
            return self.command_path()
        target = self.root
        if target.exists():
            return self.command_path()
        archive_name, expected_sha256 = _RELEASES[_architecture()]
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="winappcli-install-", dir=target.parent) as temporary:
            temporary_path = Path(temporary)
            archive = temporary_path / archive_name
            digest = hashlib.sha256()
            size = 0
            try:
                with urlopen(f"{_RELEASE_BASE}/{archive_name}", timeout=60) as response, archive.open("wb") as output:
                    while chunk := response.read(1_048_576):
                        size += len(chunk)
                        if size > _MAX_ARCHIVE_BYTES:
                            raise WinAppRuntimeError("The WinApp CLI download exceeded the pinned archive size limit.")
                        digest.update(chunk)
                        output.write(chunk)
            except OSError as exc:
                raise WinAppRuntimeError("The WinApp CLI download failed.") from exc
            if digest.hexdigest() != expected_sha256:
                raise WinAppRuntimeError("The WinApp CLI download did not match Microsoft's pinned release checksum.")
            unpacked = temporary_path / "unpacked"
            unpacked.mkdir()
            try:
                with zipfile.ZipFile(archive) as source:
                    infos = source.infolist()
                    if sum(item.file_size for item in infos) > _MAX_EXPANDED_BYTES or len(infos) > 2_000:
                        raise WinAppRuntimeError("The WinApp CLI archive exceeded its extraction limit.")
                    for item in infos:
                        destination = (unpacked / item.filename).resolve()
                        if not destination.is_relative_to(unpacked.resolve()) or stat.S_ISLNK(item.external_attr >> 16):
                            raise WinAppRuntimeError("The WinApp CLI archive has an unsafe entry.")
                        if item.is_dir():
                            destination.mkdir(parents=True, exist_ok=True)
                        else:
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            with source.open(item) as src, destination.open("wb") as dst:
                                while chunk := src.read(1_048_576):
                                    dst.write(chunk)
            except (OSError, zipfile.BadZipFile) as exc:
                raise WinAppRuntimeError("The WinApp CLI archive could not be extracted.") from exc
            if not (unpacked / "winapp.exe").is_file():
                raise WinAppRuntimeError("The pinned WinApp CLI archive did not contain winapp.exe.")
            try:
                unpacked.replace(target)
            except OSError as exc:
                if not target.exists():
                    raise WinAppRuntimeError("The WinApp CLI worker could not be installed.") from exc
        return self.command_path()
