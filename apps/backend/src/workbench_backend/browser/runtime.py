"""Install a pinned local Playwright MCP worker without ambient Node or npx.

Installation is an explicit setup action. Chat never downloads code. npm's lock
integrity and the official Node archive digest pin everything we execute.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
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
WORKER_VERSION = "0.0.2"
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

    @property
    def worker(self) -> Path:
        return self.package_root / "worker.js"

    @property
    def tool_schemas(self) -> Path:
        return self.package_root / "tool-schemas.json"

    def read_tool_schemas(self) -> list[dict[str, object]]:
        try:
            catalogue = json.loads(self.tool_schemas.read_text(encoding="utf-8"))
            tools = catalogue["tools"]
            if catalogue.get("playwright_mcp_version") != MCP_VERSION or catalogue.get("worker_version") != WORKER_VERSION:
                raise ValueError("Browser schema versions differ")
            if not isinstance(tools, list) or not tools or any(not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("inputSchema"), dict) for item in tools):
                raise ValueError("Browser tool schema catalogue is malformed")
            if len({item["name"] for item in tools}) != len(tools):
                raise ValueError("Duplicate browser tool names")
            return tools
        except (OSError, KeyError, ValueError, TypeError) as exc:
            raise HarnessError("Refresh the optional browser worker to restore its pinned tool catalogue.", code="browser_worker_schema_changed", status_code=409) from exc

    @property
    def chrome(self) -> Path | None:
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        if sys.platform == "win32":
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                        candidates.append(Path(winreg.QueryValue(key, None)))
                except OSError:
                    pass
        return next((candidate for candidate in candidates if candidate.is_file()), None)

    def status(self) -> dict[str, object]:
        supported = sys.platform == "win32" and platform.machine().lower() in {"amd64", "x86_64"}
        installed = self.node.is_file() and self.cli.is_file() and self.worker.is_file()
        if installed:
            # A package version alone cannot attest to this application's typed
            # management worker; a code refresh must explicitly reinstall it.
            try:
                installed = self.worker.read_bytes() == (PACKAGE_MANIFEST / "worker.js").read_bytes()
            except OSError:
                installed = False
        if installed:
            try:
                self.read_tool_schemas()
            except HarnessError:
                installed = False
        chrome = self.chrome if supported else None
        return {
            "supported": supported,
            "installed": installed,
            "node_version": NODE_VERSION,
            "playwright_mcp_version": MCP_VERSION,
            "chrome_available": chrome is not None,
            "chrome_version": self._chrome_version(chrome) if chrome else None,
            "reason": ("unsupported_platform" if not supported else "browser_worker_missing" if not installed else "browser_chrome_missing" if chrome is None else None),
        }

    def require_installed(self) -> tuple[Path, Path]:
        status = self.status()
        if not status["installed"]:
            raise HarnessError("Install the optional browser worker from Chat's + tools menu before using browser tools.", code="browser_worker_missing", status_code=409)
        if not status["chrome_available"]:
            raise HarnessError("Install Google Chrome on this computer before starting the Chat browser.", code="browser_chrome_missing", status_code=409)
        return self.node, self.worker

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
            for name in ("package.json", "package-lock.json", "worker.js", "catalogue.js"):
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
                text=True, timeout=300, check=False, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if completed.returncode or not (package_stage / "node_modules" / "@playwright" / "mcp" / "cli.js").is_file():
                raise HarnessError("The pinned browser package could not be installed. Check network access and retry from Chat's + tools menu.", code="browser_install_failed")
            catalogue = subprocess.run(
                [str(node_stage / "node.exe"), str(package_stage / "catalogue.js")], cwd=package_stage,
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if catalogue.returncode or not (package_stage / "tool-schemas.json").is_file():
                raise HarnessError("The pinned browser tool catalogue could not be generated.", code="browser_worker_schema_changed", status_code=409)
            self._replace(node_stage, self.node_root)
            self._replace(package_stage, self.package_root)
            return self.status()
        finally:
            # `staging` is created immediately under this verified product root.
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _chrome_version(executable: Path) -> str | None:
        if sys.platform != "win32":
            return None
        try:
            from ctypes import wintypes
            version = ctypes.WinDLL("version", use_last_error=True)
            version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
            version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
            ignored = wintypes.DWORD()
            size = version.GetFileVersionInfoSizeW(str(executable), ctypes.byref(ignored))
            if not size:
                return None
            data = ctypes.create_string_buffer(size)
            version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
            version.GetFileVersionInfoW.restype = wintypes.BOOL
            version.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
            version.VerQueryValueW.restype = wintypes.BOOL
            if not version.GetFileVersionInfoW(str(executable), 0, size, data):
                return None
            pointer, length = ctypes.c_void_p(), wintypes.UINT()
            if not version.VerQueryValueW(data, "\\", ctypes.byref(pointer), ctypes.byref(length)):
                return None
            words = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD))
            major_minor, build_patch = words[2], words[3]
            return f"{major_minor >> 16}.{major_minor & 65535}.{build_patch >> 16}.{build_patch & 65535}"
        except (OSError, ValueError):
            return None

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
