"""Native project paths and concurrent creation, with no ordinary product data."""

from __future__ import annotations

import ctypes
import ntpath
import os
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

from workbench_backend.agents.harness_backend import (
    BoundedImageLocalShellBackend, FilesystemBackend, _comparison_path,
    canonical_root, roots_overlap,
)


class ProjectPathTests(unittest.TestCase):
    def test_windows_comparison_handles_dos_unc_case_and_keeps_boundaries(self):
        for plain, extended in [
            (r"D:\Project\src\file.txt", r"\\?\d:\PROJECT\src\file.txt"),
            (r"\\server\share\Project\file.txt", r"\\?\UNC\SERVER\share\project\file.txt"),
        ]:
            self.assertEqual(_comparison_path(PureWindowsPath(plain)), _comparison_path(PureWindowsPath(extended)))
        self.assertFalse(_comparison_path(PureWindowsPath(r"D:\project2")).is_relative_to(_comparison_path(PureWindowsPath(r"D:\project"))))
        for device in [r"\\.\NUL", r"\\?\GLOBALROOT\Device\HarddiskVolume1\private"]:
            with self.assertRaises(ValueError):
                _comparison_path(PureWindowsPath(device))

    def test_parallel_nested_writes_and_expected_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for backend_type in (FilesystemBackend, BoundedImageLocalShellBackend):
                for iteration in range(6):
                    backend = backend_type(root_dir=root, virtual_mode=True)
                    barrier = threading.Barrier(6)
                    def write(index):
                        barrier.wait(timeout=5)
                        return backend.write(f"new-{backend_type.__name__}-{iteration}/nested/{index}.txt", f"file {index}")
                    with ThreadPoolExecutor(max_workers=6) as pool:
                        results = list(pool.map(write, range(6)))
                    self.assertTrue(all(result.error is None for result in results), results)
                    for index, result in enumerate(results):
                        self.assertEqual((root / result.path).read_text(), f"file {index}")
                self.assertIsNotNone(backend.write("../outside.txt", "denied").error)
                self.assertIsNotNone(backend.read("../outside.txt").error)
                self.assertIsNotNone(backend.edit("../outside.txt", "a", "b").error)
                self.assertIsNotNone(backend.ls("../").error)

    @unittest.skipUnless(os.name == "nt", "Win32 lookup transition")
    def test_parent_creation_during_resolution_does_not_fake_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            target = str(root / "src" / "world.js")
            original = ntpath._getfinalpathname
            attempts = 0
            def raced_lookup(path):
                nonlocal attempts
                if ntpath.normcase(path) == ntpath.normcase(target):
                    attempts += 1
                    raise ctypes.WinError(3 if attempts == 1 else 2)
                return original(path)
            backend = FilesystemBackend(root_dir=root)
            with patch.object(ntpath, "_getfinalpathname", side_effect=raced_lookup):
                result = backend.write("src/world.js", "export const ready = true;")
            self.assertIsNone(result.error)
            self.assertGreaterEqual(attempts, 3)
            self.assertEqual((root / "src/world.js").read_text(), "export const ready = true;")
            self.assertEqual(backend._to_virtual_path(Path("\\\\?\\" + target)), "/src/world.js")
            self.assertEqual(canonical_root(root), canonical_root(Path("\\\\?\\" + str(root))))

    @unittest.skipUnless(os.name == "nt", "Windows junction containment")
    def test_junction_escape_is_a_tool_error_and_overlap_uses_actual_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, outside = root / "project", root / "outside"
            project.mkdir()
            outside.mkdir()
            (outside / "private.txt").write_text("private")
            alias = project / "linked"
            made = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(outside)], capture_output=True, text=True)
            self.assertEqual(made.returncode, 0, made.stderr)
            try:
                backend = FilesystemBackend(root_dir=project)
                self.assertIsNotNone(backend.read("linked/private.txt").error)
                self.assertIsNotNone(backend.write("linked/new.txt", "denied").error)
                self.assertFalse((outside / "new.txt").exists())
                self.assertTrue(roots_overlap(alias, outside))
                self.assertFalse(roots_overlap(project, outside))
                for invalid in [r"C:\Windows\win.ini", r"C:relative.txt", r"\\.\NUL", "file.txt:alternate"]:
                    self.assertIsNotNone(backend.write(invalid, "denied").error)
            finally:
                alias.rmdir()  # Remove only the verified junction, not its target.


if __name__ == "__main__":
    unittest.main()
