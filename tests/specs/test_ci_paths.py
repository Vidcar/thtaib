"""Behaviour of CI selection: relevant coverage and fail-open revision handling."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ci_paths", ROOT / ".github/scripts/ci_paths.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class CiPathTests(unittest.TestCase):
    def test_changes_select_relevant_tiers(self):
        cases = {
            "README.md": set(),
            "apps/backend/tests/test_paths.py": {"backend", "contracts"},
            "apps/backend/src/workbench_backend/chat/service.py": {"backend", "contracts", "model"},
            "apps/backend/tests/support.py": {"backend", "contracts", "model"},
            "apps/backend/tests/__init__.py": {"backend", "contracts", "model"},
            "apps/desktop/src/renderer/ChatPanel.tsx": {"desktop"},
            "apps/desktop/src/generated/shared-contracts/openapi.d.ts": {"desktop", "contracts"},
            "scripts/generate_shared_contracts.py": {"contracts"},
            "scripts/check_specs.py": set(),
            "tests/specs/test_check_specs.py": set(),
            ".github/workflows/ci.yml": set(ci.TIERS),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual({key for key, value in ci.select([path]).items() if value}, expected)

    def test_unknown_revisions_and_forced_events_run_all(self):
        for event in ("workflow_dispatch", "merge_group", "push", "pull_request", "unknown"):
            with self.subTest(event=event):
                self.assertIsNone(ci.changed_paths(event, {}, "tip"))
        self.assertIsNone(ci.changed_paths("push", {"before": "0" * 40}, "tip"))
        with patch.object(ci.subprocess, "check_output", side_effect=subprocess.CalledProcessError(1, "git")):
            self.assertIsNone(ci.changed_paths("push", {"before": "base"}, "tip"))

    def test_diff_uses_event_revisions_and_preserves_paths(self):
        event = {"pull_request": {"base": {"sha": "base"}, "head": {"sha": "head"}}}
        with patch.object(ci.subprocess, "check_output", return_value="apps/backend/a b.py\0README.md\0") as diff:
            self.assertEqual(ci.changed_paths("pull_request", event, "merge"), ["apps/backend/a b.py", "README.md"])
            diff.assert_called_once_with(["git", "diff", "--name-only", "-z", "base", "head"], text=True)
