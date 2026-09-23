"""Snapshot, replay and run metadata must describe the same stream position."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.interaction.projection import event, partial_archive
from workbench_backend.interaction.service import InteractionService
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore


class SnapshotHarness:
    def __init__(self, run):
        self.run = run
        self.lock = threading.RLock()

    def get_run(self, _run_id):
        with self.lock:
            return self.run.model_copy(deep=True)

    def projection_run(self, _run_id):
        with self.lock:
            return self.run.model_dump(mode="json")

    @contextmanager
    def run_read_lock(self, _run_id):
        with self.lock:
            yield


class InteractionSnapshotRaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = ApplicationStore(WorkbenchPaths(Path(self.temporary.name)))
        self.run = AgentRun(id="run", thread_id="graph", deployment_id="model", task="task",
            enabled_tools=[], presented_tools=[], status=AgentRunStatus.running,
            created_at="2026-09-23T12:00:00Z", updated_at="2026-09-23T12:00:00Z")
        self.harness = SnapshotHarness(self.run)
        self.service = InteractionService(self.store, lambda: self.harness, lambda: None)
        self.store.put_run(self.run)
        self.store.register_interaction("display", "agent", "graph", None, {
            "messages": [], "workbench": {"run": None},
        })
        self.service.observe(self.run, None)
        for data in (
            {"event": "message-start", "role": "ai", "id": "answer"},
            {"event": "content-block-delta", "index": 0,
             "delta": {"type": "text-delta", "text": "Visible answer"}},
        ):
            self.service.observe(self.run, event("messages", data))
        self.cursor = self.store.get_interaction("display")["seq"]

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def complete(self):
        with self.harness.lock:
            self.run.status = AgentRunStatus.completed
            self.store.put_run(self.run)
            self.service.observe(self.run, None)

    def test_historical_values_keep_the_run_state_at_their_cursor(self):
        earlier = self.store.get_interaction("display")["snapshot"]
        self.complete()
        rendered = self.service.display_values(earlier)
        self.assertEqual(rendered["workbench"]["run"]["status"], "running")
        self.assertEqual(rendered["messages"], earlier["messages"])

    def test_partial_tool_arguments_survive_hydration_and_terminal_reopen(self):
        args = '{"file_path":"unfinished.txt","content":"' + "unfinished line\\n" * 800
        for status in (AgentRunStatus.running, AgentRunStatus.cancelled, AgentRunStatus.failed):
            with self.subTest(status=status):
                self.run.status = AgentRunStatus.running
                self.store.put_run(self.run)
                self.service.observe(self.run, None)
                self.service.observe(self.run, event("messages", {
                    "event": "content-block-delta", "index": 1,
                    "delta": {"type": "block-delta", "fields": {
                        "type": "tool_call_chunk", "id": "write-1", "name": "write_file", "args": args,
                    }},
                }))
                self.run.status = status
                self.store.put_run(self.run)
                self.service.observe(self.run, None)
                state = self.service.state("display")
                message = state["values"]["messages"][-1]
                chunks = [block for block in message["content"] if block["type"] == "tool_call_chunk"]
                self.assertEqual(len(chunks), 1)
                self.assertEqual(chunks[0], {"type": "tool_call_chunk", "id": "write-1", "name": "write_file", "args": args})
                self.assertFalse(message.get("tool_calls"))
                self.assertEqual(self.run.tool_invocations, [])
                self.assertIn("answer", state["values"]["workbench"]["incomplete_message_ids"])
                # Reopening reads from the saved cursor; it cannot rely on the
                # desktop replaying all preceding message deltas again.
                reopened = InteractionService(self.store, lambda: self.harness, lambda: None)
                self.assertEqual(reopened.state("display")["values"]["messages"], state["values"]["messages"])

    def test_terminal_hydration_reconciles_before_returning_saved_text(self):
        # The worker commits its run before its interaction observer publishes.
        self.run.status = AgentRunStatus.completed
        self.store.put_run(self.run)
        state = self.service.state("display")
        self.assertEqual(state["values"]["workbench"]["run"]["status"], "completed")
        self.assertEqual(state["values"]["messages"][-1]["content"],
                         [{"type": "text", "text": "Visible answer"}])
        self.assertGreater(state["interaction_cursor"], self.cursor)
        self.assertEqual(state["next"], [])

    def test_maintenance_cannot_drop_tokens_before_terminal_snapshot_is_published(self):
        self.run.status = AgentRunStatus.completed
        self.store.put_run(self.run)
        removed = self.store.discard_finished_token_log("display")
        self.assertEqual(removed, 0)
        self.service.observe(self.run, None)
        state = self.service.state("display")
        self.assertEqual(state["values"]["messages"][-1]["content"],
                         [{"type": "text", "text": "Visible answer"}])

    def test_completion_during_hydration_cannot_remove_captured_live_text(self):
        complete_once = False

        def finish_before_assembling(events):
            nonlocal complete_once
            if not complete_once:
                complete_once = True
                self.complete()
            return partial_archive(events)

        with patch("workbench_backend.interaction.service.partial_archive", side_effect=finish_before_assembling):
            state = self.service.state("display")
        self.assertEqual(state["values"]["messages"][-1]["content"],
                         [{"type": "text", "text": "Visible answer"}])
        self.assertEqual(state["values"]["workbench"]["run"]["status"], "running")
        self.assertEqual(state["interaction_cursor"], self.cursor)
        self.assertEqual(self.store.get_interaction("display")["snapshot"]["workbench"]["run"]["status"], "completed")

    def test_finished_message_remains_visible_before_graph_values_arrive(self):
        self.service.observe(self.run, event("messages", {
            "event": "content-block-finish", "index": 0,
            "content": {"type": "text", "text": "Visible answer"},
        }))
        self.service.observe(self.run, event("messages", {"event": "message-finish"}))
        state = self.service.state("display")
        self.assertEqual(state["values"]["messages"][-1]["content"][0]["text"], "Visible answer")
        self.assertNotIn("answer", state["values"]["workbench"]["incomplete_message_ids"])

        # A cancelled worker can end before the graph emits its values update.
        self.run.status = AgentRunStatus.cancelled
        self.store.put_run(self.run)
        self.service.observe(self.run, None)
        saved = self.service.state("display")
        self.assertEqual(saved["values"]["messages"][-1]["content"][0]["text"], "Visible answer")

    def test_complete_graph_values_supersede_finished_stream_projection(self):
        self.service.observe(self.run, event("messages", {
            "event": "content-block-finish", "index": 0,
            "content": {"type": "text", "text": "Visible answer"},
        }))
        self.service.observe(self.run, event("messages", {"event": "message-finish"}))
        final = {"id": "answer", "type": "ai", "content": "Canonical final answer"}
        self.service.observe(self.run, event("values", {"messages": [final]}))
        state = self.service.state("display")
        self.assertEqual(state["values"]["messages"], [final])

    def test_prepared_reconnect_page_keeps_seed_after_completion_compacts_tokens(self):
        resume = self.service.resume_view("display", self.cursor)
        self.service.observe(self.run, event("messages", {
            "event": "content-block-delta", "index": 0,
            "delta": {"type": "text-delta", "text": " continues"},
        }))
        wires, cursor, gap = self.service.stream_page(
            "display", self.cursor, {"channels": ["messages", "values"]}, resume)
        self.complete()
        self.assertFalse(gap)
        self.assertGreater(cursor, self.cursor)
        self.assertEqual([wire["params"]["data"]["event"] for wire in wires],
                         ["message-start", "content-block-start", "content-block-delta"])
        self.assertEqual(wires[1]["params"]["data"]["content"]["text"], "Visible answer")
        self.assertEqual(wires[2]["params"]["data"]["delta"]["text"], " continues")


if __name__ == "__main__":
    unittest.main()
