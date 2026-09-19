"""Portable data-root resolution, including the Windows layout."""

from __future__ import annotations

import unittest
from pathlib import Path

from workbench_backend.paths import PRODUCT_DATA_DIR, WorkbenchPaths, resolve_data_root


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

    def test_layout_includes_cases_and_snapshots(self) -> None:
        paths = WorkbenchPaths(Path("/tmp/workbench-layout-test"))
        public = paths.as_public_dict()
        self.assertEqual(paths.cases, paths.root / "cases")
        self.assertEqual(paths.snapshots, paths.root / "snapshots")
        self.assertEqual(paths.knowledge, paths.root / "knowledge")
        self.assertEqual(paths.application_db, paths.root / "application.sqlite")
        self.assertEqual(paths.checkpoints_db, paths.root / "checkpoints.sqlite")
        self.assertNotEqual(paths.application_db, paths.checkpoints_db)
        self.assertEqual(public["cases"], str(paths.cases))
        self.assertEqual(public["snapshots"], str(paths.snapshots))
        self.assertEqual(public["knowledge"], str(paths.knowledge))
        self.assertEqual(public["application_db"], str(paths.application_db))
        self.assertEqual(public["checkpoints_db"], str(paths.checkpoints_db))
        self.assertIn("cases", public["windows_layout"])
        self.assertIn("snapshots", public["windows_layout"])
        self.assertIn("knowledge", public["windows_layout"])
        self.assertIn("application.sqlite", public["windows_layout"])
        self.assertIn("checkpoints.sqlite", public["windows_layout"])


if __name__ == "__main__":
    unittest.main()
