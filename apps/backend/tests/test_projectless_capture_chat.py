"""Projectless Chat can read only its retained screenshot through native read_file."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.assets.schemas import RetainedAssetListFilters, RetainedAssetOrigin
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.probes import _image_fixture
from workbench_backend.state.checkpointer import conversation_state


class _InspectImageModel(ScriptedChatModel):
    seen: ClassVar[list[list]] = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        type(self).seen.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class ProjectlessCaptureChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        _InspectImageModel.seen = []
        self.model: _InspectImageModel | None = None
        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=lambda _run, _sink: self.model,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
            assets=self.app.state.assets,
        )
        self.client = offline_workbench_client(self.app)
        deployment = self.client.post("/v1/deployments/connected", json={
            "endpoint": "http://127.0.0.1:9/v1", "display_name": "capture-fixture",
        })
        self.assertEqual(deployment.status_code, 200, deployment.text)
        self.deployment_id = deployment.json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def test_native_read_of_session_capture_is_paired_and_durable_history_is_bounded(self) -> None:
        created = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.deployment_id, "presented_tools": [],
            "approval_mode": "full_access",
        })
        self.assertEqual(created.status_code, 200, created.text)
        conversation = created.json()
        self.assertIsNone(conversation["project_path"])

        now = utc_now()
        source = AgentRun(id=new_id("agent_capture_seed"), deployment_id=self.deployment_id,
            task="Save a screenshot", source_surface="chat", thread_id=conversation["thread_id"],
            enabled_tools=[], presented_tools=[],
            created_at=now, updated_at=now)
        self.app.state.app_store.put_run(source)
        owned = self.root / "owned-capture"
        owned.mkdir()
        encoded = _image_fixture("blue").partition(",")[2]
        screenshot = owned / "page.png"
        screenshot.write_bytes(base64.b64decode(encoded))
        asset, path = self.app.state.assets.register_capture(source, screenshot,
            source_tool_name="browser_take_screenshot", source_tool_call_id="capture-call",
            target="http://127.0.0.1:4000/", controlled_root=owned)
        self.assertEqual(path, f"/captures/{asset.id}.png")

        self.model = _InspectImageModel([
            AIMessage(content="", tool_calls=[{"name": "read_file",
                "args": {"file_path": path}, "id": "capture-read"}]),
            AIMessage(content="Blue."),
        ], profile={"image_inputs": True, "image_tool_message": True})
        started = self.client.post(f"/v1/chat/conversations/{conversation['id']}/start", json={
            "task": "Inspect the saved screenshot.", "presented_tools": ["read_file"],
        })
        self.assertEqual(started.status_code, 200, started.text)
        finished = wait_for_run(self.client, started.json()["current_run_id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertTrue(finished["capture_routes_enabled"])
        self.assertIsNone(finished["project_path"])
        calls = [event for event in finished["events"] if event["kind"] == "tool_call"]
        results = [event for event in finished["events"] if event["kind"] == "tool_result"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(calls[0]["detail"]["id"], "capture-read")
        self.assertEqual(results[0]["detail"]["tool_call_id"], "capture-read")
        self.assertEqual(results[0]["detail"]["media_path"], path)
        self.assertIn(path, str(results[0]["detail"]["content"]))
        self.assertNotIn(encoded, json.dumps(finished["events"]))

        state = conversation_state(self.manager.paths.checkpoints_db, conversation["thread_id"])
        retained = [message for message in state.get("messages", [])
            if isinstance(message, ToolMessage) and message.tool_call_id == "capture-read"]
        self.assertEqual(len(retained), 1)
        self.assertIn(path, retained[0].content)
        self.assertNotIn(encoded, json.dumps(state, default=str))
        self.assertEqual(len(_InspectImageModel.seen), 2)
        next_request = _InspectImageModel.seen[-1]
        self.assertEqual(next_request[-2].tool_call_id, "capture-read")
        self.assertIsInstance(next_request[-1], HumanMessage)
        self.assertEqual(next_request[-1].content_blocks[-1]["base64"], encoded)
        captures = self.app.state.assets.list_assets(RetainedAssetListFilters(
            session_id=conversation["id"], origin=RetainedAssetOrigin.capture))
        self.assertEqual([item.id for item in captures], [asset.id],
            "Reading an existing capture must reuse its retained path")


if __name__ == "__main__":
    unittest.main()
