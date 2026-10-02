"""Atomic original-file edits and native deletion preflight boundaries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from workbench_backend.agents.file_operations import (
    ExactEdit, apply_edits_tool, edited_original, file_order_lock, file_order_path, validate_delete_target,
)
from workbench_backend.errors import HarnessError


class ProjectOperationUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.area = TemporaryDirectory()
        self.addCleanup(self.area.cleanup)
        self.root = Path(self.area.name)
        self.run = SimpleNamespace(project_path=str(self.root), work_mode="work", enabled_tools=["apply_edits", "delete"], presented_tools=["apply_edits", "delete"])
        self.path = self.root / "file.txt"
        self.path.write_bytes("alpha\r\nbeta café\n".encode())
        self.tool = apply_edits_tool(self.run)

    def test_preview_apply_preserves_original_newlines_and_hash(self):
        before = self.path.read_bytes()
        arguments = {"file_path": "file.txt", "edits": [{"old_string": "alpha", "new_string": "first"}, {"old_string": "beta", "new_string": "second"}]}
        preview = json.loads(self.tool.invoke(arguments))
        self.assertEqual(preview["status"], "preview")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(preview["base_sha256"], hashlib.sha256(before).hexdigest())
        result = json.loads(self.tool.invoke({**arguments, "base_sha256": preview["base_sha256"]}))
        self.assertEqual(result["status"], "applied")
        self.assertEqual(self.path.read_bytes(), "first\r\nsecond café\n".encode())
        self.assertEqual(result["result_sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertFalse(list(self.root.glob(".workbench-edit-*")))

    def test_stale_ambiguous_overlap_and_missing_are_no_mutations(self):
        before = self.path.read_bytes()
        for edits, digest in [
            ([{"old_string": "alpha", "new_string": "x"}], "0" * 64),
            ([{"old_string": "missing", "new_string": "x"}], hashlib.sha256(before).hexdigest()),
            ([{"old_string": "alpha", "new_string": "x"}, {"old_string": "pha", "new_string": "y"}], hashlib.sha256(before).hexdigest()),
        ]:
            answer = self.tool.invoke({"file_path": "file.txt", "edits": edits, "base_sha256": digest})
            self.assertIsInstance(answer, str)
            self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(HarnessError):
            edited_original("aaa", [ExactEdit(old_string="aa", new_string="b", replace_all=True)])

    def test_original_matching_not_sequential_substitution(self):
        actual, count = edited_original("alpha beta", [ExactEdit(old_string="alpha", new_string="beta"), ExactEdit(old_string="beta", new_string="gamma")])
        self.assertEqual(actual, "beta gamma")
        self.assertEqual(count, 2)

    def test_cancel_before_atomic_replace_keeps_original(self):
        before = self.path.read_bytes()
        tool = apply_edits_tool(self.run, cancel_requested=lambda: True)
        with self.assertRaises(HarnessError):
            tool.invoke({"file_path": "file.txt", "edits": [{"old_string": "alpha", "new_string": "x"}], "base_sha256": hashlib.sha256(before).hexdigest()})
        self.assertEqual(self.path.read_bytes(), before)

    def test_delete_preflight_has_subtree_evidence_and_rejects_roots_routes_links(self):
        nested = self.root / "dir"
        nested.mkdir()
        (nested / "a.txt").write_bytes(b"abc")
        evidence = validate_delete_target(self.run, {"file_path": "/dir"})
        self.assertEqual((evidence["before_entries"], evidence["before_files"], evidence["before_bytes"]), (2, 1, 3))
        self.assertTrue((nested / "a.txt").exists())
        for value in ("/", "../other", "C:/host", "/skills/example", "/large_tool_results/owned/value.txt", "//host/share"):
            with self.assertRaises(HarnessError, msg=value):
                validate_delete_target(self.run, {"file_path": value})
        with TemporaryDirectory() as outside:
            link = nested / "link"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                import subprocess
                subprocess.run(["cmd", "/c", "mklink", "/J", str(link), outside], check=True, capture_output=True)
            with self.assertRaises(HarnessError):
                validate_delete_target(self.run, {"file_path": "/dir"})
            link.rmdir() if link.is_junction() else link.unlink()

    def test_same_path_edits_share_one_lease(self):
        same = file_order_path(self.root, "/file.txt")
        self.assertEqual(same, file_order_path(self.root, "file.txt"))
        self.assertEqual(same, file_order_path(self.root, "./file.txt"))
        self.assertIs(file_order_lock(same), file_order_lock(file_order_path(self.root, "./file.txt")))
        self.assertNotEqual(same, file_order_path(self.root, "other.txt"))
        from langchain_core.tools import ToolException
        from workbench_backend.agents.file_operations import hold_file_order
        with hold_file_order(file_order_path(self.root, "left.txt")):
            with hold_file_order(file_order_path(self.root, "right.txt")):
                pass
        with hold_file_order(file_order_path(self.root, "dir")):
            with self.assertRaises(ToolException):
                with hold_file_order(file_order_path(self.root, "dir/child.txt")):
                    pass


if __name__ == "__main__":
    unittest.main()
