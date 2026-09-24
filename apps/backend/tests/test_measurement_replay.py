"""Transient measurement snapshots stay bounded without losing replay events."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, GenerationObservation
from workbench_backend.errors import InteractionPersistenceError
from workbench_backend.interaction.projection import event, partial_archive
from workbench_backend.interaction.resume import ResumeProjection
from workbench_backend.interaction.service import InteractionService
from workbench_backend.knowledge.schemas import ContextCaptureSettings
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

    def test_full_values_keep_only_the_latest_snapshot_and_replay_native_events(self):
        before = self.store.get_interaction("display")["seq"]
        first = 0
        retained_tool = 0
        for index in range(24):
            self.service.observe(self.run, event("values", {"messages": [{
                "type": "ai", "id": f"answer-{index}", "content": "output " * 512,
            }]}))
            if index == 0:
                first = self.store.get_interaction("display")["seq"]
            if index == 12:
                self.service.observe(self.run, event("tools", {
                    "event": "tool-finished", "tool_call_id": "retained-tool", "output": "retained result",
                }))
                retained_tool = self.store.get_interaction("display")["seq"]
        page, latest, gap = self.store.interaction_page("display", before)
        self.assertFalse(gap)
        self.assertEqual(latest, self.store.get_interaction("display")["seq"])
        self.assertEqual([item["seq"] for item in page if item["method"] == "tools"], [retained_tool])
        self.assertNotIn(first, [item["seq"] for item in page])
        values = [item for item in page if item["method"] == "values" and not item["params"].get("measurement")]
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]["params"]["data"]["messages"][-1]["id"], "answer-23")
        self.assertEqual(len(self.store.get_interaction("display")["snapshot"]["messages"]), 40)
        retained = self.store._conn.execute(
            "SELECT COUNT(*) AS n,SUM(LENGTH(payload)) AS bytes FROM interaction_events WHERE thread_id='display'"
        ).fetchone()
        self.assertLess(retained["bytes"], 200_000)

    def test_older_full_values_are_compacted_on_first_new_snapshot(self):
        for index in range(3):
            self.service.observe(self.run, event("values", {"messages": [{
                "type": "ai", "id": f"old-{index}", "content": "retained",
            }]}))
        with self.store._lock:
            self.store._conn.execute("UPDATE interaction_threads SET full_values_seq=0 WHERE id='display'")
            self.store._conn.commit()
        self.service.observe(self.run, event("values", {"messages": [{
            "type": "ai", "id": "new", "content": "latest",
        }]}))
        page, _latest, gap = self.store.interaction_page("display", 0)
        self.assertFalse(gap)
        self.assertEqual(len([item for item in page if item["method"] == "values"]), 1)
        self.assertEqual(page[-1]["params"]["data"]["messages"][-1]["id"], "new")

    def test_full_values_compaction_does_not_hide_a_missing_native_event(self):
        cursor = self.store.get_interaction("display")["seq"]
        self.service.observe(self.run, event("values", {"messages": []}))
        self.service.observe(self.run, event("messages", {"event": "message-start", "id": "missing"}))
        missing = self.store.get_interaction("display")["seq"]
        with self.store._lock:
            self.store._conn.execute("DELETE FROM interaction_events WHERE thread_id=? AND seq=?", ("display", missing))
            self.store._conn.commit()
        self.service.observe(self.run, event("values", {"messages": []}))
        self.assertTrue(self.store.interaction_page("display", cursor)[2])

    def test_transient_full_measurements_do_not_replace_the_authoritative_snapshot(self):
        binding = self.store.get_interaction("display")
        full_seq = binding["full_values_seq"]
        for _ in range(2):
            self.store.append_interaction("display", [event("values", binding["snapshot"])],
                                          snapshot=binding["snapshot"], replaceable_measurement=True)
        page, _latest, gap = self.store.interaction_page("display", 0)
        self.assertFalse(gap)
        self.assertIn(full_seq, [item["seq"] for item in page])
        self.assertEqual(self.store.get_interaction("display")["full_values_seq"], full_seq)

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

    def test_full_values_replacement_rolls_back_with_snapshot(self):
        self.service.observe(self.run, event("values", {"messages": [{
            "type": "ai", "id": "kept", "content": "before",
        }]}))
        before = self.store.get_interaction("display")
        events = self.store.interaction_events_after("display", 0)
        self.store._conn.execute("CREATE TRIGGER fail_full_snapshot BEFORE UPDATE ON interaction_threads BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        self.store._conn.commit()
        with self.assertRaises(InteractionPersistenceError) as failure:
            self.service.observe(self.run, event("values", {"messages": [{
                "type": "ai", "id": "new", "content": "after",
            }]}))
        self.assertIsInstance(failure.exception.__cause__, sqlite3.IntegrityError)
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
                ALTER TABLE interaction_threads DROP COLUMN full_values_seq;
                DELETE FROM interaction_events WHERE seq=1;
            """)
        self.store = ApplicationStore(self.paths)
        page, _latest, gap = self.store.interaction_page("display", 0)
        self.assertTrue(gap)
        self.assertEqual(self.store.get_interaction("display")["full_values_seq"], 0)
        self.assertNotIn("after_seq", json.dumps(page))
        self.assertNotIn("replaceable_measurement", json.dumps(page))

    def test_speed_sample_does_not_rewrite_messages(self) -> None:
        self.service.observe(self.run, event("messages", {"event": "message-start", "id": "reply"}))
        self.service.observe(self.run, event("messages", {"event": "content-block-delta", "index": 0,
            "delta": {"type": "text-delta", "text": "Hello"}}))
        before = self.store.get_interaction("display")["snapshot"]["messages"]
        self.measure(4)
        after = self.store.get_interaction("display")
        self.assertEqual(after["snapshot"]["messages"], before)
        latest = self.store.interaction_events_after("display", after["seq"] - 1)[0]
        self.assertTrue(latest["params"].get("measurement"))
        self.assertNotIn("messages", latest["params"]["data"])
        self.assertEqual(latest["params"]["data"]["workbench"]["run"]["generation_observation"]["output_tokens"], 4)
        self.assertEqual(ResumeProjection(self.service, "display", 1).present(latest), [latest])

    def test_token_commits_batch_until_a_read(self) -> None:
        calls = []
        original = self.store.append_interaction

        def wrapped(*args, **kwargs):
            calls.append(len(args[1]) if len(args) > 1 else 0)
            return original(*args, **kwargs)

        self.store.append_interaction = wrapped
        for _index in range(40):
            self.service.observe(self.run, event("messages", {"event": "content-block-delta", "index": 0,
                "delta": {"type": "text-delta", "text": "x"}}))
        self.assertLess(len(calls), 40)
        stored = [item for item in self.store.interaction_events_after("display", 0) if item["method"] == "messages"]
        self.assertEqual(len(stored), 40)
        self.assertEqual("".join(item["params"]["data"]["delta"]["text"] for item in stored), "x" * 40)

    def _buffer_partial_answer_and_tool(self) -> list[dict]:
        native = [
            event("messages", {"event": "message-start", "id": "answer", "role": "ai"}),
            event("messages", {"event": "content-block-start", "index": 0,
                               "content": {"type": "text", "text": ""}}),
            event("messages", {"event": "content-block-delta", "index": 0,
                               "delta": {"type": "text-delta", "text": "kept answer"}}),
            event("tools", {"event": "tool-started", "tool_call_id": "call", "tool_name": "search"}),
            event("tools", {"event": "tool-finished", "tool_call_id": "call", "output": "kept result"}),
        ]
        # A fixed clock keeps these below the age-triggered flush threshold.
        with patch("workbench_backend.interaction.service.time.monotonic", return_value=10.0):
            for raw in native:
                self.service.observe(self.run, raw)
        self.assertEqual(len(self.service._pending["display"]), len(native))
        return native

    def _fail_next_interaction_insert(self) -> None:
        self.store._conn.execute("""CREATE TRIGGER fail_buffered_native BEFORE INSERT ON interaction_events
            BEGIN SELECT RAISE(ABORT, 'injected native write failure'); END""")
        self.store._conn.commit()

    def test_subscriber_flush_retries_buffered_answer_and_tool_after_write_failure(self) -> None:
        before = self.store.interaction_for_graph("graph")["seq"]
        native = self._buffer_partial_answer_and_tool()
        self._fail_next_interaction_insert()
        subscriber = ResumeProjection(self.service, "display", before)
        options = {"channels": ["messages", "tools"]}
        try:
            with self.assertRaises(InteractionPersistenceError) as failure:
                self.service.stream_poll("display", before, options, subscriber)
            self.assertIsInstance(failure.exception.__cause__, sqlite3.IntegrityError)
            self.assertEqual(self.store.interaction_for_graph("graph")["seq"], before)
            self.assertEqual(len(self.service._pending["display"]), len(native))
        finally:
            self.store._conn.execute("DROP TRIGGER fail_buffered_native")
            self.store._conn.commit()

        wires, cursor, gap, status = self.service.stream_poll("display", before, options, subscriber)
        self.assertFalse(gap)
        self.assertEqual(status, "running")
        self.assertEqual(cursor, before + len(native))
        self.assertEqual([item["method"] for item in wires], [item["method"] for item in native])
        saved = self.store.interaction_page("display", before)[0]
        self.assertEqual([item["params"]["data"] for item in saved if item["method"] == "tools"],
                         [item["params"]["data"] for item in native if item["method"] == "tools"])
        partials, incomplete = partial_archive(saved)
        self.assertEqual(partials[0]["content"], [{"type": "text", "text": "kept answer"}])
        self.assertEqual(incomplete, ["answer"])
        self.assertEqual(self.store.interaction_page("display", cursor)[0], [])

    def test_suppressed_telemetry_flush_failure_keeps_native_batch_for_retry(self) -> None:
        before = self.store.interaction_for_graph("graph")["seq"]
        native = self._buffer_partial_answer_and_tool()
        self._fail_next_interaction_insert()
        try:
            # The measurement publisher may suppress this exception. The
            # interaction service must still retain the essential native batch.
            with self.assertRaises(InteractionPersistenceError):
                self.measure(1)
            self.assertEqual(self.store.interaction_for_graph("graph")["seq"], before)
            self.assertEqual(len(self.service._pending["display"]), len(native))
        finally:
            self.store._conn.execute("DROP TRIGGER fail_buffered_native")
            self.store._conn.commit()

        self.measure(2)
        page = self.store.interaction_page("display", before)[0]
        retained = [item for item in page if item["method"] in {"messages", "tools"}]
        self.assertEqual([item["method"] for item in retained], [item["method"] for item in native])
        self.assertEqual(len([item for item in retained if item["method"] == "tools"]), 2)
        self.assertEqual(partial_archive(retained)[0][0]["content"],
                         [{"type": "text", "text": "kept answer"}])
        self.assertNotIn("display", self.service._pending)

    def test_native_token_batch_decodes_binding_once(self) -> None:
        with patch.object(self.store, "interaction_for_graph", side_effect=AssertionError("full binding read")), \
                patch.object(self.service, "binding", wraps=self.service.binding) as binding:
            for _ in range(32):
                self.service.observe(self.run, event("messages", {"event": "content-block-delta", "index": 0,
                    "delta": {"type": "text-delta", "text": "x"}}))
        self.assertEqual(binding.call_count, 1)

    def test_poll_and_append_use_scalar_metadata_without_decoding_snapshot(self) -> None:
        before = self.store.get_interaction("display")
        snapshot = {**before["snapshot"], "workbench": {
            **before["snapshot"]["workbench"], "display_cutover_seq": before["seq"] + 1,
        }}
        self.store.append_interaction("display", [event("lifecycle", {"event": "running"})], snapshot=snapshot)
        with patch.object(self.store, "get_interaction", side_effect=AssertionError("snapshot read")):
            latest, cutover, status, durable = self.store.interaction_stream_metadata("display")
            page, high_water, gap = self.store.interaction_page("display", before["seq"])
            appended = self.store.append_interaction("display", [event("tools", {"event": "tool-started", "tool_call_id": "a"})])
        self.assertEqual((latest, cutover, status), (before["seq"] + 1, before["seq"] + 1, "running"))
        self.assertIsNone(durable)
        self.assertEqual((len(page), high_water, gap), (1, latest, False))
        self.assertEqual(appended, latest + 1)

    def test_delayed_telemetry_cannot_erase_saving_or_terminal_state(self) -> None:
        delayed = self.run.model_copy(deep=True)
        delayed.generation_observation = GenerationObservation(
            request_id="old", phase="generating", input_tokens=10, output_tokens=5,
            context_used_tokens=15, elapsed_seconds=0.1, tokens_per_second=50,
            measured_at=delayed.updated_at, basis="llama_cpp_timings",
            interval="current_model_call_generation",
        )
        self.run.finalization_phase = "saving_changes"
        self.service.observe(self.run, None)
        saving = self.store.get_interaction("display")
        self.service.observe(delayed, None, telemetry=True)
        self.assertEqual(self.store.get_interaction("display"), saving)
        self.run.finalization_phase = None
        self.run.status = AgentRunStatus.completed
        self.store.put_run(self.run)
        self.service.observe(self.run, None)
        finished = self.store.get_interaction("display")
        self.service.observe(delayed, None, telemetry=True)
        self.assertEqual(self.store.get_interaction("display"), finished)

    def test_completed_delta_compaction_retains_ordered_tool_and_nested_history(self) -> None:
        before = self.store.get_interaction("display")["seq"]
        nested = ["worker:one"]
        events = [
            event("messages", {"event": "message-start", "id": "root", "role": "ai"}),
            event("messages", {"event": "content-block-start", "index": 0,
                               "content": {"type": "text", "text": ""}}),
            event("messages", {"event": "content-block-delta", "index": 0,
                               "delta": {"type": "text-delta", "text": "Hel"}}),
            event("tools", {"event": "tool-started", "tool_call_id": "call", "tool_name": "worker"}),
            event("lifecycle", {"event": "running", "graph_name": "worker"}, nested),
            event("messages", {"event": "message-start", "id": "child", "role": "ai"}, nested),
            event("messages", {"event": "content-block-delta", "index": 0,
                               "delta": {"type": "text-delta", "text": "ch"}}, nested),
            event("messages", {"event": "content-block-delta", "index": 0,
                               "delta": {"type": "text-delta", "text": "ild"}}, nested),
            event("messages", {"event": "message-finish"}, nested),
            event("lifecycle", {"event": "completed", "graph_name": "worker"}, nested),
            event("messages", {"event": "content-block-delta", "index": 0,
                               "delta": {"type": "text-delta", "text": "lo"}}),
            event("messages", {"event": "message-finish"}),
            event("tools", {"event": "tool-finished", "tool_call_id": "call", "output": "done"}),
            event("lifecycle", {"event": "completed"}),
        ]
        self.store.append_interaction("display", events)
        self.assertEqual(self.store.discard_finished_token_log("display"), 0)
        self.run.status = AgentRunStatus.completed
        self.store.put_run(self.run)
        snapshot = self.store.get_interaction("display")["snapshot"]
        snapshot["workbench"]["run"] = self.run.model_dump(mode="json")
        self.store.append_interaction("display", [], snapshot=snapshot, run_id=self.run.id)
        self.assertEqual(self.store.discard_finished_token_log("display"), 2)
        page, _latest, gap = self.store.interaction_page("display", before)
        self.assertFalse(gap)
        self.assertEqual([item["params"]["data"]["event"] for item in page if item["method"] == "tools"],
                         ["tool-started", "tool-finished"])
        self.assertEqual([item["params"]["data"]["event"] for item in page if item["method"] == "lifecycle"],
                         ["running", "completed", "completed"])
        compacted = [item for item in page if item["method"] == "messages" and
                     item["params"]["data"]["event"] == "content-block-finish"]
        self.assertEqual([(item["params"]["namespace"], item["params"]["data"]["content"]["text"])
                          for item in compacted], [(["worker:one"], "child"), ([], "Hello")])
        self.assertTrue(all(item["event_id"].startswith("compact:display:") for item in compacted))
        self.assertIn("Hello", str(partial_archive(page)[0]))
        self.assertEqual(self.store.discard_finished_token_log("display"), 0)
        self.assertEqual(self.store.interaction_page("display", before)[0], page)
        # A different missing event remains detectable after deliberate gaps
        # from compacted deltas have been bridged.
        tool_seq = next(item["seq"] for item in page if item["method"] == "tools")
        self.store._conn.execute("DELETE FROM interaction_events WHERE thread_id=? AND seq=?", ("display", tool_seq))
        self.store._conn.commit()
        self.assertTrue(self.store.interaction_page("display", before)[2])

    def test_legacy_deleted_history_is_labelled_on_hydration(self) -> None:
        self.store.register_interaction("legacy", "agent", "old-graph", None, {
            "messages": [{"type": "human", "id": "old-input", "content": "Saved text"}],
            "workbench": {"run": None},
        })
        self.store.append_interaction("legacy", [
            event("tools", {"event": "tool-started", "tool_call_id": "old"}),
            event("tools", {"event": "tool-finished", "tool_call_id": "old"}),
            event("lifecycle", {"event": "completed"}),
        ])
        self.store.close()
        with closing(sqlite3.connect(self.paths.application_db)) as connection:
            connection.execute("ALTER TABLE interaction_threads DROP COLUMN history_unavailable")
            connection.execute("DELETE FROM interaction_events WHERE thread_id='legacy' AND seq=2")
            connection.commit()
        self.store = ApplicationStore(self.paths)
        service = InteractionService(self.store, lambda: None, lambda: None)
        hydrated = service.state("legacy")
        self.assertEqual(hydrated["values"]["messages"][0]["content"], "Saved text")
        self.assertEqual(hydrated["values"]["workbench"]["recovery"]["kind"], "history_unavailable")
        self.assertTrue(self.store.interaction_history_unavailable("legacy"))

    def test_token_events_do_not_copy_the_run_or_rewrite_the_snapshot(self):
        harness = HarnessService(lambda: None, app_store=self.store, interaction_observer=self.service.observe)
        before = self.store.get_interaction("display")
        snapshot = json.dumps(before["snapshot"], sort_keys=True)
        seq = before["seq"]
        started = time.perf_counter()
        with patch("workbench_backend.agents.harness.apply_run_diagnostic_policy") as policy, \
                patch.object(self.store, "put_run") as put_run:
            for _index in range(200):
                harness._observe_interaction(self.run, event("messages", {
                    "event": "content-block-delta", "index": 0,
                    "delta": {"type": "text-delta", "text": "x"},
                }))
            harness._observe_interaction(self.run, event("checkpoints", {"checkpoint_id": "hidden"}))
            self.run.generation_observation = GenerationObservation(
                request_id="request", phase="generating", input_tokens=100, output_tokens=200,
                context_used_tokens=300, elapsed_seconds=1, tokens_per_second=40,
                measured_at=self.run.updated_at, basis="llama_cpp_timings",
                interval="current_model_call_generation")
            with harness._lock:
                harness._persist_and_notify(self.run, telemetry=True)
        self.assertLess(time.perf_counter() - started, 5)
        policy.assert_not_called()
        put_run.assert_not_called()
        after = self.store.get_interaction("display")
        self.assertEqual(after["seq"], seq + 201)
        self.assertEqual(after["snapshot"]["workbench"]["run"]["generation_observation"]["output_tokens"], 200)
        unchanged = json.loads(snapshot)
        self.assertEqual(after["snapshot"]["messages"], unchanged["messages"])
        self.run.status = AgentRunStatus.completed
        with patch.object(harness, "_capture_settings", return_value=ContextCaptureSettings()), harness._lock:
            harness._persist_and_notify(self.run)
        final = self.store.get_interaction("display")
        self.assertEqual(final["snapshot"]["workbench"]["run"]["status"], "completed")
        methods = []
        cursor = seq
        while page := self.store.interaction_events_after("display", cursor):
            methods.extend(item["method"] for item in page)
            cursor = page[-1]["seq"]
        # These deltas have no matching message-finish. Their partial output
        # cannot be replaced by a truthful final message record.
        self.assertEqual(methods.count("messages"), 200)
        self.assertIn("lifecycle", methods)
        self.assertEqual(self.store.get_run(self.run.id).status, AgentRunStatus.completed)
        harness._startup_reconciled = True
        harness._runs[self.run.id] = self.run
        with patch("workbench_backend.agents.harness.apply_run_diagnostic_policy") as policy:
            projected = harness.projection_run(self.run.id)
        policy.assert_not_called()
        self.assertEqual(projected["model_requests"], [])
        self.assertEqual(projected["status"], "completed")
