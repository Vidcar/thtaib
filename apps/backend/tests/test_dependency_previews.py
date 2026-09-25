"""Lifecycle previews follow real saved consumers without becoming deletion gates."""
from __future__ import annotations

import json
import unittest

from tests import test_project_agent_setups as setup_tests
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.connections.schemas import ConnectionSnapshot, ConnectionTool
from workbench_backend.inference.ids import utc_now


class DependencyPreviewTests(unittest.TestCase):
    setUp = setup_tests.ProjectSetupTests.setUp
    tearDown = setup_tests.ProjectSetupTests.tearDown
    post = setup_tests.ProjectSetupTests.post
    project = setup_tests.ProjectSetupTests.project
    setup = setup_tests.ProjectSetupTests.setup

    def preview(self, path):
        response = self.client.get(path + '/delete-preview')
        self.assertEqual(response.status_code, 200, response.text)
        value = response.json()
        self.assertEqual(value['blockers'], [])
        return value

    def memory(self, **values):
        return self.post('/v1/knowledge/entries', {'scope': 'user', 'kind': 'memory', 'content': 'PRIVATE-RETAINED-CONTENT', 'display_name': 'Selected memory', **values})

    def run_record(self, **values):
        now = utc_now()
        run = AgentRun(id='preview-run', deployment_id=self.deployment.id, task='Current task', enabled_tools=[], presented_tools=[],
            created_at=now, updated_at=now, **values)
        self.app.state.app_store.put_run(run)
        return run

    def test_project_and_setup_removal_show_consumers_and_preserve_scope_and_sources(self):
        project = self.project(name='Work folder')
        setup = self.setup(presented_tools=[])
        scoped = self.memory(scope='project', scope_id=project['id'])
        agent_memory = self.memory(scope='agent', scope_id=setup['id'])
        chat = self.post('/v1/chat/conversations', {'project_id': project['id'],
            'agent_setup_version_id': setup['current_version_id'], 'deployment_id': self.deployment.id})
        run = self.run_record(status=AgentRunStatus.running, project_id=project['id'], project_path=project['path'],
            agent_setup_id=setup['id'], agent_setup_version_id=setup['current_version_id'])
        preview = self.preview('/v1/projects/' + project['id'])
        self.assertEqual(preview['target_label'], 'Work folder')
        consumers = {(item['kind'], item['id']): item for item in preview['consumers']}
        self.assertTrue(consumers['agent_run', run.id]['live'])
        self.assertTrue(consumers['chat', chat['id']]['future_use'])
        self.assertTrue(consumers['knowledge', scoped['id']]['retained'])
        self.assertNotIn('PRIVATE-RETAINED-CONTENT', json.dumps(preview))
        self.assertEqual(self.client.delete('/v1/projects/' + project['id']).status_code, 200)
        self.assertEqual((self.folder / 'sample.txt').read_text(), 'original')
        self.assertEqual(self.app.state.knowledge.get_entry(scoped['id']).scope_id, project['id'])
        self.assertEqual(self.app.state.app_store.get_run(run.id).project_id, project['id'])
        setup_preview = self.preview('/v1/agent-setups/' + setup['id'])
        self.assertTrue(any(item['kind'] == 'knowledge' and item['id'] == agent_memory['id'] for item in setup_preview['consumers']))
        removed_setup = self.client.delete('/v1/agent-setups/' + setup['id'])
        self.assertEqual(removed_setup.status_code, 200, removed_setup.text)
        self.assertEqual(len(self.client.get(f"/v1/agent-setups/{setup['id']}/versions").json()), 1)
        self.assertEqual(self.app.state.app_store.get_run(run.id).status, AgentRunStatus.running)

    def test_all_knowledge_versions_and_packages_have_truthful_retention_preview(self):
        memory = self.memory()
        newer = self.post(f"/v1/knowledge/entries/{memory['id']}/edit", {'base_version': memory['current_version_id'], 'content': 'NEW-PRIVATE-CONTENT'})
        project = self.project(defaults={'memory_version_refs': [newer['current_version_id']]})
        setup = self.setup(memory_version_refs=[memory['current_version_id']])
        selected = self.post('/v1/chat/conversations', {'agent_setup_version_id': setup['current_version_id'],
            'deployment_id': self.deployment.id})
        cleared = self.post('/v1/chat/conversations', {'deployment_id': self.deployment.id, 'memory_version_refs': []})
        preview = self.preview('/v1/knowledge/entries/' + memory['id'])
        consumers = {(item['kind'], item['id']): item for item in preview['consumers']}
        self.assertNotIn(('setup_defaults', 'application'), consumers)
        self.assertTrue(consumers['project', project['id']]['future_use'])
        self.assertTrue(consumers['agent_setup_version', setup['current_version_id']]['future_use'])
        self.assertTrue(consumers['chat', selected['id']]['future_use'])
        self.assertNotIn(('chat', cleared['id']), consumers)
        self.assertEqual({item['id'] for item in preview['consumers'] if item['kind'] == 'knowledge_version'}, {memory['current_version_id'], newer['current_version_id']})
        self.assertEqual(self.client.delete('/v1/knowledge/entries/' + memory['id']).status_code, 200)
        self.assertEqual(self.app.state.knowledge.get_version(memory['current_version_id']).content, 'PRIVATE-RETAINED-CONTENT')
        self.assertTrue(self.app.state.setups.get_setup(setup['id']).missing_dependencies)
        package = self.root / 'skill'
        (package / 'references').mkdir(parents=True)
        (package / 'SKILL.md').write_text('---\nname: retained-example\ndescription: Read the reference\n---\nRead references/example.txt.\n')
        (package / 'references' / 'example.txt').write_text('Retained resource')
        skill = self.post('/v1/knowledge/skills/import', {'source_path': str(package)})
        skill_preview = self.preview('/v1/knowledge/entries/' + skill['id'])
        self.assertEqual(skill_preview['target_kind'], 'skill_package')
        self.assertTrue(any('resources' in item for item in skill_preview['retained']))
        self.assertEqual(self.client.delete('/v1/knowledge/entries/' + skill['id']).status_code, 200)
        resource = self.client.get(f"/v1/knowledge/versions/{skill['current_version_id']}/resource", params={'path': 'references/example.txt'})
        self.assertEqual(resource.status_code, 200, resource.text)
        self.assertEqual(resource.json()['content'], 'Retained resource')

    def test_disconnect_and_credential_preview_do_not_claim_cancellation_or_expose_secret(self):
        connection = self.post('/v1/connections', {'name': 'Remote documentation', 'kind': 'mcp', 'transport': 'http', 'url': 'https://example.com/mcp'})
        credential = self.client.put(f"/v1/connections/{connection['id']}/credential", json={'secret': 'PRIVATE-CONNECTION-TOKEN'})
        self.assertEqual(credential.status_code, 200, credential.text)
        connection = credential.json()
        setup = self.setup(connection_ids=[connection['id']])
        tools_off = self.setup(connection_ids=[connection['id']], presented_tools=[])
        descriptor = ConnectionTool(id='external-tool', name='remote_read', remote_name='read', description='Read docs', input_schema={'type': 'object'})
        run = self.run_record(status=AgentRunStatus.running, connection_ids=[connection['id']],
            connection_snapshots=[ConnectionSnapshot(id=connection['id'], name=connection['name'], version=connection['version'], kind='mcp', transport='http', credential_ref=connection['credential_ref'], tools=[descriptor])])
        run.presented_tools = ['remote_read']
        self.app.state.app_store.put_run(run)
        for suffix in ('', '/credential'):
            preview = self.preview('/v1/connections/' + connection['id'] + suffix)
            consumers = {(item['kind'], item['id']): item for item in preview['consumers']}
            self.assertTrue(consumers['agent_setup_version', setup['current_version_id']]['future_use'])
            self.assertFalse(consumers['agent_setup_version', tools_off['current_version_id']]['future_use'])
            self.assertTrue(consumers['agent_run', run.id]['live'])
            self.assertIn('not cancelled', consumers['agent_run', run.id]['effect'])
            self.assertNotIn('PRIVATE-CONNECTION-TOKEN', json.dumps(preview))
        self.assertEqual(self.client.delete('/v1/connections/' + connection['id']).status_code, 200)
        self.assertEqual(self.app.state.app_store.get_run(run.id).status, AgentRunStatus.running)
        self.assertTrue(self.app.state.app_store.get_run(run.id).connection_snapshots)
        self.assertEqual(self.client.get('/v1/projects/missing/delete-preview').status_code, 404)
