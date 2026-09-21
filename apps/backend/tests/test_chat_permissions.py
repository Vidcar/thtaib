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
)
from workbench_backend.agents.harness import HarnessService, _resume_value
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.preferences import PreferenceStore, PresentationPreferences
from workbench_backend.state.store import ApplicationStore


class ChatPermissionTests(unittest.TestCase):
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

    def test_typed_question_and_cancellation_use_separate_resume_shape(self):
        pending = pending_interrupt_from_raw({"kind": "ask_user", "question": {
            "prompt": "Choose a format", "answer_type": "choice", "choices": ["Text", "Code"]}})
        self.assertEqual(pending.kind, "ask_user")
        self.assertEqual(pending.action_requests, [])
        self.assertEqual(_resume_value([{"type": "user_answer", "answer": "Code"}]), {"answer": "Code"})
        self.assertEqual(_resume_value(reject_decisions_for(pending)), {"cancelled": "true"})
