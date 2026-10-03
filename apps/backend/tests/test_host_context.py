"""Host facts reach accepted native inputs without changing tool authority."""

from __future__ import annotations

import json
import platform
import unittest
from unittest.mock import patch

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from workbench_backend.agents.context import token_counter_for_model
from workbench_backend.agents.effective_setup import compose_system_prompt
from workbench_backend.agents.input_sources import build_input_sources
from workbench_backend.agents.setup_schemas import AgentInputPolicy, InstructionLayer
from workbench_backend.knowledge.costs import content_token_estimate
from workbench_backend.inference.adapter import RecordingTransport
from tests import test_agent_capabilities as capabilities
from tests import test_chat as chat_fixtures
from tests import test_effective_setup as adapter_fixtures
from tests import test_host_shell as approval_fixtures
from tests import test_project_agent_setups as fixtures
from tests import test_request_projection as projection_fixtures
from tests.scripted_model import ScriptedChatModel
from tests.support import wait_for_run


HOST_FACT = f"The Workbench host operating system is {platform.system()}."


class HostContextCompositionTests(unittest.TestCase):
    def test_current_and_legacy_composition_keep_host_fact_and_authored_text(self):
        authored = "  Follow these authored steps.\nKeep this whitespace.\n"
        for policy in (AgentInputPolicy(), None):
            with self.subTest(policy=policy):
                prompt = compose_system_prompt(
                    input_policy=policy, default_system_prompt="Default instructions.",
                    profile_system_prompt="Model instructions.", surface_system_prompt=None,
                    instruction_layers=[InstructionLayer(name="Agent: Main", content=authored)],
                    versions=[], selected_agent=True)
                self.assertEqual(prompt.count(HOST_FACT), 1)
                self.assertIn(authored, prompt)
                self.assertIn("Model instructions.", prompt)
                row = next(row for row in build_input_sources(policy=policy,
                    instruction_layers=[InstructionLayer(name="Agent: Main", content=authored)],
                    presented_tools=[], include_content=True) if row.id == "workbench_core")
                self.assertIn(HOST_FACT, row.content)
                self.assertTrue(row.required)
                self.assertEqual(row.mode, "always")
                self.assertEqual(row.estimated_tokens, content_token_estimate(row.content))
                self.assertIn(row.content, prompt)

    def test_native_count_and_recorded_request_include_the_same_host_fact(self):
        counts, generations, captures = [], [], []

        def endpoint(request):
            body = json.loads(request.content)
            if request.url.path.endswith('/chat/completions/input_tokens'):
                counts.append(body)
                return httpx.Response(200, json={"input_tokens": 123})
            generations.append(body)
            return httpx.Response(200, json={"id": "host-fact", "object": "chat.completion", "created": 1,
                "model": "fixture", "choices": [{"index": 0,
                    "message": {"role": "assistant", "content": "Done"}, "finish_reason": "stop"}]})

        value = projection_fixtures.model(transport=RecordingTransport(captures, httpx.MockTransport(endpoint)))
        value.set_input_token_counting(value.http_client, "http://127.0.0.1:9/v1", native=True)
        prompt = compose_system_prompt(input_policy=AgentInputPolicy(),
            default_system_prompt="Default instructions.", profile_system_prompt=None,
            surface_system_prompt=None, versions=[])
        messages = [SystemMessage(content=prompt), HumanMessage(content="Generate platform-dependent code")]
        try:
            self.assertEqual(token_counter_for_model(value)(messages), 123)
            value.invoke(messages)
            self.assertEqual(counts[0]["messages"], generations[0]["messages"])
            self.assertEqual(captures[0]["body"]["messages"][0]["content"],
                generations[0]["messages"][0]["content"])
            self.assertEqual(captures[0]["body"]["messages"][1]["content_preview"],
                generations[0]["messages"][1]["content"])
            self.assertEqual(generations[0]["messages"][0]["content"].count(HOST_FACT), 1)
        finally:
            value.close()


