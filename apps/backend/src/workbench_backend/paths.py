"""Portable Local AI Workbench data-root resolution.

On Windows the layout is ``%LOCALAPPDATA%\\LocalAIWorkbench\\`` with
``models\\``, ``runtimes\\`` and ``state\\``. Other platforms use the same
directory names under a portable data root so tests and smoke can run
without claiming a second product mode.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PRODUCT_DATA_DIR = "LocalAIWorkbench"
DATA_ROOT_ENV = "WORKBENCH_DATA_ROOT"


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

    def ensure(self) -> "WorkbenchPaths":
        for path in (self.root, self.models, self.runtimes, self.state):
            path.mkdir(parents=True, exist_ok=True)
        return self

    def as_public_dict(self) -> dict[str, str]:
        return {
            "root": str(self.root),
            "models": str(self.models),
            "runtimes": str(self.runtimes),
            "state": str(self.state),
            "windows_layout": r"%LOCALAPPDATA%\LocalAIWorkbench\{models,runtimes,state}",
        }
