"""STATE-003 / LAB-002 restore integrity: missing tree and hash mismatch fail."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench_backend.errors import LabError
from workbench_backend.lab.schemas import SnapshotFile
from workbench_backend.lab.snapshot import capture_project_snapshot, restore_snapshot_tree, write_snapshot_tree
from workbench_backend.paths import WorkbenchPaths


class SnapshotRestoreIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "project"
        self.tree = self.root / "snap" / "tree"
        self.dest = self.root / "restored"
        self.source.mkdir()
        (self.source / "notes.md").write_text("original notes", encoding="utf-8")
        nested = self.source / "src"
        nested.mkdir()
        (nested / "hello.py").write_text("print('hi')\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _capture(self, project: Path | None = None) -> list[SnapshotFile]:
        included, _exclusions = write_snapshot_tree(project or self.source, self.tree)
        return included

    def test_valid_snapshot_round_trips_matching_manifest(self) -> None:
        included = self._capture()
        restore_snapshot_tree(self.tree, self.dest, included_files=included)
        self.assertEqual((self.dest / "notes.md").read_text(encoding="utf-8"), "original notes")
        self.assertEqual((self.dest / "src" / "hello.py").read_text(encoding="utf-8"), "print('hi')\n")
        restore_snapshot_tree(self.dest, self.root / "second", included_files=included)
        self.assertEqual(
            (self.root / "second" / "notes.md").read_text(encoding="utf-8"),
            "original notes",
        )

    def test_capture_publishes_only_verified_tree_and_cleans_failed_staging(self) -> None:
        paths = WorkbenchPaths(self.root / "data").ensure()
        with patch("workbench_backend.lab.snapshot._copy_stable_file", side_effect=OSError("copy interrupted")):
            with self.assertRaisesRegex(OSError, "copy interrupted"):
                capture_project_snapshot(paths, workspace_id="test", project_root=self.source, kind="final")
        self.assertEqual(list(paths.snapshots.iterdir()), [])

        manifest = capture_project_snapshot(paths, workspace_id="test", project_root=self.source, kind="final")
        self.assertTrue((paths.snapshots / manifest.id / "manifest.json").is_file())
        self.assertEqual((Path(manifest.tree_path) / "notes.md").read_text(encoding="utf-8"), "original notes")
        self.assertFalse(any(path.name.endswith(".staging") for path in paths.snapshots.iterdir()))

    def test_prunes_excluded_directories_before_scanning_their_files(self) -> None:
        excluded_file = self.source / "node_modules" / "pkg" / "index.js"
        excluded_file.parent.mkdir(parents=True)
        excluded_file.write_text("large dependency", encoding="utf-8")
        real_scandir = os.scandir
        scanned: list[Path] = []

        def record_scan(path: str | os.PathLike[str]):
            scanned.append(Path(path))
            return real_scandir(path)

        with patch("workbench_backend.lab.snapshot.os.scandir", side_effect=record_scan):
            included, exclusions = write_snapshot_tree(self.source, self.tree)
        self.assertEqual({item.path: item.reason for item in exclusions}["node_modules"], "node_modules")
        self.assertNotIn("node_modules/pkg/index.js", {item.path for item in included})
        self.assertFalse(any(path.name == "node_modules" for path in scanned))

    def test_explicit_empty_allowlist_captures_no_files(self) -> None:
        included, exclusions = write_snapshot_tree(self.source, self.tree, allowlist=[])
        self.assertEqual(included, [])
        self.assertEqual(exclusions, [])
        self.assertEqual(list(self.tree.iterdir()), [])

    def test_escaping_symlink_is_reported_by_lexical_path_and_not_copied(self) -> None:
        outside = self.root / "private.txt"
        outside.write_text("outside project", encoding="utf-8")
        link = self.source / "alias.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"File symlinks unavailable: {exc}")
        included, exclusions = write_snapshot_tree(self.source, self.tree)
        self.assertNotIn("alias.txt", {item.path for item in included})
        self.assertEqual({item.path: item.reason for item in exclusions}["alias.txt"], "symlink_escape")
        self.assertFalse((self.tree / "alias.txt").exists())

    def test_changed_source_aborts_capture_without_publishing_a_snapshot(self) -> None:
        paths = WorkbenchPaths(self.root / "data").ensure()
        real_copy = shutil.copyfileobj

        def change_after_copy(source, target, *args, **kwargs):
            real_copy(source, target, *args, **kwargs)
            if Path(source.name).name == "notes.md":
                (self.source / "notes.md").write_text("changed while copying", encoding="utf-8")

        with patch("workbench_backend.lab.snapshot.shutil.copyfileobj", side_effect=change_after_copy):
            with self.assertRaisesRegex(OSError, "changed"):
                capture_project_snapshot(paths, workspace_id="test", project_root=self.source, kind="final")
        self.assertEqual(list(paths.snapshots.iterdir()), [])

    def test_intentionally_empty_snapshot_round_trips(self) -> None:
        empty_source = self.root / "empty-project"
        empty_source.mkdir()
        included = self._capture(empty_source)
        self.assertEqual(included, [])
        self.assertTrue(self.tree.is_dir())
        restore_snapshot_tree(self.tree, self.dest, included_files=included)
        self.assertTrue(self.dest.is_dir())
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_missing_tree_fails_even_when_manifest_is_empty(self) -> None:
        included: list[SnapshotFile] = []
        self.assertFalse(self.tree.exists())
        with self.assertRaises(LabError) as ctx:
            restore_snapshot_tree(self.tree, self.dest, included_files=included)
        self.assertEqual(ctx.exception.code, "snapshot_tree_missing")
        self.assertFalse(self.dest.exists())

    def test_missing_expected_file_fails_and_discards_staging(self) -> None:
        included = self._capture()
        (self.tree / "notes.md").unlink()
        with self.assertRaises(LabError) as ctx:
            restore_snapshot_tree(self.tree, self.dest, included_files=included)
        self.assertEqual(ctx.exception.code, "snapshot_file_missing")
        self.assertEqual(ctx.exception.details.get("path"), "notes.md")
        self.assertFalse(self.dest.exists())

    def test_hash_mismatch_fails_and_discards_staging(self) -> None:
        included = self._capture()
        (self.tree / "notes.md").write_text("tampered after capture", encoding="utf-8")
        with self.assertRaises(LabError) as ctx:
            restore_snapshot_tree(self.tree, self.dest, included_files=included)
        self.assertEqual(ctx.exception.code, "snapshot_hash_mismatch")
        self.assertEqual(ctx.exception.details.get("path"), "notes.md")
        self.assertFalse(self.dest.exists())

    def test_unexpected_tree_file_fails_and_discards_staging(self) -> None:
        included = self._capture()
        (self.tree / "extra.txt").write_text("not in manifest", encoding="utf-8")
        with self.assertRaises(LabError) as ctx:
            restore_snapshot_tree(self.tree, self.dest, included_files=included)
        self.assertEqual(ctx.exception.code, "snapshot_unexpected_file")
        self.assertEqual(ctx.exception.details.get("path"), "extra.txt")
        self.assertFalse(self.dest.exists())

    def test_nonempty_destination_is_left_untouched(self) -> None:
        included = self._capture()
        self.dest.mkdir()
        leftover = self.dest / "keep-me.txt"
        leftover.write_text("pre-existing", encoding="utf-8")
        with self.assertRaises(LabError) as ctx:
            restore_snapshot_tree(self.tree, self.dest, included_files=included)
        self.assertEqual(ctx.exception.code, "snapshot_restore_incomplete")
        self.assertEqual(leftover.read_text(encoding="utf-8"), "pre-existing")
        self.assertFalse((self.dest / "notes.md").exists())

    def test_incomplete_copy_cleans_failed_staging(self) -> None:
        included = self._capture()
        real_copy = shutil.copy2

        def skip_notes(src: object, dst: object, *args: object, **kwargs: object) -> object:
            if Path(str(src)).name == "notes.md":
                return dst
            return real_copy(src, dst, *args, **kwargs)

        with patch("workbench_backend.lab.snapshot.shutil.copy2", skip_notes):
            with self.assertRaises(LabError) as ctx:
                restore_snapshot_tree(self.tree, self.dest, included_files=included)
        self.assertEqual(ctx.exception.code, "snapshot_file_missing")
        self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
