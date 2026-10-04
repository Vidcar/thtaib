"""Existing interaction arrays retain checkpoint-owned parallel approvals."""
from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest

from tests.test_interaction_snapshot_races import SnapshotHarness
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, PendingInterrupt, PendingInterruptAction
from workbench_backend.errors import HarnessError
from workbench_backend.interaction.service import InteractionService
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore


class ParallelHarness(SnapshotHarness):
    def __init__(self, run):
        super().__init__(run)
        self.pending = []
        self.decisions = []

    def saved_pending_interrupts(self, _run):
        return list(self.pending)

    def resume_interrupt(self, run_id, request, *, require_interrupt_identity=False):
        selected = self.run.pending_interrupt
        if (not require_interrupt_identity or run_id != self.run.id or selected is None
                or request.interrupt_id != selected.interrupt_id or request.namespace != selected.namespace):
            raise HarnessError("This approval is stale or belongs to another run.", code="stale_interrupt", status_code=409)
        self.decisions.append(request)
        self.run.pending_interrupt = None
        return self.run


class InteractionParallelApprovalTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[3] / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="parallel-projection-", dir=scratch)
        self.store = ApplicationStore(WorkbenchPaths(Path(self.temporary.name)))
        self.run = AgentRun(id="parallel-root", thread_id="parallel-graph", deployment_id="model", task="Delegate",
            enabled_tools=["write_file"], presented_tools=["write_file"], status=AgentRunStatus.running,
            created_at="2026-10-04T00:00:00Z", updated_at="2026-10-04T00:00:00Z")
        self.harness = ParallelHarness(self.run)
        self.service = InteractionService(self.store, lambda: self.harness, lambda: None)
        self.store.put_run(self.run)
        self.store.register_interaction("parallel-display", "agent", self.run.thread_id, None,
            {"messages": [], "workbench": {"run": None}})
        self.service.observe(self.run, None)
        self.alpha = self.request("alpha")
        self.beta = self.request("beta")
        if os.environ.get("WORKBENCH_HELPER_APPROVAL_CONTROL") == "singleton-projection":
            original = self.service._project_native
            def singleton_projection(binding, run, raw):
                events, snapshot = original(binding, run, raw)
                if snapshot is not None and snapshot.get("__interrupt__"):
                    snapshot["__interrupt__"] = snapshot["__interrupt__"][-1:]
                return events, snapshot
            self.service._project_native = singleton_projection

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def request(self, name):
        return PendingInterrupt(interrupt_id=f"native-{name}", namespace=[f"tools:{name}"],
            action_requests=[PendingInterruptAction(name="write_file", args={"file_path": f"/{name}.txt", "content": name})])

    def emit(self, pending):
        self.service.observe(self.run, {"method": "values", "params": {
            "namespace": pending.namespace, "data": {"messages": []},
            "interrupts": [{"id": pending.interrupt_id, "value": pending.model_dump(mode="json")}],
        }})

    def snapshot(self):
        return self.store.get_interaction("parallel-display")["snapshot"]

    def publish(self, selected, pending):
        self.run.pending_interrupt = selected
        self.harness.pending = pending
        self.store.put_run(self.run)
        self.service.observe(self.run, None)

    def respond(self, pending, namespace=None):
        return self.service.command("parallel-display", {"id": f"answer-{len(self.harness.decisions)}", "method": "input.respond",
            "params": {"interrupt_id": pending.interrupt_id,
                "namespace": pending.namespace if namespace is None else namespace,
                "response": {"decisions": [{"type": "approve"}]}}})

    def test_streamed_requests_accumulate_once_and_pause_replaces_stale_set(self):
        self.emit(self.alpha)
        self.emit(self.beta)
        self.emit(self.alpha)
        self.assertEqual({item["id"] for item in self.snapshot()["__interrupt__"]}, {"native-alpha", "native-beta"})
        self.assertEqual(len(self.snapshot()["__interrupt__"]), 2)
        self.emit(self.request("retired"))
        self.publish(self.alpha, [self.alpha, self.beta, self.alpha])
        current = self.service.state("parallel-display")["values"]
        self.assertEqual([item["id"] for item in current["__interrupt__"]], ["native-alpha", "native-beta"])
        self.assertEqual(current["workbench"]["run"]["pending_interrupt"]["interrupt_id"], "native-alpha")
        self.assertEqual([item["namespace"] for item in current["__interrupt__"]], [self.alpha.namespace, self.beta.namespace])

    def test_only_selected_request_can_be_answered_and_duplicate_is_stale(self):
        self.publish(self.alpha, [self.alpha, self.beta])
        for request, namespace in ((self.beta, None), (self.alpha, self.beta.namespace), (self.request("retired"), None)):
            with self.subTest(request=request.interrupt_id, namespace=namespace):
                with self.assertRaisesRegex(Exception, "stale|another run"):
                    self.respond(request, namespace)
        self.assertEqual(self.harness.decisions, [])
        self.respond(self.alpha)
        self.assertEqual(len(self.harness.decisions), 1)
        with self.assertRaisesRegex(Exception, "stale|another run"):
            self.respond(self.alpha)
        self.assertEqual(len(self.harness.decisions), 1)

    def test_refresh_keeps_remaining_request_and_clears_terminal_requests(self):
        self.publish(self.alpha, [self.alpha, self.beta])
        self.publish(None, [self.alpha, self.beta])
        self.assertEqual(self.service.state("parallel-display")["values"]["__interrupt__"], [])
        self.publish(self.beta, [self.beta])
        current = self.service.state("parallel-display")["values"]
        self.assertEqual([item["id"] for item in current["__interrupt__"]], ["native-beta"])
        self.run.status = AgentRunStatus.cancel_requested
        self.store.put_run(self.run)
        self.service.observe(self.run, None)
        self.assertEqual(self.service.state("parallel-display")["values"]["__interrupt__"], [])
        self.run.status = AgentRunStatus.cancelled
        self.publish(None, [])
        self.assertEqual(self.snapshot()["__interrupt__"], [])

    def test_legacy_singleton_owner_remains_readable(self):
        self.harness.saved_pending_interrupts = None
        self.publish(self.alpha, [])
        current = self.service.state("parallel-display")["values"]
        self.assertEqual([item["id"] for item in current["__interrupt__"]], ["native-alpha"])
