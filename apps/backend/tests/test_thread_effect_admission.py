"""Continuation gates unconfirmed effects even without a project folder."""
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool

import tests.test_harness as harness_fixture
from tests.scripted_model import ScriptedChatModel
from tests.support import wait_for_run
from workbench_backend.agents.harness import _invoke_config
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, ToolOutcome
from workbench_backend.inference.ids import utc_now
from workbench_backend.state.checkpointer import run_checkpoint_task


class ThreadEffectAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = harness_fixture.HarnessApiTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.harness = self.fixture.app.state.harness
        self.client = self.fixture.client

    def uncertain_run(self, thread_id, *, name="browser_click", ident="uncertain-root"):
        now = utc_now()
        run = AgentRun(id=ident, deployment_id=self.fixture.deployment_id,
            status=AgentRunStatus.failed, task="Interrupted external action", thread_id=thread_id,
            enabled_tools=[], presented_tools=[], created_at=now, updated_at=now, finished_at=now,
            tool_outcomes={"action": ToolOutcome(call_id="action", name=name, outcome="uncertain", updated_at=now)})
        self.harness.store.put_run(run)
        return run

    def test_actual_external_effect_blocks_same_thread_until_acknowledged(self):
        effects = []
        async def interrupted_update():
            effects.append("updated")
            raise RuntimeError("Connection ended before confirming the external update")
        tool = StructuredTool.from_function(coroutine=interrupted_update, name="external_update", description="Update external fixture")
        now = utc_now()
        run = AgentRun(id="external-owner", deployment_id=self.fixture.deployment_id, status="running",
            task="Update external fixture", thread_id="external-thread", enabled_tools=[tool.name],
            presented_tools=[tool.name], approval_mode="full_access", created_at=now, updated_at=now)
        self.fixture.scripted = ScriptedChatModel([AIMessage(content="", tool_calls=[
            {"id": "external-call", "name": tool.name, "args": {}}])])
        agent = self.harness._create_compiled_agent(run, [], None, external_tools=[tool])
        async def fail_and_retain():
            with self.assertRaisesRegex(RuntimeError, "Connection ended"):
                await agent.ainvoke({"messages": [HumanMessage(content=run.task)]}, _invoke_config(run))
            run.error = "External action was interrupted"
            run.status = AgentRunStatus.failed
            run.finished_at = utc_now()
            await self.harness._alink_run(run, agent)
            self.harness.store.put_run(run)
        run_checkpoint_task(self.fixture.manager.paths.checkpoints_db, fail_and_retain())
        self.assertEqual(effects, ["updated"])
        self.assertEqual(run.tool_outcomes["external-call"].outcome, "uncertain")
        self.fixture.scripted = ScriptedChatModel([AIMessage(content="Continue after inspection")])
        payload = {"deployment_id": self.fixture.deployment_id, "thread_id": run.thread_id,
            "task": "Continue", "presented_tools": []}
        with patch.object(self.fixture.manager, "ensure_deployment_ready", wraps=self.fixture.manager.ensure_deployment_ready) as prepare:
            denied = self.client.post("/v1/agent-runs", json=payload)
            self.assertEqual(denied.status_code, 409, denied.text)
            self.assertEqual(denied.json()["code"], "effects_unconfirmed")
            self.assertEqual(denied.json()["run_id"], run.id)
            self.assertEqual(denied.json()["recovery_action"], "inspect_effects")
            prepare.assert_not_called()
        self.assertEqual(effects, ["updated"])
        acknowledged = self.harness.acknowledge_project_effects(run.id)
        self.assertEqual(acknowledged.tool_outcomes["external-call"].outcome, "uncertain")
        self.assertTrue(acknowledged.tool_outcomes["external-call"].evidence["acknowledged_at"])
        accepted = self.client.post("/v1/agent-runs", json=payload)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(wait_for_run(self.client, accepted.json()["id"])["status"], "completed")
        self.assertEqual(effects, ["updated"], "Continuing does not replay the external action")

    def test_saved_browser_and_desktop_effects_block_only_their_thread(self):
        from workbench_backend.errors import HarnessError
        for index, name in enumerate(("browser_click", "desktop_click")):
            run = self.uncertain_run(f"saved-thread-{index}", name=name, ident=f"saved-{index}")
            restarted = self.fixture._restart_harness()
            with self.assertRaises(HarnessError) as caught:
                restarted.require_thread_effects_confirmed(run.thread_id)
            self.assertEqual(caught.exception.code, "effects_unconfirmed")
            restarted.require_thread_effects_confirmed("unrelated-thread")
            restarted.acknowledge_project_effects(run.id)
            restarted.require_thread_effects_confirmed(run.thread_id)

    def test_projectless_chat_dispatch_and_queue_resume_keep_inspection_gate(self):
        chat_response = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.fixture.deployment_id, "presented_tools": []})
        self.assertEqual(chat_response.status_code, 200, chat_response.text)
        chat = chat_response.json()
        run = self.uncertain_run(chat["thread_id"])
        saved = self.fixture.app.state.chat.store.get(chat["id"])
        saved.run_ids = [run.id]
        saved.current_run_id = run.id
        self.fixture.app.state.chat.store.put(saved)
        with patch.object(self.fixture.manager, "ensure_deployment_ready", wraps=self.fixture.manager.ensure_deployment_ready) as prepare:
            readiness = self.client.post(f"/v1/chat/conversations/{chat['id']}/readiness", json={})
            self.assertEqual(readiness.status_code, 200, readiness.text)
            self.assertNotIn("effects_unconfirmed", [issue["code"] for issue in readiness.json()["issues"]],
                "Readiness must not hide the existing turn's inspection action behind setup")
            denied = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": "Continue"})
            self.assertEqual(denied.status_code, 409, denied.text)
            self.assertEqual(denied.json()["code"], "effects_unconfirmed")
            prepare.assert_not_called()
        queued = self.client.post(f"/v1/chat/conversations/{chat['id']}/queue", json={"task": "Queued follow-up"})
        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertEqual(self.fixture.app.state.chat.dispatch_idle_queued(), 0)
        paused = self.fixture.app.state.chat.store.get(chat["id"]).queue[0]
        self.assertEqual(paused.status, "paused")
        self.assertEqual(paused.pause_reason, "failed")
        self.assertEqual(paused.pause_error_code, "effects_unconfirmed")
        denied_resume = self.client.post(f"/v1/chat/conversations/{chat['id']}/queue/resume", json={"resume_paused": True})
        self.assertEqual(denied_resume.status_code, 409, denied_resume.text)
        self.assertEqual(self.fixture.app.state.chat.store.get(chat["id"]).queue[0].status, "paused")
        ack = self.client.post(f"/v1/chat/conversations/{chat['id']}/runs/{run.id}/acknowledge-effects", json={})
        self.assertEqual(ack.status_code, 200, ack.text)
        self.fixture.scripted = ScriptedChatModel([AIMessage(content="Continued after inspection")])
        resumed = self.client.post(f"/v1/chat/conversations/{chat['id']}/queue/resume", json={"resume_paused": True})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(wait_for_run(self.client, resumed.json()["current_run_id"])["status"], "completed")
