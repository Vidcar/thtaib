"""Observed file effects and conflict-aware reversal through actual tools/API."""
from __future__ import annotations

import unittest

from langchain_core.messages import AIMessage
from tests import test_harness as harness_tests
from tests.scripted_model import ScriptedChatModel
from tests.support import wait_for_run
from workbench_backend.inference.ids import new_id


class ContentLineCountTests(unittest.TestCase):
    def test_counts_use_stored_text_and_omit_missing_text(self) -> None:
        from workbench_backend.agents.file_changes import content_line_counts

        self.assertEqual(content_line_counts("a\nb\nc\nd\ne", "a\nB\nC\nD\nE\nf"), (5, 4))
        self.assertIsNone(content_line_counts(None, "a\nB"))
        self.assertIsNone(content_line_counts("a", None))

    def test_view_counts_match_a_five_and_four_edit(self) -> None:
        import tempfile
        from pathlib import Path
        from workbench_backend.agents.file_changes import FileImage, ProjectFileChange, change_view
        from workbench_backend.inference.ids import new_id, utc_now

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "thistest.md"
            target.write_text("a\nB\nC\nD\nE\nf\n", encoding="utf-8")
            now = utc_now()
            change = ProjectFileChange(
                id=new_id("change"),
                run_id="run",
                tool_call_id="edit-1",
                tool_name="edit_file",
                operation="modified",
                path="thistest.md",
                before=FileImage(exists=True, text="a\nb\nc\nd\ne"),
                after=FileImage(exists=True, text="a\nB\nC\nD\nE\nf"),
                status="changed",
                created_at=now,
                observed_at=now,
            )
            view = change_view(root, change, run_active=False)
            self.assertEqual((view.added_lines, view.removed_lines), (5, 4))
            self.assertIn("-b", view.diff or "")
            self.assertIn("+f", view.diff or "")


