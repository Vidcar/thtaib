"""Lab challenges exercise the same Deep Agents graph with only two safe tools."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.app import create_app
from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run


class RecordingChallengeModel(ScriptedChatModel):
    offered: ClassVar[list[set[str]]] = []

    def bind_tools(self, tools, **kwargs):
        names = set()
        for tool in tools:
            if isinstance(tool, dict):
                name = tool.get("name") or tool.get("function", {}).get("name")
            else:
                name = getattr(tool, "name", None)
            if name:
                names.add(name)
        type(self).offered.append(names)
        return super().bind_tools(tools, **kwargs)


class LabChallengeHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(data_root=Path(self.temp.name))
        self.client = offline_workbench_client(self.app)
        response = self.client.post("/v1/deployments/connected", json={
            "endpoint": "http://127.0.0.1:9/v1", "display_name": "Lab graph fixture",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.deployment_id = response.json()["id"]
        RecordingChallengeModel.offered = []

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.temp.cleanup()

    def run_challenge(self, script):
        model = RecordingChallengeModel(script)
        self.app.state.harness.close()
        self.app.state.harness = HarnessService(
            lambda: self.app.state.manager,
            app_store=self.app.state.app_store,
            knowledge_provider=lambda: self.app.state.knowledge,
            model_factory=lambda _run, _sink: model,
        )
        response = self.client.post("/v1/agent-runs", json={
            "deployment_id": self.deployment_id,
            "source_surface": "lab", "task": "Use the requested safe tool and answer LAB-CODE-42.",
            "presented_tools": ["echo", "time_now"], "connection_ids": [],
            "helper_agent_ids": [], "approval_mode": "ask",
            "input_policy": {"tool_loading": "always", "pinned_tools": ["echo", "time_now"],
                             "excluded_sources": ["tool:read_file"]},
            "memory_version_refs": [], "skill_version_refs": [],
            "protected_instruction_version_refs": [], "knowledge_version_refs": [],
        })
        self.assertEqual(response.status_code, 200, response.text)
        run = wait_for_run(self.client, response.json()["id"])
        self.assertTrue(RecordingChallengeModel.offered)
        for offered in RecordingChallengeModel.offered:
            self.assertEqual(offered, {"echo", "time_now"})
        self.assertIsNone(run.get("pending_interrupt"))
        self.assertIsNone(run.get("project_path"))
        self.assertEqual(self.client.get("/v1/chat/conversations").json(), [])
        return run

    def test_echo_and_clock_complete_without_approval_or_chat(self):
        for name, arguments in (("echo", {"text": "LAB-CODE-42"}), ("time_now", {})):
            with self.subTest(tool=name):
                run = self.run_challenge([
                    AIMessage(content="", tool_calls=[{"name": name, "args": arguments, "id": "safe-call"}]),
                    AIMessage(content="LAB-CODE-42"),
                ])
                self.assertEqual(run["status"], "completed", run.get("error"))
                outcomes = run.get("tool_outcomes", {})
                if isinstance(outcomes, dict):
                    outcomes = list(outcomes.values())
                self.assertTrue(any(item["name"] == name and item["outcome"] == "succeeded" for item in outcomes), outcomes)

    def test_unoffered_file_tool_cannot_write(self):
        run = self.run_challenge([
            AIMessage(content="", tool_calls=[{"name": "write_file", "args": {
                "file_path": "forbidden.txt", "content": "Must not be written",
            }, "id": "forbidden-call"}]),
            AIMessage(content="LAB-CODE-42"),
        ])
        self.assertFalse(list(Path(self.temp.name).rglob("forbidden.txt")))
        self.assertNotIn("write_file", run["presented_tools"])
        self.assertFalse(any(item.get("name") == "write_file" and item.get("outcome") == "succeeded"
                             for item in run.get("tool_outcomes", {}).values()))


if __name__ == "__main__":
    unittest.main()
