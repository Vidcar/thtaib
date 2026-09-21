from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import (
    AgentRun,
    AgentRunStatus,
    InterruptDecisionRequest,
    PendingInterrupt,
    PendingInterruptAction,
    UserAnswerRequest,
    UserQuestion,
)
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.chat.service import ChatService
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.interaction.service import InteractionService
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore


class _FakeHarness:
    def __init__(self, run: AgentRun) -> None:
        self.run = run
        self.resume_calls: list[tuple[str, Any, dict[str, Any]]] = []

    def get_run(self, run_id: str) -> AgentRun:
        if run_id != self.run.id:
            raise AssertionError(f'unexpected run id {run_id}')
        return self.run

    def resume_interrupt(self, run_id: str, request: Any, **kwargs: Any) -> AgentRun:
        if not kwargs.get('require_interrupt_identity'):
            raise AssertionError('SDK responses must require durable interrupt identity')
        pending = self.run.pending_interrupt
        if (
            pending is None
            or getattr(request, 'interrupt_id', None) != pending.interrupt_id
            or list(getattr(request, 'namespace', []) or []) != pending.namespace
        ):
            raise HarnessError(
                'This approval is stale or belongs to another run.',
                code='stale_interrupt',
                status_code=409,
            )
        self.resume_calls.append((run_id, request, kwargs))
        return self.run


