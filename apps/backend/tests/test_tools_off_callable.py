"""Tools-off is enforced at native callable dispatch, not just model disclosure."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import ClassVar
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage

from tests.scripted_model import ScriptedChatModel
from tests.support import wait_for_run
from tests import test_harness as harness_fixtures
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware


CALLS = (
    ("read_file", {"file_path": "/protected.txt"}),
    ("write_file", {"file_path": "/created.txt", "content": "must not exist"}),
    ("edit_file", {"file_path": "/protected.txt", "old_string": "KEEP", "new_string": "BAD"}),
    ("delete", {"file_path": "/protected.txt"}),
    ("execute", {"command": "cmd /c echo BAD > marker.txt"}),
    ("task", {"description": "Write marker.txt", "subagent_type": "general-purpose"}),
)


class OfferedModel(ScriptedChatModel):
    offered: ClassVar[list[list[str]]] = []

    def bind_tools(self, tools, **kwargs):
        type(self).offered.append([getattr(tool, "name", "") for tool in tools])
        return super().bind_tools(tools, **kwargs)


class ToolsOffCallableTests(unittest.TestCase):
    setUp = harness_fixtures.HarnessApiTests.setUp
    tearDown = harness_fixtures.HarnessApiTests.tearDown
    _start = harness_fixtures.HarnessApiTests._start

    def test_forced_native_calls_never_reach_handlers_in_eager_and_deferred_graphs(self):
        project = self.root / "off-project"
        project.mkdir()
        (project / "protected.txt").write_text("KEEP", encoding="utf-8")
        for loading in ("always", "when_needed"):
            for project_path in (None, str(project)):
                with self.subTest(loading=loading, project=project_path):
                    OfferedModel.offered.clear()
                    self.scripted = OfferedModel([
                        AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"off-{index}"}
                            for index, (name, args) in enumerate(CALLS)]),
                        AIMessage(content="No authorized action performed."),
                    ])
                    with patch.object(WorkbenchHarnessMiddleware, "_wrap_tool_call",
                            side_effect=AssertionError("Tools-off reached an effect handler")) as sync_dispatch, \
                            patch.object(WorkbenchHarnessMiddleware, "_awrap_tool_call",
                            side_effect=AssertionError("Tools-off reached an effect handler")) as async_dispatch:
                        run = wait_for_run(self.client, self._start(presented_tools=[], project_path=project_path,
                            approval_mode="full_access", input_policy={"tool_loading": loading})["id"])
                    self.assertEqual(run["status"], "completed", run.get("error"))
                    sync_dispatch.assert_not_called()
                    async_dispatch.assert_not_called()
                    self.assertFalse(any(OfferedModel.offered))
                    self.assertEqual(run["framework_read_paths"], [])
                    self.assertEqual(set(run["tool_outcomes"]), {f"off-{index}" for index in range(len(CALLS))})
                    for outcome in run["tool_outcomes"].values():
                        self.assertEqual(outcome["outcome"], "failed")
                        self.assertIn("Tools are explicitly off", outcome["detail"])
                    self.assertEqual(sorted(path.name for path in project.iterdir()), ["protected.txt"])
                    self.assertEqual((project / "protected.txt").read_text(encoding="utf-8"), "KEEP")

    def test_sync_and_async_refusal_precedes_reader_fallback_and_plan_handlers(self):
        from workbench_backend.agents.schemas import AgentRun
        from workbench_backend.inference.ids import utc_now

        for asynchronous in (False, True):
            for mode in ("work", "plan"):
                for name, args in CALLS:
                    with self.subTest(asynchronous=asynchronous, mode=mode, tool=name):
                        run = AgentRun(id="off", deployment_id=self.deployment_id, task="Do nothing",
                            presented_tools=[], enabled_tools=[], work_mode=mode,
                            framework_read_paths=["/conversation_history/"], created_at=utc_now(), updated_at=utc_now())
                        middleware = WorkbenchHarnessMiddleware(run)
                        request = SimpleNamespace(tool_call={"name": name, "args": args, "id": "shared"})
                        invoked = []
                        def handler(_request):
                            invoked.append(name)
                            return ToolMessage(content="must not execute", name=name, tool_call_id="shared")
                        async def async_handler(_request):
                            return handler(_request)
                        result = (asyncio.run(middleware.awrap_tool_call(request, async_handler)) if asynchronous
                            else middleware.wrap_tool_call(request, handler))
                        self.assertEqual(invoked, [])
                        self.assertEqual(result.status, "error")
                        self.assertEqual(run.tool_outcomes["shared"].outcome, "failed")

    def test_selected_native_writer_positive_control_reaches_effect_once(self):
        project = self.root / "positive-project"
        project.mkdir()
        self.scripted = OfferedModel([
            AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": "/selected.txt", "content": "once"}, "id": "positive"}]),
            AIMessage(content="Written."),
        ])
        run = wait_for_run(self.client, self._start(presented_tools=["write_file"], project_path=str(project),
            approval_mode="full_access", input_policy={"tool_loading": "always"})["id"])
        self.assertEqual(run["status"], "completed", run.get("error"))
        self.assertEqual((project / "selected.txt").read_text(encoding="utf-8"), "once")
        self.assertEqual(run["tool_outcomes"]["positive"]["outcome"], "succeeded")
        self.assertEqual(run["dispatched_tool_calls"], 1)
