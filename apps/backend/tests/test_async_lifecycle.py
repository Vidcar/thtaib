"""Real common graph execution owns one async loop through waits and cleanup."""
from __future__ import annotations

import asyncio
import sqlite3
import threading
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse

from tests.scripted_model import ScriptedChatModel
from tests.support import wait_for_run
from tests import test_harness as harness_tests
from tests.scripted_model import RECEIVED_PROMPTS, reset_received_prompts
from workbench_backend.agents.schemas import UserAnswerRequest
from workbench_backend.inference.adapter import _AsyncObservation
from workbench_backend.state.checkpointer import (
    close_sqlite_checkpointer, open_sqlite_checkpointer, run_checkpoint_task,
)


class AsyncLifecycleTests(unittest.TestCase):
    setUp = harness_tests.HarnessApiTests.setUp
    tearDown = harness_tests.HarnessApiTests.tearDown
    _start = harness_tests.HarnessApiTests._start
    _wait_for_pending_interrupt = harness_tests.HarnessApiTests._wait_for_pending_interrupt

    def test_failed_saver_initialization_does_not_leave_owner_loop_running(self):
        from workbench_backend.state.checkpointer import _CheckpointOwner
        holder = object.__new__(_CheckpointOwner)
        async def failed_open(_self, _path):
            raise OSError('synthetic checkpoint open failure')
        try:
            with patch.object(_CheckpointOwner, '_open', failed_open):
                with self.assertRaisesRegex(OSError, 'checkpoint open failure'):
                    holder.__init__(self.manager.paths.checkpoints_db)
            self.assertFalse(holder.thread.is_alive(), 'failed admission leaked its async owner thread')
        finally:
            if holder.thread.is_alive():
                holder.loop.call_soon_threadsafe(holder.loop.stop)
                holder.thread.join(5)

    def test_existing_synchronous_checkpoint_continues_on_common_async_driver(self):
        path = self.manager.paths.checkpoints_db
        close_sqlite_checkpointer(path)
        with sqlite3.connect(path, check_same_thread=False) as conn:
            saver = SqliteSaver(conn)
            agent = create_deep_agent(model=ScriptedChatModel([AIMessage(content='Remembered COPPER-MOON-71')]), checkpointer=saver)
            agent.invoke({'messages': [{'role': 'user', 'content': 'Remember COPPER-MOON-71'}]},
                {'configurable': {'thread_id': 'before-async-migration'}})
        conn.close()
        reset_received_prompts()
        self.scripted = ScriptedChatModel([AIMessage(content='COPPER-MOON-71')])
        started = self._start(thread_id='before-async-migration', presented_tools=[], task='Repeat the saved phrase')
        final = wait_for_run(self.client, started['id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        self.assertTrue(any('Remembered COPPER-MOON-71' in prompt for prompt in RECEIVED_PROMPTS))
        self.assertGreater(len(final['checkpoint_ids']), 2)

    def test_async_only_model_and_session_context_survive_native_input_wait(self):
        entered, exited = threading.Event(), threading.Event()
        loops = []

        class AsyncOnlyModel(ScriptedChatModel):
            def _generate(self, *args, **kwargs):
                raise AssertionError('A synchronous model path was invoked')

            async def _agenerate(self, *args, **kwargs):
                loops.append(asyncio.get_running_loop())
                return ChatResult(generations=[ChatGeneration(message=self._next_message())])

        self.scripted = AsyncOnlyModel([
            AIMessage(content='', tool_calls=[{'name': 'ask_user', 'args': {'prompt': 'Choose a value', 'answer_type': 'text'}, 'id': 'async-question'}]),
            AIMessage(content='continued on the same session'),
        ])
        harness = self.app.state.harness
        original = harness._compiled_agent_context

        @asynccontextmanager
        async def session(*args):
            loops.append(asyncio.get_running_loop())
            entered.set()
            try:
                async with original(*args) as agent:
                    yield agent
            finally:
                loops.append(asyncio.get_running_loop())
                exited.set()

        with patch.object(harness, '_compiled_agent_context', session):
            run = self._start(presented_tools=['ask_user'])
            pending = self._wait_for_pending_interrupt(run['id'])['pending_interrupt']
            self.assertTrue(entered.is_set())
            self.assertFalse(exited.is_set())
            harness.resume_interrupt(run['id'], UserAnswerRequest(answer='approved value',
                interrupt_id=pending['interrupt_id'], namespace=pending['namespace']), require_interrupt_identity=True)
            final = wait_for_run(self.client, run['id'])
            self.assertEqual(final['status'], 'completed', final.get('error'))
            self.assertTrue(exited.wait(5))
        saver = open_sqlite_checkpointer(self.manager.paths.checkpoints_db)
        self.assertIsInstance(saver, AsyncSqliteSaver)
        self.assertTrue(loops and all(loop is saver.loop for loop in loops))
        harness.close()
        close_sqlite_checkpointer(self.manager.paths.checkpoints_db)
        self.assertTrue(saver.loop.is_closed())
        # Windows ownership proof: no saver connection/thread still locks the file.
        path = self.manager.paths.checkpoints_db
        moved = path.with_suffix('.moved')
        path.rename(moved)
        moved.rename(path)

    def test_cancel_aborts_inflight_async_model_before_terminal_publication(self):
        entered, settled = threading.Event(), threading.Event()

        class WaitingAsyncModel(ScriptedChatModel):
            def _generate(self, *args, **kwargs):
                raise AssertionError('A synchronous model path was invoked')

            async def _agenerate(self, *args, **kwargs):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    settled.set()

        self.scripted = WaitingAsyncModel([])
        started = self._start(presented_tools=[])
        self.assertTrue(entered.wait(5))
        self.app.state.harness.cancel(started['id'])
        final = wait_for_run(self.client, started['id'])
        self.assertEqual(final['status'], 'cancelled', final.get('error'))
        self.assertTrue(settled.is_set())
        self.assertFalse(final['tool_invocations'])
        self.assertIsNone(final['pending_interrupt'])

    def test_slow_measurement_publication_does_not_block_saver_owner(self):
        entered, release = threading.Event(), threading.Event()
        observed = []
        def publish(sample):
            entered.set()
            self.assertTrue(release.wait(5))
            observed.append(sample['n'])
        async def check():
            observer = _AsyncObservation(publish)
            observer({'n': 1})
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            # This query must finish while publication is blocked on another owner.
            saver = open_sqlite_checkpointer(self.manager.paths.checkpoints_db)
            self.assertIsNone(await asyncio.wait_for(saver.aget_tuple({'configurable': {'thread_id': 'empty'}}), 2))
            observer({'n': 2})
            release.set()
            await observer.flush()
        try:
            run_checkpoint_task(self.manager.paths.checkpoints_db, check())
        finally:
            release.set()
        self.assertEqual(observed, [1, 2])

    def test_cancel_does_not_release_project_while_executor_backed_local_tool_is_active(self):
        entered, release, settled = threading.Event(), threading.Event(), threading.Event()
        project = self.root / 'local-tool'
        project.mkdir()
        marker = project / 'finished.txt'
        self.scripted = ScriptedChatModel([
            AIMessage(content='', tool_calls=[{'name': 'execute', 'args': {'command': 'echo owned'}, 'id': 'local-owned'}]),
            AIMessage(content='done'),
        ])
        def execute(*args, **kwargs):
            entered.set()
            try:
                if not release.wait(5):
                    raise TimeoutError('test did not release local tool')
                marker.write_text('one completed effect')
                return ExecuteResponse(output='done', exit_code=0, truncated=False)
            finally:
                settled.set()
        with patch.object(LocalShellBackend, 'execute', execute):
            started = self._start(project_path=str(project), presented_tools=['execute'])
            try:
                self.assertTrue(entered.wait(5))
                self.app.state.harness.cancel(started['id'])
                # A saver-loop round trip proves cancellation was processed.
                async def turn():
                    await asyncio.sleep(0)
                run_checkpoint_task(self.manager.paths.checkpoints_db, turn())
                self.assertEqual(self.app.state.harness.get_run(started['id']).status, 'cancel_requested')
                self.assertFalse(settled.is_set())
                self.assertFalse(marker.exists())
            finally:
                release.set()
            final = wait_for_run(self.client, started['id'])
            self.assertEqual(final['status'], 'cancelled', final.get('error'))
            self.assertTrue(settled.is_set())
            self.assertEqual(marker.read_text(), 'one completed effect')
