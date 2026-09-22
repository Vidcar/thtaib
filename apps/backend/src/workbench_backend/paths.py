"""Portable Local AI Workbench data-root resolution.

On Windows the layout is ``%LOCALAPPDATA%\\LocalAIWorkbench\\`` with
``models\\``, ``runtimes\\``, ``state\\``, ``cases\\``, ``snapshots\\``,
``workspaces\\``, ``knowledge\\``, ``logs\\``, plus ``application.sqlite``
and ``checkpoints.sqlite``. Other platforms use the same names under a
portable data root so tests and smoke can run without claiming a second
product mode.
"""

from __future__ import annotations

import os
import json
import sys
from pathlib import Path

PRODUCT_DATA_DIR = "LocalAIWorkbench"
DATA_ROOT_ENV = "WORKBENCH_DATA_ROOT"
APPLICATION_DB_NAME = "application.sqlite"
CHECKPOINTS_DB_NAME = "checkpoints.sqlite"
SHARED_SECRET_FILENAME = "desktop_backend_shared_secret"


def _base_data_root(
    *,
    environ: dict[str, str] | None = None,
    platform: str | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    override = env.get(DATA_ROOT_ENV)
    if override:
        return Path(override).expanduser()

    current_platform = sys.platform if platform is None else platform
    if current_platform == "win32":
        local_appdata = env.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / PRODUCT_DATA_DIR
        return Path.home() / "AppData" / "Local" / PRODUCT_DATA_DIR

    xdg = env.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / PRODUCT_DATA_DIR
    return Path.home() / ".local" / "share" / PRODUCT_DATA_DIR


def resolve_data_root(*, environ: dict[str, str] | None = None, platform: str | None = None) -> Path:
    root = _base_data_root(environ=environ, platform=platform)
    seen: set[Path] = set()
    while (root / "state" / "active-data-root.json").is_file():
        resolved = root.resolve()
        if resolved in seen or len(seen) >= 8:
            raise ValueError("Invalid restored application root chain")
        seen.add(resolved)
        record = json.loads((root / "state" / "active-data-root.json").read_text(encoding="utf-8"))
        target = Path(record["destination_root"])
        if record.get("version") != 1 or not target.is_absolute() or not (target / APPLICATION_DB_NAME).is_file():
            raise ValueError("The activated restore is unavailable")
        root = target
    return root


class WorkbenchPaths:
    """Resolved on-disk locations for weights, runtimes and records."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or resolve_data_root()).resolve()
        self.models = self.root / "models"
        self.runtimes = self.root / "runtimes"
        self.state = self.root / "state"
        self.cases = self.root / "cases"
        self.snapshots = self.root / "snapshots"
        self.workspaces = self.root / "workspaces"
        self.knowledge = self.root / "knowledge"
        self.logs = self.root / "logs"
        self.application_db = self.root / APPLICATION_DB_NAME
        self.checkpoints_db = self.root / CHECKPOINTS_DB_NAME
        self.desktop_backend_shared_secret = self.state / SHARED_SECRET_FILENAME

    def ensure(self) -> "WorkbenchPaths":
        for path in (
            self.root,
            self.models,
            self.runtimes,
            self.state,
            self.cases,
            self.snapshots,
            self.workspaces,
            self.knowledge,
            self.logs,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self

    def as_public_dict(self) -> dict[str, str]:
        return {
            "root": str(self.root),
            "models": str(self.models),
            "runtimes": str(self.runtimes),
            "state": str(self.state),
            "cases": str(self.cases),
            "snapshots": str(self.snapshots),
            "workspaces": str(self.workspaces),
            "knowledge": str(self.knowledge),
            "logs": str(self.logs),
            "application_db": str(self.application_db),
            "checkpoints_db": str(self.checkpoints_db),
            "windows_layout": (
                r"%LOCALAPPDATA%\LocalAIWorkbench\{models,runtimes,state,cases,snapshots,workspaces,knowledge,logs,application.sqlite,checkpoints.sqlite}"
            ),
        }
