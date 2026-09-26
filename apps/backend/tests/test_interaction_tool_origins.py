"""A warm subscriber retains exact tool ownership across successive runs."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from tests.test_interaction_snapshot_races import SnapshotHarness
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.interaction.projection import event
from workbench_backend.interaction.service import InteractionService
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore


class InteractionToolOriginTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = ApplicationStore(WorkbenchPaths(Path(self.temporary.name)))
        self.run = self.make_run(1)
        self.harness = SnapshotHarness(self.run)
        self.service = InteractionService(self.store, lambda: self.harness, lambda: None)
        self.store.register_interaction("display", "agent", "graph", None, {
            "messages": [], "workbench": {"run": None},
        })
        self.start(self.run)

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def make_run(self, number):
        return AgentRun(id=f"run-{number}", thread_id="graph", deployment_id="model",
            input_message_id=f"user-{number}", task=f"task-{number}", enabled_tools=[],
            presented_tools=[], status=AgentRunStatus.running,
            created_at="2026-09-26T12:00:00Z", updated_at="2026-09-26T12:00:00Z")

    def start(self, run):
        self.run = self.harness.run = run
        self.store.put_run(run)
        self.service.observe(run, None)

    def tool(self, kind, *, namespace=None):
        self.service.observe(self.run, event("tools", {
            "event": kind, "tool_call_id": "reused-call", "tool_name": "read_file",
            **({"output": "read result"} if kind == "tool-finished" else {}),
        }, namespace))

    def finish(self, status=AgentRunStatus.completed):
        self.run.status = status
        self.store.put_run(self.run)
        self.service.observe(self.run, None)

    def test_native_origin_precedes_tool_and_is_retained_once_per_scoped_call(self):
        cursor = self.service.state("display")["interaction_cursor"]
        self.tool("tool-started")
        self.tool("tool-finished")
        self.tool("tool-started", namespace=["helper:one"])
        # Later authoritative values compact ordinary earlier snapshots; the
        # ownership observation must still precede its native call in replay.
        self.service.observe(self.run, event("values", {"messages": []}))
        self.finish()
        through = self.store.get_interaction("display")["seq"]
        wires = self.service.replay("display", cursor, through)
        origins = []
        for wire in wires:
            if wire["method"] == "values" and not wire["params"].get("namespace"):
                origins = wire["params"]["data"]["workbench"].get("tool_origins", [])
                if wire["params"].get("_tool_origin"):
                    self.assertNotIn("messages", wire["params"]["data"])
                    messages = json.loads(zlib.decompress(base64.b64decode(wire["params"]["data"]["_tool_origin_messages"])))
                    self.assertEqual([message["id"] for message in messages], ["user-1"])
            if wire["method"] == "tools":
                self.assertIn({"run_id": "run-1", "input_message_id": "user-1",
                    "namespace": wire["params"]["namespace"], "call_id": "reused-call"}, origins)
        public = self.service.state("display")["values"]["workbench"]
        self.assertEqual(public["tool_origins"], [
            {"run_id": "run-1", "input_message_id": "user-1", "namespace": [], "call_id": "reused-call"},
            {"run_id": "run-1", "input_message_id": "user-1", "namespace": ["helper:one"], "call_id": "reused-call"},
        ])

    def test_reconnect_keeps_other_namespace_open_when_root_reuses_call_id(self):
        self.tool("tool-started")
        self.tool("tool-started", namespace=["helper:one"])
        self.tool("tool-finished")
        cursor = self.service.state("display")["interaction_cursor"]
        opening = self.service.resume_view("display", cursor).opening({"channels": ["tools"]})
        self.assertEqual([wire["params"]["namespace"] for wire in opening], [["helper:one"]])

    def test_message_tokens_do_not_rewrite_snapshot_or_republish_origins(self):
        self.tool("tool-started")
        cursor = self.service.state("display")["interaction_cursor"]
        stored = self.store.get_interaction("display")["snapshot"]
        self.service.observe(self.run, event("messages", {"event": "message-start", "role": "ai", "id": "streaming"}))
        for _index in range(64):
            self.service.observe(self.run, event("messages", {"event": "content-block-delta", "index": 0,
                "delta": {"type": "text-delta", "text": "x"}}))
        binding = self.store.get_interaction("display")
        self.assertEqual(binding["snapshot"], stored)
        wires = list(self.service.replay("display", cursor, binding["seq"]))
        self.assertEqual(len(wires), 65)
        self.assertTrue(all(wire["method"] == "messages" for wire in wires))

    def test_origin_replay_preserves_complete_message_bytes_at_its_cursor(self):
        original = {"id": "edited-complete", "type": "ai", "content": "ORIGINAL COMPLETE"}
        self.service.observe(self.run, event("values", {"messages": [original]}))
        cursor = self.service.state("display")["interaction_cursor"]
        resume = self.service.resume_view("display", cursor)
        self.tool("tool-started")
        future = {**original, "content": "FUTURE REWRITE"}
        self.service.observe(self.run, event("values", {"messages": [future]}))
        wires, _cursor, gap = self.service.stream_page("display", cursor,
            {"channels": ["values", "tools"]}, resume)
        self.assertFalse(gap)
        values = [wire["params"]["data"] for wire in wires if wire["method"] == "values"]
        self.assertEqual(values[0]["messages"][-1], original)
        self.assertEqual(values[-1]["messages"][-1], future)

    def test_one_subscriber_resets_cancelled_prefix_and_open_tools_at_next_run(self):
        self.service.observe(self.run, event("messages", {"event": "message-start", "role": "ai", "id": "partial-1"}))
        self.service.observe(self.run, event("messages", {"event": "content-block-delta", "index": 0,
            "delta": {"type": "text-delta", "text": "Stopped partial"}}))
        self.tool("tool-started")
        cursor = self.service.state("display")["interaction_cursor"]
        resume = self.service.resume_view("display", cursor)
        self.assertEqual(len(resume.opening({"channels": ["tools"]})), 1)
        self.finish(AgentRunStatus.cancelled)
        _wires, cursor, gap = self.service.stream_page("display", cursor,
            {"channels": ["values", "messages", "tools"]}, resume)
        self.assertFalse(gap)
        self.start(self.make_run(2))
        started = self.store.get_interaction("display")["snapshot"]["workbench"]["run_started_seq"]
        wires, _cursor, gap = self.service.stream_page("display", cursor,
            {"channels": ["values", "messages", "tools"]}, resume)
        self.assertFalse(gap)
        self.assertEqual(resume._run_started_seq, started)
        self.assertEqual(resume._message_prefixes, {})
        self.assertEqual(resume._open_tools, {})
        self.assertEqual(resume._partial.active, {})
        self.assertNotIn("run_started_seq", wires[-1]["params"]["data"]["workbench"])
        self.assertTrue(all("_tool_origin" not in wire["params"] for wire in wires))
        self.assertTrue(all("_tool_origin_messages" not in wire["params"].get("data", {}) for wire in wires))
        self.tool("tool-started")
        self.service.observe(self.run, event("values", {"messages": [
            {"id": "partial-1", "type": "ai", "content": "Later checkpoint reconciliation"},
            {"id": "answer-2", "type": "ai", "content": "Later second-turn output"},
        ]}))
        wires, _cursor, gap = self.service.stream_page("display", _cursor,
            {"channels": ["values", "messages", "tools"]}, resume)
        self.assertFalse(gap)
        values = [wire["params"]["data"] for wire in wires if wire["method"] == "values"]
        earlier = {message["id"]: message for message in values[0]["messages"]}
        self.assertEqual(earlier["partial-1"]["content"], [{"type": "text", "text": "Stopped partial"}])
        self.assertNotIn("answer-2", earlier)
        self.assertEqual(values[-1]["messages"][-1]["content"], "Later second-turn output")
        self.assertTrue(all("_tool_origin_messages" not in value for value in values))

    def test_persistent_subscriber_three_runs_reused_calls_and_compacted_reconnect(self):
        cursor = self.service.state("display")["interaction_cursor"]
        resume = self.service.resume_view("display", cursor)
        expected = []
        options = {"channels": ["values", "messages", "tools", "lifecycle"]}
        for number in range(1, 4):
            if number > 1:
                self.start(self.make_run(number))
            self.tool("tool-started")
            self.tool("tool-finished")
            answer = {"id": f"answer-{number}", "type": "ai", "content": f"answer {number}"}
            self.service.observe(self.run, event("messages", {"event": "message-start", "role": "ai", "id": answer["id"]}))
            self.service.observe(self.run, event("messages", {"event": "content-block-delta", "index": 0,
                "delta": {"type": "text-delta", "text": answer["content"]}}))
            self.service.observe(self.run, event("messages", {"event": "message-finish"}))
            call_message = {"id": f"call-message-{number}", "type": "ai", "content": "Checking the file",
                "tool_calls": [{"id": "reused-call", "name": "read_file", "args": {"path": "example.txt"}}]}
            result_message = {"id": f"result-{number}", "type": "tool", "content": "read result",
                "tool_call_id": "reused-call"}
            self.service.observe(self.run, event("values", {"messages": [call_message, result_message, answer]}))
            self.finish()
            wires, cursor, gap = self.service.stream_page("display", cursor, options, resume)
            self.assertFalse(gap)
            expected.extend([f"user-{number}", f"call-message-{number}", f"result-{number}", f"answer-{number}"])
            values = [wire["params"]["data"] for wire in wires if wire["method"] == "values"][-1]
            self.assertEqual([message["id"] for message in values["messages"]], expected)
            self.assertEqual([origin["run_id"] for origin in values["workbench"].get("tool_origins", [])],
                [f"run-{index}" for index in range(1, number + 1)])
            self.assertEqual(self.service.state("display")["values"], values)
        reopened = self.service.resume_view("display", 0)
        wires, _cursor, gap = self.service.stream_page("display", 0, options, reopened)
        self.assertFalse(gap)
        self.assertEqual([origin["run_id"] for origin in
            [wire for wire in wires if wire["method"] == "values"][-1]["params"]["data"]["workbench"]["tool_origins"]],
            ["run-1", "run-2", "run-3"])


if __name__ == "__main__":
    unittest.main()
