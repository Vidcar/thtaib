"""Install a pinned local Playwright MCP worker without ambient Node or npx.

Installation is an explicit setup action. Chat never downloads code. npm's lock
integrity and the official Node archive digest pin everything we execute.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import uuid
import zipfile
from pathlib import Path

from workbench_backend.errors import HarnessError
from workbench_backend.paths import WorkbenchPaths

NODE_VERSION = "24.19.0"
MCP_VERSION = "0.0.82"
NODE_ARCHIVE = f"node-v{NODE_VERSION}-win-x64.zip"
NODE_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/{NODE_ARCHIVE}"
NODE_SHA256 = "57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73"
PACKAGE_MANIFEST = Path(__file__).parent / "worker_package"


class BrowserRuntime:
    def __init__(self, paths: WorkbenchPaths):
        self.root = paths.runtimes / "browser"
        self.node_root = self.root / f"node-v{NODE_VERSION}-win-x64"
        self.package_root = self.root / f"playwright-mcp-{MCP_VERSION}"

    @property
    def node(self) -> Path:
        return self.node_root / "node.exe"

    @property
    def cli(self) -> Path:
        return self.package_root / "node_modules" / "@playwright" / "mcp" / "cli.js"

    def status(self) -> dict[str, object]:
        supported = sys.platform == "win32" and platform.machine().lower() in {"amd64", "x86_64"}
        installed = self.node.is_file() and self.cli.is_file()
        return {
            "supported": supported,
            "installed": installed,
            "node_version": NODE_VERSION,
            "playwright_mcp_version": MCP_VERSION,
            "reason": None if installed else ("unsupported_platform" if not supported else "browser_worker_missing"),
        }

    def require_installed(self) -> tuple[Path, Path]:
        if not self.node.is_file() or not self.cli.is_file():
            raise HarnessError("Install the optional browser worker from Chat's + tools menu before using browser tools.", code="browser_worker_missing", status_code=409)
        return self.node, self.cli

    def install(self) -> dict[str, object]:
        if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
            raise HarnessError("The managed browser worker currently supports Windows x64.", code="browser_worker_unsupported", status_code=409)
        self.root.mkdir(parents=True, exist_ok=True)
        staging = self.root / f".install-{uuid.uuid4().hex}"
        staging.mkdir()
        try:
            archive = staging / NODE_ARCHIVE
            self._download_node(archive)
            node_stage = self._extract_node(archive, staging)
            package_stage = staging / "package"
            package_stage.mkdir()
            for name in ("package.json", "package-lock.json"):
                shutil.copy2(PACKAGE_MANIFEST / name, package_stage / name)
            npm_cli = node_stage / "node_modules" / "npm" / "bin" / "npm-cli.js"
            if not npm_cli.is_file():
                raise HarnessError("The verified Node archive has no npm runtime.", code="browser_install_invalid")
            env = os.environ.copy()
            env["PATH"] = str(node_stage) + os.pathsep + env.get("PATH", "")
            env["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
            completed = subprocess.run(
                [str(node_stage / "node.exe"), str(npm_cli), "ci", "--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund"],
                cwd=package_stage, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=300, check=False,
            )
            if completed.returncode or not (package_stage / "node_modules" / "@playwright" / "mcp" / "cli.js").is_file():
                raise HarnessError("The pinned browser package could not be installed. Check network access and retry from Chat's + tools menu.", code="browser_install_failed")
            self._replace(node_stage, self.node_root)
            self._replace(package_stage, self.package_root)
            return self.status()
        finally:
            # `staging` is created immediately under this verified product root.
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _download_node(destination: Path) -> None:
        digest = hashlib.sha256()
        total = 0
        try:
            with urllib.request.urlopen(NODE_URL, timeout=30) as response, destination.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 100 * 1024 * 1024:
                        raise ValueError("Node archive is unexpectedly large")
                    digest.update(chunk)
                    output.write(chunk)
        except (OSError, TimeoutError, ValueError) as exc:
            raise HarnessError("The pinned Node runtime could not be downloaded.", code="browser_node_download_failed") from exc
        if digest.hexdigest() != NODE_SHA256:
            raise HarnessError("The Node archive failed its pinned SHA-256 check.", code="browser_node_hash_failed")

    @staticmethod
    def _extract_node(archive: Path, staging: Path) -> Path:
        expected = f"node-v{NODE_VERSION}-win-x64"
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                relative = Path(member.filename)
                if not relative.parts or relative.parts[0] != expected or any(part in {"..", ""} for part in relative.parts):
                    raise HarnessError("The Node archive contains an unsafe path.", code="browser_node_archive_invalid")
            package.extractall(staging)
        extracted = staging / expected
        if not (extracted / "node.exe").is_file():
            raise HarnessError("The Node archive is missing node.exe.", code="browser_node_archive_invalid")
        return extracted

    @staticmethod
    def _replace(source: Path, destination: Path) -> None:
        old = destination.with_name(destination.name + f".old-{uuid.uuid4().hex}")
        if destination.exists():
            destination.rename(old)
        try:
            source.rename(destination)
        except BaseException:
            if old.exists():
                old.rename(destination)
            raise
        if old.exists():
            shutil.rmtree(old)
