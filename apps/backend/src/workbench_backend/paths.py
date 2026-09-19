"""Portable Local AI Workbench data-root resolution.

On Windows the layout is ``%LOCALAPPDATA%\\LocalAIWorkbench\\`` with
``models\\``, ``runtimes\\``, ``state\\``, ``cases\\``, ``snapshots\\``,
``workspaces\\``, ``knowledge\\``, plus ``application.sqlite`` and
``checkpoints.sqlite``. Other platforms use the same names under a portable
data root so tests and smoke can run without claiming a second product mode.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PRODUCT_DATA_DIR = "LocalAIWorkbench"
DATA_ROOT_ENV = "WORKBENCH_DATA_ROOT"
APPLICATION_DB_NAME = "application.sqlite"
CHECKPOINTS_DB_NAME = "checkpoints.sqlite"
SHARED_SECRET_FILENAME = "desktop_backend_shared_secret"


def resolve_data_root(
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
            "application_db": str(self.application_db),
            "checkpoints_db": str(self.checkpoints_db),
            "windows_layout": (
                r"%LOCALAPPDATA%\LocalAIWorkbench\{models,runtimes,state,cases,snapshots,workspaces,knowledge,application.sqlite,checkpoints.sqlite}"
            ),
        }
