"""Real embedded graphs for Plan, named helpers and requested rubric review."""
from __future__ import annotations

import unittest
import asyncio
import threading
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import patch, PropertyMock

from langchain_core.messages import AIMessage
from workbench_backend.agents.harness import HarnessService
from workbench_backend.interaction.service import InteractionService
from tests.scripted_model import ScriptedChatModel, set_generate_hold, wait_for_generate_hold
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
        observer = self.app.state.harness._interaction_observer
        self.app.state.harness = HarnessService(lambda: self.app.state.manager,
            app_store=self.app.state.app_store, knowledge_provider=lambda: self.app.state.knowledge,
            model_factory=factory, interaction_observer=observer)

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

    def test_queue_keeps_required_project_and_shell_authority(self):
        model_calls = []
        self.harness(lambda *args: model_calls.append(args) or ScriptedChatModel([AIMessage(content="Must not run")]))
        for requirement, expected, project in (
            ("requires_project", "setup_project_required", None),
            ("requires_host_shell", "setup_shell_required", self.project()),
        ):
            with self.subTest(requirement=requirement):
                agent = self.setup(**{requirement: True}, presented_tools=[])
                chat = self.post('/v1/chat/conversations', {
                    "deployment_id": self.deployment.id, "project_id": project['id'] if project else None,
                    "agent_setup_version_id": agent['current_version_id'], "presented_tools": []})
                queued = self.post(f'/v1/chat/conversations/{chat["id"]}/queue', {"task": "Run"})
                frozen = queued['queue'][0]['execution_snapshot']['selection']['configuration']
                self.assertTrue(frozen[requirement])
                resumed = self.post(f'/v1/chat/conversations/{chat["id"]}/queue/resume', {})
                self.assertEqual(resumed['run_ids'], [])
                self.assertEqual(resumed['queue'][0]['pause_error_code'], expected)
        self.assertEqual(model_calls, [])

    def test_helper_requirements_survive_parent_tool_intersection(self):
        child_calls = []
        for requirement, tools, path, error in (
            ("requires_project", ["echo"], None, "requires a project folder"),
            ("requires_host_shell", ["execute", "echo"], str(self.folder), "requires the host-shell tool"),
        ):
            with self.subTest(requirement=requirement):
                helper = self.setup(**{requirement: True}, presented_tools=tools)
                main = ScriptedChatModel([call('task', {'subagent_type': helper['id'], 'description': 'Report'}, 'delegate'), AIMessage(content='Done')])
                self.harness(lambda run, _sink: child_calls.append(run) or ScriptedChatModel([AIMessage(content='Must not run')]) if run.parent_run_id else main)
                final = wait_for_run(self.client, self.start(project_path=path, presented_tools=['echo'], helper_agent_ids=[helper['id']])['id'])
                self.assertEqual(final['status'], 'failed', final)
                self.assertIn(error, final['error'])
                self.assertEqual(len(final['child_runs']), 1)
                self.assertEqual(final['child_runs'][0]['tool_call_id'], 'delegate')
                self.assertEqual(final['child_runs'][0]['status'], 'failed')
                self.assertIn(error, final['child_runs'][0]['error'])
        self.assertEqual(child_calls, [])

    def test_plan_cannot_silently_drop_required_shell_and_run_keeps_requirements(self):
        model_calls = []
        self.harness(lambda *args: model_calls.append(args) or ScriptedChatModel([AIMessage(content='Done')]))
        agent = self.setup(requires_project=True, requires_host_shell=True, presented_tools=['execute'])
        request = {'deployment_id': self.deployment.id, 'agent_setup_version_id': agent['current_version_id'],
            'project_path': str(self.folder), 'task': 'Plan', 'work_mode': 'plan',
            'presented_tools': ['execute']}
        response = self.client.post('/v1/agent-runs', json=request)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['code'], 'setup_shell_required')
        self.assertEqual(model_calls, [])
        request['work_mode'] = 'work'
        final = wait_for_run(self.client, self.post('/v1/agent-runs', request)['id'])
        self.assertTrue(final['requires_project'])
        self.assertTrue(final['requires_host_shell'])

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

    def test_helper_messages_and_tools_replay_under_its_owned_namespace(self):
        helper = self.setup(presented_tools=["echo"])
        main = ScriptedChatModel([call("task", {"subagent_type": helper["id"], "description": "Report the echo"}, "delegate"), AIMessage(content="Parent done.")])
        child = ScriptedChatModel([call("echo", {"text": "child result"}, "echo"), AIMessage(content="Child done.")])
        self.harness(lambda run, _sink: child if run.parent_run_id else main)
        chat = self.post('/v1/chat/conversations', {"deployment_id": self.deployment.id, "presented_tools": ["echo"]})
        thread = self.post('/v1/agent-interaction/threads', {"source_surface": "chat", "conversation_id": chat["id"]})["thread_id"]
        self.post(f'/v1/chat/conversations/{chat["id"]}/start', {"task": "Delegate", "helper_agent_ids": [helper["id"]]})
        finished = chat_fixtures.wait_for_chat(self.client, chat["id"])["current_run"]
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        activity, = finished["child_runs"]
        namespace = activity["namespace"]
        self.assertTrue(namespace and namespace[0].startswith("tools:"), activity)
        last_seq = self.app.state.app_store.get_interaction(thread)["seq"]
        reopened = InteractionService(self.app.state.app_store, lambda: self.app.state.harness, lambda: self.app.state.chat)
        replay = list(reopened.replay(thread, 0, last_seq))
        scoped = [item for item in replay if item["params"].get("namespace", [])[:len(namespace)] == namespace]
        self.assertTrue(any(item["method"] == "tools" for item in scoped), scoped)
        self.assertTrue(any(item["method"] == "values" and item["params"].get("namespace") == namespace
            and any(message.get("content") == "Child done." for message in item["params"]["data"].get("messages", []))
            for item in scoped), scoped)
        root_values = [item for item in replay if item["method"] == "values" and not item["params"].get("namespace")]
        self.assertTrue(root_values)
        self.assertTrue(all(((item["params"]["data"].get("workbench") or {}).get("run") or {}).get("id") in {None, finished["id"]}
            for item in root_values))
        self.assertFalse(any(message.get("type") == "ai" and message.get("content") == "Child done."
            for item in root_values for message in item["params"]["data"].get("messages", [])))

    def test_parallel_helpers_keep_separate_replayed_transcripts(self):
        helper = self.setup(presented_tools=[])
        main = ScriptedChatModel([AIMessage(content="", tool_calls=[
            {"name": "task", "args": {"subagent_type": helper["id"], "description": "Alpha"}, "id": "alpha"},
            {"name": "task", "args": {"subagent_type": helper["id"], "description": "Beta"}, "id": "beta"},
        ]), AIMessage(content="Both done.")])
        self.harness(lambda run, _sink: ScriptedChatModel([AIMessage(content=f"Child {run.task} done.")])
            if run.parent_run_id else main)
        chat = self.post('/v1/chat/conversations', {"deployment_id": self.deployment.id, "presented_tools": ["echo"]})
        thread = self.post('/v1/agent-interaction/threads', {"source_surface": "chat", "conversation_id": chat["id"]})["thread_id"]
        self.post(f'/v1/chat/conversations/{chat["id"]}/start', {"task": "Delegate twice", "helper_agent_ids": [helper["id"]]})
        finished = chat_fixtures.wait_for_chat(self.client, chat["id"])["current_run"]
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        activities = {item["tool_call_id"]: item for item in finished["child_runs"]}
        self.assertEqual(set(activities), {"alpha", "beta"}, (finished["child_runs"], finished["events"], finished.get("error")))
        self.assertNotEqual(activities["alpha"]["namespace"], activities["beta"]["namespace"])
        events = self.app.state.app_store.interaction_events_after(thread, 0)
        for call_id, own_text, other_text, other_request in (("alpha", "Child Alpha done.", "Child Beta done.", "Beta"),
                                                             ("beta", "Child Beta done.", "Child Alpha done.", "Alpha")):
            namespace = activities[call_id]["namespace"]
            scoped = [item for item in events if item["params"].get("namespace", [])[:len(namespace)] == namespace]
            content = [message.get("content") for item in scoped if item["method"] == "values"
                and item["params"].get("namespace") == namespace
                for message in item["params"]["data"].get("messages", [])]
            self.assertIn(own_text, content)
            self.assertNotIn(other_text, content)
            self.assertNotIn(other_request, content)

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

    def test_helper_activity_is_visible_before_model_reservation_finishes(self):
        helper = self.setup(presented_tools=["echo"])
        parent_gate = threading.Event()
        reserve_gate = threading.Event()
        entered_reserve = threading.Event()
        main = ScriptedChatModel([call("task", {"subagent_type": helper["id"], "description": "Report"}, "delegate"),
            AIMessage(content="Done")], hold=parent_gate)
        child = ScriptedChatModel([AIMessage(content="Reported")])
        self.harness(lambda run, _sink: child if run.parent_run_id else main)
        original_reserve = self.app.state.manager.reserve_deployment

        @contextmanager
        def held_reservation(*args, **kwargs):
            entered_reserve.set()
            if not reserve_gate.wait(timeout=10):
                raise AssertionError("Helper reservation was not released")
            with original_reserve(*args, **kwargs) as admitted:
                yield admitted

        try:
            set_generate_hold(parent_gate)
            run = self.start(presented_tools=["echo"], helper_agent_ids=[helper["id"]])
            wait_for_generate_hold()
            with patch.object(self.app.state.manager, "reserve_deployment", side_effect=held_reservation):
                parent_gate.set()
                self.assertTrue(entered_reserve.wait(timeout=10))
                live = self.client.get('/v1/agent-runs/' + run['id']).json()
                activity, = live['child_runs']
                self.assertEqual(activity['tool_call_id'], 'delegate')
                self.assertEqual(activity['status'], 'waiting for model')
                self.assertIsNone(self.app.state.app_store.get_run(activity['run_id']))
                reserve_gate.set()
                finished = wait_for_run(self.client, run['id'])
                self.assertEqual(finished['status'], 'completed', finished.get('error'))
        finally:
            parent_gate.set()
            reserve_gate.set()
            set_generate_hold(None)

    def test_failed_helper_settles_activity_and_child_record(self):
        helper = self.setup(presented_tools=["echo"])
        main = ScriptedChatModel([call("task", {"subagent_type": helper["id"], "description": "Report"}, "delegate"),
            AIMessage(content="The helper failed.")])

        class FailingModel(ScriptedChatModel):
            def _generate(self, *args, **kwargs):
                raise RuntimeError("helper model failed")

        self.harness(lambda run, _sink: FailingModel([]) if run.parent_run_id else main)
        finished = wait_for_run(self.client, self.start(presented_tools=["echo"], helper_agent_ids=[helper["id"]])['id'])
        activity, = finished['child_runs']
        self.assertEqual(activity['status'], 'failed')
        self.assertIn('helper model failed', activity['error'])
        saved = self.client.get('/v1/agent-runs/' + activity['run_id']).json()
        self.assertEqual(saved['status'], 'failed')
        self.assertIn('helper model failed', saved['error'])

    def test_cancel_while_helper_waits_for_model_settles_unadmitted_activity(self):
        helper = self.setup(presented_tools=["echo"])
        parent_gate = threading.Event()
        reserve_gate = threading.Event()
        entered_reserve = threading.Event()
        main = ScriptedChatModel([call("task", {"subagent_type": helper["id"], "description": "Report"}, "delegate"),
            AIMessage(content="Must not continue")], hold=parent_gate)
        self.harness(lambda run, _sink: ScriptedChatModel([AIMessage(content="Must not run")])
            if run.parent_run_id else main)
        original_reserve = self.app.state.manager.reserve_deployment

        @contextmanager
        def held_reservation(*args, **kwargs):
            entered_reserve.set()
            if not reserve_gate.wait(timeout=10):
                raise AssertionError("Helper reservation was not released")
            with original_reserve(*args, **kwargs) as admitted:
                yield admitted

        cancel_error = []
        cancel_thread = None
        try:
            set_generate_hold(parent_gate)
            run = self.start(presented_tools=["echo"], helper_agent_ids=[helper["id"]])
            wait_for_generate_hold()
            with patch.object(self.app.state.manager, "reserve_deployment", side_effect=held_reservation):
                parent_gate.set()
                self.assertTrue(entered_reserve.wait(timeout=10))
                before = self.app.state.harness.get_run(run['id'])
                activity, = before.child_runs
                self.assertEqual(activity.status, 'waiting for model')

                def cancel_run():
                    try:
                        self.app.state.harness.cancel(run['id'])
                    except BaseException as exc:
                        cancel_error.append(exc)

                cancel_thread = threading.Thread(target=cancel_run, daemon=True)
                cancel_thread.start()
                cancelling, _events = self.app.state.harness.wait_after(run['id'], len(before.events), timeout=10)
                self.assertIn(cancelling.status.value, {'cancel_requested', 'cancelled'})
                reserve_gate.set()
                cancel_thread.join(timeout=10)
                self.assertFalse(cancel_thread.is_alive())
                self.assertEqual(cancel_error, [])
                finished = wait_for_run(self.client, run['id'])
                self.assertEqual(finished['status'], 'cancelled')
                activity, = finished['child_runs']
                self.assertEqual(activity['status'], 'cancelled')
                self.assertIsNone(activity['error'])
                self.assertIsNone(self.app.state.app_store.get_run(activity['run_id']))
        finally:
            parent_gate.set()
            reserve_gate.set()
            set_generate_hold(None)
            if cancel_thread is not None:
                cancel_thread.join(timeout=10)

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
        self.assertEqual(waiting["pending_interrupt"]["namespace"], waiting['child_runs'][0]['namespace'])
        self.assertEqual(waiting['child_runs'][0]['status'], 'waiting for approval or answer')
        paused_child = self.client.get('/v1/agent-runs/' + waiting['child_runs'][0]['run_id']).json()
        self.assertEqual(paused_child['pending_interrupt']['interrupt_id'], waiting['pending_interrupt']['interrupt_id'])
        self.post(f'/v1/agent-runs/{run["id"]}/interrupt-decision', approval_fixtures.run_direct_interrupt_decision(waiting, "approve"))
        finished = wait_for_run(self.client, run["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual((self.folder / "child.txt").read_text(), "approved child")
        self.assertEqual(len(finished["child_runs"]), 1)
        resumed_child = self.client.get('/v1/agent-runs/' + finished['child_runs'][0]['run_id']).json()
        self.assertIsNone(resumed_child['pending_interrupt'])
        self.assertEqual([item['id'] for item in resumed_child['tool_invocations'] if item['id'] == 'child-write'], ['child-write'])
        self.assertEqual(sum(item['kind'] == 'tool_call' and item['detail'].get('id') == 'child-write'
            for item in resumed_child['events']), 1)
        self.assertEqual(sum(item['kind'] == 'tool_result' and item['detail'].get('tool_call_id') == 'child-write'
            for item in resumed_child['events']), 1)

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
            'profile_id':profile.id,'per_request_overrides':{'temperature':0.3},'presented_tools':[]})
        self.assertEqual(chat['profile_id'], profile.id)
        self.post(f'/v1/chat/conversations/{chat["id"]}/start', {'task':'Use inherited settings',
            'profile_id':None,'per_request_overrides':None,'startup_overrides':None})
        finished = chat_fixtures.wait_for_chat(self.client, chat['id'])
        self.assertEqual(finished['current_run']['status'], 'completed', finished['current_run'].get('error'))
        self.assertIsNone(finished['profile_id'])
        self.assertIsNone(finished['current_run']['effective_setup']['selected_profile_id'])
        self.assertNotIn('temperature', finished['current_run']['effective_setup']['bags']['per_request']['applied'])

    def test_ask_write_has_no_effect_until_exact_approval(self):
        self.harness(lambda *_: ScriptedChatModel([call('write_file', {'file_path': 'ask.txt', 'content': 'approved'}, 'write'), AIMessage(content='Done')]))
        run = self.start(project_path=str(self.folder), presented_tools=['write_file'], approval_mode='ask')
        waiting = approval_fixtures.wait_for_interrupt(self.client, run['id'])
        self.assertFalse((self.folder / 'ask.txt').exists())
        self.post(f'/v1/agent-runs/{run["id"]}/interrupt-decision', approval_fixtures.run_direct_interrupt_decision(waiting, 'approve'))
        finished = wait_for_run(self.client, run['id'])
        self.assertEqual(finished['status'], 'completed', finished.get('error'))
        self.assertEqual((self.folder / 'ask.txt').read_text(), 'approved')
        self.assertTrue(any(event['kind'] == 'tool_result' for event in finished['events']))

    def test_full_access_native_edit_is_effective_without_an_approval(self):
        self.harness(lambda *_: ScriptedChatModel([call('edit_file', {'file_path': 'sample.txt', 'old_string': 'original', 'new_string': 'changed'}, 'edit'), AIMessage(content='Done')]))
        run = self.start(project_path=str(self.folder), presented_tools=['edit_file'], approval_mode='full_access')
        finished = wait_for_run(self.client, run['id'])
        self.assertEqual(finished['status'], 'completed', finished.get('error'))
        self.assertIsNone(finished['pending_interrupt'])
        self.assertEqual((self.folder / 'sample.txt').read_text(), 'changed')

    def test_full_access_native_write_cannot_escape_the_project(self):
        outside = self.folder.parent / 'outside.txt'
        self.harness(lambda *_: ScriptedChatModel([call('write_file', {'file_path': '../outside.txt', 'content': 'forbidden'}, 'escape'), AIMessage(content='Done')]))
        run = self.start(project_path=str(self.folder), presented_tools=['write_file'], approval_mode='full_access')
        finished = wait_for_run(self.client, run['id'])
        self.assertFalse(outside.exists())
        self.assertTrue(any(event['kind'] == 'tool_result' and event['detail'].get('tool_call_id') == 'escape'
            for event in finished['events']))

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
            for mode in ('ask', 'full_access'):
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
        for mode in ('ask', 'full_access'):
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
        self.assertIsNone(saved['pending_interrupt'])

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
