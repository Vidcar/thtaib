"""Owned job callbacks and UI starts cannot outlive their recorded chat/helper."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from langgraph.checkpoint.base import empty_checkpoint

from tests import test_asset_lifecycle as asset_fixture
from tests.test_permission_boundary import _run
from workbench_backend.agents.execution_policy import ExecutionControl
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.helper_execution import _finalize_child_activity
from workbench_backend.agents.managed_commands import ManagedCommandService
from workbench_backend.agents.schemas import AgentRunStatus, ChildRunActivity, InterruptDecisionRequest, PendingInterrupt, PendingInterruptAction, ToolOutcome
from workbench_backend.assets.lifecycle_routes import delete_conversation
from workbench_backend.errors import HarnessError, ManagerError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.lifecycle import LifecycleCoordinator
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.preview.routes import StaticPreviewRequest, start_static_preview
from workbench_backend.state.checkpointer import close_sqlite_checkpointer, open_sqlite_checkpointer
from workbench_backend.state.store import ApplicationStore


class _CheckedLock:
    """A bounded real RLock: regressions fail without leaving blocked workers."""
    def __init__(self, inner, label, first_lock, attempted, owner_entered, publishing, callback_entered=None):
        self.inner, self.label = inner, label
        self.first_lock, self.attempted = first_lock, attempted
        self.owner_entered, self.publishing = owner_entered, publishing
        self.callback_entered = callback_entered

    def __enter__(self):
        helper = threading.current_thread().name == "helper-finalize"
        if helper and not self.first_lock:
            self.first_lock.append(self.label)
            self.attempted.set()
        if not self.inner.acquire(timeout=2):
            raise AssertionError("Lock inversion blocked " + self.label)
        if self.callback_entered is not None and threading.current_thread().name == "job-callback":
            self.callback_entered.set()
            if not self.attempted.wait(2) or self.first_lock[0] == "owner" and not self.owner_entered.wait(2):
                self.inner.release()
                raise AssertionError("Helper finalization did not reach its first lock")
            self.publishing.set()
        if helper and self.label == "owner":
            self.owner_entered.set()
            if self.first_lock[0] == "owner" and not self.publishing.wait(2):
                self.inner.release()
                raise AssertionError("Callback never reached publication")
        return self

    def __exit__(self, *_):
        self.inner.release()


class HelperJobPublicationTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        project = Path(temp.name) / "project"
        project.mkdir()
        paths = WorkbenchPaths(Path(temp.name) / "data").ensure()
        store = ApplicationStore(paths)
        self.addCleanup(store.close)
        harness = HarnessService(lambda: SimpleNamespace(paths=paths), app_store=store)
        commands = ManagedCommandService(paths, app_store=store)
        harness.managed_commands = commands
        self.addCleanup(commands.shutdown)
        parent = _run(id="parent", thread_id="thread", project_path=str(project))
        child = parent.model_copy(deep=True, update={"id": "child", "parent_run_id": parent.id})
        activity = ChildRunActivity(run_id=child.id, agent_id="helper", version_id="version", name="Helper")
        parent.child_runs = [activity]
        harness._runs[parent.id] = parent
        harness._runs[child.id] = child
        return project, store, harness, commands, parent, child, activity

    def test_helper_settlement_and_native_job_callback_publish_without_deadlock_or_lost_effects(self):
        project, store, harness, commands, parent, child, activity = self.fixture()
        child.status, activity.status = AgentRunStatus.failed, "failed"
        child.tool_outcomes["previous"] = ToolOutcome(call_id="previous", name="execute", outcome="running", updated_at=utc_now())
        control = harness._control_for_run(parent)
        attempted, owner_entered, publishing, callback_entered = [threading.Event() for _ in range(4)]
        first_lock, snapshots, errors = [], [], []
        harness._lock = _CheckedLock(harness._lock, "owner", first_lock, attempted, owner_entered, publishing)
        control._lock = _CheckedLock(control._lock, "control", first_lock, attempted, owner_entered, publishing, callback_entered)
        original_publish = control.publish
        def publish():
            original_publish()
            snapshots.append(store.get_execution_run(parent.id))
        control.publish = publish
        script = project / "wait.py"
        script.write_text("import threading\nthreading.Event().wait(30)\n", encoding="utf-8")
        sibling = parent.model_copy(deep=True, update={"id": "sibling", "parent_run_id": parent.id, "child_runs": [], "tool_outcomes": {}})
        created = commands.start(sibling, [sys._base_executable, str(script)], 30,
            record_outcome=lambda outcome: harness._record_managed_command_outcome(control, sibling, outcome))
        def run(operation):
            try:
                operation()
            except BaseException as error:
                errors.append(error)
        watcher = threading.Thread(name="job-callback", target=run,
            args=(lambda: commands._finish(commands._commands[created["command_id"]], "timed_out", 124),))
        helper = threading.Thread(name="helper-finalize", target=run,
            args=(lambda: _finalize_child_activity(harness, parent, child, activity, "task-call", child.id, control),))
        watcher.start()
        try:
            self.assertTrue(callback_entered.wait(3))
            helper.start()
        finally:
            watcher.join(5)
            if helper.ident is not None:
                helper.join(5)
        self.assertFalse(watcher.is_alive())
        self.assertFalse(helper.is_alive())
        self.assertEqual(errors, [])
        saved_parent, saved_child = store.get_execution_run(parent.id), store.get_execution_run(child.id)
        managed_id = "managed-command:" + created["command_id"]
        self.assertEqual(saved_parent.tool_outcomes[child.id + ":previous"], saved_child.tool_outcomes["previous"])
        self.assertEqual(saved_child.tool_outcomes["previous"].outcome, "uncertain")
        self.assertEqual(saved_parent.tool_outcomes[sibling.id + ":" + managed_id], store.get_execution_run(sibling.id).tool_outcomes[managed_id])
        self.assertEqual(saved_parent.tool_outcomes[sibling.id + ":" + managed_id].outcome, "uncertain")
        self.assertEqual(saved_parent.tool_outcomes["task-call"].outcome, "failed")
        self.assertTrue(snapshots)
        self.assertTrue(all(sibling.id + ":" + managed_id in snapshot.tool_outcomes for snapshot in snapshots))
        with self.assertRaises(HarnessError):
            control.require_dispatch(parent)

    def test_late_helper_job_timeout_persists_source_outcome_and_truthful_terminal_activity(self):
        project, store, harness, commands, parent, child, activity = self.fixture()
        control = harness._control_for_run(parent)
        script = project / "partial.py"
        script.write_text("from pathlib import Path\nimport threading\nPath('partial.txt').write_text('partial')\nthreading.Event().wait(30)\n", encoding="utf-8")
        created = commands.start(child, [sys._base_executable, str(script)], 1,
            record_outcome=lambda outcome: harness._record_managed_command_outcome(control, child, outcome))
        child.status, child.finished_at, activity.status = AgentRunStatus.completed, utc_now(), "completed"
        # Model completion precedes its cleanup boundary. A timeout can arrive
        # in this interval and must update the already-published source record.
        harness._persist(child)
        harness._publish_control_update(parent)
        self.assertEqual(store.get_execution_run(child.id).status, AgentRunStatus.completed)
        self.assertTrue(commands._commands[created["command_id"]].settled.wait(5))
        saved_child, saved_parent = store.get_execution_run(child.id), store.get_execution_run(parent.id)
        self.assertEqual(saved_child.status, AgentRunStatus.failed)
        self.assertEqual(saved_child.failure.category, "uncertain_effects")
        managed_id = "managed-command:" + created["command_id"]
        self.assertEqual(saved_child.tool_outcomes[managed_id].evidence["exit_code"], 124)
        self.assertEqual(saved_parent.tool_outcomes[child.id + ":" + managed_id], saved_child.tool_outcomes[managed_id])
        self.assertEqual(saved_parent.child_runs[0].status, "failed")
        harness._finish(parent, AgentRunStatus.completed, "completed")
        self.assertEqual(store.get_execution_run(parent.id).status, AgentRunStatus.failed)
        restarted = HarnessService(lambda: SimpleNamespace(paths=harness.manager.paths), app_store=store)
        with self.assertRaises(HarnessError):
            restarted.require_thread_effects_confirmed(parent.thread_id)
        self.assertTrue((project / "partial.txt").is_file())

    def test_helper_completion_stops_its_owned_job_before_terminal_settlement(self):
        project, store, harness, commands, parent, child, activity = self.fixture()
        control = harness._control_for_run(parent)
        script = project / "wait.py"
        script.write_text("import threading\nthreading.Event().wait(30)\n", encoding="utf-8")
        created = commands.start(child, [sys._base_executable, str(script)], 30,
            record_outcome=lambda outcome: harness._record_managed_command_outcome(control, child, outcome))
        managed_id = "managed-command:" + created["command_id"]
        self.assertEqual(store.get_execution_run(child.id).tool_outcomes[managed_id].outcome, "running")
        child.status, child.finished_at, activity.status = AgentRunStatus.completed, utc_now(), "completed"
        _finalize_child_activity(harness, parent, child, activity, "task-call", child.id, control)
        command = commands._commands[created["command_id"]]
        self.assertIsNotNone(command.process.poll())
        self.assertTrue(command.settled.is_set())
        saved = store.get_execution_run(child.id)
        self.assertEqual(saved.status, AgentRunStatus.completed)
        self.assertIsNone(saved.failure)
        self.assertEqual(saved.tool_outcomes[managed_id].outcome, "succeeded")
        control.require_dispatch(parent)

    def test_terminal_batch_failure_reconciles_durable_running_job_after_restart(self):
        project, store, harness, commands, parent, child, _ = self.fixture()
        control = harness._control_for_run(parent)
        script = project / "wait.py"
        script.write_text("import threading\nthreading.Event().wait(30)\n", encoding="utf-8")
        created = commands.start(child, [sys._base_executable, str(script)], 30,
            record_outcome=lambda outcome: harness._record_managed_command_outcome(control, child, outcome))
        command = commands._commands[created["command_id"]]
        managed_id = "managed-command:" + command.id
        self.assertEqual(store.get_execution_run(parent.id).tool_outcomes[child.id + ":" + managed_id].outcome, "running")
        write = store._write_run_record_locked
        def interrupted(run, payload):
            write(run, payload)
            if run.id == parent.id:
                raise OSError("terminal root write failed")
        with patch.object(store, "_write_run_record_locked", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "terminal root"):
                commands._finish(command, "timed_out", 124)
        effect = commands.effects.get_effect(command.effect_id)
        self.assertEqual(effect.evidence["state"], "timed_out")
        self.assertTrue(effect.evidence["partial_effects_unconfirmed"])
        self.assertEqual(store.get_execution_run(parent.id).tool_outcomes[child.id + ":" + managed_id].outcome, "running")
        restarted = HarnessService(lambda: SimpleNamespace(paths=harness.manager.paths), app_store=store)
        with self.assertRaises(HarnessError) as blocked:
            restarted.require_thread_effects_confirmed(parent.thread_id)
        self.assertEqual(blocked.exception.code, "effects_unconfirmed")
        reconciled = store.get_execution_run(parent.id)
        self.assertEqual(reconciled.tool_outcomes[child.id + ":" + managed_id].outcome, "uncertain")

    def test_restart_does_not_resume_saved_approval_past_a_lost_running_job(self):
        project, store, harness, commands, parent, child, _ = self.fixture()
        control = harness._control_for_run(parent)
        script = project / "wait.py"
        script.write_text("import threading\nthreading.Event().wait(30)\n", encoding="utf-8")
        created = commands.start(child, [sys._base_executable, str(script)], 30,
            record_outcome=lambda outcome: harness._record_managed_command_outcome(control, child, outcome))
        checkpoint_path = harness.manager.paths.checkpoints_db
        saver = open_sqlite_checkpointer(checkpoint_path)
        self.addCleanup(close_sqlite_checkpointer, checkpoint_path)
        checkpoint = saver.put(
            {"configurable": {"thread_id": parent.thread_id, "checkpoint_ns": ""}},
            empty_checkpoint(), {"source": "test", "step": 0, "writes": {}, "parents": {}}, {})
        action = {"name": "execute", "args": {"command": "echo later"}}
        saver.put_writes(checkpoint, [("__interrupt__", [{"id": "saved-approval", "value": {"action_requests": [action]}}])], "approval-task")
        parent.checkpoint_ids = [checkpoint["configurable"]["checkpoint_id"]]
        parent.pending_interrupt = PendingInterrupt(interrupt_id="saved-approval", action_requests=[PendingInterruptAction(
            **action, allowed_decisions=["approve", "reject"])])
        harness._publish_control_update(parent)
        restarted = HarnessService(lambda: SimpleNamespace(paths=harness.manager.paths), app_store=store)
        self.assertTrue(restarted._has_resume_checkpoint(parent))
        observed = restarted.get_run(parent.id)
        self.assertEqual(observed.status, AgentRunStatus.failed)
        self.assertEqual(observed.stop_reason, "orphaned")
        saved = store.get_execution_run(parent.id)
        managed_id = child.id + ":managed-command:" + created["command_id"]
        self.assertEqual(saved.tool_outcomes[managed_id].outcome, "uncertain")
        self.assertEqual(saved.failure.category, "uncertain_effects")
        with self.assertRaises(HarnessError) as blocked:
            restarted._control_for_run(restarted._runs[parent.id]).require_dispatch(restarted._runs[parent.id])
        self.assertEqual(blocked.exception.code, "effects_unconfirmed")
        with self.assertRaises(HarnessError) as resume:
            restarted.resume_interrupt(parent.id, InterruptDecisionRequest(decisions=[{"type": "approve"}]))
        self.assertEqual(resume.exception.code, "run_not_live")
        restarted.acknowledge_project_effects(parent.id)
        restarted.require_thread_effects_confirmed(parent.thread_id)

    def test_root_notification_failure_keeps_durable_scoped_hold_on_restart(self):
        _, store, harness, _, parent, child, activity = self.fixture()
        parent.status, child.status, activity.status = AgentRunStatus.completed, AgentRunStatus.completed, "completed"
        store.put_execution_runs([child, parent])
        control = harness._control_for_run(parent)
        outcome = ToolOutcome(call_id="managed-command:late", name="start_command", outcome="uncertain",
            failure_category="runtime", recovery_action="inspect_effects", evidence={"exit_code": 124, "process_stopped": True}, updated_at=utc_now())
        with patch.object(harness, "_persist_and_notify", side_effect=OSError("root publication failed")):
            with self.assertRaisesRegex(OSError, "root publication"):
                harness._record_managed_command_outcome(control, child, outcome)
        saved_child, saved_parent = store.get_execution_run(child.id), store.get_execution_run(parent.id)
        self.assertEqual(saved_child.tool_outcomes[outcome.call_id], saved_parent.tool_outcomes[child.id + ":" + outcome.call_id])
        restarted = HarnessService(lambda: SimpleNamespace(paths=harness.manager.paths), app_store=store)
        with self.assertRaises(HarnessError) as blocked:
            restarted.require_thread_effects_confirmed(parent.thread_id)
        self.assertEqual(blocked.exception.code, "effects_unconfirmed")
        restarted.acknowledge_project_effects(parent.id)
        restarted.require_thread_effects_confirmed(parent.thread_id)

    def test_batch_write_failure_rolls_back_both_outcomes_and_linkage(self):
        _, store, _, _, parent, child, _ = self.fixture()
        store.put_execution_runs([child, parent])
        outcome = ToolOutcome(call_id="late", name="start_command", outcome="uncertain", updated_at=utc_now())
        child.tool_outcomes[outcome.call_id] = outcome
        parent.tool_outcomes[child.id + ":" + outcome.call_id] = outcome
        child.checkpoint_ids, parent.checkpoint_ids = ["child-new"], ["parent-new"]
        write = store._write_run_record_locked
        def interrupted(run, payload):
            write(run, payload)
            if run.id == parent.id:
                raise OSError("second run write failed")
        with patch.object(store, "_write_run_record_locked", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "second run"):
                store.put_execution_runs([child, parent])
        for run in (child, parent):
            saved = store.get_execution_run(run.id)
            self.assertEqual(saved.tool_outcomes, {})
            self.assertEqual(saved.checkpoint_ids, [])
        self.assertFalse(store._conn.in_transaction)


class PreviewAdmissionDeletionTests(unittest.TestCase):
    def test_start_and_delete_both_orderings_cannot_leave_a_deleted_chat_preview(self):
        for first in ("start", "delete"):
            with self.subTest(first=first):
                fixture = asset_fixture.AssetLifecycleTests(methodName="runTest")
                fixture.setUp()
                entered, release = threading.Event(), threading.Event()
                calls, outcomes = [], {}
                try:
                    project = fixture.root / "project"
                    project.mkdir()
                    fixture.put_conversation("chat", thread_id="thread", project_path=str(project))
                    conversation = fixture.store.get_conversation("chat")
                    fixture.store.put_conversation(conversation.model_copy(update={"presented_tools": ["start_preview"]}))
                    class Preview:
                        owned = False
                        def start_static(self, *args):
                            calls.append("start")
                            if first == "start":
                                entered.set()
                                if not release.wait(3):
                                    raise AssertionError("Start barrier was not released")
                            self.owned = True
                            return {"state": "active"}
                        def stop(self, *_):
                            calls.append("stop")
                            if first == "delete":
                                entered.set()
                                if not release.wait(3):
                                    raise AssertionError("Delete barrier was not released")
                            self.owned = False
                            return True
                    preview = Preview()
                    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
                        app_store=fixture.store, asset_lifecycle=fixture.lifecycle, preview=preview,
                        chat=SimpleNamespace(store=SimpleNamespace(get=fixture.store.get_conversation, conversation_lock=fixture.store.conversation_lock)),
                        manager=SimpleNamespace(lifecycle=LifecycleCoordinator()),
                    )))
                    def invoke(name):
                        try:
                            outcomes[name] = start_static_preview(request, "thread", StaticPreviewRequest(entry_path="page.html")) if name == "start" else delete_conversation(request, "chat", SimpleNamespace(execute=True, include_diagnostics=False))
                        except BaseException as error:
                            outcomes[name] = error
                    worker = threading.Thread(target=invoke, args=(first,))
                    worker.start()
                    try:
                        self.assertTrue(entered.wait(3))
                        invoke("delete" if first == "start" else "start")
                    finally:
                        release.set()
                        worker.join(5)
                    self.assertFalse(worker.is_alive())
                    self.assertIsInstance(outcomes["delete" if first == "start" else "start"], ManagerError)
                    if first == "start":
                        invoke("delete")  # Once admission completes, deletion stops that exact owner.
                        self.assertNotIsInstance(outcomes["delete"], BaseException)
                    else:
                        self.assertNotIsInstance(outcomes["delete"], BaseException)
                        invoke("start")  # A stale UI request rechecks the missing conversation.
                        self.assertIsInstance(outcomes["start"], HarnessError)
                        self.assertEqual(outcomes["start"].code, "preview_thread_required")
                    self.assertIsNone(fixture.store.get_conversation("chat"))
                    self.assertFalse(preview.owned)
                    self.assertEqual(calls, ["start", "stop"] if first == "start" else ["stop"])
                finally:
                    release.set()
                    fixture.tearDown()
