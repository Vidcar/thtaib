"""Framework offloads remain readable without granting project file access."""
from __future__ import annotations

import unittest

from langchain_core.messages import AIMessage, ToolMessage
from tests import test_harness as harness_tests
from tests.scripted_model import ScriptedChatModel
from tests.support import wait_for_run
from workbench_backend.state.checkpointer import conversation_state


class FrameworkArtifactReadTests(unittest.TestCase):
    setUp = harness_tests.HarnessApiTests.setUp
    tearDown = harness_tests.HarnessApiTests.tearDown
    _start = harness_tests.HarnessApiTests._start

    def test_real_upstream_offload_can_be_read_without_a_project(self):
        content = '\n'.join(f'{index:04d}: retained documentation detail ' + 'x' * 60 for index in range(3000)) + '\nEND-OF-FULL-RESULT-71'
        self.scripted = ScriptedChatModel([
            AIMessage(content='', tool_calls=[{'name': 'echo', 'args': {'text': content}, 'id': 'oversized-result'}]),
            AIMessage(content='', tool_calls=[{'name': 'read_file', 'args': {'file_path': '/large_tool_results/oversized-result', 'offset': 2995, 'limit': 10}, 'id': 'read-tail'}]),
            AIMessage(content='Read the full result tail'),
        ])
        started = self._start(presented_tools=['echo'])
        final = wait_for_run(self.client, started['id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        self.assertIn('read_file', final['model_requests'][1]['presented_tools'])
        messages = conversation_state(self.manager.paths.checkpoints_db, final['thread_id'])['messages']
        initial = next(item for item in messages if isinstance(item, ToolMessage) and item.tool_call_id == 'oversized-result')
        self.assertIn('/large_tool_results/oversized-result', initial.content)
        result = next(item for item in messages if isinstance(item, ToolMessage) and item.tool_call_id == 'read-tail')
        self.assertEqual(result.status, 'success', result.content)
        self.assertIn('END-OF-FULL-RESULT-71', result.content)

    def test_implicit_reader_and_unselected_tools_cannot_access_project(self):
        project = self.root / 'project'
        project.mkdir()
        (project / 'private.txt').write_text('PRIVATE-PROJECT-CONTENT')
        self.scripted = ScriptedChatModel([
            AIMessage(content='', tool_calls=[{'name': 'read_file', 'args': {'file_path': '/private.txt'}, 'id': 'blocked-read'}]),
            AIMessage(content='', tool_calls=[{'name': 'read_file', 'args': {'file_path': '/large_tool_results/../private.txt'}, 'id': 'blocked-escape'}]),
            AIMessage(content='', tool_calls=[{'name': 'write_file', 'args': {'file_path': '/unselected.txt', 'content': 'must not write'}, 'id': 'blocked-write'}]),
            AIMessage(content='Stopped at the scope boundary'),
        ])
        started = self._start(presented_tools=['echo'], project_path=str(project))
        final = wait_for_run(self.client, started['id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        messages = conversation_state(self.manager.paths.checkpoints_db, final['thread_id'])['messages']
        for call_id in ('blocked-read', 'blocked-escape', 'blocked-write'):
            result = next(item for item in messages if isinstance(item, ToolMessage) and item.tool_call_id == call_id)
            self.assertEqual(result.status, 'error', result.content)
            self.assertNotIn('PRIVATE-PROJECT-CONTENT', result.content)
        self.assertFalse((project / 'unselected.txt').exists())
