"""Real embedded graphs for Plan, named helpers and requested rubric review."""
from __future__ import annotations

import unittest
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch, PropertyMock

from langchain_core.messages import AIMessage
from workbench_backend.agents.harness import HarnessService
from tests.scripted_model import ScriptedChatModel
from tests import test_project_agent_setups as fixtures
from tests.support import wait_for_run
from tests import test_host_shell as approval_fixtures
from tests import test_chat as chat_fixtures
from workbench_backend.inference.schemas import ProfileWriteRequest, ConnectedDeploymentRequest


def call(name, args, ident):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": ident}])


class AgentCapabilitiesTests(unittest.TestCase):
    setUp = fixtures.ProjectSetupTests.setUp
    tearDown = fixtures.ProjectSetupTests.tearDown
    post = fixtures.ProjectSetupTests.post
    setup = fixtures.ProjectSetupTests.setup
    project = fixtures.ProjectSetupTests.project

    def harness(self, factory):
        self.app.state.harness = HarnessService(lambda: self.app.state.manager,
            app_store=self.app.state.app_store, knowledge_provider=lambda: self.app.state.knowledge,
            model_factory=factory)

    def start(self, **changes):
        return self.post("/v1/agent-runs", {"deployment_id": self.deployment.id, "task": "Do the requested work", **changes})

    def test_plan_blocks_real_graph_file_effect_under_full_access(self):
        model = ScriptedChatModel([call("write_file", {"file_path": "forbidden.txt", "content": "bad"}, "write"), AIMessage(content="Plan only.")])
        self.harness(lambda *_: model)
        run = self.start(project_path=str(self.folder), presented_tools=["read_file", "write_file"], work_mode="plan", approval_mode="full_access")
        finished = wait_for_run(self.client, run["id"])
        self.assertFalse((self.folder / "forbidden.txt").exists())
        self.assertNotIn("write_file", finished["presented_tools"])
        self.assertEqual(finished["work_mode"], "plan")

    def test_named_helper_uses_parent_scope_and_persists_child(self):
        helper = self.setup(presented_tools=["echo", "write_file"], approval_mode="full_access")
        main = ScriptedChatModel([call("task", {"subagent_type": helper["id"], "description": "Read and report"}, "delegate"), AIMessage(content="Parent done.")])
        child = ScriptedChatModel([call("echo", {"text": "child result"}, "echo"), AIMessage(content="Child done.")])
        self.harness(lambda run, _sink: child if run.parent_run_id else main)
        run = self.start(presented_tools=["echo"], helper_agent_ids=[helper["id"]], approval_mode="ask")
        finished = wait_for_run(self.client, run["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual(len(finished["child_runs"]), 1, finished)
        saved = self.client.get('/v1/agent-runs/' + finished["child_runs"][0]["run_id"]).json()
        self.assertEqual(saved["approval_mode"], "ask")
        self.assertEqual(saved["presented_tools"], ["echo"])
        self.assertEqual(saved["helper_agent_ids"], [])
        self.assertEqual(saved["agent_setup_version_id"], helper["current_version_id"])
        self.assertTrue(any(item["kind"] == "tool_result" for item in saved["events"]))

    def test_helper_uses_its_explicit_other_connected_model(self):
        other = self.app.state.manager.attach_connected(ConnectedDeploymentRequest(display_name='Other model', endpoint='http://127.0.0.1:10/v1'))
        helper = self.setup(deployment_id=other.id, presented_tools=['echo'])
        main = ScriptedChatModel([call('task', {'subagent_type':helper['id'], 'description':'Report'}, 'delegate'), AIMessage(content='Done')])
        child = ScriptedChatModel([AIMessage(content='Different model result')])
        self.harness(lambda run, _sink: child if run.parent_run_id else main)
        finished = wait_for_run(self.client, self.start(presented_tools=['echo'], helper_agent_ids=[helper['id']])['id'])
        self.assertEqual(finished['status'], 'completed', finished.get('error'))
        saved = self.client.get('/v1/agent-runs/' + finished['child_runs'][0]['run_id']).json()
        self.assertEqual(saved['deployment_id'], other.id)

    def test_review_is_distinct_and_stops_after_two_revisions(self):
        verdict = {"result": "needs_revision", "explanation": "The requested evidence is missing.",
            "criteria": [{"name": "Evidence provided", "passed": False, "gap": "Provide evidence"}]}
        script = []
        for index in range(3):
            script.extend([AIMessage(content=f"Draft {index}"), call("GraderResponse", verdict, f"review-{index}")])
        model = ScriptedChatModel(script)
        self.harness(lambda *_: model)
        run = self.start(presented_tools=[], review={"enabled": True, "criteria": "Evidence provided", "max_revisions": 2})
        finished = wait_for_run(self.client, run["id"])
        self.assertEqual(finished["status"], "failed", finished.get("error"))
        self.assertEqual(finished["stop_reason"], "review_max_iterations_reached", finished)
        self.assertEqual(len(finished["review_observation"]["evaluations"]), 3)
        self.assertEqual(finished["completion"]["judgement"]["model_review"], verdict["explanation"])
        self.assertEqual(finished["completion"]["judgement"]["source"], "rubric_review")
        self.assertEqual([item['purpose'] for item in finished['model_requests']], ['work', 'review'] * 3)

    def test_review_off_does_not_claim_answer_is_review(self):
        self.harness(lambda *_: ScriptedChatModel([AIMessage(content="Answer only")]))
        finished = wait_for_run(self.client, self.start(presented_tools=[])["id"])
        self.assertIsNone(finished["completion"]["judgement"]["model_review"])
        self.assertEqual(finished["review_observation"]["status"], "not_requested")

    def test_child_approval_resumes_once_with_same_owned_child(self):
        project = self.project()
        helper = self.setup(presented_tools=["write_file"], approval_mode="full_access")
        main = ScriptedChatModel([call("task", {"subagent_type": helper["id"], "description": "Create result"}, "delegate"), AIMessage(content="Done")])
        child = ScriptedChatModel([call("write_file", {"file_path": "child.txt", "content": "approved child"}, "child-write"), AIMessage(content="Written")])
        self.harness(lambda run, _sink: child if run.parent_run_id else main)
        run = self.start(project_id=project["id"], presented_tools=["write_file"], helper_agent_ids=[helper["id"]], approval_mode="ask")
        waiting = approval_fixtures.wait_for_interrupt(self.client, run["id"])
        self.assertFalse((self.folder / "child.txt").exists())
        self.assertTrue(waiting["pending_interrupt"]["namespace"])
        self.assertEqual(waiting['child_runs'][0]['status'], 'waiting for approval or answer')
        self.post(f'/v1/agent-runs/{run["id"]}/interrupt-decision', approval_fixtures.run_direct_interrupt_decision(waiting, "approve"))
        finished = wait_for_run(self.client, run["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual((self.folder / "child.txt").read_text(), "approved child")
        self.assertEqual(len(finished["child_runs"]), 1)

    def test_queued_helpers_freeze_version_mode_and_review(self):
        helper = self.setup(presented_tools=["echo"], instructions="ORIGINAL HELPER")
        main = ScriptedChatModel([call("task", {"subagent_type": helper["id"], "description": "Report"}, "delegate"), AIMessage(content="Done")])
        child = ScriptedChatModel([AIMessage(content="Reported")])
        self.harness(lambda run, _sink: child if run.parent_run_id else main)
        chat = self.post('/v1/chat/conversations', {"deployment_id": self.deployment.id, "presented_tools": ["echo"]})
        queued = self.post(f'/v1/chat/conversations/{chat["id"]}/queue', {"task": "Plan", "work_mode": "plan", "helper_agent_ids": [helper["id"]], "review": {"enabled": False}})
        self.assertEqual(queued["queue"][0]["helper_snapshots"][0]["version_id"], helper["current_version_id"])
        changed = self.client.patch('/v1/agent-setups/' + helper["id"], json={"name": "Edited", "base_version": helper["current_version_id"], "configuration": {"deployment_id": self.deployment.id, "instructions": "LATER HELPER", "presented_tools": ["echo"]}})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.post(f'/v1/chat/conversations/{chat["id"]}/queue/resume', {})
        finished = chat_fixtures.wait_for_chat(self.client, chat["id"])["current_run"]
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual(finished["work_mode"], "plan")
        self.assertEqual(finished["helper_snapshots"][0]["version_id"], helper["current_version_id"])
        saved = self.client.get('/v1/agent-runs/' + finished["child_runs"][0]["run_id"]).json()
        self.assertIn("ORIGINAL HELPER", saved["system_prompt"])
        self.assertNotIn("LATER HELPER", saved["system_prompt"])

    def test_queue_freezes_parent_and_helper_profile_bags(self):
        manager = self.app.state.manager
        profile = manager.create_profile(ProfileWriteRequest(display_name="Original", per_request={"temperature": 0.2}, agent={"system_prompt": "ORIGINAL PROFILE"}))
        helper = self.setup(profile_id=profile.id, presented_tools=["echo"])
        main = ScriptedChatModel([call("task", {"subagent_type": helper["id"], "description": "Report"}, "delegate"), AIMessage(content="Done")])
        child = ScriptedChatModel([AIMessage(content="Reported")])
        self.harness(lambda run, _sink: child if run.parent_run_id else main)
        chat = self.post('/v1/chat/conversations', {"deployment_id": self.deployment.id, "profile_id": profile.id, "presented_tools": ["echo"]})
        queued = self.post(f'/v1/chat/conversations/{chat["id"]}/queue', {"task": "Report", "helper_agent_ids": [helper["id"]]})
        self.assertEqual(queued['queue'][0]['execution_snapshot']['settings']['per_request']['applied']['temperature'], 0.2)
        manager.update_profile(profile.id, ProfileWriteRequest(display_name="Changed", per_request={"temperature": 0.8}, agent={"system_prompt": "LATER PROFILE"}))
        self.post(f'/v1/chat/conversations/{chat["id"]}/queue/resume', {})
        finished = chat_fixtures.wait_for_chat(self.client, chat["id"])["current_run"]
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        child = self.client.get('/v1/agent-runs/' + finished['child_runs'][0]['run_id']).json()
        for captured in (finished, child):
            self.assertEqual(captured['effective_setup']['bags']['per_request']['applied']['temperature'], 0.2)
            self.assertIn('ORIGINAL PROFILE', captured['system_prompt'])
            self.assertNotIn('LATER PROFILE', captured['system_prompt'])

    def test_chat_null_configuration_and_response_overrides_reset_inheritance(self):
        profile = self.app.state.manager.create_profile(ProfileWriteRequest(display_name='Temporary', per_request={'temperature':0.8}))
        self.harness(lambda *_: ScriptedChatModel([AIMessage(content='Done')]))
        chat = self.post('/v1/chat/conversations', {'deployment_id':self.deployment.id,
            'model_configuration_id':profile.id,'per_request_overrides':{'temperature':0.3},'presented_tools':[]})
        self.assertEqual(chat['model_configuration_id'], profile.id)
        self.post(f'/v1/chat/conversations/{chat["id"]}/start', {'task':'Use inherited settings',
            'model_configuration_id':None,'per_request_overrides':None,'startup_overrides':None})
        finished = chat_fixtures.wait_for_chat(self.client, chat['id'])
        self.assertEqual(finished['current_run']['status'], 'completed', finished['current_run'].get('error'))
        self.assertIsNone(finished['model_configuration_id'])
        self.assertIsNone(finished['current_run']['effective_setup']['selected_profile_id'])
        self.assertNotIn('temperature', finished['current_run']['effective_setup']['bags']['per_request']['applied'])

    def test_ask_write_has_no_effect_until_exact_approval(self):
        self.harness(lambda *_: ScriptedChatModel([call('write_file', {'file_path': 'ask.txt', 'content': 'approved'}, 'write'), AIMessage(content='Done')]))
        run = self.start(project_path=str(self.folder), presented_tools=['write_file'], approval_mode='ask')
        waiting = approval_fixtures.wait_for_interrupt(self.client, run['id'])
        self.assertFalse((self.folder / 'ask.txt').exists())
        self.assertFalse(waiting['file_changes'])
        self.post(f'/v1/agent-runs/{run["id"]}/interrupt-decision', approval_fixtures.run_direct_interrupt_decision(waiting, 'approve'))
        finished = wait_for_run(self.client, run['id'])
        self.assertEqual(finished['status'], 'completed', finished.get('error'))
        self.assertEqual((self.folder / 'ask.txt').read_text(), 'approved')
        self.assertEqual(len(finished['file_changes']), 1)

    def test_approve_text_is_recoverable_but_binary_delete_still_pauses(self):
        self.harness(lambda *_: ScriptedChatModel([call('edit_file', {'file_path': 'sample.txt', 'old_string': 'original', 'new_string': 'changed'}, 'edit'), AIMessage(content='Done')]))
        run = self.start(project_path=str(self.folder), presented_tools=['edit_file'], approval_mode='approve_for_me')
        finished = wait_for_run(self.client, run['id'])
        self.assertEqual(finished['status'], 'completed', finished.get('error'))
        view, = self.client.get(f'/v1/agent-runs/{run["id"]}/file-changes').json()
        self.assertTrue(view['reversal_available'])
        self.assertEqual(view['change']['before']['text'], 'original')
        (self.folder / 'binary.dat').write_bytes(b'\x00binary')
        self.harness(lambda *_: ScriptedChatModel([call('delete_file', {'file_path': 'binary.dat'}, 'delete'), AIMessage(content='Done')]))
        run = self.start(project_path=str(self.folder), presented_tools=['delete_file'], approval_mode='approve_for_me')
        waiting = approval_fixtures.wait_for_interrupt(self.client, run['id'])
        self.assertEqual((self.folder / 'binary.dat').read_bytes(), b'\x00binary')
        self.post(f'/v1/agent-runs/{run["id"]}/interrupt-decision', approval_fixtures.run_direct_interrupt_decision(waiting, 'reject'))
        wait_for_run(self.client, run['id'])

    def test_external_receiver_requires_approval_except_full_access(self):
        from fastmcp import FastMCP, Client
        from langchain.mcp import MCPAdapter
        from workbench_backend.connections.service import ConnectionService
        from workbench_backend.connections.schemas import ConnectionWrite
        server = FastMCP('Permission receiver')
        effects = []
        @server.tool
        async def receive(value: str) -> str:
            """Record one actual external protocol call."""
            effects.append(value)
            return 'received:' + value
        @asynccontextmanager
        async def factory(record, unsupported):
            async with MCPAdapter(Client(server)) as adapter:
                yield adapter
        service = ConnectionService(self.app.state.app_store, adapter_factory=factory)
        record = service.create(ConnectionWrite(name='Receiver', kind='mcp', transport='http', url='http://localhost/mcp'))
        tested = asyncio.run(service.test(record.id))
        tool_name = tested.tools[0].name
        with patch.object(HarnessService, 'connections', new_callable=PropertyMock, return_value=service):
            for mode in ('ask', 'approve_for_me', 'full_access'):
                self.harness(lambda *_, mode=mode: ScriptedChatModel([call(tool_name, {'value':mode}, mode), AIMessage(content='Done')]))
                run = self.start(connection_ids=[record.id], presented_tools=[tool_name], approval_mode=mode)
                if mode != 'full_access':
                    waiting = approval_fixtures.wait_for_interrupt(self.client, run['id'])
                    self.assertNotIn(mode, effects)
                    self.post(f'/v1/agent-runs/{run["id"]}/interrupt-decision', approval_fixtures.run_direct_interrupt_decision(waiting, 'reject'))
                finished = wait_for_run(self.client, run['id'])
                self.assertEqual(finished['status'], 'completed', finished.get('error'))
        self.assertEqual(effects, ['full_access'])

    def test_access_does_not_commit_memory_without_scope_permission(self):
        for mode in ('ask', 'approve_for_me', 'full_access'):
            self.harness(lambda *_, mode=mode: ScriptedChatModel([call('propose_memory', {'content':'A proposed preference', 'scope':'user'}, mode), AIMessage(content='Proposed')]))
            run = self.start(presented_tools=['propose_memory'], approval_mode=mode)
            finished = wait_for_run(self.client, run['id'])
            self.assertEqual(finished['status'], 'completed', finished.get('error'))
            proposal, = self.app.state.knowledge.list_proposals(run_id=run['id'])
            self.assertEqual(proposal.status, 'pending')
            self.assertIsNone(proposal.committed_version_id)

    def test_cancel_child_approval_never_writes_and_settles_child(self):
        project = self.project()
        helper = self.setup(presented_tools=["write_file"])
        main = ScriptedChatModel([call("task", {"subagent_type": helper["id"], "description": "Create result"}, "delegate"), AIMessage(content="Done")])
        child = ScriptedChatModel([call("write_file", {"file_path": "cancelled.txt", "content": "must not write"}, "child-write"), AIMessage(content="Written")])
        self.harness(lambda run, _sink: child if run.parent_run_id else main)
        run = self.start(project_id=project["id"], presented_tools=["write_file"], helper_agent_ids=[helper["id"]], approval_mode="ask")
        waiting = approval_fixtures.wait_for_interrupt(self.client, run["id"])
        self.post(f'/v1/agent-runs/{run["id"]}/cancel', {})
        finished = wait_for_run(self.client, run["id"])
        self.assertEqual(finished["status"], "cancelled", finished.get("error"))
        self.assertFalse((self.folder / "cancelled.txt").exists())
        self.assertEqual(finished["child_runs"][0]["status"], "cancelled")
        saved = self.client.get('/v1/agent-runs/' + waiting["child_runs"][0]["run_id"]).json()
        self.assertEqual(saved["status"], "cancelled")

    def test_shared_tool_budget_includes_helper_dispatch(self):
        helper = self.setup(presented_tools=["echo"])
        main = ScriptedChatModel([call("task", {"subagent_type": helper["id"], "description": "Report"}, "delegate"), call("echo", {"text": "over budget"}, "parent-extra"), AIMessage(content="Done")])
        child = ScriptedChatModel([call("echo", {"text": "in budget"}, "child-echo"), AIMessage(content="Reported")])
        self.harness(lambda run, _sink: child if run.parent_run_id else main)
        run = self.start(presented_tools=["echo"], helper_agent_ids=[helper["id"]], budgets={"max_tool_calls": 2})
        finished = wait_for_run(self.client, run["id"])
        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["stop_reason"], "tool_budget_exhausted")
        self.assertEqual(finished["dispatched_tool_calls"], 2)
        self.assertFalse(any(event["kind"] == "tool_result" and event["detail"].get("tool_call_id") == "parent-extra" for event in finished["events"]))
