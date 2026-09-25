"""Authenticated Windows testing setup and conversation-scope API."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess

from fastapi.testclient import TestClient

from tests.support import close_workbench_sqlite, workbench_client
from workbench_backend.app import create_app
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.desktop_automation import (
    DesktopAutomationError,
    DesktopAutomationService,
    WindowIdentity,
)
from workbench_backend.desktop_automation.runtime import WinAppRuntimeError
from workbench_backend.inference.ids import utc_now


class _Runtime:
    def __init__(self):
        self.installs = 0
        self.enabled = True

    def command_path(self):
        if not self.enabled:
            raise WinAppRuntimeError("Optional worker is unavailable")
        return Path("winapp.exe")

    def install(self):
        self.installs += 1
        self.enabled = True
        return Path("winapp.exe")


class DesktopAutomationRouteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.app = create_app(data_root=Path(self.temporary.name))
        self.runtime = _Runtime()
        self.identities = {
            101: WindowIdentity(101, 10, 1000.0),
            202: WindowIdentity(202, 20, 2000.0),
        }

        def runner(args, _timeout):
            self.assertEqual(args, ["ui", "list-windows", "--json"])
            windows = [
                {"hwnd": 101, "processId": 10, "processName": "fixture", "title": "First test window",
                 "width": 800, "height": 600, "ownerHwnd": 0, "className": "Fixture", "isForeground": True},
                {"hwnd": 202, "processId": 20, "processName": "fixture", "title": "Second test window",
                 "width": 800, "height": 600, "ownerHwnd": 0, "className": "Fixture", "isForeground": False},
            ]
            return CompletedProcess(args=args, returncode=0, stdout=json.dumps(windows), stderr="")

        self.app.state.desktop_automation = DesktopAutomationService(
            self.app.state.manager.paths, runtime=self.runtime,
            identity_lookup=lambda hwnd: self.identities[hwnd], command_runner=runner,
        )
        now = utc_now()
        self.app.state.chat.store.put(ChatConversation(
            id="chat-fixture", deployment_id="unused", thread_id="thread-fixture",
            created_at=now, updated_at=now,
        ))
        self.client = workbench_client(self.app)
        self.addCleanup(lambda: close_workbench_sqlite(self.app, self.client))

    def test_local_auth_and_pinned_runtime_setup(self):
        anonymous = TestClient(self.app)
        try:
            self.assertEqual(anonymous.get("/v1/window-testing/windows").status_code, 401)
            self.assertEqual(anonymous.put("/v1/window-testing/conversations/chat-fixture/scope",
                json={"scope": "all"}).status_code, 401)
        finally:
            anonymous.close()

        status = self.client.get("/v1/window-testing/runtime")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["version"], "0.7.0")
        self.assertTrue(status.json()["available"])
        self.runtime.enabled = False
        self.assertFalse(self.client.get("/v1/window-testing/runtime").json()["available"])
        self.assertEqual(self.client.get("/v1/window-testing/windows").status_code, 409)
        installed = self.client.post("/v1/window-testing/runtime/install")
        self.assertEqual(installed.status_code, 200)
        self.assertTrue(installed.json()["available"])
        self.assertEqual(self.runtime.installs, 1)

    def test_picker_and_scope_are_bound_to_existing_conversation(self):
        windows = self.client.get("/v1/window-testing/windows")
        self.assertEqual(windows.status_code, 200)
        self.assertEqual([window["hwnd"] for window in windows.json()], [101, 202])
        base = "/v1/window-testing/conversations/chat-fixture/scope"
        self.assertEqual(self.client.get(base).json()["scope"], "off")
        selected = self.client.put(base, json={"scope": "selected", "hwnd": 101})
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.json()["selected_window"]["hwnd"], 101)
        self.assertFalse(selected.json()["stale"])
        self.assertEqual(self.client.get(base).json()["scope"], "selected")
        broad = self.client.put(base, json={"scope": "all"})
        self.assertEqual(broad.status_code, 200)
        self.assertEqual(broad.json()["scope"], "all")
        self.assertIsNone(broad.json()["selected_window"])
        cleared = self.client.put(base, json={"scope": "off"})
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["scope"], "off")
        self.assertEqual(self.client.get("/v1/window-testing/conversations/missing/scope").status_code, 404)
        self.assertEqual(self.client.put("/v1/window-testing/conversations/missing/scope",
            json={"scope": "all"}).status_code, 404)

    def test_invalid_selection_and_stale_window_are_explicit(self):
        base = "/v1/window-testing/conversations/chat-fixture/scope"
        missing = self.client.put(base, json={"scope": "selected"})
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()["code"], "desktop_invalid_arguments")
        self.assertEqual(self.client.put(base, json={"scope": "selected", "hwnd": 101}).status_code, 200)
        self.identities[101] = WindowIdentity(101, 10, 3000.0)
        stale = self.client.get(base)
        self.assertEqual(stale.status_code, 200)
        self.assertEqual(stale.json()["scope"], "selected")
        self.assertTrue(stale.json()["stale"])
        self.assertIsNone(stale.json()["selected_window"])
        self.runtime.enabled = False
        unavailable = self.client.put(base, json={"scope": "all"})
        self.assertEqual(unavailable.status_code, 409)
        self.assertEqual(unavailable.json()["code"], "desktop_runtime_unavailable")


if __name__ == "__main__":
    unittest.main()
