"""Inline helpers own their outcomes, context failures and terminal measurements."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage

from tests import test_agent_capabilities as helper_fixture
from tests import test_context_budget as context_fixture
from tests.scripted_model import ScriptedChatModel
from tests.support import wait_for_run
from workbench_backend.agents.context import ContextObservation
from workbench_backend.agents.harness_backend import FilesystemBackend
from workbench_backend.agents.schemas import GenerationObservation, RunFailure, ToolOutcome
from workbench_backend.inference.ids import utc_now


class HelperRecoveryTests(unittest.TestCase):
    setUp = helper_fixture.AgentCapabilitiesTests.setUp
    tearDown = helper_fixture.AgentCapabilitiesTests.tearDown
    post = helper_fixture.AgentCapabilitiesTests.post
    setup = helper_fixture.AgentCapabilitiesTests.setup
    harness = helper_fixture.AgentCapabilitiesTests.harness
    start = helper_fixture.AgentCapabilitiesTests.start

    def test_always_skill_requirement_survives_parent_tool_intersection_before_child_model(self):
        skill = self.post("/v1/knowledge/entries", {"scope": "user", "kind": "skill",
            "content": "---\nname: echo-required\ndescription: Use the selected echo.\nrequired-tools: [echo]\n---\nUse echo before replying.\n"})
        helper = self.setup(presented_tools=["echo"], skill_entry_ids=[skill["id"]],
            input_policy={"reference_loading": {skill["id"]: "always"}})
        main = ScriptedChatModel([helper_fixture.call("task", {"subagent_type": helper["id"],
            "description": "Report"}, "delegate"), AIMessage(content="Done")])
        child_calls = []

        def factory(run, _sink):
            if run.parent_run_id:
                child_calls.append(run)
                return ScriptedChatModel([AIMessage(content="Body must not reach this model")])
            return main

        self.harness(factory)
        final = wait_for_run(self.client, self.start(presented_tools=["time_now"], helper_agent_ids=[helper["id"]])["id"])
        self.assertEqual(final["status"], "failed", final)
        self.assertIn("Select these tools: echo", final["error"])
        self.assertEqual(final["child_runs"][0]["status"], "failed")
        self.assertEqual(final["tool_outcomes"]["delegate"]["outcome"], "failed")
        self.assertEqual(child_calls, [])
        self.assertNotIn("echo", final["presented_tools"])

    def test_child_does_not_inherit_parent_outcomes_failure_or_housekeeping(self):
        helper = self.setup(presented_tools=["echo"])
        main = ScriptedChatModel([helper_fixture.call("task", {"subagent_type": helper["id"], "description": "Return an echo"}, "delegate"), AIMessage(content="Done")])
        admitted = []

        def factory(run, _sink):
            if run.parent_run_id:
                admitted.append(run.model_copy(deep=True))
                return ScriptedChatModel([helper_fixture.call("echo", {"text": "helper output"}, "child-echo"), AIMessage(content="Helper done")])
            run.tool_outcomes = {
                "parent-success": ToolOutcome(call_id="parent-success", name="echo", outcome="succeeded", result="known", updated_at=utc_now()),
                "parent-unknown": ToolOutcome(call_id="parent-unknown", name="write_file", outcome="uncertain", recovery_action="continue", evidence={"acknowledged_at": utc_now()}, updated_at=utc_now()),
            }
            run.failure = RunFailure(category="capacity", code="context_capacity_exceeded", message="Parent-only failure", recovery_action="change_limit")
            run.housekeeping_context = {"summary": ContextObservation(purpose="summary", input_tokens=456)}
            run.housekeeping_generation = {"summary": GenerationObservation(purpose="summary", output_tokens=123, elapsed_seconds=1, measured_at=utc_now())}
            run.project_outline = {"cache_key": "parent-only"}
            run.retrieved_material = ["parent-only retrieval"]
            return main

        self.harness(factory)
        finished = wait_for_run(self.client, self.start(project_path=str(self.folder), presented_tools=["echo"], helper_agent_ids=[helper["id"]])["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        child, = admitted
        self.assertEqual(child.tool_outcomes, {})
        self.assertIsNone(child.failure)
        self.assertEqual(child.housekeeping_context, {})
        self.assertEqual(child.housekeeping_generation, {})
        self.assertIsNone(child.project_outline)
        self.assertIsNone(child.activity_phase)
        self.assertEqual(child.retrieved_material, [])
        saved = self.app.state.harness.get_run(child.id)
        self.assertEqual(set(saved.tool_outcomes), {"child-echo"})
        self.assertEqual(saved.tool_outcomes["child-echo"].outcome, "succeeded")
        self.assertIsNone(saved.failure)
        self.assertIsNone(saved.activity_phase)
        self.assertEqual(finished["tool_outcomes"][f"{child.id}:child-echo"]["outcome"], "succeeded")

    def test_helper_model_failure_has_known_task_result_without_uncertain_effect_gate(self):
        helper = self.setup(presented_tools=["echo"])
        main = ScriptedChatModel([helper_fixture.call("task", {"subagent_type": helper["id"], "description": "Report"}, "delegate")])

        class FailedModel(ScriptedChatModel):
            def _generate(self, *args, **kwargs):
                raise RuntimeError("helper model unavailable")

        self.harness(lambda run, sink: FailedModel([]) if run.parent_run_id else main)
        finished = wait_for_run(self.client, self.start(project_path=str(self.folder), presented_tools=["echo"], helper_agent_ids=[helper["id"]])["id"])
        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["tool_outcomes"]["delegate"]["outcome"], "failed")
        self.assertEqual(finished["failure"]["recovery_action"], "continue")
        saved = self.app.state.harness.get_run(finished["child_runs"][0]["run_id"])
        self.assertEqual(saved.tool_outcomes, {})
        self.assertEqual(saved.failure.recovery_action, "continue")
        self.assertIsNone(saved.activity_phase)
        self.assertIsNone(self.app.state.harness.project_blocker(str(self.folder)))

    def test_helper_unconfirmed_write_still_gates_project_with_exact_child_identity(self):
        helper = self.setup(presented_tools=["write_file"], approval_mode="full_access")
        main = ScriptedChatModel([helper_fixture.call("task", {"subagent_type": helper["id"], "description": "Write once"}, "delegate")])
        child = ScriptedChatModel([helper_fixture.call("write_file", {"file_path": "/child.txt", "content": "expected complete content"}, "write")])
        self.harness(lambda run, _sink: child if run.parent_run_id else main)
        native_write = FilesystemBackend.write

        def interrupted_write(backend, path, content):
            if path == "/child.txt":
                native_write(backend, path, "partial unexpected bytes")
                raise RuntimeError("writer terminated before confirming completion")
            return native_write(backend, path, content)

        with patch.object(FilesystemBackend, "write", interrupted_write):
            finished = wait_for_run(self.client, self.start(project_path=str(self.folder), presented_tools=["write_file"], helper_agent_ids=[helper["id"]], approval_mode="full_access")["id"])
        child_id = finished["child_runs"][0]["run_id"]
        self.assertEqual(finished["tool_outcomes"]["delegate"]["outcome"], "failed")
        self.assertEqual(finished["tool_outcomes"][f"{child_id}:write"]["outcome"], "uncertain")
        self.assertEqual(finished["failure"]["recovery_action"], "inspect_effects")
        saved = self.app.state.harness.get_run(child_id)
        self.assertEqual(saved.failure.recovery_action, "inspect_effects")
        self.assertEqual(set(saved.tool_outcomes), {"write"})
        self.assertIsNone(saved.activity_phase)
        self.assertEqual((self.folder / "child.txt").read_text(), "partial unexpected bytes")
        self.assertIsNone(self.app.state.harness.project_blocker(str(self.folder)))


class HelperContextTests(unittest.TestCase):
    def test_irreducible_helper_request_reaches_native_recovery_and_keeps_its_failure(self):
        fixture = context_fixture.ContextBudgetHarnessTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        helper_response = fixture.client.post("/v1/agent-setups", json={"name": "Bounded helper", "configuration": {
            "deployment_id": fixture.deployment_id, "presented_tools": [], "per_request_overrides": {"max_tokens": 1024}}})
        self.assertEqual(helper_response.status_code, 200, helper_response.text)
        helper = helper_response.json()
        main = ScriptedChatModel([helper_fixture.call("task", {"subagent_type": helper["id"], "description": "Important oversized request. " * 4000}, "delegate")])
        factory = fixture._mock_transport_model
        admitted = []

        def model_for_run(run, sink):
            if run.parent_run_id:
                admitted.append(run.model_copy(deep=True))
                return factory(run, sink)
            return main

        fixture.harness._model_factory = model_for_run
        started = fixture._start(thread_id="helper-context", task="Delegate", presented_tools=["echo"], helper_agent_ids=[helper["id"]])
        self.assertEqual(started.status_code, 200, started.text)
        finished = fixture._complete(started.json())
        self.assertEqual(len(admitted), 1, finished)
        child, = admitted
        self.assertIsNone(child.context_observation.fits, "estimated admission must not preempt native context reduction")
        saved = fixture.harness.get_run(child.id)
        self.assertEqual(saved.failure.category, "capacity")
        self.assertEqual(saved.failure.recovery_action, "change_limit")
        self.assertIs(saved.context_observation.fits, False)
        self.assertIn("Deep Agents exhausted native context reduction", " ".join(saved.context_observation.notes))
        self.assertIsNone(saved.activity_phase)
        self.assertEqual(fixture.chat_payloads, [], "an irreducible request must fail before model dispatch")
        self.assertEqual(finished["tool_outcomes"]["delegate"]["outcome"], "failed")
        self.assertNotEqual(finished["failure"]["category"], "uncertain_effects")
