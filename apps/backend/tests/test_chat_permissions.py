"""Durable scoped grants and typed input do not broaden execution authority."""
import tempfile
import unittest
import asyncio
import threading
from pathlib import Path

from workbench_backend.agents.host_shell import pending_interrupt_from_raw, reject_decisions_for
from workbench_backend.agents.schemas import (
    AgentRun,
    AgentRunStatus,
    InterruptDecisionRequest,
    PendingInterrupt,
    PendingInterruptAction,
    UserQuestion,
)
from workbench_backend.agents.harness import HarnessService, _resume_value
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.preferences import PreferenceStore, PresentationPreferences
from workbench_backend.state.store import ApplicationStore


class ChatPermissionTests(unittest.TestCase):
    def test_independent_preference_updates_preserve_other_fields_after_restart(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WorkbenchPaths(Path(root))
            store = ApplicationStore(paths)
            try:
                prefs = PreferenceStore(store)
                prefs.save_preferences(PresentationPreferences(
                    theme="light", attention_notifications=False, success_notifications=True))
                barrier = threading.Barrier(3)
                errors = []

                def update(patch):
                    try:
                        barrier.wait(timeout=5)
                        prefs.update_preferences(PresentationPreferences(**patch))
                    except Exception as error:
                        errors.append(error)

                workers = [threading.Thread(target=update, args=(patch,)) for patch in
                           ({"theme": "dark"}, {"detailed_streams": True})]
                for worker in workers:
                    worker.start()
                barrier.wait(timeout=5)
                for worker in workers:
                    worker.join(timeout=5)
                    self.assertFalse(worker.is_alive())
                self.assertEqual(errors, [])
            finally:
                store.close()
            store = ApplicationStore(paths)
            try:
                self.assertEqual(PreferenceStore(store).preferences(), PresentationPreferences(
                    theme="dark", detailed_streams=True,
                    attention_notifications=False, success_notifications=True))
            finally:
                store.close()

    def test_mixed_ordered_question_and_approvals_survive_restart_without_extra_grants(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WorkbenchPaths(Path(root))
            store = ApplicationStore(paths)
            stop_thread = threading.Event()
            try:
                actions = [
                    PendingInterruptAction(name="ask_user", args={"prompt": "Choose a format", "answer_type": "choice", "choices": ["Text", "Code"]},
                                           question=UserQuestion(prompt="Choose a format", answer_type="choice", choices=["Text", "Code"]),
                                           allowed_decisions=["respond", "reject"]),
                    PendingInterruptAction(name="execute", args={"command": "echo once > once.txt"}),
                    PendingInterruptAction(name="execute", args={"command": "echo session > session.txt"}),
                    PendingInterruptAction(name="execute", args={"command": "echo always > always.txt"}),
                    PendingInterruptAction(name="execute", args={"command": "echo reject > reject.txt"}),
                ]
                run = AgentRun(
                    id="run_mixed_decisions",
                    status=AgentRunStatus.running,
                    deployment_id="model",
                    task="work",
                    thread_id="session1",
                    project_path=root,
                    enabled_tools=["ask_user", "execute"],
                    presented_tools=["ask_user", "execute"],
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    pending_interrupt=PendingInterrupt(
                        interrupt_id="interrupt-mixed-decisions",
                        namespace=["__interrupt__", "mixed"],
                        action_requests=actions,
                    ),
                )

                store.put_run(run)
                store.close()
                store = ApplicationStore(paths)
                restored = store.get_run(run.id)
                self.assertIsNotNone(restored)
                assert restored is not None
                self.assertEqual([action.name for action in restored.pending_interrupt.action_requests],
                                 ["ask_user", "execute", "execute", "execute", "execute"])
                harness = HarnessService(lambda: type("Manager", (), {"paths": paths})(), app_store=store)
                harness._startup_reconciled = True
                run = restored

                worker = threading.Thread(target=stop_thread.wait)
                worker.start()
                self.addCleanup(stop_thread.set)
                self.addCleanup(worker.join, 1)
                harness._runs[run.id] = run
                harness._threads[run.id] = worker
                harness._cancels[run.id] = threading.Event()
                request = InterruptDecisionRequest(
                    interrupt_id="interrupt-mixed-decisions",
                    namespace=["__interrupt__", "mixed"],
                    decisions=[
                        {"type": "respond", "message": "Code"},
                        {"type": "approve", "scope": "once"},
                        {"type": "approve", "scope": "session"},
                        {"type": "approve", "scope": "always"},
                        {"type": "reject"},
                    ],
                )

                exposed = harness.resume_interrupt(run.id, request, require_interrupt_identity=True)

                self.assertEqual(exposed.id, run.id)
                self.assertEqual(
                    [payload["type"] for payload in harness._pending_decisions[run.id]],
                    ["respond", "approve", "approve", "approve", "reject"],
                )
                prefs = PreferenceStore(store)
                grants = prefs.grants()
                self.assertEqual(len(grants), 2)
                self.assertFalse(prefs.matches(run, "execute", actions[1].args))
                self.assertTrue(prefs.matches(run, "execute", actions[2].args))
                self.assertFalse(
                    prefs.matches(run.model_copy(update={"thread_id": "other"}), "execute", actions[2].args)
                )
                self.assertTrue(
                    prefs.matches(run.model_copy(update={"thread_id": "other"}), "execute", actions[3].args)
                )
                self.assertFalse(prefs.matches(run, "execute", actions[4].args))
                self.assertEqual(
                    {(grant.scope, grant.arguments["command"]) for grant in grants},
                    {
                        ("session", "echo session > session.txt"),
                        ("always", "echo always > always.txt"),
                    },
                )
            finally:
                stop_thread.set()
                store.close()

    def test_ordered_decision_mismatch_cannot_approve_wrong_pending_action(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WorkbenchPaths(Path(root))
            store = ApplicationStore(paths)
            try:
                harness = HarnessService(lambda: type("Manager", (), {"paths": paths})(), app_store=store)
                harness._startup_reconciled = True
                run = AgentRun(
                    id="run_order_mismatch",
                    status=AgentRunStatus.running,
                    deployment_id="model",
                    task="work",
                    thread_id="session1",
                    project_path=root,
                    enabled_tools=["execute"],
                    presented_tools=["execute"],
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    pending_interrupt=PendingInterrupt(
                        interrupt_id="interrupt-order-mismatch",
                        namespace=["__interrupt__", "ordered"],
                        action_requests=[
                            PendingInterruptAction(
                                name="execute",
                                args={"command": "echo first > first.txt"},
                                allowed_decisions=["approve"],
                            ),
                            PendingInterruptAction(
                                name="execute",
                                args={"command": "echo second > second.txt"},
                                allowed_decisions=["reject"],
                            ),
                        ],
                    ),
                )
                harness._runs[run.id] = run
                harness._cancels[run.id] = threading.Event()
                request = InterruptDecisionRequest(
                    interrupt_id="interrupt-order-mismatch",
                    namespace=["__interrupt__", "ordered"],
                    decisions=[
                        {"type": "reject"},
                        {"type": "approve", "scope": "always"},
                    ],
                )

                with self.assertRaises(HarnessError) as raised:
                    harness.resume_interrupt(run.id, request, require_interrupt_identity=True)

                self.assertEqual(raised.exception.code, "interrupt_decision_not_allowed")
                self.assertIsNone(harness._pending_decisions.get(run.id))
                prefs = PreferenceStore(store)
                self.assertEqual(prefs.grants(), [])
                self.assertFalse(prefs.matches(run, "execute", {"command": "echo first > first.txt"}))
                self.assertFalse(prefs.matches(run, "execute", {"command": "echo second > second.txt"}))
            finally:
                store.close()

    def test_cancel_prevents_all_model_and_tool_dispatch_hooks(self):
        from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
        from workbench_backend.errors import HarnessError
        run = AgentRun(id="cancel", deployment_id="model", task="work", status="cancel_requested",
            enabled_tools=["echo"], presented_tools=["echo"], created_at=utc_now(), updated_at=utc_now())
        middleware = WorkbenchHarnessMiddleware(run)
        calls = []
        def handler(request):
            calls.append(request)
        async def ahandler(request):
            calls.append(request)
        for hook in (middleware.wrap_model_call, middleware.wrap_tool_call):
            with self.assertRaises(HarnessError):
                hook(None, handler)
        for hook in (middleware.awrap_model_call, middleware.awrap_tool_call):
            with self.assertRaises(HarnessError):
                asyncio.run(hook(None, ahandler))
        self.assertEqual(calls, [])

    def test_exact_grants_survive_restart_and_revocation(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WorkbenchPaths(Path(root))
            store = ApplicationStore(paths)
            run = AgentRun(id="run1", deployment_id="model", task="work", thread_id="session1",
                project_path=root, enabled_tools=["execute"], presented_tools=["execute"],
                created_at=utc_now(), updated_at=utc_now())
            action = PendingInterruptAction(name="execute", args={"command": "echo approved > result.txt"})
            prefs = PreferenceStore(store)
            grant = prefs.allow(run, action, "session")
            prefs.save_preferences(PresentationPreferences(theme="light"))
            store.close()
            store = ApplicationStore(paths)
            try:
                prefs = PreferenceStore(store)
                self.assertEqual(prefs.preferences().theme, "light")
                self.assertTrue(prefs.matches(run, "execute", action.args))
                self.assertFalse(prefs.matches(run.model_copy(update={"thread_id": "other"}), "execute", action.args))
                self.assertFalse(prefs.matches(run, "execute", {"command": action.args["command"] + " & del other.txt"}))
                self.assertFalse(prefs.matches(run.model_copy(update={"presented_tools": []}), "execute", action.args))
                self.assertFalse(prefs.matches(run.model_copy(update={"project_path": str(Path(root) / "other")}), "execute", action.args))
                prefs.revoke(grant.id)
                self.assertFalse(prefs.matches(run, "execute", action.args))
                prefs.allow(run, action, "always")
                self.assertTrue(prefs.matches(run.model_copy(update={"thread_id": "other"}), "execute", action.args))
            finally:
                store.close()

    def test_resume_rechecks_tool_authority_after_disable(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WorkbenchPaths(Path(root))
            store = ApplicationStore(paths)
            try:
                harness = HarnessService(lambda: type("Manager", (), {"paths": paths})(), app_store=store)
                harness._startup_reconciled = True
                run = AgentRun(
                    id="run_disabled_tool",
                    status=AgentRunStatus.running,
                    deployment_id="model",
                    task="work",
                    thread_id="session1",
                    project_path=root,
                    enabled_tools=["execute"],
                    presented_tools=[],
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    pending_interrupt=PendingInterrupt(
                        interrupt_id="interrupt-disabled-tool",
                        action_requests=[
                            PendingInterruptAction(
                                name="execute",
                                args={"command": "echo approved > result.txt"},
                            )
                        ],
                    ),
                )
                harness._runs[run.id] = run
                harness._cancels[run.id] = threading.Event()
                request = InterruptDecisionRequest(
                    interrupt_id="interrupt-disabled-tool",
                    decisions=[{"type": "approve", "scope": "always"}],
                )
                with self.assertRaises(HarnessError) as raised:
                    harness.resume_interrupt(run.id, request, require_interrupt_identity=True)
                self.assertEqual(raised.exception.code, "interrupt_tool_unavailable")
                self.assertFalse(PreferenceStore(store).matches(run, "execute", {"command": "echo approved > result.txt"}))
            finally:
                store.close()

    def test_typed_question_and_cancellation_use_native_ordered_decisions(self):
        pending = pending_interrupt_from_raw({
            "action_requests": [{"name": "ask_user", "args": {
                "prompt": "Choose a format", "answer_type": "choice", "choices": ["Text", "Code"]}}],
            "review_configs": [{"action_name": "ask_user", "allowed_decisions": ["respond", "reject"]}],
        })
        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertEqual(pending.kind, "deepagents_interrupt_on")
        self.assertEqual(pending.action_requests[0].question.choices, ["Text", "Code"])
        self.assertEqual(_resume_value([{"type": "respond", "message": "Code"}]),
                         {"decisions": [{"type": "respond", "message": "Code"}]})
        self.assertEqual(_resume_value(reject_decisions_for(pending)),
                         {"decisions": reject_decisions_for(pending)})