class InteractionAuthorityBoundaryTests(unittest.TestCase):
    def _run(self, *, interrupt_id: str = 'durable-current', kind: str = 'ask_user') -> AgentRun:
        now = utc_now()
        pending = PendingInterrupt(
            interrupt_id=interrupt_id,
            namespace=[],
            kind='ask_user',
            question=UserQuestion(prompt='Current question?', answer_type='text'),
        )
        if kind == 'approval':
            pending = PendingInterrupt(
                interrupt_id=interrupt_id,
                namespace=[],
                kind='deepagents_interrupt_on',
                action_requests=[PendingInterruptAction(name='execute', args={'command': 'echo ok'})],
            )
        return AgentRun(
            id='run-authority',
            status=AgentRunStatus.running,
            deployment_id='dep-authority',
            task='ask safely',
            enabled_tools=['ask_user', 'execute'],
            presented_tools=['ask_user', 'execute'],
            created_at=now,
            updated_at=now,
            thread_id='graph-authority',
            pending_interrupt=pending,
        )

    def _service_for(self, run: AgentRun, *, projected_id: str) -> tuple[InteractionService, _FakeHarness, ApplicationStore, tempfile.TemporaryDirectory[str]]:
        snapshot = {
            '__interrupt__': [
                {
                    'id': projected_id,
                    'namespace': [],
                    'value': {'kind': run.pending_interrupt.kind if run.pending_interrupt else 'ask_user'},
                }
            ],
            'messages': [],
            'workbench': {
                'run': run.model_dump(mode='json'),
                'interrupt_run_id': run.id,
            },
        }
        temp_root = tempfile.TemporaryDirectory()
        store = ApplicationStore(WorkbenchPaths(Path(temp_root.name)))
        store.register_interaction(
            thread_id='thread-authority',
            surface='agent',
            graph_thread_id='graph-authority',
            conversation_id=None,
            snapshot=snapshot,
        )
        store.append_interaction('thread-authority', [], snapshot=snapshot, run_id=run.id)
        harness = _FakeHarness(run)
        service = InteractionService(store, lambda: harness, lambda: object())
        return service, harness, store, temp_root

    def test_sdk_answer_rejects_when_projection_id_differs_from_durable_pending_interrupt(self) -> None:
        run = self._run(interrupt_id='durable-new')
        service, harness, store, temp_root = self._service_for(run, projected_id='sdk-old')
        try:
            with self.assertRaisesRegex(Exception, 'stale|belongs to another run'):
                service.command(
                    'thread-authority',
                    {
                        'id': 'respond-old-projection',
                        'method': 'input.respond',
                        'params': {
                            'namespace': [],
                            'interrupt_id': 'sdk-old',
                            'response': {'answer': 'answer intended for the old projection'},
                        },
                    },
                )
            self.assertEqual([], harness.resume_calls)
        finally:
            store.close()
            temp_root.cleanup()

    def test_sdk_valid_answer_carries_identity_to_harness_boundary(self) -> None:
        run = self._run(interrupt_id='durable-current')
        service, harness, store, temp_root = self._service_for(run, projected_id='durable-current')
        try:
            result = service.command(
                'thread-authority',
                {
                    'id': 'respond-current',
                    'method': 'input.respond',
                    'params': {
                        'namespace': [],
                        'interrupt_id': 'durable-current',
                        'response': {'answer': 'current answer'},
                    },
                },
            )
            self.assertEqual(result['run_id'], run.id)
            self.assertEqual(len(harness.resume_calls), 1)
            _run_id, request, kwargs = harness.resume_calls[0]
            self.assertIsInstance(request, UserAnswerRequest)
            self.assertEqual(request.interrupt_id, 'durable-current')
            self.assertEqual(request.namespace, [])
            self.assertTrue(kwargs['require_interrupt_identity'])
        finally:
            store.close()
            temp_root.cleanup()

    def test_sdk_cancelled_question_is_typed_without_answer_text(self) -> None:
        run = self._run()
        service, harness, store, temp_root = self._service_for(run, projected_id='durable-current')
        try:
            service.command('thread-authority', {
                'id': 'cancel-question', 'method': 'input.respond',
                'params': {'namespace': [], 'interrupt_id': 'durable-current',
                           'response': {'cancelled': True}},
            })
            request = harness.resume_calls[0][1]
            self.assertIsInstance(request, UserAnswerRequest)
            self.assertTrue(request.cancelled)
            self.assertEqual(request.answer, '')
        finally:
            store.close()
            temp_root.cleanup()

    def test_sdk_approval_rejects_when_projection_id_differs_from_durable_pending_interrupt(self) -> None:
        run = self._run(interrupt_id='durable-approval', kind='approval')
        service, harness, store, temp_root = self._service_for(run, projected_id='sdk-approval-old')
        try:
            with self.assertRaisesRegex(Exception, 'stale|belongs to another run'):
                service.command(
                    'thread-authority',
                    {
                        'id': 'respond-old-approval',
                        'method': 'input.respond',
                        'params': {
                            'namespace': [],
                            'interrupt_id': 'sdk-approval-old',
                            'response': {'decisions': [{'type': 'approve', 'scope': 'once'}]},
                        },
                    },
                )
            self.assertEqual([], harness.resume_calls)
        finally:
            store.close()
            temp_root.cleanup()

    def test_harness_rejects_stale_typed_answer_identity_under_lock(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = WorkbenchPaths(Path(root))
            store = ApplicationStore(paths)
            try:
                harness = HarnessService(lambda: type('Manager', (), {'paths': paths})(), app_store=store)
                harness._startup_reconciled = True
                run = self._run(interrupt_id='durable-question')
                harness._runs[run.id] = run
                harness._cancels[run.id] = threading.Event()
                with self.assertRaises(HarnessError) as raised:
                    harness.resume_interrupt(
                        run.id,
                        UserAnswerRequest(answer='old answer', interrupt_id='sdk-question-old'),
                        require_interrupt_identity=True,
                    )
                self.assertEqual(raised.exception.code, 'stale_interrupt')
            finally:
                store.close()

    def test_harness_rejects_stale_approval_identity_under_lock(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = WorkbenchPaths(Path(root))
            store = ApplicationStore(paths)
            try:
                harness = HarnessService(lambda: type('Manager', (), {'paths': paths})(), app_store=store)
                harness._startup_reconciled = True
                run = self._run(interrupt_id='durable-approval', kind='approval')
                harness._runs[run.id] = run
                harness._cancels[run.id] = threading.Event()
                with self.assertRaises(HarnessError) as raised:
                    harness.resume_interrupt(
                        run.id,
                        InterruptDecisionRequest(
                            interrupt_id='sdk-approval-old',
                            decisions=[{'type': 'approve', 'scope': 'once'}],
                        ),
                        require_interrupt_identity=True,
                    )
                self.assertEqual(raised.exception.code, 'stale_interrupt')
            finally:
                store.close()

    def test_chat_resume_requires_durable_interrupt_identity(self) -> None:
        run = self._run(interrupt_id='durable-chat-approval', kind='approval')
        harness = _FakeHarness(run)
        with tempfile.TemporaryDirectory() as root:
            paths = WorkbenchPaths(Path(root))
            store = ApplicationStore(paths)
            try:
                store.put_conversation(
                    ChatConversation(
                        id='conversation-authority',
                        deployment_id='dep-authority',
                        thread_id='graph-authority',
                        current_run_id=run.id,
                        run_ids=[run.id],
                        created_at=utc_now(),
                        updated_at=utc_now(),
                    )
                )
                service = ChatService(
                    lambda: type('Manager', (), {'paths': paths})(),
                    lambda: harness,
                    lambda: object(),
                    app_store=store,
                )
                with self.assertRaisesRegex(Exception, 'stale|belongs to another run'):
                    service.resume_interrupt(
                        'conversation-authority',
                        InterruptDecisionRequest(
                            interrupt_id='stale-chat-approval',
                            decisions=[{'type': 'approve', 'scope': 'once'}],
                        ),
                    )
                self.assertEqual([], harness.resume_calls)
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
