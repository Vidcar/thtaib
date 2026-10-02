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
        # Keep the application's real interaction and reservation-release wiring.
        self.harness = self.app.state.harness
        self.harness._model_factory = factory
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
        waiting = self.start(first, "first")
        waiting_second = self.start(second, "second")
        repeated = self.start(first, "first")
        self.assertEqual(waiting["queue"], [])
        self.assertEqual(waiting_second["queue"], [])
        self.assertIsNotNone(waiting["current_run_id"])
        self.assertNotEqual(waiting["current_run_id"], started["current_run_id"])
        self.assertEqual(repeated["current_run_id"], waiting["current_run_id"])
        self.assertEqual(repeated["queue"], [])
        independent = self.root / "independent"
        independent.mkdir()
        unrelated = self.start(self.chat(independent), "independent")
        self.assertEqual(wait_for_run(self.client, unrelated["current_run_id"])["status"], "completed")
        self.assertLess(self.started.index("first"), self.started.index("second"))
        for body in (waiting, waiting_second):
            self.assertEqual(wait_for_run(self.client, body["current_run_id"])["status"], "completed")
        self.hold.set()
        self.assertEqual(wait_for_run(self.client, started["current_run_id"])["status"], "completed")

    def interaction(self, chat):
        response = self.client.post("/v1/agent-interaction/threads", json={
            "source_surface": "chat", "conversation_id": chat["id"]})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["thread_id"]

    def submit_interaction(self, thread, ident="queued-input", task="queued work"):
        return self.client.post(f"/v1/agent-interaction/threads/{thread}/commands", json={
            "id": "command-" + ident, "method": "run.start", "params": {
                "input": {"messages": [{"id": ident, "type": "human", "content": task}]},
                "metadata": {"workbench": {}}}})

    def test_interaction_accepts_busy_project_once_and_streams_the_same_input(self):
        owner, waiter = self.chat(), self.chat()
        thread = self.interaction(waiter)
        self.app.state.chat_coordinator = ChatCoordinator(self.app)
        self.start(owner, "owner")
        self.assertTrue(self.entered.wait(8))
        accepted = self.submit_interaction(thread)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertIn("run_id", accepted.json()["result"])
        run_id = accepted.json()["result"]["run_id"]
        saved = self.app.state.chat.store.get(waiter["id"])
        self.assertEqual(saved.queue, [])
        self.assertEqual(saved.current_run_id, run_id)
        # The run has started, so the input is already in the transcript.
        repeated = self.submit_interaction(thread)
        self.assertEqual(repeated.status_code, 409, repeated.text)
        self.assertEqual(repeated.json()["error"], "duplicate_input")
        edited = self.submit_interaction(thread, task="edited retry")
        self.assertEqual(edited.status_code, 409, edited.text)
        self.assertEqual(edited.json()["error"], "duplicate_input")
        self.assertIn("queued work", self.started)
        self.assertNotIn("edited retry", self.started)
        self.hold.set()
        self.assertEqual(wait_for_run(self.client, run_id)["status"], "completed")
        state = self.client.get(f"/v1/agent-interaction/threads/{thread}/state").json()
        self.assertEqual(state["values"]["workbench"]["run"]["input_message_id"], "queued-input")
        self.assertEqual([message["id"] for message in state["values"]["messages"]
            if message["type"] == "human"], ["queued-input"])
        self.assertEqual(self.started.count("queued work"), 1)
        self.assertEqual(len(self.app.state.chat.store.get(waiter["id"]).run_ids), 1)

    def test_interaction_queued_acceptance_does_not_return_the_previous_run(self):
        waiter = self.chat()
        prior = self.start(waiter, "previous work", "previous-input")
        wait_for_run(self.client, prior["current_run_id"])
        thread = self.interaction(waiter)
        self.start(self.chat(), "owner")
        self.assertTrue(self.entered.wait(8))
        accepted = self.submit_interaction(thread)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertIn("run_id", accepted.json()["result"])
        saved = self.app.state.chat.store.get(waiter["id"])
        self.assertEqual(saved.current_run_id, accepted.json()["result"]["run_id"])
        self.assertNotEqual(saved.current_run_id, prior["current_run_id"])
        self.assertEqual(saved.queue, [])
        self.assertEqual(self.started, ["previous work", "owner", "queued work"])

    def test_identical_queued_interaction_retry_wakes_idle_coordinator(self):
        waiter = self.chat()
        thread = self.interaction(waiter)
        queued = self.client.post(f"/v1/chat/conversations/{waiter['id']}/queue",
            json={"task": "queued work", "input_message_id": "queued-input"})
        self.assertEqual(queued.status_code, 200, queued.text)
        self.app.state.chat_coordinator = ChatCoordinator(self.app)
        accepted = self.submit_interaction(thread)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.until(lambda: len(self.app.state.chat.store.get(waiter["id"]).run_ids) == 1)
        run_id = self.app.state.chat.store.get(waiter["id"]).run_ids[0]
        self.assertEqual(wait_for_run(self.client, run_id)["status"], "completed")
        self.assertEqual(self.started, ["queued work"])

    def test_stopped_queued_submission_settles_without_restart_and_preserves_tombstone(self):
        owner, waiter = self.chat(), self.chat()
        current = self.start(owner, "owner")
        self.assertTrue(self.entered.wait(8))
        queued = self.client.post(f"/v1/chat/conversations/{waiter['id']}/queue",
            json={"task": "stopped work", "input_message_id": "stopped-input"})
        self.assertEqual(queued.status_code, 200, queued.text)
        queued = queued.json()
        thread = self.interaction(waiter)
        self.assertEqual(self.client.get(f"/v1/agent-interaction/threads/{thread}/state").json()["next"], ["running"])
        stopped = self.client.post(f"/v1/chat/conversations/{waiter['id']}/cancel",
            json={"input_message_id": "stopped-input"})
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(stopped.json()["pending_cancel_input_ids"], [])
        self.assertEqual(stopped.json()["queue"][0]["status"], "paused")
        self.assertEqual(self.client.get(f"/v1/agent-interaction/threads/{thread}/state").json()["next"], [])
        self.assertTrue(self.app.state.app_store.chat_submission_cancel_known(waiter["id"], "stopped-input"))
        self.assertFalse(self.harness._cancels[current["current_run_id"]].is_set())
        removed = self.client.delete(f"/v1/chat/conversations/{waiter['id']}/queue/{queued['queue'][0]['id']}")
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json()["pending_cancel_input_ids"], [])
        self.assertEqual(removed.json()["queue"], [])
        self.hold.set()
        wait_for_run(self.client, current["current_run_id"])
        retried = self.start(waiter, "stopped work", "stopped-input")
        cancelled = wait_for_run(self.client, retried["current_run_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertNotIn("stopped work", self.started)

    def test_accepted_interaction_queue_recovers_after_restart_without_refreezing(self):
        waiter = self.chat()
        thread = self.interaction(waiter)
        queued = self.client.post(f"/v1/chat/conversations/{waiter['id']}/queue",
            json={"task": "saved queued work", "input_message_id": "saved-input"})
        self.assertEqual(queued.status_code, 200, queued.text)
        frozen = self.app.state.chat.store.get(waiter["id"]).queue[0].execution_snapshot
        close_workbench_sqlite(self.app, self.client)
        self.app = create_app(data_root=self.root / "data")
        self.harness = self.app.state.harness
        self.harness._model_factory = self.factory
        self.client = offline_workbench_client(self.app)
        self.app.state.chat.reconcile_saved_queue_on_startup()
        self.assertEqual(self.app.state.chat.store.get(waiter["id"]).queue[0].execution_snapshot, frozen)
        state = self.client.get(f"/v1/agent-interaction/threads/{thread}/state").json()
        self.assertEqual(state["next"], ["running"])
        self.assertIsNone(state["values"]["workbench"].get("run"))
        self.app.state.chat_coordinator = ChatCoordinator(self.app)
        accepted = self.submit_interaction(thread, "saved-input", "saved queued work")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.until(lambda: len(self.app.state.chat.store.get(waiter["id"]).run_ids) == 1)
        run_id = self.app.state.chat.store.get(waiter["id"]).run_ids[0]
        wait_for_run(self.client, run_id)
        state = self.client.get(f"/v1/agent-interaction/threads/{thread}/state").json()
        self.assertEqual(state["values"]["workbench"]["run"]["input_message_id"], "saved-input")
        self.assertEqual(self.started, ["saved queued work"])

    def test_stop_before_or_during_queue_admission_settles_without_owner_completion(self):
        owner = self.chat()
        current = self.start(owner, "owner")
        self.assertTrue(self.entered.wait(8))
        for phase in ("before request", "before queue commit", "after queue commit"):
            with self.subTest(phase=phase):
                waiter = self.chat()
                ident = "stop-" + phase
                entered, release = threading.Event(), threading.Event()
                result = []
                append = self.app.state.chat._append_queue_item_reserved

                def held_append(*args, **kwargs):
                    queued = append(*args, **kwargs) if phase == "after queue commit" else None
                    entered.set()
                    if not release.wait(8):
                        raise TimeoutError("Queue admission was not released")
                    return queued if queued is not None else append(*args, **kwargs)

                def stop():
                    response = self.client.post(f"/v1/chat/conversations/{waiter['id']}/cancel",
                        json={"input_message_id": ident})
                    self.assertEqual(response.status_code, 200, response.text)
                    return response.json()

                if phase == "before request":
                    self.assertEqual(stop()["pending_cancel_input_ids"], [])
                with patch.object(self.app.state.chat, "_append_queue_item_reserved", side_effect=held_append):
                    worker = threading.Thread(target=lambda: result.append(self.client.post(
                        f"/v1/chat/conversations/{waiter['id']}/queue",
                        json={"task": ident, "input_message_id": ident})))
                    worker.start()
                    try:
                        self.assertTrue(entered.wait(6))
                        if phase != "before request":
                            self.assertIn(ident, stop()["pending_cancel_input_ids"])
                        release.set()
                        worker.join(10)
                        self.assertFalse(worker.is_alive())
                    finally:
                        release.set()
                        worker.join(10)
                self.assertEqual(result[0].status_code, 200, result[0].text)
                observed = self.client.get(f"/v1/chat/conversations/{waiter['id']}").json()
                self.assertEqual(observed["pending_cancel_input_ids"], [])
                self.assertEqual(observed["queue"][0]["status"], "paused")
                self.assertEqual(observed["queue"][0]["pause_reason"], "cancelled")
                self.assertEqual(observed["run_ids"], [])
                self.assertTrue(self.app.state.app_store.chat_submission_cancel_known(waiter["id"], ident))
                self.assertFalse(self.harness._cancels[current["current_run_id"]].is_set())
                repeated = self.start(waiter, ident, ident)
                self.assertEqual(len(repeated["queue"]), 1)
                self.assertEqual(repeated["queue"][0]["status"], "paused")
                self.assertNotIn(ident, self.started)
        self.hold.set()
        wait_for_run(self.client, current["current_run_id"])
        self.assertEqual(self.app.state.chat.dispatch_idle_queued(), 0)
        self.assertEqual(self.started, ["owner"])

    def test_failed_admission_releases_waiting_chat_without_terminal_run(self):
        self.app.state.chat_coordinator = ChatCoordinator(self.app)
        waiter = self.chat()
        entered, release = threading.Event(), threading.Event()
        original = self.harness._start_admitted
        result = []
        def start_or_fail(request, **kwargs):
            if request.task == "failed admission":
                entered.set()
                if not release.wait(8):
                    raise TimeoutError("Admission was not released")
                raise HarnessError("fixture admission failure", code="fixture_failure", status_code=409)
            return original(request, **kwargs)
        def start_owner():
            result.append(self.client.post("/v1/agent-runs", json={"deployment_id": self.deployment,
                "project_path": str(self.project), "task": "failed admission", "presented_tools": []}))
        with patch.object(self.harness, "_start_admitted", side_effect=start_or_fail):
            worker = threading.Thread(target=start_owner)
            worker.start()
            try:
                self.assertTrue(entered.wait(6))
                started = self.start(waiter, "after failed admission")
                self.until(lambda: "after failed admission" in self.started)
                self.assertEqual(self.app.state.chat.store.get(waiter["id"]).queue, [])
                release.set()
                worker.join(10)
                self.assertFalse(worker.is_alive())
                self.assertEqual(result[0].status_code, 409)
                self.assertEqual(wait_for_run(self.client, started["current_run_id"])["status"], "completed")
                self.assertEqual(self.started, ["after failed admission"])
            finally:
                release.set()
                worker.join(10)

    def test_nested_reservations_wake_once_after_the_outer_owner_releases(self):
        self.app.state.chat_coordinator = ChatCoordinator(self.app)
        with patch.object(self.app.state.chat_coordinator, "wake") as wake:
            with self.harness.project_admission(str(self.project)):
                with self.harness.project_admission(str(self.project / "child")):
                    wake.assert_not_called()
                wake.assert_not_called()
            wake.assert_called_once_with()

    def test_cancelling_waiter_does_not_cancel_owner(self):
        owner, waiter = self.chat(), self.chat()
        current = self.start(owner, "owner")
        self.assertTrue(self.entered.wait(8))
        pending = self.client.post(f"/v1/chat/conversations/{waiter['id']}/queue", json={"task": "cancel-this"})
        self.assertEqual(pending.status_code, 200, pending.text)
        item = pending.json()["queue"][0]
        removed = self.client.delete(f"/v1/chat/conversations/{waiter['id']}/queue/{item['id']}")
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertFalse(self.harness._cancels[current["current_run_id"]].is_set())
        self.hold.set()
        wait_for_run(self.client, current["current_run_id"])
        self.assertEqual(self.app.state.chat.dispatch_idle_queued(), 0)
        self.assertNotIn("cancel-this", self.started)

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
        self.assertEqual(pending["queue"], [])
        self.assertIsNotNone(pending["current_run_id"])
        denied = self.client.post(f"/v1/chat/conversations/{owner['id']}/start",
            json={"task": "continue owner", "input_message_id": "continue-owner"})
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(denied.json()["code"], "effects_unconfirmed")
        restarted = HarnessService(lambda: self.app.state.manager, model_factory=self.factory,
            app_store=self.app.state.app_store, knowledge_provider=lambda: self.app.state.knowledge, interaction_observer=self.observer)
        with self.assertRaises(HarnessError) as blocked:
            restarted.require_thread_effects_confirmed(owner["thread_id"])
        self.assertEqual(blocked.exception.code, "effects_unconfirmed")
        restarted.require_thread_effects_confirmed(waiter["thread_id"])
        acknowledged = self.client.post(f"/v1/chat/conversations/{owner['id']}/runs/{run.id}/acknowledge-effects")
        self.assertEqual(acknowledged.status_code, 200, acknowledged.text)
        outcome = self.harness.get_run(run.id).tool_outcomes["call"]
        self.assertEqual(outcome.outcome, "uncertain")
        self.assertIn("acknowledged_at", outcome.evidence)
        restarted.require_thread_effects_confirmed(owner["thread_id"])
        continued = self.start(owner, "continue owner", "continue-after")
        self.assertEqual(wait_for_run(self.client, continued["current_run_id"])["status"], "completed")
        self.assertEqual(wait_for_run(self.client, pending["current_run_id"])["status"], "completed")

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
                admitted = []
                for candidate in (str(alias), "\\\\?\\" + str(self.project), str(self.project / "child")):
                    with self.harness.project_admission(candidate):
                        admitted.append(candidate)
                self.assertEqual(len(admitted), 3)
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
