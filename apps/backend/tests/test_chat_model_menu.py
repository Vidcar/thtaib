"""A chat Thinking change uses the existing llama.cpp fields and leaves the saved setup alone."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from langchain_core.messages import AIMessage

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client
from tests.test_chat import wait_for_chat
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.inference.adapter import _direct_kwargs, _extra_body


class ChatModelMenuTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.seen: list[AgentRun] = []
        self.scripted = ScriptedChatModel([AIMessage(content="Thinking stayed on the next message.")])

        def factory(run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            self.seen.append(run)
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "chat-menu"},
        ).json()["id"]
        self.profile_id = self.client.post(
            "/v1/profiles",
            json={"display_name": "chat-menu", "startup": {}, "per_request": {"temperature": 0.2}, "agent": {}},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def test_thinking_reaches_llama_cpp_fields_without_reload_or_a_capability_check(self) -> None:
        created = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.deployment_id,
            "profile_id": self.profile_id,
            "presented_tools": [],
        })
        self.assertEqual(created.status_code, 200, created.text)
        saved = self.manager.get_profile(self.profile_id).bags.per_request.model_dump()
        with patch.object(self.manager, "reload_deployment", side_effect=AssertionError("thinking reloaded the model")), \
             patch.object(self.manager.capability_checks, "start", side_effect=AssertionError("thinking started capability checks")):
            started = self.client.post(
                f"/v1/chat/conversations/{created.json()['id']}/start",
                json={"task": "Say hello.", "per_request_overrides": {"temperature": 0.4, "reasoning": "on", "reasoning_effort": "low"}},
            )
        self.assertEqual(started.status_code, 200, started.text)
        wait_for_chat(self.client, created.json()["id"])
        self.assertTrue(self.seen)
        bag = self.seen[0].effective_setup.bags.per_request
        direct = _direct_kwargs(bag)
        extra = _extra_body(bag)
        self.assertEqual(direct["reasoning_effort"], "low")
        self.assertEqual(direct["temperature"], 0.4)
        self.assertEqual(extra["chat_template_kwargs"]["enable_thinking"], True)
        self.assertEqual(self.manager.get_profile(self.profile_id).bags.per_request.model_dump(), saved)


if __name__ == "__main__":
    unittest.main()
