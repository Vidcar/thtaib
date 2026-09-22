"""Transient measurement snapshots stay bounded without losing replay events."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, GenerationObservation
from workbench_backend.interaction.projection import event, partial_archive
from workbench_backend.interaction.service import InteractionService
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore


class MeasurementReplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = WorkbenchPaths(Path(self.temporary.name))
        self.store = ApplicationStore(self.paths)
        self.service = InteractionService(self.store, lambda: None, lambda: None)
        self.run = AgentRun(id="run", thread_id="graph", deployment_id="model", task="task",
            enabled_tools=[], presented_tools=[], status=AgentRunStatus.running,
            created_at="2026-09-22T12:00:00Z", updated_at="2026-09-22T12:00:00Z")
        self.store.register_interaction("display", "agent", "graph", None, {
            "messages": [{"type": "human", "id": str(i), "content": "history " * 511} for i in range(16)],
            "workbench": {"run": None},
        })
        self.service.observe(self.run, None)

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def measure(self, count, *, phase="generating"):
        self.run.generation_observation = GenerationObservation(request_id="request", phase=phase,
            input_tokens=100, output_tokens=count, context_used_tokens=100 + count,
            elapsed_seconds=count / 40, tokens_per_second=40, measured_at=self.run.updated_at,
            basis="llama_cpp_timings", interval="current_model_call_generation" if phase == "generating" else "last_model_call_generation")
        self.store.put_run(self.run)
        self.service.observe(self.run, None, telemetry=True)
        return self.store.get_interaction("display")["seq"]

    def test_retention_is_bounded_and_native_output_and_final_survive_restart(self):
        before = self.store.get_interaction("display")["seq"]
        removed_cursor = self.measure(1)
        native = [event("messages", {"event": "message-start", "id": "reply"}),
                  event("messages", {"event": "content-block-start", "index": 0, "content": {"type": "text", "text": ""}}),
                  event("messages", {"event": "content-block-delta", "index": 0, "delta": {"type": "text-delta", "text": "partial reply"}}),
                  event("tools", {"event": "tool-finished", "tool_call_id": "tool", "output": "retained result"})]
        native_records = []
        for index, raw in enumerate(native, 2):
            self.service.observe(self.run, raw)
            native_records.append(self.store.interaction_events_after("display", self.store.get_interaction("display")["seq"] - 1)[0])
            self.measure(index)
        for index in range(6, 241):
            self.measure(index)
        page, latest, gap = self.store.interaction_page("display", removed_cursor)
        self.assertFalse(gap)
        self.assertEqual([item for item in page if item["method"] in {"messages", "tools"}], native_records)
        self.assertEqual(page[-1]["seq"], latest)
        self.assertGreater(latest, 240)
        self.assertNotIn(removed_cursor, [item["seq"] for item in self.store.interaction_events_after("display", 0)])
        retained = self.store._conn.execute("SELECT COUNT(*) AS n,SUM(LENGTH(payload)) AS bytes FROM interaction_events WHERE thread_id='display'").fetchone()
        self.assertEqual(retained["n"], before + len(native) + 1)
        self.assertLess(retained["bytes"], 150_000)
        partials, incomplete = partial_archive(page)
        self.assertEqual(partials[0]["content"], [{"type": "text", "text": "partial reply"}])
        self.assertEqual(incomplete, ["reply"])

        final_request_seq = self.measure(240, phase="interrupted")
        self.run.status = AgentRunStatus.cancelled
        self.store.put_run(self.run)
        self.service.observe(self.run, None)
        final = self.store.get_interaction("display")
        self.store.close()
        self.store = ApplicationStore(self.paths)
        self.assertEqual(self.store.get_interaction("display"), final)
        self.assertEqual(self.store.get_run("run").generation_observation.phase, "interrupted")
        page, _latest, gap = self.store.interaction_page("display", removed_cursor)
        self.assertFalse(gap)
        self.assertIn(final_request_seq, [item["seq"] for item in page])
        self.assertEqual(self.store._conn.execute("SELECT COUNT(*) FROM interaction_events WHERE replaceable_measurement=1").fetchone()[0], 0)
        self.assertEqual(final["snapshot"]["messages"][-1]["content"], [{"type": "text", "text": "partial reply"}])

    def test_missing_native_event_is_not_hidden_when_measurements_are_coalesced(self):
        cursor = self.store.get_interaction("display")["seq"]
        self.measure(1)
        self.service.observe(self.run, event("messages", {"event": "message-start", "id": "missing"}))
        missing = self.store.get_interaction("display")["seq"]
        self.store._conn.execute("DELETE FROM interaction_events WHERE thread_id=? AND seq=?", ("display", missing))
        self.store._conn.commit()
        self.measure(2)
        self.assertTrue(self.store.interaction_page("display", cursor)[2])

    def test_metadata_changes_are_never_classified_as_replaceable_measurements(self):
        self.measure(1)
        self.run.tool_invocations.append({"name": "echo", "result": "important"})
        preserved = self.measure(2)
        self.measure(3)
        self.measure(4)
        self.assertIn(preserved, [item["seq"] for item in self.store.interaction_events_after("display", 0)])

    def test_snapshot_delete_and_append_roll_back_together(self):
        self.measure(1)
        before = self.store.get_interaction("display")
        events = self.store.interaction_events_after("display", 0)
        self.store._conn.execute("CREATE TRIGGER fail_snapshot BEFORE UPDATE ON interaction_threads BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        self.store._conn.commit()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "injected failure"):
            self.measure(2)
        self.assertEqual(self.store.get_interaction("display"), before)
        self.assertEqual(self.store.interaction_events_after("display", 0), events)

    def test_existing_replay_migration_preserves_real_gap_detection(self):
        self.store.close()
        with closing(sqlite3.connect(self.paths.application_db)) as connection:
            connection.executescript("""
                ALTER TABLE interaction_events RENAME TO old_events;
                CREATE TABLE interaction_events(thread_id TEXT NOT NULL,seq INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(thread_id,seq));
                INSERT INTO interaction_events(thread_id,seq,payload) SELECT thread_id,seq,payload FROM old_events;
                DROP TABLE old_events;
                DELETE FROM interaction_events WHERE seq=1;
            """)
        self.store = ApplicationStore(self.paths)
        page, _latest, gap = self.store.interaction_page("display", 0)
        self.assertTrue(gap)
        self.assertNotIn("after_seq", json.dumps(page))
        self.assertNotIn("replaceable_measurement", json.dumps(page))
