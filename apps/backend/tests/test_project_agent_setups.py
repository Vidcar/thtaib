"""Canonical folders, immutable setup versions and real Chat dispatch selection."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage

from workbench_backend.app import create_app
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.setup_schemas import SetupConfiguration
from workbench_backend.inference.schemas import ConnectedDeploymentRequest
from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client
from tests.test_chat import wait_for_chat


class ProjectSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root / "data")
        self.client = offline_workbench_client(self.app)
        self.folder = self.root / "project"
        self.folder.mkdir()
        (self.folder / "sample.txt").write_text("original", encoding="utf-8")
        self.deployment = self.app.state.manager.attach_connected(ConnectedDeploymentRequest(display_name="Fixture", endpoint="http://127.0.0.1:9/v1"))

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def project(self, **values):
        return self.post("/v1/projects", {"path": str(self.folder), **values})

    def setup(self, **configuration):
        return self.post("/v1/agent-setups", {"name": "Helper", "configuration": {"deployment_id": self.deployment.id, **configuration}})

    def test_project_aliases_removal_and_fixed_chat_area(self):
        project = self.project(name="Work")
        alias = self.project(path=str(self.folder / ".." / "project"))
        self.assertEqual(project["id"], alias["id"])
        chat = self.post("/v1/chat/conversations", {"project_id": project["id"], "deployment_id": self.deployment.id})
        self.assertEqual(chat["area_id"], project["id"])
        self.assertEqual(chat["area_label"], "Work")
        listing = self.client.get(f'/v1/projects/{project["id"]}/files').json()
        self.assertEqual(listing["path"], "")
        self.assertEqual(listing["entries"][0]["path"], "sample.txt")
        self.assertEqual(self.client.get(f'/v1/projects/{project["id"]}/files', params={"path": ".."}).status_code, 403)
        self.assertEqual(self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json={"task": "go", "project_id": None}).status_code, 409)
        removed = self.client.delete(f'/v1/projects/{project["id"]}').json()
        self.assertFalse(removed["active"])
        self.assertEqual((self.folder / "sample.txt").read_text(), "original")
        self.assertEqual(self.client.get(f'/v1/chat/conversations/{chat["id"]}').json()["area_id"], project["id"])
        self.assertEqual(self.client.get('/v1/projects').json(), [])
        self.assertEqual(self.project()["id"], project["id"])

    def test_versions_conflicts_duplicate_and_dependency_removal(self):
        setup = self.setup(presented_tools=[])
        payload = {"base_version": setup["current_version_id"], "name": "Renamed", "configuration": setup["configuration"]}
        updated = self.client.patch(f'/v1/agent-setups/{setup["id"]}', json=payload)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(self.client.patch(f'/v1/agent-setups/{setup["id"]}', json=payload).status_code, 409)
        versions = self.client.get(f'/v1/agent-setups/{setup["id"]}/versions').json()
        self.assertEqual([v["name"] for v in versions], ["Helper", "Renamed"])
        copied = self.post(f'/v1/agent-setups/{setup["id"]}/duplicate', {})
        self.assertNotEqual(copied["id"], setup["id"])
        self.app.state.manager.store.delete_deployment(self.deployment.id)
        view = self.client.get(f'/v1/agent-setups/{setup["id"]}').json()
        self.assertEqual(view["missing_dependencies"][0]["id"], self.deployment.id)
        failed = self.client.post('/v1/setup-resolution', json={"agent_setup_version_id": setup["current_version_id"]})
        self.assertEqual(failed.status_code, 409, failed.text)
        self.client.delete(f'/v1/agent-setups/{setup["id"]}')
        self.assertEqual(len(self.client.get(f'/v1/agent-setups/{setup["id"]}/versions').json()), 2)

    def test_named_layers_and_empty_selection_do_not_erase_protected_restrictions(self):
        self.app.state.app_store.put_setup_defaults(SetupConfiguration(instructions="APP", presented_tools=["read_file"], requires_project=True))
        project = self.project(defaults={"instructions": "PROJECT", "presented_tools": ["ls"]})
        setup = self.setup(instructions="AGENT", presented_tools=[])
        resolved = self.post('/v1/setup-resolution', {"project_id": project["id"], "agent_setup_version_id": setup["current_version_id"], "overrides": {"instructions": "TURN", "requires_project": False}})
        self.assertEqual(resolved["configuration"]["presented_tools"], [])
        self.assertTrue(resolved["configuration"]["requires_project"])
        self.assertEqual([i["content"] for i in resolved["instruction_layers"]], ["APP", "PROJECT", "AGENT", "TURN"])

    def test_dependency_preview_matches_inherited_application_selection(self):
        self.app.state.app_store.put_setup_defaults(SetupConfiguration(embedding_deployment_id=self.deployment.id))
        setup = self.setup(presented_tools=['search_knowledge'])
        self.post('/v1/setup-resolution', {'agent_setup_version_id': setup['current_version_id']})
        self.assertEqual(setup['missing_dependencies'], [])
        self.app.state.app_store.put_setup_defaults(SetupConfiguration(profile_id='removed-preset'))
        inherited = self.setup(presented_tools=[])
        self.assertEqual([(issue['kind'], issue['id']) for issue in inherited['missing_dependencies']], [('profile_id', 'removed-preset')])

    def test_edit_cannot_reactivate_setup_removed_before_version_commit(self):
        setup = self.setup(presented_tools=[])
        store = self.app.state.app_store
        save = store.save_agent_setup

        def remove_before_commit(record, version=None, *, base_version=None):
            if base_version is not None:
                current = store.get_agent_setup(record.id)
                save(current.model_copy(update={'active': False}))
            return save(record, version, base_version=base_version)

        with patch.object(store, 'save_agent_setup', side_effect=remove_before_commit):
            response = self.client.patch(f'/v1/agent-setups/{setup["id"]}', json={
                'name': 'Stale edit', 'base_version': setup['current_version_id'], 'configuration': setup['configuration']})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertFalse(store.get_agent_setup(setup['id']).active)
        self.assertEqual(len(store.list_agent_setup_versions(setup['id'])), 1)

    def test_tools_off_does_not_require_inactive_connection(self):
        setup = self.setup(presented_tools=[], connection_ids=['removed-connection'])
        self.assertEqual(setup['missing_dependencies'], [])
        resolved = self.post('/v1/setup-resolution', {'agent_setup_version_id': setup['current_version_id']})
        self.assertEqual(resolved['configuration']['presented_tools'], [])
        enabled = self.client.post('/v1/setup-resolution', json={
            'agent_setup_version_id': setup['current_version_id'], 'overrides': {'presented_tools': ['echo']}})
        self.assertEqual(enabled.status_code, 409, enabled.text)

    def test_dependency_preview_reports_different_model_and_deployment(self):
        from workbench_backend.inference.schemas import ModelBundle, BundleSource
        self.app.state.manager.store.put_bundle(ModelBundle(id='other-model', display_name='Other model',
            source=BundleSource(kind='local'), files=[], created_at=self.deployment.created_at))
        setup = self.setup(bundle_id='other-model', presented_tools=[])
        self.assertTrue(any(issue['kind'] == 'bundle_id' and 'different model' in issue['reason'] for issue in setup['missing_dependencies']), setup)
        response = self.client.post('/v1/setup-resolution', json={'agent_setup_version_id': setup['current_version_id']})
        self.assertEqual(response.status_code, 409, response.text)

    def test_explicit_null_clears_inherited_embedding_on_subsequent_turns(self):
        setup = self.setup(embedding_deployment_id=self.deployment.id)
        resolved = self.post('/v1/setup-resolution', {'agent_setup_version_id': setup['current_version_id'], 'overrides': {'embedding_deployment_id': None}})
        self.assertIsNone(resolved['configuration']['embedding_deployment_id'])
        chat = self.post('/v1/chat/conversations', {'agent_setup_version_id': setup['current_version_id']})
        from workbench_backend.chat.schemas import ChatStartRequest
        conversation = self.app.state.app_store.get_conversation(chat['id'])
        self.app.state.chat._apply_start_configuration(conversation, ChatStartRequest(task='clear', embedding_deployment_id=None))
        self.app.state.app_store.put_conversation(conversation)
        reloaded = self.app.state.app_store.get_conversation(chat['id'])
        self.app.state.chat._apply_start_configuration(reloaded, ChatStartRequest(task='continue'))
        self.assertIsNone(reloaded.embedding_deployment_id)

    def test_chat_uses_selected_version_and_next_turn_explicit_empty(self):
        setup = self.setup(instructions="AGENT ORIGINAL", presented_tools=["read_file"], per_request_overrides={"temperature": 0.2})
        project = self.project(defaults={"instructions": "PROJECT FIRST"})
        self.app.state.harness = HarnessService(lambda: self.app.state.manager, app_store=self.app.state.app_store,
            knowledge_provider=lambda: self.app.state.knowledge, model_factory=lambda *_: ScriptedChatModel([AIMessage(content="done")]))
        chat = self.post('/v1/chat/conversations', {"project_id": project["id"], "agent_setup_version_id": setup["current_version_id"]})
        with patch.object(self.app.state.manager, 'ensure_deployment_ready', return_value=self.deployment):
            self.post(f'/v1/chat/conversations/{chat["id"]}/start', {"task": "hello"})
            first = wait_for_chat(self.client, chat["id"])
            run = first["current_run"]
            self.assertEqual(run["agent_setup_version_id"], setup["current_version_id"])
            self.assertIn("AGENT ORIGINAL", run["effective_setup"]["system_prompt"])
            self.assertIn("PROJECT FIRST", run["effective_setup"]["system_prompt"])
            self.assertEqual(run["effective_setup"]["bags"]["per_request"]["applied"]["temperature"], 0.2)
            self.post(f'/v1/chat/conversations/{chat["id"]}/start', {"task": "again", "presented_tools": []})
            second = wait_for_chat(self.client, chat["id"])
            self.assertEqual(second["thread_id"], first["thread_id"])
            self.assertEqual(second["current_run"]["presented_tools"], [])

    def test_general_chat_applies_explicit_turn_instructions(self):
        self.app.state.harness = HarnessService(lambda: self.app.state.manager, app_store=self.app.state.app_store,
            knowledge_provider=lambda: self.app.state.knowledge, model_factory=lambda *_: ScriptedChatModel([AIMessage(content="done")]))
        chat = self.post('/v1/chat/conversations', {"deployment_id": self.deployment.id})
        self.post(f'/v1/chat/conversations/{chat["id"]}/start', {"task": "hello", "instructions": "GENERAL TURN INSTRUCTIONS", "presented_tools": []})
        finished = wait_for_chat(self.client, chat['id'])
        self.assertEqual(finished['current_run']['status'], 'completed', finished['current_run'].get('error'))
        self.assertIn('GENERAL TURN INSTRUCTIONS', finished['current_run']['effective_setup']['system_prompt'])

    def test_queued_setup_retains_selected_version_and_project_instruction_snapshot(self):
        setup = self.setup(instructions='SAVED AGENT ORIGINAL', presented_tools=[])
        project = self.project(defaults={'instructions': 'PROJECT AT ENQUEUE'})
        self.app.state.harness = HarnessService(lambda: self.app.state.manager, app_store=self.app.state.app_store,
            knowledge_provider=lambda: self.app.state.knowledge, model_factory=lambda *_: ScriptedChatModel([AIMessage(content="done")]))
        chat = self.post('/v1/chat/conversations', {'project_id': project['id'], 'agent_setup_version_id': setup['current_version_id']})
        queued = self.post(f'/v1/chat/conversations/{chat["id"]}/queue', {'task': 'queued work'})
        self.assertEqual(queued['queue'][0]['intended_config']['agent_setup_version_id'], setup['current_version_id'])
        self.assertEqual(self.client.patch(f'/v1/projects/{project["id"]}', json={'defaults': {'instructions': 'PROJECT LATER EDIT'}}).status_code, 200)
        changed = self.client.patch(f'/v1/agent-setups/{setup["id"]}', json={'base_version': setup['current_version_id'], 'name': 'Helper', 'configuration': {'deployment_id': self.deployment.id, 'instructions': 'SAVED AGENT LATER EDIT', 'presented_tools': []}})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.post(f'/v1/chat/conversations/{chat["id"]}/queue/resume', {})
        finished = wait_for_chat(self.client, chat['id'])
        run = finished['current_run']
        self.assertEqual(run['status'], 'completed', run.get('error'))
        self.assertEqual(run['agent_setup_version_id'], setup['current_version_id'])
        prompt = run['effective_setup']['system_prompt']
        self.assertIn('PROJECT AT ENQUEUE', prompt)
        self.assertIn('SAVED AGENT ORIGINAL', prompt)
        self.assertNotIn('LATER EDIT', prompt)
