"""Project reservations and the existing durable Chat queue across Windows roots."""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, ToolOutcome
from workbench_backend.app import create_app
from workbench_backend.chat.coordinator import ChatCoordinator
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run


class ProjectAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "child").mkdir()
        self.app = create_app(data_root=self.root / "data")
        self.hold = threading.Event()
        self.entered = threading.Event()
        hold, entered = self.hold, self.entered
        self.started = []

        class HeldModel(ScriptedChatModel):
            def _next_message(self):
                entered.set()
                if not hold.wait(timeout=15):
                    raise TimeoutError("Test owner was not released")
                return super()._next_message()

        def factory(run, _sink):
            self.started.append(run.task)
            return HeldModel([AIMessage(content="Owner done")]) if run.task == "owner" else ScriptedChatModel([AIMessage(content=run.task + " done")])

        def observer(run, _event, **_kwargs):
            coordinator = getattr(self.app.state, "chat_coordinator", None)
            if coordinator is not None:
                coordinator.observe(run)

        self.factory, self.observer = factory, observer
        self.app.state.harness = self.harness = HarnessService(lambda: self.app.state.manager,
            model_factory=factory, app_store=self.app.state.app_store,
            knowledge_provider=lambda: self.app.state.knowledge, interaction_observer=observer)
        self.client = offline_workbench_client(self.app)
        self.deployment = self.client.post("/v1/deployments/connected", json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "admission fixture"}).json()["id"]

    def tearDown(self):
        self.hold.set()
        coordinator = getattr(self.app.state, "chat_coordinator", None)
        if coordinator is not None:
            coordinator.close()
            del self.app.state.chat_coordinator
        close_workbench_sqlite(self.app, self.client)
        self.temp.cleanup()

    def chat(self, project=None, *, title=None):
        response = self.client.post("/v1/chat/conversations", json={"deployment_id": self.deployment,
            "project_path": str(project or self.project), "title": title,
            "presented_tools": [], "approval_mode": "full_access"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def start(self, chat, task, ident=None):
        response = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": task, "input_message_id": ident or task})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def until(self, predicate):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            threading.Event().wait(.02)
        self.fail("Admission did not settle before timeout")

    def test_shared_root_waits_durably_before_load_and_drains_fifo(self):
        owner, first, second = self.chat(title="Queue owner"), self.chat(), self.chat(self.project / "child")
        started = self.start(owner, "owner")
        self.assertTrue(self.entered.wait(8))
        with patch.object(self.app.state.manager, "ensure_deployment_ready", wraps=self.app.state.manager.ensure_deployment_ready) as loaded:
            waiting = self.start(first, "first")
            waiting_second = self.start(second, "second")
            repeated = self.start(first, "first")
            loaded.assert_not_called()
        self.assertEqual(len(repeated["queue"]), 1)
        self.assertEqual(waiting["run_ids"], [])
        self.assertEqual(waiting["queue"][0]["waiting_run_id"], started["current_run_id"])
        self.assertEqual(waiting["queue"][0]["waiting_owner_title"], "Queue owner")
        self.assertEqual(waiting["queue"][0]["wait_reason"], "project_busy")
        self.assertEqual(waiting_second["queue"][0]["queue_position"], 2)
        self.assertIsNotNone(waiting["queue"][0]["execution_snapshot"])
        independent = self.root / "independent"
        independent.mkdir()
        unrelated = self.start(self.chat(independent), "independent")
        self.assertEqual(wait_for_run(self.client, unrelated["current_run_id"])["status"], "completed")
        self.app.state.chat_coordinator = ChatCoordinator(self.app)
        self.hold.set()
        self.until(lambda: len(self.app.state.chat.store.get(second["id"]).run_ids) == 1)
        second_run = self.app.state.chat.store.get(second["id"]).run_ids[0]
        self.assertEqual(wait_for_run(self.client, second_run)["status"], "completed")
        self.assertLess(self.started.index("first"), self.started.index("second"))

    def test_cancelling_waiter_does_not_cancel_owner(self):
        owner, waiter = self.chat(), self.chat()
        current = self.start(owner, "owner")
        self.assertTrue(self.entered.wait(8))
        pending = self.start(waiter, "cancel-this")
        item = pending["queue"][0]
        removed = self.client.delete(f"/v1/chat/conversations/{waiter['id']}/queue/{item['id']}")
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertFalse(self.harness._cancels[current["current_run_id"]].is_set())
        self.hold.set()
        wait_for_run(self.client, current["current_run_id"])
        self.assertEqual(self.app.state.chat.dispatch_idle_queued(), 0)
        self.assertNotIn("cancel-this", self.started)

    def test_lab_capture_holds_reservation_through_snapshot(self):
        from workbench_backend.lab.snapshot import capture_project_snapshot
        workspace = self.client.post("/v1/lab/workspaces", json={"display_name": "capture fixture", "files": {"notes.md": "before"}}).json()
        entered, release = threading.Event(), threading.Event()
        result = []
        def paused_snapshot(*args, **kwargs):
            entered.set()
            if not release.wait(8):
                raise TimeoutError("Snapshot was not released")
            return capture_project_snapshot(*args, **kwargs)
        def capture():
            result.append(self.client.post("/v1/lab/cases/capture", json={"workspace_id": workspace["id"], "deployment_id": self.deployment, "task": "Read notes"}))
        with patch("workbench_backend.lab.service.capture_project_snapshot", side_effect=paused_snapshot):
            worker = threading.Thread(target=capture)
            worker.start()
            try:
                self.assertTrue(entered.wait(6))
                blocked = self.client.post("/v1/agent-runs", json={"deployment_id": self.deployment,
                    "workspace_id": workspace["id"], "task": "Must wait", "presented_tools": []})
                self.assertEqual(blocked.status_code, 409, blocked.text)
                self.assertEqual(blocked.json()["code"], "project_busy")
            finally:
                release.set()
                worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result[0].status_code, 200, result[0].text)

    def test_uncertainty_survives_restart_until_explicit_acknowledgement(self):
        owner, waiter = self.chat(), self.chat()
        now = utc_now()
        run = AgentRun(id="uncertain_owner", status=AgentRunStatus.failed, deployment_id=self.deployment,
            task="interrupted command", enabled_tools=["execute"], presented_tools=["execute"], project_path=str(self.project),
            thread_id=owner["thread_id"], source_surface="chat", created_at=now, updated_at=now,
            tool_outcomes={"call": ToolOutcome(call_id="call", name="execute", outcome="uncertain", updated_at=now)})
        self.harness.store.put_run(run)
        saved = self.app.state.chat.store.get(owner["id"])
        saved.run_ids = [run.id]
        saved.current_run_id = run.id
        self.app.state.chat.store.put(saved)
        pending = self.start(waiter, "after inspection")
        self.assertEqual(pending["queue"][0]["wait_reason"], "project_uncertain")
        self.app.state.harness = self.harness = HarnessService(lambda: self.app.state.manager, model_factory=self.factory,
            app_store=self.app.state.app_store, knowledge_provider=lambda: self.app.state.knowledge, interaction_observer=self.observer)
        self.app.state.chat.reconcile_saved_queue_on_startup()
        self.assertEqual(self.app.state.chat.dispatch_idle_queued(), 0)
        acknowledged = self.client.post(f"/v1/chat/conversations/{owner['id']}/runs/{run.id}/acknowledge-effects")
        self.assertEqual(acknowledged.status_code, 200, acknowledged.text)
        outcome = self.harness.get_run(run.id).tool_outcomes["call"]
        self.assertEqual(outcome.outcome, "uncertain")
        self.assertIn("acknowledged_at", outcome.evidence)
        self.assertEqual(self.app.state.chat.dispatch_idle_queued(), 1)
        admitted = self.app.state.chat.store.get(waiter["id"])
        wait_for_run(self.client, admitted.current_run_id)
        self.assertEqual(len(admitted.run_ids), 1)

    @unittest.skipUnless(os.name == "nt", "Windows actual root identity")
    def test_junction_and_extended_spelling_conflict_during_admission(self):
        alias = self.root / "alias"
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(self.project)], capture_output=True, text=True)
        self.assertEqual(made.returncode, 0, made.stderr)
        try:
            entered, release = threading.Event(), threading.Event()
            def own():
                with self.harness.project_admission(str(self.project)):
                    entered.set()
                    release.wait(8)
            thread = threading.Thread(target=own)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                for candidate in (str(alias), "\\\\?\\" + str(self.project), str(self.project / "child")):
                    with self.assertRaises(HarnessError) as failure:
                        with self.harness.project_admission(candidate):
                            self.fail("Aliased project was admitted twice")
                    self.assertEqual(failure.exception.code, "project_busy")
                independent = self.root / "independent"
                independent.mkdir()
                with self.harness.project_admission(str(independent)):
                    pass
            finally:
                release.set()
                thread.join(10)
        finally:
            alias.rmdir()


if __name__ == "__main__":
    unittest.main()
