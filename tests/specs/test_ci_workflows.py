"""Lock the slim GitHub CI policy. Enforcement-system test: workflows only."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

REPOSITORY = Path(__file__).resolve().parents[2]
WORKFLOWS = REPOSITORY / ".github" / "workflows"
WORKFLOW_NAMES = (
    "backend.yml",
    "contracts.yml",
    "desktop.yml",
    "real-model-smoke.yml",
    "specs.yml",
)


class CiWorkflowPolicyTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return (WORKFLOWS / name).read_text(encoding="utf-8")

    def test_known_workflow_set(self) -> None:
        found = {path.name for path in WORKFLOWS.glob("*.yml")}
        self.assertEqual(found, set(WORKFLOW_NAMES))
        script = REPOSITORY / ".github" / "scripts" / "ci-path-filter.sh"
        self.assertTrue(script.is_file(), script)

    def test_push_is_main_only_with_pull_request_and_dispatch(self) -> None:
        push_main = re.compile(r"^  push:\n    branches:\n      - main\n", re.M)
        bare_push = re.compile(r"^  push:\n  [a-z_]", re.M)
        for name in WORKFLOW_NAMES:
            text = self.read(name)
            with self.subTest(name):
                self.assertRegex(text, push_main)
                self.assertIsNone(bare_push.search(text))
                self.assertIn("\n  pull_request:\n", text)
                self.assertIn("\n  workflow_dispatch:\n", text)
                self.assertIn("cancel-in-progress: true", text)
                self.assertIn("concurrency:", text)

    def test_spec_integrity_is_linux_only(self) -> None:
        text = self.read("specs.yml")
        self.assertIn("name: spec-integrity (ubuntu-latest)", text)
        self.assertNotIn("os: [ubuntu-latest, windows-latest]", text)
        self.assertNotIn("runs-on: windows-latest", text)

    def test_shared_contract_freshness_is_linux_only(self) -> None:
        text = self.read("contracts.yml")
        self.assertIn("name: shared-contract-freshness (ubuntu-latest)", text)
        self.assertNotIn("os: [ubuntu-latest, windows-latest]", text)
        self.assertNotIn("runs-on: windows-latest", text)

    def test_backend_keeps_windows_coverage(self) -> None:
        text = self.read("backend.yml")
        self.assertIn("os: [ubuntu-latest, windows-latest]", text)
        self.assertIn("apps/backend/", text)
        self.assertIn("ci-path-filter.sh", text)

    def test_desktop_keeps_one_windows_build(self) -> None:
        text = self.read("desktop.yml")
        self.assertIn("os: [ubuntu-latest, windows-latest]", text)
        self.assertIn("apps/desktop/", text)
        self.assertIn("ci-path-filter.sh", text)

    def test_real_model_smoke_is_path_filtered_linux(self) -> None:
        text = self.read("real-model-smoke.yml")
        self.assertIn("name: real-model-smoke (ubuntu-latest)", text)
        self.assertIn("runs-on: ubuntu-latest", text)
        self.assertIn("apps/backend/**", text)
        self.assertNotIn("windows-latest", text)
