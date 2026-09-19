"""Shared-contract names, OpenAPI export, and freshness-set comparisons."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from workbench_backend.agents.schemas import AgentRunStatus
from workbench_backend.app import create_app
from workbench_backend.contracts.auth import (
    WORKBENCH_LOCAL_TOKEN_HEADER,
    LocalSessionTrustContract,
)
from workbench_backend.contracts.cli import OPENAPI_TYPESCRIPT_CLI, openapi_typescript_command
from workbench_backend.contracts.export import build_json_schema, build_openapi_document
from workbench_backend.contracts.freshness import compare_generated_trees
from workbench_backend.contracts.lifecycle import (
    RunLifecycleStatus,
    is_run_lifecycle_live,
)
from workbench_backend.contracts.paths import (
    DESKTOP_TYPES_RELATIVE,
    OPENAPI_RELATIVE,
    generated_relative_paths,
    repo_root_from,
)
from support import close_workbench_sqlite, workbench_client


class SharedContractSurfaceTests(unittest.TestCase):
    def test_session_header_name_is_locked(self) -> None:
        envelope = LocalSessionTrustContract()
        self.assertEqual(WORKBENCH_LOCAL_TOKEN_HEADER, "X-Workbench-Local-Token")
        self.assertEqual(envelope.header_name, "X-Workbench-Local-Token")
        self.assertEqual(envelope.bind, "127.0.0.1")
        self.assertEqual(envelope.remote_backend, "unsupported")

    def test_lifecycle_includes_cancel_requested_and_cancelled(self) -> None:
        values = {item.value for item in RunLifecycleStatus}
        self.assertIn("cancel_requested", values)
        self.assertIn("cancelled", values)
        self.assertTrue(is_run_lifecycle_live(RunLifecycleStatus.cancel_requested))
        self.assertFalse(is_run_lifecycle_live(RunLifecycleStatus.cancelled))

    def test_harness_status_enum_is_unchanged_by_this_slice(self) -> None:
        harness_values = {item.value for item in AgentRunStatus}
        self.assertEqual(
            harness_values,
            {"queued", "running", "completed", "cancelled", "failed"},
        )
        self.assertNotIn("cancel_requested", harness_values)

    def test_openapi_documents_header_and_lifecycle(self) -> None:
        document = build_openapi_document()
        dumped = str(document)
        self.assertIn("X-Workbench-Local-Token", dumped)
        self.assertIn("WorkbenchLocalToken", dumped)
        self.assertIn("cancel_requested", dumped)
        self.assertIn("cancelled", dumped)
        schemas = document["components"]["schemas"]
        self.assertIn("LocalSessionTrustContract", schemas)
        self.assertIn("RunLifecycleContract", schemas)
        self.assertIn("RunLifecycleStatus", schemas)

    def test_json_schema_export_includes_status_names(self) -> None:
        schema = build_json_schema("RunLifecycleStatus")
        self.assertIn("cancel_requested", schema["enum"])
        self.assertIn("cancelled", schema["enum"])

    def test_product_openapi_stays_unpublished(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(data_root=Path(tmp))
            anonymous = TestClient(app)
            authorized = workbench_client(app)
            try:
                self.assertEqual(anonymous.get("/openapi.json").status_code, 401)
                self.assertEqual(anonymous.get("/v1/shared-contracts/session-trust").status_code, 401)
                self.assertEqual(authorized.get("/openapi.json").status_code, 404)
                self.assertEqual(authorized.get("/v1/shared-contracts/session-trust").status_code, 404)
            finally:
                close_workbench_sqlite(app, anonymous, authorized)


class OpenApiTypescriptInvocationTests(unittest.TestCase):
    def test_windows_safe_command_uses_node_and_pinned_cli(self) -> None:
        repo = repo_root_from(Path(__file__).resolve())
        desktop = repo / "apps" / "desktop"
        if not (desktop / OPENAPI_TYPESCRIPT_CLI).is_file():
            self.skipTest("desktop node_modules not installed in this environment")
        command = openapi_typescript_command(repo, pnpm_dir=desktop)
        self.assertNotEqual(command[0], "pnpm")
        self.assertTrue(command[0].lower().endswith(("node", "node.exe")))
        self.assertEqual(Path(command[1]), desktop / OPENAPI_TYPESCRIPT_CLI)
        self.assertIn("--root-types", command)


class FreshnessComparisonTests(unittest.TestCase):
    def _write(self, root: Path, relative: str, text: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _populated(self, root: Path, *, ts_text: str = "export type X = 'ok';\n") -> None:
        for relative in generated_relative_paths():
            payload = ts_text if relative == DESKTOP_TYPES_RELATIVE else '{"ok": true}\n'
            if relative == OPENAPI_RELATIVE:
                payload = '{"openapi":"3.1.0"}\n'
            self._write(root, relative, payload)
        self._write(root, "apps/backend/contracts/README.md", "handwritten\n")

    def test_matching_trees_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / "expected"
            committed = Path(tmp) / "committed"
            self._populated(expected)
            self._populated(committed)
            self.assertEqual(compare_generated_trees(expected, committed), [])

    def test_changed_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / "expected"
            committed = Path(tmp) / "committed"
            self._populated(expected)
            self._populated(committed, ts_text="export type X = 'stale';\n")
            errors = compare_generated_trees(expected, committed)
            self.assertTrue(any("drifted" in item for item in errors))

    def test_removed_committed_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / "expected"
            committed = Path(tmp) / "committed"
            self._populated(expected)
            self._populated(committed)
            (committed / DESKTOP_TYPES_RELATIVE).unlink()
            errors = compare_generated_trees(expected, committed)
            self.assertTrue(any("not committed" in item for item in errors))

    def test_extra_committed_file_is_removed_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / "expected"
            committed = Path(tmp) / "committed"
            self._populated(expected)
            self._populated(committed)
            self._write(committed, "apps/backend/contracts/jsonschema/extra.schema.json", "{}\n")
            errors = compare_generated_trees(expected, committed)
            self.assertTrue(any("no longer produced" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
