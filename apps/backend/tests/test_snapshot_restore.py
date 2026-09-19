"""STATE-003 / LAB-002 restore integrity: missing tree and hash mismatch fail."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench_backend.errors import LabError
from workbench_backend.lab.schemas import SnapshotFile
from workbench_backend.lab.snapshot import restore_snapshot_tree, write_snapshot_tree


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
