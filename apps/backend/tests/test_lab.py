"""Lab no longer serves case capture. Performance, Memory, and Challenges stay."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workbench_backend.app import create_app
from workbench_backend.paths import WorkbenchPaths

from tests.support import close_workbench_sqlite, offline_workbench_client


class LabApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.app = create_app(data_root=self.root)
        self.client = offline_workbench_client(self.app)

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def test_paths_advertise_cases_and_snapshots(self) -> None:
        body = self.client.get("/v1/paths").json()
        self.assertEqual(body["cases"], str(self.paths.cases))
        self.assertEqual(body["snapshots"], str(self.paths.snapshots))
        self.assertEqual(body["knowledge"], str(self.paths.knowledge))
        self.assertIn("cases", body["windows_layout"])
        self.assertIn("snapshots", body["windows_layout"])
        self.assertIn("knowledge", body["windows_layout"])

    def test_case_routes_are_gone_and_workbench_views_still_load(self) -> None:
        retired = (
            ("POST", "/v1/lab/cases/capture", {}),
            ("GET", "/v1/lab/cases", None),
            ("GET", "/v1/lab/cases/case_missing", None),
            ("GET", "/v1/lab/cases/case_missing/export", None),
            ("POST", "/v1/lab/cases/case_missing/restore", None),
            ("POST", "/v1/lab/cases/case_missing/rerun", {"tool_mode": "recorded-tool", "workspace_id": "ws_missing"}),
            ("POST", "/v1/lab/workspaces", {"display_name": "retired"}),
            ("GET", "/v1/lab/workspaces", None),
            ("POST", "/v1/lab/engine-measurements", {}),
            ("GET", "/v1/lab/engine-measurements", None),
            ("GET", "/v1/lab/results", None),
            ("GET", "/v1/lab/snapshots/snap_missing", None),
        )
        for method, path, body in retired:
            response = self.client.request(method, path, json=body)
            self.assertEqual(response.status_code, 404, f"{method} {path}: {response.text}")
        runs = self.client.get("/v1/lab/workbench/runs")
        self.assertEqual(runs.status_code, 200, runs.text)
        self.assertIsInstance(runs.json(), list)
        challenges = self.client.get("/v1/lab/workbench/challenges")
        self.assertEqual(challenges.status_code, 200, challenges.text)
        self.assertIsInstance(challenges.json(), list)
