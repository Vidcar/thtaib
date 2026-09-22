"""Durable memory proposals retain real scopes and backend-owned actor evidence."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench_backend.app import create_app
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.inference.ids import utc_now
from tests.support import close_workbench_sqlite, offline_workbench_client


class KnowledgeScopeProposalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root / 'data')
        self.client = offline_workbench_client(self.app)
        folder = self.root / 'project'
        folder.mkdir()
        self.project = self.client.post('/v1/projects', json={'path': str(folder), 'name': 'Work'}).json()
        self.setup = self.client.post('/v1/agent-setups', json={'name': 'Writer'}).json()
        now = utc_now()
        self.run = AgentRun(id='agent_test', deployment_id='fixture', task='remember', enabled_tools=[], presented_tools=[], created_at=now, updated_at=now, project_id=self.project['id'], agent_setup_id=self.setup['id'])
        self.app.state.app_store.put_run(self.run)
        self.knowledge = self.app.state.knowledge

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def create(self, **overrides):
        response = self.client.post('/v1/knowledge/entries', json={'scope': 'user', 'kind': 'memory', 'content': 'original', **overrides})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_real_scope_required_and_client_cannot_assign_actor(self):
        for scope, ident in [('agent', None), ('agent', 'invented'), ('project', None), ('project', 'invented'), ('user', 'another-user')]:
            response = self.client.post('/v1/knowledge/entries', json={'scope': scope, 'scope_id': ident, 'kind': 'memory', 'content': 'x'})
            self.assertEqual(response.status_code, 409, response.text)
        created = self.create(scope='project', scope_id=self.project['id'])
        self.assertEqual(created['scope_label'], 'Work')
        self.assertEqual(created['provenance']['actor'], 'human')
        for provenance in [{'actor': 'agent'}, {'actor': 'api_maintainer'}, {'actor': 'human', 'run_id': 'forged'}, {'actor': 'human', 'reviewed_by': 'human'}]:
            response = self.client.post('/v1/knowledge/entries', json={'scope': 'user', 'kind': 'protected_instruction', 'content': 'x', 'provenance': provenance})
            self.assertEqual(response.status_code, 403, response.text)

    def test_proposal_is_not_saved_and_review_retains_agent_origin(self):
        proposal = self.knowledge.propose_memory(run_id=self.run.id, content='remember after review', scope='project', scope_id=self.project['id'])
        self.assertEqual(proposal.status, 'pending')
        self.assertEqual(self.knowledge.list_entries(), [])
        accepted = self.client.post(f'/v1/knowledge/proposals/{proposal.id}/review', json={'decision': 'accept'})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        result = accepted.json()
        saved = self.knowledge.get_entry(result['entry_id'])
        self.assertEqual(saved.content, 'remember after review')
        self.assertEqual(saved.provenance.actor, 'agent')
        self.assertEqual(saved.provenance.run_id, self.run.id)
        self.assertEqual(saved.provenance.reviewed_by, 'human')
        again = self.client.post(f'/v1/knowledge/proposals/{proposal.id}/review', json={'decision': 'accept'}).json()
        self.assertEqual(again['committed_version_id'], result['committed_version_id'])
        self.assertEqual(len(self.knowledge.list_versions(saved.id)), 1)

    def test_automatic_permission_is_exact_scope_and_protected_write_cannot_bypass(self):
        response = self.client.put('/v1/knowledge/automatic-save-policy', json={'scope': 'project', 'scope_id': self.project['id'], 'automatic_agent_writes': True})
        self.assertEqual(response.status_code, 200, response.text)
        saved = self.knowledge.propose_memory(run_id=self.run.id, content='project automatic', scope='project', scope_id=self.project['id'])
        pending = self.knowledge.propose_memory(run_id=self.run.id, content='personal requires review')
        self.assertEqual(saved.status, 'accepted')
        self.assertTrue(saved.automatic)
        self.assertEqual(pending.status, 'pending')
        protected = self.create(kind='protected_instruction')
        with self.assertRaisesRegex(Exception, 'protected instructions'):
            self.knowledge.propose_memory(run_id=self.run.id, content='override', entry_id=protected['id'], base_version=protected['current_version_id'])
        forged_run = self.run.model_copy(update={'id': 'agent_other', 'project_id': None})
        self.app.state.app_store.put_run(forged_run)
        with self.assertRaisesRegex(Exception, 'not bound'):
            self.knowledge.propose_memory(run_id=forged_run.id, content='no', scope='project', scope_id=self.project['id'])

    def test_stale_proposal_conflict_and_revert_append_new_version(self):
        entry = self.create()
        proposal = self.knowledge.propose_memory(run_id=self.run.id, content='agent update', entry_id=entry['id'], base_version=entry['current_version_id'])
        changed = self.client.post(f'/v1/knowledge/entries/{entry["id"]}/edit', json={'content': 'human newer', 'base_version': entry['current_version_id']}).json()
        response = self.client.post(f'/v1/knowledge/proposals/{proposal.id}/review', json={'decision': 'accept'})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.knowledge.get_entry(entry['id']).content, 'human newer')
        reverted = self.client.post(f'/v1/knowledge/entries/{entry["id"]}/revert', json={'target_version_id': entry['current_version_id'], 'base_version': changed['current_version_id']}).json()
        self.assertEqual(reverted['content'], 'original')
        self.assertNotEqual(reverted['current_version_id'], entry['current_version_id'])
        self.assertEqual(len(self.knowledge.list_versions(entry['id'])), 3)

    def test_config_user_permission_and_exact_policy_cannot_disagree(self):
        response = self.client.put('/v1/knowledge/automatic-save-policy', json={'scope': 'user', 'automatic_agent_writes': True})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.put('/v1/knowledge/config', json={'scope_policies': {'user': {'automatic_agent_writes': False}}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()['scope_policies']['user']['automatic_agent_writes'])
        proposal = self.knowledge.propose_memory(run_id=self.run.id, content='Must require review after saving was switched off')
        self.assertEqual(proposal.status, 'pending')
        self.assertEqual(self.knowledge.list_entries(), [])
        policy = next(policy for policy in response.json()['automatic_save_policies'] if policy['scope'] == 'user')
        self.assertFalse(policy['automatic_agent_writes'])

    def test_disable_remove_and_crash_after_commit_do_not_replay_save(self):
        proposal = self.knowledge.propose_memory(run_id=self.run.id, content='save once')
        with patch.object(self.knowledge.store, 'put_proposal', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.knowledge.review_proposal(proposal.id, 'accept')
        recovered = self.knowledge.review_proposal(proposal.id, 'accept')
        self.assertEqual(len(self.knowledge.list_entries()), 1)
        self.assertEqual(len(self.knowledge.list_versions(recovered.entry_id)), 1)
        self.client.patch(f'/v1/knowledge/entries/{recovered.entry_id}', json={'enabled': False})
        with self.assertRaisesRegex(Exception, 'disabled or removed'):
            self.knowledge.resolve_refs(memory_version_refs=[recovered.committed_version_id])
        self.client.delete(f'/v1/knowledge/entries/{recovered.entry_id}')
        self.assertEqual(self.knowledge.list_entries(), [])
        self.assertEqual(self.knowledge.get_version(recovered.committed_version_id).content, 'save once')
