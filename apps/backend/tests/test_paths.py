"""Portable data-root resolution, including the Windows layout."""

from __future__ import annotations

import unittest
from pathlib import Path

from workbench_backend.paths import PRODUCT_DATA_DIR, resolve_data_root


class PathResolutionTests(unittest.TestCase):
    def test_windows_uses_localappdata_layout(self) -> None:
        root = resolve_data_root(
            environ={"LOCALAPPDATA": r"C:\Users\david\AppData\Local"},
            platform="win32",
        )
        self.assertEqual(root, Path(r"C:\Users\david\AppData\Local") / PRODUCT_DATA_DIR)

    def test_override_wins(self) -> None:
        root = resolve_data_root(
            environ={"WORKBENCH_DATA_ROOT": "/tmp/workbench-data", "LOCALAPPDATA": "C:/x"},
            platform="win32",
        )
        self.assertEqual(root, Path("/tmp/workbench-data"))

    def test_xdg_on_linux(self) -> None:
        root = resolve_data_root(
            environ={"XDG_DATA_HOME": "/var/data"},
            platform="linux",
        )
        self.assertEqual(root, Path("/var/data") / PRODUCT_DATA_DIR)


if __name__ == "__main__":
    unittest.main()
