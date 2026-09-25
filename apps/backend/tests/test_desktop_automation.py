"""Windows worker policy checks without touching the user's live desktop."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess

from PIL import Image

from workbench_backend.agents.execution_policy import CURRENT_TOOL_CALL
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.desktop_automation import (
    DesktopAccessScope,
    DesktopAutomationError,
    DesktopAutomationService,
    WindowIdentity,
)
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths


class _Runtime:
    def available(self):
        return True

    def command_path(self):
        return Path("winapp.exe")


class DesktopAutomationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.paths = WorkbenchPaths(Path(self.temporary.name)).ensure()
        self.identities = {
            101: WindowIdentity(101, 10, 1000.0),
            202: WindowIdentity(202, 20, 2000.0),
        }
        self.commands = []
        self.captured = []

        def runner(args, timeout):
            self.commands.append((list(args), timeout))
            action = args[1]
            if action == "list-windows":
                payload = [
                    {"hwnd": 101, "processId": 10, "processName": "fixture-one", "title": "Fixture One",
                     "width": 800, "height": 600, "ownerHwnd": 0, "className": "TestWindow", "isForeground": True},
                    {"hwnd": 202, "processId": 20, "processName": "fixture-two", "title": "Fixture Two",
                     "width": 800, "height": 600, "ownerHwnd": 0, "className": "TestWindow", "isForeground": False},
                ]
            elif action == "screenshot":
                output = Path(args[args.index("--output") + 1])
                Image.new("RGB", (40, 30), "red").save(output, format="PNG")
                payload = {"path": str(output), "mode": "wgc", "width": 40, "height": 30}
            else:
                payload = {"ok": True, "action": action}
            return CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload), stderr="")

        def capture_sink(run, path, **kwargs):
            self.captured.append((run.id, path, path.read_bytes(), kwargs))
            return object(), "/captures/asset-1.png"

        self.service = DesktopAutomationService(
            self.paths, runtime=_Runtime(), capture_sink=capture_sink,
            identity_lookup=lambda hwnd: self.identities[hwnd], command_runner=runner,
        )

    def _run(self, **updates):
        now = utc_now()
        values = dict(id="visual-run", deployment_id="model", task="test window",
            enabled_tools=[], presented_tools=[], created_at=now, updated_at=now,
            thread_id="thread-one", source_surface="chat", desktop_access="selected",
            desktop_window={"hwnd": 101, "process_id": 10, "process_created_at": 1000.0})
        values.update(updates)
        return AgentRun(**values)

    def test_selected_window_never_lists_or_controls_other_window(self):
        self.service.set_scope("thread-one", "selected", hwnd=101)
        self.assertEqual([item.hwnd for item in self.service.list_windows("thread-one")], [101])
        self.service.inspect("thread-one")
        self.assertEqual(self.commands[-1][0], ["ui", "inspect", "--depth", "3", "-w", "101", "--json"])
        before = len(self.commands)
        with self.assertRaisesRegex(DesktopAutomationError, "outside the selected-window grant"):
            self.service.invoke("thread-one", "Close", hwnd=202)
        self.assertEqual(len(self.commands), before)

    def test_all_windows_requires_authenticated_scope_and_explicit_target(self):
        with self.assertRaisesRegex(DesktopAutomationError, "access is off"):
            self.service.list_windows("thread-one")
        self.service.set_scope("thread-one", DesktopAccessScope.all)
        self.assertEqual([item.hwnd for item in self.service.list_windows("thread-one")], [101, 202])
        with self.assertRaisesRegex(DesktopAutomationError, "requires an HWND"):
            self.service.invoke("thread-one", "Close")
        self.service.invoke("thread-one", "Close", hwnd=202)
        self.assertEqual(self.commands[-1][0], ["ui", "invoke", "Close", "-w", "202", "--json"])
        self.service.clear_scope("thread-one")
        with self.assertRaisesRegex(DesktopAutomationError, "access is off"):
            self.service.invoke("thread-one", "Close", hwnd=202)

    def test_reused_hwnd_or_pid_is_rejected_before_action(self):
        self.service.set_scope("thread-one", "selected", hwnd=101)
        self.identities[101] = WindowIdentity(101, 10, 3000.0)
        before = len(self.commands)
        with self.assertRaisesRegex(DesktopAutomationError, "changed"):
            self.service.set_value("thread-one", "Name", "new")
        self.assertEqual(len(self.commands), before + 1)  # discovery only
        self.assertEqual(self.commands[-1][0][1], "list-windows")

    def test_tool_capture_returns_only_virtual_path_and_deletes_raw_file(self):
        self.service.set_scope("thread-one", "selected", hwnd=101)
        tools = {item.name: item for item in self.service.tools_for_run(self._run())}
        self.assertIn("desktop_screenshot", tools)
        token = CURRENT_TOOL_CALL.set("call-17")
        try:
            result = json.loads(tools["desktop_screenshot"].invoke({}))
        finally:
            CURRENT_TOOL_CALL.reset(token)
        self.assertEqual(result["path"], "/captures/asset-1.png")
        self.assertEqual(result["window"]["hwnd"], 101)
        self.assertNotIn("source_path", result)
        self.assertEqual(self.captured[0][0], "visual-run")
        self.assertTrue(self.captured[0][2].startswith(b"\x89PNG"))
        self.assertEqual(self.captured[0][3]["source_tool_call_id"], "call-17")
        self.assertIn("HWND 101, PID 10", self.captured[0][3]["target"])
        self.assertFalse(self.captured[0][1].exists())

    def test_plan_recorded_and_off_runs_do_not_expose_tools(self):
        self.service.set_scope("thread-one", "selected", hwnd=101)
        self.assertEqual(self.service.tools_for_run(self._run(work_mode="plan")), [])
        self.assertEqual(self.service.tools_for_run(self._run(desktop_access="off")), [])
        self.service.clear_scope("thread-one")
        self.assertEqual(self.service.tools_for_run(self._run()), [])

    def test_frozen_helper_selection_cannot_expand_thread_scope(self):
        self.service.set_scope("thread-one", "all")
        selected_run = self._run()
        tools = {item.name: item for item in self.service.tools_for_run(selected_run)}
        result = json.loads(tools["desktop_list_windows"].invoke({}))
        self.assertEqual(result["scope"], "selected")
        self.assertEqual([item["hwnd"] for item in result["windows"]], [101])
        before = len(self.commands)
        denied = tools["desktop_invoke"].invoke({"selector": "Close", "hwnd": 202})
        self.assertIn("desktop_scope_denied", denied)
        self.assertEqual(len(self.commands), before)
        self.assertEqual(self.service.tools_for_run(self._run(desktop_window=None)), [])

        self.service.set_scope("thread-one", "selected", hwnd=101)
        broad_run = self._run(desktop_access="all", desktop_window=None)
        tools = {item.name: item for item in self.service.tools_for_run(broad_run)}
        result = json.loads(tools["desktop_list_windows"].invoke({}))
        self.assertEqual(result["scope"], "selected")
        self.assertEqual([item["hwnd"] for item in result["windows"]], [101])

    def test_controlled_cli_args_do_not_allow_global_input_switch(self):
        self.service.set_scope("thread-one", "selected", hwnd=101)
        self.service.send_keys("thread-one", "ctrl+a", target="Name")
        args = self.commands[-1][0]
        self.assertEqual(args, ["ui", "send-keys", "ctrl+a", "--target", "Name", "-w", "101", "--json"])
        self.assertNotIn("--via", args)
        self.assertNotIn("--allow-system-keys", args)


if __name__ == "__main__":
    unittest.main()