class HostContextDispatchTests(unittest.TestCase):
    setUp = fixtures.ProjectSetupTests.setUp
    tearDown = fixtures.ProjectSetupTests.tearDown
    post = fixtures.ProjectSetupTests.post
    setup = fixtures.ProjectSetupTests.setup
    harness = capabilities.AgentCapabilitiesTests.harness
    start = capabilities.AgentCapabilitiesTests.start

    def test_parent_and_helper_receive_one_system_fact_without_extra_user_turn(self):
        captured = {"root": [], "helper": []}

        class RootModel(ScriptedChatModel):
            def _generate(self, messages, **kwargs):
                captured["root"].append([message.model_copy(deep=True) for message in messages])
                return super()._generate(messages, **kwargs)

        class HelperModel(ScriptedChatModel):
            def _generate(self, messages, **kwargs):
                captured["helper"].append([message.model_copy(deep=True) for message in messages])
                return super()._generate(messages, **kwargs)

        helper = self.setup(instructions="  Helper authored instructions.\n", presented_tools=[])
        root = RootModel([capabilities.call("task", {
            "subagent_type": helper["id"], "description": "Delegated request"}, "delegate"),
            AIMessage(content="Parent done.")])
        child = HelperModel([AIMessage(content="Helper done.")])
        self.harness(lambda run, _sink: child if run.parent_run_id else root)
        run = self.start(task="Original parent request", presented_tools=["echo"],
            helper_agent_ids=[helper["id"]], approval_mode="ask", input_policy={"tool_loading": "always"})
        finished = wait_for_run(self.client, run["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual(len(captured["root"]), 2)
        self.assertEqual(len(captured["helper"]), 1)
        for owner, requests in captured.items():
            for messages in requests:
                systems = [message for message in messages if isinstance(message, SystemMessage)]
                self.assertEqual(len(systems), 1)
                self.assertEqual(systems[0].content.count(HOST_FACT), 1)
                users = [message.content for message in messages if message.type == "human"]
                self.assertEqual(users, ["Delegated request" if owner == "helper" else "Original parent request"])
        saved = self.client.get('/v1/agent-runs/' + finished["child_runs"][0]["run_id"]).json()
        self.assertEqual(saved["presented_tools"], [])
        self.assertEqual(saved["approval_mode"], "ask")
        self.assertIn("  Helper authored instructions.\n", saved["system_prompt"])
        for accepted in (finished, saved):
            self.assertEqual(accepted["system_prompt"].count(HOST_FACT), 1)
            row = next(row for row in accepted["input_sources"] if row["id"] == "workbench_core")
            self.assertGreater(row["estimated_tokens"], 0)

    def test_question_resume_keeps_frozen_system_and_one_tool_answer(self):
        captured = []

        class RecordingModel(ScriptedChatModel):
            def _generate(self, messages, **kwargs):
                captured.append([message.model_copy(deep=True) for message in messages])
                return super()._generate(messages, **kwargs)

        model = RecordingModel([capabilities.call("ask_user", {
            "prompt": "Choose a label", "answer_type": "choice", "choices": ["A", "B"]}, "question"),
            AIMessage(content="Done.")])
        self.harness(lambda *_: model)
        run = self.start(presented_tools=["ask_user"], input_policy={"tool_loading": "always"})
        paused = approval_fixtures.wait_for_interrupt(self.client, run["id"])
        self.assertEqual(paused["system_prompt"].count(HOST_FACT), 1)
        future = "Future composition marker must not enter an accepted run."
        with patch("workbench_backend.agents.effective_setup.WORKBENCH_CORE_INSTRUCTIONS", future), \
                patch("workbench_backend.agents.input_sources.WORKBENCH_CORE_INSTRUCTIONS", future):
            pending = paused["pending_interrupt"]
            self.post(f'/v1/agent-runs/{run["id"]}/interrupt-decision', {
                "interrupt_id": pending["interrupt_id"], "namespace": pending["namespace"],
                "decisions": [{"type": "respond", "message": "B"}]})
            finished = wait_for_run(self.client, run["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual(finished["system_prompt"], paused["system_prompt"])
        self.assertEqual(finished["input_sources"], paused["input_sources"])
        self.assertEqual(len(captured), 2)
        systems = [[message.content for message in messages if isinstance(message, SystemMessage)]
            for messages in captured]
        self.assertEqual(systems[0], systems[1])
        self.assertNotIn(future, systems[1][0])
        self.assertEqual(systems[1][0].count(HOST_FACT), 1)
        self.assertEqual([message.content for message in captured[1] if message.type == "human"],
            ["Do the requested work"])
        answers = [message for message in captured[1] if isinstance(message, ToolMessage)
            and message.tool_call_id == "question"]
        self.assertEqual([message.content for message in answers], ["B"])

    def test_queued_turn_keeps_accepted_prompt_and_source_estimates(self):
        captured = []

        class RecordingModel(ScriptedChatModel):
            def _generate(self, messages, **kwargs):
                captured.append([message.model_copy(deep=True) for message in messages])
                return super()._generate(messages, **kwargs)

        self.harness(lambda *_: RecordingModel([AIMessage(content="Done.")]))
        chat = self.post('/v1/chat/conversations', {
            "deployment_id": self.deployment.id, "presented_tools": []})
        self.post(f'/v1/chat/conversations/{chat["id"]}/queue', {"task": "Queued request"})
        # An unprepared queue item has no model prompt yet. Exercise the
        # explicitly frozen prompt boundary used when one has been prepared.
        stored = self.app.state.chat.store.get(chat["id"])
        stored.queue[0].execution_snapshot.system_prompt = compose_system_prompt(
            input_policy=AgentInputPolicy(), default_system_prompt="Default instructions.",
            profile_system_prompt=None, surface_system_prompt=None, versions=[])
        self.app.state.chat.store.put(stored)
        frozen = stored.queue[0].execution_snapshot.model_dump(mode="json")
        self.assertEqual(frozen["system_prompt"].count(HOST_FACT), 1)
        core = next(row for row in frozen["selection"]["input_sources"] if row["id"] == "workbench_core")
        future = "Future composition marker must not replace queued context."
        with patch("workbench_backend.agents.effective_setup.WORKBENCH_CORE_INSTRUCTIONS", future), \
                patch("workbench_backend.agents.input_sources.WORKBENCH_CORE_INSTRUCTIONS", future):
            self.post(f'/v1/chat/conversations/{chat["id"]}/queue/resume', {})
            finished = chat_fixtures.wait_for_chat(self.client, chat["id"])["current_run"]
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual(finished["system_prompt"], frozen["system_prompt"])
        self.assertEqual(next(row for row in finished["input_sources"] if row["id"] == "workbench_core"), core)
        self.assertEqual(len(captured), 1)
        system, = [message.content for message in captured[0] if isinstance(message, SystemMessage)]
        self.assertEqual(system.count(HOST_FACT), 1)
        self.assertNotIn(future, system)


class HostContextWireTests(unittest.TestCase):
    setUp = adapter_fixtures.EffectiveSetupLiveAdapterTests.setUp
    tearDown = adapter_fixtures.EffectiveSetupLiveAdapterTests.tearDown

    def test_cold_preview_matches_host_fact_in_first_serialized_request(self):
        with patch.object(self.app.state.manager, 'ensure_deployment_ready',
                side_effect=AssertionError('Cold preview started inference')):
            preview = self.client.post('/v1/setup-resolution', json={
                "include_input_content": True, "overrides": {
                    "deployment_id": self.deployment_id, "presented_tools": []}})
        self.assertEqual(preview.status_code, 200, preview.text)
        core = next(row for row in preview.json()["input_sources"] if row["id"] == "workbench_core")
        self.assertEqual(core["content"].count(HOST_FACT), 1)
        self.assertEqual(core["estimated_tokens"], content_token_estimate(core["content"]))
        started = self.client.post('/v1/agent-runs', json={
            "deployment_id": self.deployment_id, "task": "Generate platform-dependent code", "presented_tools": []})
        self.assertEqual(started.status_code, 200, started.text)
        finished = adapter_fixtures.wait_for_run(self.client, started.json()["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        request = adapter_fixtures._RecordingHandler.requests[0]["body"]
        system, = [message["content"] for message in request["messages"] if message["role"] == "system"]
        self.assertEqual(system.count(HOST_FACT), 1)
        self.assertIn(core["content"], system)
        self.assertEqual([message["content"] for message in request["messages"] if message["role"] == "user"],
            ["Generate platform-dependent code"])
        accepted = next(row for row in finished["input_sources"] if row["id"] == "workbench_core")
        self.assertEqual(accepted["estimated_tokens"], core["estimated_tokens"])
        self.assertEqual(finished["presented_tools"], [])


if __name__ == "__main__":
    unittest.main()
