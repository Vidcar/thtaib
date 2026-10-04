"""Native context reduction cannot rewrite already-published display evidence."""
from __future__ import annotations

import copy
import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tests import test_interaction as interaction_fixture
from tests.test_interaction_snapshot_races import SnapshotHarness
from tests.scripted_model import ScriptedChatModel
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.interaction.projection import archive_messages, event, message_dict
from workbench_backend.interaction.service import InteractionService
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.inference.telemetry import current_request_purpose
from workbench_backend.state.checkpointer import conversation_state
from workbench_backend.state.store import ApplicationStore


class NativeCompactionHistoryTests(unittest.TestCase):
    setUp = interaction_fixture.InteractionApiTests.setUp
    tearDown = interaction_fixture.InteractionApiTests.tearDown
    _install_model = interaction_fixture.InteractionApiTests._install_model
    _register_agent = interaction_fixture.InteractionApiTests._register_agent
    _register_chat = interaction_fixture.InteractionApiTests._register_chat
    _run_start = interaction_fixture.InteractionApiTests._run_start
    _wait_state = interaction_fixture.InteractionApiTests._wait_state
    _set_server_props = interaction_fixture.InteractionApiTests._set_server_props

    def test_repeated_native_compaction_keeps_identical_text_in_distinct_ordered_turns(self):
        self._set_server_props(n_ctx=8192)
        summaries = []
        class PurposeModel(ScriptedChatModel):
            def _generate(self, messages, *args, **kwargs):
                if current_request_purpose() == "summary":
                    summaries.append(list(messages))
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(content="INTERNAL-SUMMARY-ONLY"))])
                return super()._generate(messages, *args, **kwargs)
        model = PurposeModel([AIMessage(content="Same complete answer") for _ in range(4)])
        self.app.state.harness._model_factory = lambda _run, _sink: model
        thread = self._register_agent()
        previous = []
        cutoffs = []
        for index in range(4):
            response = self._run_start(thread, command_id=f"repeat-{index}", message_id=f"repeat-input-{index}",
                content="retained historic detail " * 650)
            self.assertEqual(response.status_code, 200, response.text)
            state = self._wait_state(thread)
            messages = state["values"]["messages"]
            self.assertEqual(messages[:len(previous)], previous)
            self.assertEqual(len(messages), len(previous) + 2)
            self.assertEqual(messages[-2]["id"], f"repeat-input-{index}")
            self.assertEqual(messages[-1]["content"], "Same complete answer")
            self.assertNotIn("INTERNAL-SUMMARY-ONLY", str(messages))
            self.assertEqual(len(messages), len({item["id"] for item in messages}))
            native = conversation_state(self.manager.paths.checkpoints_db, state["values"]["workbench"]["run"]["thread_id"])
            if event := native.get("_summarization_event"):
                cutoffs.append(event["cutoff_index"])
            previous = copy.deepcopy(messages)
        self.assertGreaterEqual(len(summaries), 2, "The fixture must actually compact more than once.")
        self.assertGreater(cutoffs[-1], cutoffs[0])
        self.assertEqual(model._index, 4)

    def test_native_read_clipping_keeps_complete_agent_history_across_reconnect_and_reopen(self):
        self._check_native_read_clipping("agent")

    def test_native_read_clipping_keeps_complete_chat_history_across_reconnect_and_reopen(self):
        self._check_native_read_clipping("chat")

    def test_native_clipped_history_assertion_rejects_legacy_overwrite(self):
        def overwrite_published_result(existing, values):
            incoming = archive_messages([], values)
            result = copy.deepcopy(existing)
            positions = {message["id"]: index for index, message in enumerate(result)}
            for message in incoming:
                if message["id"] in positions:
                    result[positions[message["id"]]] = message
                else:
                    positions[message["id"]] = len(result)
                    result.append(message)
            return result
        with patch("workbench_backend.interaction.service.archive_messages", side_effect=overwrite_published_result):
            with self.assertRaisesRegex(AssertionError, "Published tool result changed during native reduction"):
                self._check_native_read_clipping("agent")

    def test_cancel_during_stock_summary_keeps_published_result_without_repeating_effect(self):
        self._check_interrupted_summary("cancelled")

    def test_failed_stock_summary_keeps_published_result_without_repeating_effect(self):
        self._check_interrupted_summary("failed")

    def _check_interrupted_summary(self, status):
        before = self._check_native_read_clipping("agent")
        previous_messages = before["values"]["messages"]
        thread = self.app.state.app_store.interaction_id_for_graph(before["values"]["workbench"]["run"]["thread_id"])
        entered, settled = threading.Event(), threading.Event()
        purposes = []
        class InterruptedSummaryModel(ScriptedChatModel):
            async def _agenerate(self, messages, *args, **kwargs):
                purpose = current_request_purpose()
                purposes.append(purpose)
                if purpose != "summary":
                    raise AssertionError("Interrupted compaction must not invoke work or an old tool")
                entered.set()
                try:
                    if status == "failed":
                        raise RuntimeError("Stock summary fixture failed")
                    await asyncio.Event().wait()
                finally:
                    settled.set()
        model = InterruptedSummaryModel([])
        self.app.state.harness._model_factory = lambda _run, _sink: model
        response = self._run_start(thread, command_id="interrupted-summary", message_id="interrupted-input",
            content="important later detail " * 2200)
        self.assertEqual(response.status_code, 200, response.text)
        run_id = response.json()["result"]["run_id"]
        harness = self.app.state.harness
        try:
            self.assertTrue(entered.wait(5), "The stock summarizer must actually enter its model request.")
            with harness._lock:
                worker = harness._threads[run_id]
            if status == "cancelled":
                cancelled = self.client.post(f"/v1/agent-runs/{run_id}/cancel")
                self.assertEqual(cancelled.status_code, 200, cancelled.text)
            after = self._wait_state(thread, status=status)
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive(), "Terminal publication must settle the owning worker.")
            self.assertTrue(settled.is_set())
            run = after["values"]["workbench"]["run"]
            self.assertEqual(run["status"], status)
            if status == "failed":
                self.assertIn("Stock summary fixture failed", run["error"])
            self.assertEqual(run["dispatched_tool_calls"], 0)
            self.assertEqual(run["tool_invocations"], [])
            self.assertTrue(purposes and all(purpose == "summary" for purpose in purposes))
            self.assertEqual(after["values"]["messages"][:len(previous_messages)], previous_messages)
            self.assertEqual([message["id"] for message in after["values"]["messages"][len(previous_messages):]],
                ["interrupted-input"])
            self.assertEqual(harness.get_run(before["values"]["workbench"]["run"]["id"]).dispatched_tool_calls, 1)
            reopened = InteractionService(self.app.state.app_store, lambda: harness, lambda: self.app.state.chat)
            self.assertEqual(reopened.state(thread)["values"]["messages"], after["values"]["messages"])
        finally:
            harness.cancel(run_id)

    def _check_native_read_clipping(self, surface):
        self.maxDiff = 1500
        self._set_server_props(n_ctx=8192)
        original_file = "\n".join(f"{index:04d} original retained line café Ω" for index in range(1500)) + "\nHISTORY-END-93"
        source = self.project / "original.txt"
        source.write_text(original_file, encoding="utf-8")
        model = self._install_model([
            AIMessage(content="", tool_calls=[{"id": "read-source", "name": "read_file",
                "args": {"file_path": "/original.txt", "limit": 2000}}]),
            AIMessage(content="internal summary must remain hidden"),
            AIMessage(content="Finished reading the complete original"),
        ])
        thread = self._register_agent() if surface == "agent" else self._register_chat()[1]
        service = self.app.state.interaction
        original_projection = service._project_native
        published = []

        def capture_complete_result(binding, run, raw):
            outgoing, snapshot = original_projection(binding, run, raw)
            if snapshot is not None and not published:
                result = next((message for message in snapshot.get("messages", [])
                    if message.get("type") == "tool" and "HISTORY-END-93" in str(message.get("content"))), None)
                if result is not None:
                    published.append((copy.deepcopy(snapshot["messages"]), binding["seq"]))
            return outgoing, snapshot

        with patch.object(service, "_project_native", side_effect=capture_complete_result):
            response = self._run_start(thread, content="Read the original file and report completion.",
                metadata={"presented_tools": ["read_file"], "approval_mode": "full_access"})
            self.assertEqual(response.status_code, 200, response.text)
            state = self._wait_state(thread)
        run = state["values"]["workbench"]["run"]
        self.assertEqual(run["status"], "completed", run.get("error"))
        self.assertEqual(len(published), 1, "The native tool result must be published before context reduction.")
        original_messages, before_reduction = published[0]
        archive = state["values"]["messages"]
        complete_result = next(message for message in original_messages if message["type"] == "tool")
        native = conversation_state(self.manager.paths.checkpoints_db, run["thread_id"])
        self.assertGreater(native["_summarization_event"]["cutoff_index"], 0)
        shortened = next(message for message in native["messages"]
            if isinstance(message, ToolMessage) and message.id == complete_result["id"])
        self.assertNotIn("HISTORY-END-93", shortened.content)
        self.assertLess(len(shortened.content), len(complete_result["content"]))
        self.assertEqual(archive[:len(original_messages)], original_messages,
            "Published tool result changed during native reduction")
        self.assertNotIn("internal summary must remain hidden", str(archive))
        self.assertTrue(any(item["kind"] == "context_compacted" for item in run["events"]))
        self.assertEqual(run["dispatched_tool_calls"], 1)
        self.assertEqual(len(archive), len({message["id"] for message in archive}))
        self.assertEqual(source.read_text(encoding="utf-8"), original_file)

        options = {"channels": ["values", "messages", "tools"], "namespaces": [[]], "depth": 1}
        resume = service.resume_view(thread, before_reduction)
        wires, cursor, gap = service.stream_page(thread, before_reduction, options, resume)
        self.assertFalse(gap)
        final_values = [wire["params"]["data"] for wire in wires
            if wire["method"] == "values" and not wire["params"].get("measurement")]
        self.assertEqual(final_values[-1]["messages"], archive)
        self.assertEqual(cursor, state["interaction_cursor"])

        # Rebuild both the connection and observation owner from durable data.
        reopened_store = ApplicationStore(self.app.state.app_store.paths)
        try:
            operational = AgentRun.model_validate(run)
            reopened_harness = SnapshotHarness(operational)
            reopened = InteractionService(reopened_store, lambda: reopened_harness, lambda: self.app.state.chat)
            self.assertEqual(reopened.state(thread)["values"]["messages"], archive)
            self.assertEqual(reopened.state(thread)["interaction_cursor"], state["interaction_cursor"])
        finally:
            reopened_store.close()
        self.assertEqual(model._index, 3, "Hydration must not execute another model request.")
        return state