class ProjectFileChangesTests(unittest.TestCase):
    setUp = harness_tests.HarnessApiTests.setUp
    tearDown = harness_tests.HarnessApiTests.tearDown
    _start = harness_tests.HarnessApiTests._start
    _wait_for_pending_interrupt = harness_tests.HarnessApiTests._wait_for_pending_interrupt

    def _project_run(self, name, args, *, project=None, thread_id=None):
        project = project or self.root / 'project'
        project.mkdir(exist_ok=True)
        self.observed_call_id = new_id('filecall')
        self.scripted = ScriptedChatModel([AIMessage(content='', tool_calls=[{'name': name, 'args': args, 'id': self.observed_call_id}]), AIMessage(content='finished')])
        return self._start(project_path=str(project), thread_id=thread_id, presented_tools=[name],
            approval_mode='approve_for_me' if name in {'write_file', 'edit_file'} else 'ask'), project

    def _settled(self, run_id):
        final = wait_for_run(self.client, run_id)
        worker = self.app.state.harness._threads.get(run_id)
        if worker:
            worker.join(5)
            self.assertFalse(worker.is_alive())
        return final

    def _changes(self, run_id):
        response = self.client.get(f'/v1/agent-runs/{run_id}/file-changes')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _decide(self, run_id, decision, *, scope='once'):
        pending = self._wait_for_pending_interrupt(run_id)['pending_interrupt']
        response = self.client.post(f'/v1/agent-runs/{run_id}/interrupt-decision', json={
            'interrupt_id': pending['interrupt_id'], 'namespace': pending['namespace'],
            'decisions': [{'type': decision, 'scope': scope}]})
        self.assertEqual(response.status_code, 200, response.text)

    def test_real_edit_records_before_after_diff_and_blocks_conflicting_reversal(self):
        project = self.root / 'project'
        project.mkdir()
        path = project / 'note.txt'
        path.write_text('before\n', newline='')
        started, _ = self._project_run('edit_file', {'file_path': '/note.txt', 'old_string': 'before', 'new_string': 'after'}, project=project)
        final = self._settled(started['id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        view, = self._changes(started['id'])
        self.assertTrue(view['reversal_available'], view)
        self.assertEqual(view['change']['before']['text'], 'before\n')
        self.assertEqual(view['change']['after']['text'], 'after\n')
        self.assertEqual(view['change']['tool_call_id'], self.observed_call_id)
        self.assertIn('-before', view['diff'])
        self.assertIn('+after', view['diff'])
        path.write_text('later editor\n')
        url = f"/v1/agent-runs/{started['id']}/file-changes/{view['change']['id']}/reverse"
        conflict = self.client.post(url)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(path.read_text(), 'later editor\n')
        path.write_text('after\n', newline='')
        reversed_result = self.client.post(url)
        self.assertEqual(reversed_result.status_code, 200, reversed_result.text)
        self.assertEqual(path.read_text(), 'before\n')
        self.assertIsNotNone(reversed_result.json()['change']['reversed_at'])
        self.assertEqual(self.client.post(url).status_code, 409)

    def test_rename_denial_and_approved_exact_grant_produce_only_verified_effects(self):
        project = self.root / 'project'
        project.mkdir()
        source = project / 'original.txt'
        source.write_text('original')
        args = {'file_path': '/original.txt', 'destination': '/renamed.txt'}
        denied, _ = self._project_run('rename_file', args, project=project, thread_id='rename-grant')
        self._decide(denied['id'], 'reject')
        self._settled(denied['id'])
        self.assertTrue(source.exists())
        self.assertFalse((project / 'renamed.txt').exists())
        self.assertFalse(any(view['change']['status'] == 'changed' for view in self._changes(denied['id'])))
        approved, _ = self._project_run('rename_file', args, project=project, thread_id='rename-grant')
        self._decide(approved['id'], 'approve', scope='session')
        final = self._settled(approved['id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        changed = [view for view in self._changes(approved['id']) if view['change']['status'] == 'changed']
        self.assertEqual(len(changed), 1, changed)
        self.assertFalse(source.exists())
        self.assertEqual((project / 'renamed.txt').read_text(), 'original')
        url = f"/v1/agent-runs/{approved['id']}/file-changes/{changed[0]['change']['id']}/reverse"
        self.assertEqual(self.client.post(url).status_code, 200)
        again, _ = self._project_run('rename_file', args, project=project, thread_id='rename-grant')
        repeated = self._settled(again['id'])
        self.assertEqual(repeated['status'], 'completed')
        result = next(event for event in repeated['events'] if event['kind'] == 'tool_result')
        self.assertEqual(result['detail'].get('authorization_source'), 'saved_permission')
        grant, = self.app.state.preferences.grants()
        matched = result['detail'].get('authorization_grant')
        self.assertIsNotNone(matched, 'The actual matching saved permission must reach durable tool results')
        self.assertEqual({key: matched[key] for key in type(grant).model_fields}, grant.model_dump(mode='json'))
        self.assertEqual(matched['display_name'], 'Rename /original.txt → /renamed.txt · This session')
        self.assertEqual(repeated['tool_authorization_grants'][self.observed_call_id], matched)
        authorized_call_id = self.observed_call_id
        # A changed destination does not inherit the exact-action grant.
        changed_args, _ = self._project_run('rename_file', {'file_path': '/renamed.txt', 'destination': '/other.txt'}, project=project, thread_id='rename-grant')
        self._decide(changed_args['id'], 'reject')
        self._settled(changed_args['id'])
        self.assertFalse((project / 'other.txt').exists())
        self.app.state.preferences.revoke(grant.id)
        restored = self.app.state.harness.store.get_run(again['id'])
        self.assertEqual(restored.tool_authorization_grants[authorized_call_id].model_dump(mode='json'), matched)

    def test_delete_restores_captured_text_and_rejects_folders_or_escape(self):
        project = self.root / 'project'
        project.mkdir()
        path = project / 'removed.txt'
        path.write_text('retain the exact preimage')
        started, _ = self._project_run('delete_file', {'file_path': '/removed.txt'}, project=project)
        self._decide(started['id'], 'approve')
        final = self._settled(started['id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        self.assertFalse(path.exists())
        view = next(item for item in self._changes(started['id']) if item['change']['status'] == 'changed')
        self.assertEqual(view['change']['operation'], 'deleted')
        response = self.client.post(f"/v1/agent-runs/{started['id']}/file-changes/{view['change']['id']}/reverse")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(path.read_text(), 'retain the exact preimage')
        from workbench_backend.agents.tools import project_mutation_tools
        delete = next(tool for tool in project_mutation_tools(str(project)) if tool.name == 'delete_file')
        (project / 'folder').mkdir()
        for invalid in ('/folder', '../outside.txt', '/skills/instructions.md'):
            message = delete.invoke({'type': 'tool_call', 'name': 'delete_file', 'id': 'invalid', 'args': {'file_path': invalid}})
            self.assertEqual(message.status, 'error', message)
        self.assertTrue((project / 'folder').is_dir())

    def test_memory_proposal_binds_real_run_and_does_not_commit_without_scope_permission(self):
        self.scripted = ScriptedChatModel([AIMessage(content='', tool_calls=[{'name': 'propose_memory',
            'args': {'content': 'A proposed preference', 'scope': 'user', 'run_id': 'forged-run'}, 'id': 'proposal-call'}]), AIMessage(content='Proposed for review')])
        started = self._start(presented_tools=['propose_memory'])
        final = self._settled(started['id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        proposals = self.app.state.knowledge.list_proposals(run_id=started['id'])
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].status, 'pending')
        self.assertEqual(proposals[0].provenance.run_id, started['id'])
        self.assertIsNone(proposals[0].committed_version_id)

    def test_created_file_evidence_survives_reload_without_replay_content_copies(self):
        from workbench_backend.interaction.service import InteractionService
        started, project = self._project_run('write_file', {'file_path': '/created.txt', 'content': 'Captured file text'})
        self.assertEqual(self._settled(started['id'])['status'], 'completed')
        view, = self._changes(started['id'])
        self.assertEqual(view['change']['operation'], 'created')
        self.assertFalse(view['change']['before']['exists'])
        # ApplicationStore owns full evidence; replay owns only descriptors.
        restored = self.app.state.harness.store.get_run(started['id'])
        self.assertEqual(restored.file_changes[0].after.text, 'Captured file text')
        replay = InteractionService._stored_run(restored)
        self.assertIsNone(replay['file_changes'][0]['after']['text'])
        self.assertEqual(replay['file_changes'][0]['after']['sha256'], restored.file_changes[0].after.sha256)
        self.assertEqual(restored.file_changes[0].after.text, 'Captured file text')
        response = self.client.post(f"/v1/agent-runs/{started['id']}/file-changes/{view['change']['id']}/reverse")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse((project / 'created.txt').exists())

    def test_binary_delete_is_observed_without_fabricated_diff_or_reversal(self):
        project = self.root / 'project'
        project.mkdir()
        (project / 'binary.dat').write_bytes(b'\x00\xffbinary')
        started, _ = self._project_run('delete_file', {'file_path': '/binary.dat'}, project=project)
        self._decide(started['id'], 'approve')
        self.assertEqual(self._settled(started['id'])['status'], 'completed')
        view, = self._changes(started['id'])
        self.assertEqual(view['change']['status'], 'changed')
        self.assertIsNone(view['diff'])
        self.assertIn('binary', view['diff_unavailable_reason'])
        self.assertFalse(view['reversal_available'])
        response = self.client.post(f"/v1/agent-runs/{started['id']}/file-changes/{view['change']['id']}/reverse")
        self.assertEqual(response.status_code, 409)
        self.assertFalse((project / 'binary.dat').exists())

    def test_rename_with_unexpected_destination_content_is_unconfirmed(self):
        from types import SimpleNamespace
        from workbench_backend.agents.file_changes import FileChangeRecorder, change_view
        project = self.root / 'project'
        project.mkdir()
        source = project / 'original.txt'
        source.write_text('captured source')
        run = SimpleNamespace(id='observed-run', project_path=str(project), file_changes=[])
        recorder = FileChangeRecorder(run, lambda update: update())
        change = recorder.prepare('rename_file', {'file_path': '/original.txt', 'destination': '/renamed.txt'}, 'call')
        source.rename(project / 'renamed.txt')
        (project / 'renamed.txt').write_text('different concurrent content')
        recorder.finish(change)
        self.assertEqual(run.file_changes[0].status, 'unconfirmed')
        self.assertFalse(change_view(project, run.file_changes[0], run_active=False).reversal_available)

    def test_reversal_waits_for_other_work_in_same_project(self):
        started, project = self._project_run('write_file', {'file_path': '/owned.txt', 'content': 'recorded content'})
        self.assertEqual(self._settled(started['id'])['status'], 'completed')
        view, = self._changes(started['id'])
        waiting, _ = self._project_run('ask_user', {'prompt': 'Continue project work?'}, project=project)
        self._wait_for_pending_interrupt(waiting['id'])
        try:
            current, = self._changes(started['id'])
            self.assertFalse(current['reversal_available'])
            response = self.client.post(f"/v1/agent-runs/{started['id']}/file-changes/{view['change']['id']}/reverse")
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual((project / 'owned.txt').read_text(), 'recorded content')
        finally:
            self.app.state.harness.cancel(waiting['id'])
            self._settled(waiting['id'])
        self.assertTrue(self._changes(started['id'])[0]['reversal_available'])

    def test_failed_native_edit_and_concurrent_change_are_not_reversible(self):
        from types import SimpleNamespace
        from workbench_backend.agents.file_changes import FileChangeRecorder, change_view
        project = self.root / 'project'
        project.mkdir()
        path = project / 'note.txt'
        path.write_text('Original text')
        started, _ = self._project_run('edit_file', {'file_path': '/note.txt', 'old_string': 'missing text', 'new_string': 'replacement'}, project=project)
        self.assertEqual(self._settled(started['id'])['status'], 'completed')
        view, = self._changes(started['id'])
        self.assertEqual(view['change']['status'], 'failed')
        self.assertTrue(view['change']['error'])
        self.assertFalse(view['reversal_available'])
        run = SimpleNamespace(id='failed-run', project_path=str(project), file_changes=[])
        recorder = FileChangeRecorder(run, lambda update: update())
        change = recorder.prepare('edit_file', {'file_path': '/note.txt'}, 'failed-call')
        path.write_text('Concurrent external edit')
        recorder.finish(change, error=OSError('edit operation failed'))
        self.assertEqual(run.file_changes[0].status, 'unconfirmed')
        self.assertFalse(change_view(project, run.file_changes[0], run_active=False).reversal_available)
        self.assertEqual(path.read_text(), 'Concurrent external edit')
