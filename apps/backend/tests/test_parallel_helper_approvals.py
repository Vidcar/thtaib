"""Native concurrent helper requests keep exact identities and one owned effect."""
from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langgraph.types import Command

from tests import test_agent_capabilities as fixtures
from tests.scripted_model import ScriptedChatModel
from tests.support import wait_for_run
from tests.test_host_shell import wait_for_interrupt, run_direct_interrupt_decision
from workbench_backend.agents.harness import HarnessService, _resume_value
from workbench_backend.agents.harness_backend import FilesystemBackend
from workbench_backend.agents.schemas import AgentRunStatus


class ParallelHelperApprovalTests(unittest.TestCase):
    setUp = fixtures.AgentCapabilitiesTests.setUp
    tearDown = fixtures.AgentCapabilitiesTests.tearDown
    post = fixtures.AgentCapabilitiesTests.post
    project = fixtures.AgentCapabilitiesTests.project
    harness = fixtures.AgentCapabilitiesTests.harness
    start = fixtures.AgentCapabilitiesTests.start

    def _start_parallel(self, order=("Alpha", "Beta"), *, on_owner=None):
        project = self.project()
        helpers = [self.post("/v1/agent-setups", {"name": name, "configuration": {
            "deployment_id": self.deployment.id, "presented_tools": ["write_file"]}}) for name in order]
        main = ScriptedChatModel([AIMessage(content="", tool_calls=[
            {"name": "task", "args": {"subagent_type": helper["id"], "description": name}, "id": name.lower()}
            for helper, name in zip(helpers, order, strict=True)]), AIMessage(content="Both helpers returned.")])
        children = {}

        def factory(run, _sink):
            if not run.parent_run_id:
                return main
            # Preserve model sequence across native checkpoint resumption. A
            # fresh script per compile would invent repeated model requests.
            if run.id not in children:
                children[run.id] = ScriptedChatModel([
                    fixtures.call("write_file", {"file_path": f"{run.task}.txt", "content": f"Owned {run.task}"}, "same-write"),
                    AIMessage(content=f"{run.task} returned.")])
            return children[run.id]

        self.factory = factory
        self.harness(factory)
        if on_owner is not None:
            on_owner(self.app.state.harness)
        started = self.start(project_id=project["id"], presented_tools=["write_file"],
            helper_agent_ids=[helper["id"] for helper in helpers], approval_mode="ask")
        waiting = wait_for_interrupt(self.client, started["id"])
        requests = self.app.state.harness.saved_pending_interrupts(self.app.state.harness._runs[started["id"]])
        self.assertEqual(len(requests), 2, waiting)
        self.assertEqual(len({request.interrupt_id for request in requests}), 2)
        self.assertEqual(len({tuple(request.namespace) for request in requests}), 2)
        self.assertEqual({request.action_requests[0].args["file_path"] for request in requests}, {"Alpha.txt", "Beta.txt"})
        self.assertTrue(all(item["status"] == "waiting for approval or answer" for item in waiting["child_runs"]))
        self.assertFalse((self.folder / "Alpha.txt").exists())
        self.assertFalse((self.folder / "Beta.txt").exists())
        return waiting

    def _next_interrupt(self, run_id, previous_id):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            run = self.client.get("/v1/agent-runs/" + run_id).json()
            if run["status"] in {"failed", "cancelled", "completed"}:
                self.fail(f"Run ended instead of retaining its other helper request: {run}")
            pending = run.get("pending_interrupt")
            if pending and pending["interrupt_id"] != previous_id:
                return run
            time.sleep(.02)
        self.fail("The remaining helper request was not published")

    def _decide(self, waiting, choice):
        return self.client.post("/v1/agent-runs/" + waiting["id"] + "/interrupt-decision",
            json=run_direct_interrupt_decision(waiting, choice))

    def _assert_complete(self, run_id):
        finished = wait_for_run(self.client, run_id)
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertIsNone(finished["pending_interrupt"])
        self.assertTrue(all(child["status"] == "completed" for child in finished["child_runs"]))
        self.assertEqual(self.app.state.harness.saved_pending_interrupts(self.app.state.harness._runs[run_id]), [])
        return finished

    def _exercise_opposite_decisions(self, order):
        writes = []
        native_write = FilesystemBackend.write

        def counted(backend, path, content):
            writes.append(path)
            return native_write(backend, path, content)

        with patch.object(FilesystemBackend, "write", counted):
            first = self._start_parallel(order)
            approved_path = first["pending_interrupt"]["action_requests"][0]["args"]["file_path"]
            self.assertEqual(approved_path, order[0] + ".txt")
            response = self._decide(first, "approve")
            self.assertEqual(response.status_code, 200, response.text)
            second = self._next_interrupt(first["id"], first["pending_interrupt"]["interrupt_id"])
            rejected_path = second["pending_interrupt"]["action_requests"][0]["args"]["file_path"]
            self.assertNotEqual(approved_path, rejected_path)
            self.assertEqual((self.folder / approved_path).read_text(), "Owned " + order[0])
            self.assertFalse((self.folder / rejected_path).exists())
            remaining = self.app.state.harness.saved_pending_interrupts(self.app.state.harness._runs[first["id"]])
            self.assertEqual([item.interrupt_id for item in remaining], [second["pending_interrupt"]["interrupt_id"]])
            response = self._decide(second, "reject")
            self.assertEqual(response.status_code, 200, response.text)
            finished = self._assert_complete(first["id"])
        self.assertEqual([path.lstrip("/") for path in writes], [approved_path])
        self.assertFalse((self.folder / rejected_path).exists())
        self.assertEqual(len([event for event in finished["events"] if event["kind"] == "interrupt_resolved"]), 2)
        for activity in finished["child_runs"]:
            child = self.app.state.harness.get_run(activity["run_id"])
            self.assertIsNone(child.pending_interrupt)
            self.assertEqual([item["id"] for item in child.tool_invocations], ["same-write"])
            self.assertEqual(sum(event.kind == "tool_result" and event.detail.get("tool_call_id") == "same-write" for event in child.events), 1)
            result = next(event.detail for event in child.events if event.kind == "tool_result" and event.detail.get("tool_call_id") == "same-write")
            if child.task + ".txt" == approved_path:
                self.assertEqual(finished["tool_outcomes"][child.id + ":same-write"]["outcome"], "succeeded")
                self.assertEqual(result["status"], "success")
            else:
                # Native HITL rejection returns an error ToolMessage without
                # entering the application's effectful dispatch ledger.
                self.assertEqual(result["status"], "error")
                self.assertIn("rejected", str(result["content"]).lower())
                self.assertNotIn(child.id + ":same-write", finished["tool_outcomes"])

    def test_parallel_same_local_ids_approve_alpha_reject_beta(self):
        self._exercise_opposite_decisions(("Alpha", "Beta"))

    def test_parallel_same_local_ids_approve_beta_reject_alpha(self):
        self._exercise_opposite_decisions(("Beta", "Alpha"))

    def test_wrong_namespace_hidden_request_and_duplicate_decisions_have_no_effect(self):
        first = self._start_parallel()
        owner = self.app.state.harness
        pending = owner.saved_pending_interrupts(owner._runs[first["id"]])
        endpoint = "/v1/agent-runs/" + first["id"] + "/interrupt-decision"
        wrong = run_direct_interrupt_decision(first, "approve")
        wrong["namespace"] = pending[1].namespace
        response = self.client.post(endpoint, json=wrong)
        self.assertEqual(response.status_code, 409, response.text)
        hidden = {"interrupt_id": pending[1].interrupt_id, "namespace": pending[1].namespace, "decisions": [{"type": "approve"}]}
        response = self.client.post(endpoint, json=hidden)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertFalse((self.folder / "Alpha.txt").exists())
        self.assertFalse((self.folder / "Beta.txt").exists())
        self.assertEqual(self._decide(first, "approve").status_code, 200)
        duplicate = self._decide(first, "approve")
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        second = self._next_interrupt(first["id"], first["pending_interrupt"]["interrupt_id"])
        stale = self._decide(first, "reject")
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(self._decide(second, "reject").status_code, 200)
        self._assert_complete(first["id"])
        self.assertFalse((self.folder / "Beta.txt").exists())

    def _restart_paused_owner(self, run_id):
        old = self.app.state.harness
        # Retire the old waiting worker without changing its durable checkpoint
        # or records, reproducing a process boundary rather than a second owner.
        old._persist_and_notify = lambda _run: None
        async def skip_reject(*_args, **_kwargs):
            return None
        old._aresume_reject_then_stop = skip_reject
        with old._lock:
            old._runs[run_id].status = AgentRunStatus.completed
            old._runs[run_id].pending_interrupt = None
            old._cancels[run_id].set()
            old._decision_ready[run_id].set()
        old._threads[run_id].join(timeout=5)
        self.assertFalse(old._threads[run_id].is_alive())
        restarted = HarnessService(lambda: self.app.state.manager, app_store=self.app.state.app_store,
            model_factory=self.factory, knowledge_provider=lambda: self.app.state.knowledge,
            interaction_observer=old._interaction_observer)
        self.app.state.harness = restarted
        observed = self.client.get("/v1/agent-runs/" + run_id).json()
        self.assertEqual(observed["status"], "running", observed)
        return observed

    def test_restart_hydrates_both_requests_before_exact_decisions(self):
        first = self._start_parallel()
        restarted = self._restart_paused_owner(first["id"])
        pending = self.app.state.harness.saved_pending_interrupts(self.app.state.harness._runs[first["id"]])
        self.assertEqual(len(pending), 2)
        self.assertEqual(restarted["pending_interrupt"]["interrupt_id"], first["pending_interrupt"]["interrupt_id"])
        self.assertTrue(all(item["status"] == "waiting for approval or answer" for item in restarted["child_runs"]))
        self.assertEqual(self._decide(restarted, "approve").status_code, 200)
        second = self._next_interrupt(first["id"], first["pending_interrupt"]["interrupt_id"])
        self.assertEqual(self._decide(second, "reject").status_code, 200)
        self._assert_complete(first["id"])
        self.assertEqual((self.folder / "Alpha.txt").read_text(), "Owned Alpha")
        self.assertFalse((self.folder / "Beta.txt").exists())

    def test_restart_between_decisions_retains_completion_and_other_namespace(self):
        first = self._start_parallel()
        self.assertEqual(self._decide(first, "approve").status_code, 200)
        second = self._next_interrupt(first["id"], first["pending_interrupt"]["interrupt_id"])
        restarted = self._restart_paused_owner(first["id"])
        self.assertEqual(restarted["pending_interrupt"], second["pending_interrupt"])
        pending = self.app.state.harness.saved_pending_interrupts(self.app.state.harness._runs[first["id"]])
        self.assertEqual([item.namespace for item in pending], [second["pending_interrupt"]["namespace"]])
        self.assertEqual(self._decide(restarted, "reject").status_code, 200)
        self._assert_complete(first["id"])
        self.assertEqual((self.folder / "Alpha.txt").read_text(), "Owned Alpha")
        self.assertFalse((self.folder / "Beta.txt").exists())

    def test_stop_rejects_every_pending_identity_without_writes(self):
        first = self._start_parallel()
        requests = self.app.state.harness.saved_pending_interrupts(self.app.state.harness._runs[first["id"]])
        with patch("workbench_backend.agents.harness.Command", wraps=Command) as command:
            self.assertEqual(self.client.post("/v1/agent-runs/" + first["id"] + "/cancel", json={}).status_code, 200)
            finished = wait_for_run(self.client, first["id"])
        self.assertEqual(finished["status"], "cancelled", finished.get("error"))
        resume = next(call.kwargs["resume"] for call in command.call_args_list if "resume" in call.kwargs)
        self.assertEqual(set(resume), {item.interrupt_id for item in requests})
        self.assertTrue(all(value["decisions"] == [{"type": "reject", "message": "Run cancelled before this action was approved."}] for value in resume.values()))
        self.assertFalse((self.folder / "Alpha.txt").exists())
        self.assertFalse((self.folder / "Beta.txt").exists())
        self.assertTrue(all(child["status"] == "cancelled" for child in finished["child_runs"]))
        for child in finished["child_runs"]:
            self.assertIsNone(self.app.state.harness.get_run(child["run_id"]).pending_interrupt)

    def test_stop_after_one_approval_preserves_only_its_completed_effect(self):
        first = self._start_parallel()
        self.assertEqual(self._decide(first, "approve").status_code, 200)
        self._next_interrupt(first["id"], first["pending_interrupt"]["interrupt_id"])
        self.assertEqual(self.client.post("/v1/agent-runs/" + first["id"] + "/cancel", json={}).status_code, 200)
        finished = wait_for_run(self.client, first["id"])
        self.assertEqual(finished["status"], "cancelled", finished.get("error"))
        self.assertEqual((self.folder / "Alpha.txt").read_text(), "Owned Alpha")
        self.assertFalse((self.folder / "Beta.txt").exists())
        activities = {item["tool_call_id"]: item for item in finished["child_runs"]}
        self.assertEqual(activities["alpha"]["status"], "completed")
        self.assertEqual(activities["beta"]["status"], "cancelled")
        self.assertEqual(finished["tool_outcomes"][activities["alpha"]["run_id"] + ":same-write"]["outcome"], "succeeded")

    def test_scalar_resume_negative_control_fails_native_outcome_assertion(self):
        first = self._start_parallel()
        with patch("workbench_backend.agents.harness._resume_command", side_effect=lambda _pending, decisions: Command(resume=_resume_value(decisions))):
            self.assertEqual(self._decide(first, "approve").status_code, 200)
            with self.assertRaises(AssertionError):
                self._assert_complete(first["id"])
        finished = self.client.get("/v1/agent-runs/" + first["id"]).json()
        self.assertEqual(finished["status"], "failed")
        self.assertIn("multiple pending interrupts", finished["error"])
        self.assertFalse((self.folder / "Alpha.txt").exists())
        self.assertFalse((self.folder / "Beta.txt").exists())

    def test_pending_projection_read_never_waits_for_harness_lock_or_checkpoint(self):
        first = self._start_parallel()
        owner = self.app.state.harness
        values = []
        with owner._lock, patch.object(owner, "_create_compiled_agent", side_effect=AssertionError("projection reader compiled a graph")):
            reader = threading.Thread(target=lambda: values.extend(owner.saved_pending_interrupts(owner._runs[first["id"]])))
            reader.start()
            reader.join(timeout=1)
            self.assertFalse(reader.is_alive(), "projection reader acquired the harness lock")
        self.assertEqual(len(values), 2)
        self.client.post("/v1/agent-runs/" + first["id"] + "/cancel", json={})
        wait_for_run(self.client, first["id"])

    def test_unreadable_native_pending_set_fails_closed_without_singleton_projection(self):
        def corrupt_read(owner):
            original = owner._create_compiled_agent
            def compile_with_unreadable_state(*args, **kwargs):
                graph = original(*args, **kwargs)
                if not kwargs.get("is_child"):
                    async def unreadable(*_args, **_kwargs):
                        raise OSError("injected native checkpoint read failure")
                    graph.aget_state = unreadable
                return graph
            controlled = patch.object(owner, "_create_compiled_agent", side_effect=compile_with_unreadable_state)
            controlled.start()
            self.addCleanup(controlled.stop)
        with self.assertRaisesRegex(TimeoutError, "run finished without interrupt"):
            self._start_parallel(on_owner=corrupt_read)
        owner = self.app.state.harness
        root = next(run for run in owner._runs.values() if not run.parent_run_id)
        self.assertEqual(root.status, AgentRunStatus.failed)
        self.assertIn("saved approval requests could not be read", root.error)
        self.assertEqual(root.failure.code, "interrupt_checkpoint_unavailable")
        self.assertEqual(owner.saved_pending_interrupts(root), [])
        self.assertNotIn(root.id, owner._native_pending_interrupts)
        self.assertFalse((self.folder / "Alpha.txt").exists())
        self.assertFalse((self.folder / "Beta.txt").exists())