class CompactionTerminalHistoryTests(unittest.TestCase):
    def test_repeated_shortening_and_terminal_states_keep_exact_history_and_cursor(self):
        for status in (AgentRunStatus.completed, AgentRunStatus.cancelled, AgentRunStatus.failed):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                paths = WorkbenchPaths(Path(temporary))
                store = ApplicationStore(paths)
                try:
                    run = AgentRun(id="run", thread_id="graph", deployment_id="model", task="task",
                        enabled_tools=[], presented_tools=[], status=AgentRunStatus.running,
                        created_at="2026-10-04T12:00:00Z", updated_at="2026-10-04T12:00:00Z")
                    harness = SnapshotHarness(run)
                    service = InteractionService(store, lambda: harness, lambda: None)
                    store.register_interaction("display", "agent", "graph", None,
                        {"messages": [], "workbench": {"run": None}})
                    store.put_run(run)
                    service.observe(run, None)
                    original = [message_dict(AIMessage(id="answer", content="Repeated answer")),
                        message_dict(ToolMessage(id="result", tool_call_id="same-call", name="read_file",
                            status="success", content="Full original café Ω\n" * 1000)),
                        message_dict(AIMessage(id="second-answer", content="Repeated answer"))]
                    service.observe(run, event("values", {"messages": original}))
                    cursor = service.state("display")["interaction_cursor"]
                    # Identical text and repeated call IDs never define message identity.
                    sibling = {**original[1], "id": "sibling-result", "content": "Independent sibling result"}
                    service.observe(run, event("values", {"messages": [{**original[1], "content": "stub-1"}, sibling]}))
                    service.observe(run, event("values", {"messages": [{**original[1], "content": "stub-2"}]}))
                    expected = [*original, sibling]
                    run.status = status
                    if status == AgentRunStatus.failed:
                        run.error = "Model stopped after context reduction"
                    store.put_run(run)
                    service.observe(run, None)
                    state = service.state("display")
                    self.assertEqual(state["values"]["messages"], expected)
                    self.assertEqual(state["values"]["workbench"]["run"]["status"], status.value)
                    wires, high_water, gap = service.stream_page("display", cursor,
                        {"channels": ["values"]}, service.resume_view("display", cursor))
                    self.assertFalse(gap)
                    self.assertEqual(high_water, state["interaction_cursor"])
                    self.assertEqual(wires[-1]["params"]["data"]["messages"], expected)
                finally:
                    store.close()
                reopened_store = ApplicationStore(paths)
                try:
                    reopened = InteractionService(reopened_store, lambda: harness, lambda: None)
                    self.assertEqual(reopened.state("display")["values"]["messages"], expected)
                    self.assertEqual(reopened.state("display")["interaction_cursor"], high_water)
                finally:
                    reopened_store.close()


if __name__ == "__main__":
    unittest.main()
