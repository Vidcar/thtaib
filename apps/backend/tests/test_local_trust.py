"""Issue #40 desktop↔backend shared-secret trust (partial OQ-002)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from workbench_backend.app import create_app
from workbench_backend.contracts.auth import (
    WORKBENCH_LOCAL_BIND,
    WORKBENCH_LOCAL_TOKEN_HEADER,
    WORKBENCH_LOCAL_TOKEN_SCHEME,
    LocalSessionTrustContract,
)
from workbench_backend.local_trust import (
    ensure_shared_secret,
    require_loopback_bind,
    shared_secret_path,
)
from workbench_backend.paths import SHARED_SECRET_FILENAME, WorkbenchPaths

from support import close_workbench_sqlite, workbench_client


PRIVILEGED_GETS = (
    "/v1/paths",
    "/v1/chat/conversations",
    "/v1/lab/workspaces",
    "/v1/lab/workspaces/ws_missing/files",
    "/v1/knowledge/entries",
    "/v1/agent-runs",
    "/v1/effects",
    "/v1/deployments",
)


class LocalTrustConstantsTests(unittest.TestCase):
    def test_header_and_bind_match_issue_41_names(self) -> None:
        envelope = LocalSessionTrustContract()
        self.assertEqual(WORKBENCH_LOCAL_TOKEN_HEADER, "X-Workbench-Local-Token")
        self.assertEqual(envelope.header_name, WORKBENCH_LOCAL_TOKEN_HEADER)
        self.assertEqual(WORKBENCH_LOCAL_TOKEN_SCHEME, "shared_secret")
        self.assertEqual(envelope.scheme, WORKBENCH_LOCAL_TOKEN_SCHEME)
        self.assertEqual(WORKBENCH_LOCAL_BIND, "127.0.0.1")
        self.assertEqual(envelope.bind, WORKBENCH_LOCAL_BIND)
        self.assertEqual(envelope.injector, "electron_main")
        self.assertEqual(SHARED_SECRET_FILENAME, "desktop_backend_shared_secret")

    def test_loopback_bind_rejects_non_loopback(self) -> None:
        self.assertEqual(require_loopback_bind("127.0.0.1"), "127.0.0.1")
        with self.assertRaises(ValueError) as raised:
            require_loopback_bind("0.0.0.0")
        self.assertIn("127.0.0.1", str(raised.exception))
        with self.assertRaises(ValueError):
            require_loopback_bind("192.168.1.10")


class SharedSecretFileTests(unittest.TestCase):
    def test_secret_is_created_under_state_and_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp)).ensure()
            first = ensure_shared_secret(paths)
            second = ensure_shared_secret(paths)
            path = shared_secret_path(paths)
            self.assertEqual(path, paths.state / SHARED_SECRET_FILENAME)
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_text(encoding="utf-8"), first)
            self.assertEqual(first, second)
            self.assertGreaterEqual(len(first), 32)
            self.assertNotIn(first, str(paths.root))
            public = paths.as_public_dict()
            self.assertNotIn(first, public.values())
            self.assertNotIn("shared_secret", public)


class LocalTrustHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root)
        self.anonymous = TestClient(self.app)
        self.authorized = workbench_client(self.app)
        self.wrong = workbench_client(self.app, token="definitely-not-the-secret")

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, self.anonymous, self.authorized, self.wrong)
        self.tmp.cleanup()

    def test_health_remains_public(self) -> None:
        response = self.anonymous.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_privileged_routes_reject_missing_token(self) -> None:
        for path in PRIVILEGED_GETS:
            with self.subTest(path=path):
                response = self.anonymous.get(path)
                self.assertEqual(response.status_code, 401, response.text)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_privileged_routes_reject_wrong_token(self) -> None:
        for path in PRIVILEGED_GETS:
            with self.subTest(path=path):
                response = self.wrong.get(path)
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(response.json()["code"], "invalid_token")

    def test_authorized_token_reaches_privileged_route(self) -> None:
        response = self.authorized.get("/v1/paths")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["state"], str(WorkbenchPaths(self.root).state))

    def test_lab_project_file_ops_require_token(self) -> None:
        created = self.authorized.post(
            "/v1/lab/workspaces",
            json={"display_name": "trust-files", "files": {"notes.md": "hello"}},
        )
        self.assertEqual(created.status_code, 200, created.text)
        workspace_id = created.json()["id"]
        files_path = f"/v1/lab/workspaces/{workspace_id}/files"
        denied = self.anonymous.get(files_path)
        self.assertEqual(denied.status_code, 401)
        wrong = self.wrong.put(files_path, json={"files": {"notes.md": "nope"}})
        self.assertEqual(wrong.status_code, 403)
        allowed = self.authorized.get(files_path)
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(allowed.json()["files"]["notes.md"], "hello")

    def test_chat_create_requires_token(self) -> None:
        denied = self.anonymous.post(
            "/v1/chat/conversations",
            json={"deployment_id": "dep_missing"},
        )
        self.assertEqual(denied.status_code, 401)
        wrong = self.wrong.post(
            "/v1/chat/conversations",
            json={"deployment_id": "dep_missing"},
        )
        self.assertEqual(wrong.status_code, 403)


if __name__ == "__main__":
    unittest.main()
