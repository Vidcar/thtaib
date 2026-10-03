"""Disposable real-application fixtures for rendered desktop acceptance tests.

This package is never imported by production application composition. Configure
the scratch data root before importing the application, which has a module-level
instance. Inference is deterministic; application admission, graphs, permissions,
storage, assets and process cleanup retain their production owners.
"""

from pathlib import Path
import os
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[3]


def require_unredirected_directory(path: Path, label: str) -> Path:
    expected = Path(os.path.abspath(path))
    if expected.resolve() != expected:
        raise ValueError(f"{label} must not redirect outside its expected checkout path")
    return expected


def require_child_path(path: Path, parent: Path, label: str) -> Path:
    expected = Path(os.path.abspath(path))
    resolved = expected.resolve()
    if parent not in expected.parents or parent not in resolved.parents:
        raise ValueError(f"{label} must remain a child of {parent}")
    return resolved


def configure_environment(data_root: Path) -> Path:
    scratch = require_unredirected_directory(REPO_ROOT / ".scratch", "Checkout .scratch directory")
    root = require_child_path(data_root, scratch, "UI fixture data root")
    temporary = require_child_path(root / "temporary", root, "UI fixture temporary directory")
    root.mkdir(parents=True, exist_ok=True)
    temporary.mkdir(exist_ok=True)
    os.environ["WORKBENCH_DATA_ROOT"] = str(root)
    os.environ["TEMP"] = os.environ["TMP"] = str(temporary)
    tempfile.tempdir = str(temporary)
    return root
