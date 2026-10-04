"""Interaction display projection keeps native reasoning and message identity."""

from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from deepagents.backends import StateBackend
from deepagents.middleware._overflow_clip import _clip_overflow_tail
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, GenerationObservation
from workbench_backend.interaction.service import InteractionService
from workbench_backend.interaction.projection import archive_messages, message_dict, message_resume_seed, native_event, open_tool_starts


class InteractionProjectionTests(unittest.TestCase):
    def test_native_clipped_result_cannot_replace_completed_archive_content(self) -> None:
        call = AIMessage(id="read-call", content="", tool_calls=[{
            "id": "read", "name": "read_file", "args": {"file_path": "/original.txt"},
        }])
        result = ToolMessage(id="read-result", tool_call_id="read", name="read_file",
            status="success", content="ORIGINAL-BEGIN\n" + "original line\n" * 1500 + "ORIGINAL-END")
        original = archive_messages([], [call, result])
        clipped, replacements = _clip_overflow_tail([call, result], StateBackend(),
            keep=("tokens", 1), max_input_tokens=8192,
            token_counter=lambda messages: sum(len(str(message.content)) // 4 for message in messages),
            large_tool_results_prefix="/large_tool_results")
        self.assertEqual(len(replacements), 1)
        self.assertEqual(replacements[0].id, result.id)
        self.assertNotIn("ORIGINAL-END", replacements[0].content,
            "The fixture must actually exercise native shortening, not an unchanged message.")
        self.assertEqual(archive_messages(original, clipped), original)
        # Native checkpoint replacement is still different from the display row.
        self.assertNotEqual(message_dict(replacements[0]), original[-1])

    def test_archive_identity_keeps_distinct_results_but_allows_answer_and_user_updates(self) -> None:
        first = ToolMessage(id="root-result", tool_call_id="local-call", name="read_file",
            content=[{"type": "text", "text": "same text"}, {"type": "image", "url": "retained.png"}])
        sibling = first.model_copy(update={"id": "helper-result"})
        later = first.model_copy(update={"id": "later-run-result"})
        original = archive_messages([], [HumanMessage(id="user", content="Original"),
            AIMessage(id="answer", content="Partial"), first, sibling])
        shortened = first.model_copy(update={"content": "shortened", "status": "error", "name": "changed"})
        updated = archive_messages(original, [HumanMessage(id="user", content="Edited"),
            AIMessage(id="answer", content="Completed", additional_kwargs={"reasoning_content": "Thought"}),
            shortened, sibling.model_copy(update={"content": "also shortened"}), later])
        self.assertEqual([message["id"] for message in updated],
            ["user", "answer", "root-result", "helper-result", "later-run-result"])
        self.assertEqual(updated[0]["content"], "Edited")
        self.assertEqual(updated[1]["content"], [
            {"type": "reasoning", "reasoning": "Thought"}, {"type": "text", "text": "Completed"}])
        self.assertEqual(updated[2:4], original[2:4])
        self.assertEqual(updated[4], message_dict(later))

    def test_measurement_projection_retains_history_without_rebuilding_it_for_each_sample(self):
        service = object.__new__(InteractionService)
        service.store = SimpleNamespace(append_interaction=Mock())
        at = "2026-09-27T12:00:00Z"
        run = AgentRun(id="run-measurement", deployment_id="deployment", task="Check",
            enabled_tools=[], presented_tools=[], status=AgentRunStatus.running,
            created_at=at, updated_at=at)
        run.generation_history = [GenerationObservation(request_id="old", purpose="work", phase="completed",
            elapsed_seconds=1, prefill_seconds=42.2, cached_input_tokens=713, processed_input_tokens=5370,
            measured_at=at, basis="llama_cpp_timings")]
        transcript = [{"id": "answer", "content": "Retained answer"}]
        binding = {"id": "thread", "snapshot": {"messages": transcript, "workbench": {"run": {"id": run.id}}}}
        service._observe_measurement(binding, run)
        first = service.store.append_interaction.call_args.kwargs["snapshot"]
        history = first["workbench"]["run"]["generation_history"]
        self.assertEqual(history[0]["prefill_seconds"], 42.2)
        self.assertIs(first["messages"], transcript)
        binding["snapshot"] = first
        service._observe_measurement(binding, run)
        second = service.store.append_interaction.call_args.kwargs["snapshot"]
        self.assertIs(second["workbench"]["run"]["generation_history"], history)
        self.assertIs(second["messages"], transcript)
        self.assertEqual(AgentRun.model_validate({**run.model_dump(), "generation_history": history}).generation_history[0].processed_input_tokens, 5370)

    def test_resume_seed_keeps_text_already_shown_and_leaves_the_new_delta(self) -> None:
        prefix = [
            {"method": "messages", "params": {"namespace": [], "timestamp": 1, "node": "model",
                "data": {"event": "message-start", "role": "ai", "id": "partial-ai"}}},
            {"method": "messages", "params": {"namespace": [], "timestamp": 2,
                "data": {"event": "content-block-delta", "index": 0, "delta": {"type": "text-delta", "text": "Hello"}}}},
        ]
        seed = message_resume_seed(prefix, seq=4)
        self.assertEqual(seed[0]["params"]["data"]["event"], "message-start")
        self.assertEqual(seed[0]["params"]["data"]["id"], "partial-ai")
        self.assertEqual(seed[0]["seq"], 4)
        self.assertEqual(seed[1]["params"]["data"], {
            "event": "content-block-start", "index": 0, "content": {"type": "text", "text": "Hello"},
        })
        self.assertEqual(seed[1]["params"]["node"], "model")
        self.assertEqual([item["event_id"] for item in seed],
                         [item["event_id"] for item in message_resume_seed(prefix, seq=4)])
        self.assertEqual(len({item["event_id"] for item in seed}), len(seed))
        self.assertNotEqual(seed[1]["event_id"], message_resume_seed(prefix, seq=5)[1]["event_id"])

    def test_open_tool_start_drops_a_finished_call(self) -> None:
        started = {"method": "tools", "params": {"namespace": [], "data": {"event": "tool-started", "tool_call_id": "call-1", "tool_name": "write_file"}}}
        finished = {"method": "tools", "params": {"namespace": [], "data": {"event": "tool-finished", "tool_call_id": "call-1"}}}
        still_open = {"method": "tools", "params": {"namespace": [], "data": {"event": "tool-started", "tool_call_id": "call-2", "tool_name": "read_file"}}}
        self.assertEqual(open_tool_starts([started, finished, still_open]), [still_open])

    def test_tool_command_projects_matching_reply_without_graph_state_or_routing(self) -> None:
        command = Command(update={"messages": [ToolMessage(content="other reply", tool_call_id="other"),
            ToolMessage(content="Updated todo list", tool_call_id="todo", name="write_todos")],
            "private_state": "must stay private"}, goto="private_route")
        raw = {"method": "tools", "params": {"namespace": [], "data": {
            "event": "tool-finished", "tool_call_id": "todo", "output": command}}}
        projected = native_event(raw)[0]
        self.assertEqual(projected["params"]["data"]["output"]["content"], "Updated todo list")
        self.assertNotIn("private", str(projected))
        self.assertNotIn("other reply", str(projected))

    def test_nested_lifecycle_keeps_identity_cause_but_not_checkpoint(self) -> None:
        raw = {"method": "lifecycle", "params": {"namespace": ["worker:instance-1"], "node": "worker",
            "timestamp": 123, "data": {"event": "running", "graph_name": "researcher",
                "cause": {"type": "toolCall", "tool_call_id": "call-child"},
                "checkpoint": {"checkpoint_id": "private"}}}}
        projected = native_event(raw)[0]
        self.assertEqual(projected["params"]["namespace"], ["worker:instance-1"])
        self.assertEqual(projected["params"]["data"]["cause"]["tool_call_id"], "call-child")
        self.assertEqual(projected["params"]["node"], "worker")
        self.assertNotIn("checkpoint", projected["params"]["data"])
        raw["params"]["namespace"] = []
        self.assertEqual(native_event(raw), [])

    def test_archive_uses_public_blocks_for_reasoning_and_keeps_plain_text(self) -> None:
        plain = AIMessage(id="plain-1", content="A short answer.")
        reasoning = AIMessage(
            id="reasoning-1",
            content="",
            additional_kwargs={"reasoning_content": "I checked the available evidence."},
        )
        mixed = AIMessage(
            id="mixed-1",
            content="The answer is 42.",
            additional_kwargs={"reasoning_content": "I calculated it."},
        )

        plain_projection = message_dict(plain)
        reasoning_projection = message_dict(reasoning)
        self.assertEqual(plain_projection["content"], "A short answer.")
        self.assertEqual(plain_projection["id"], "plain-1")
        self.assertEqual(
            reasoning_projection["content"],
            [{"type": "reasoning", "reasoning": "I checked the available evidence."}],
        )
        self.assertEqual(
            message_dict(mixed)["content"],
            [
                {"type": "reasoning", "reasoning": "I calculated it."},
                {"type": "text", "text": "The answer is 42."},
            ],
        )
        archived = archive_messages([], [plain, reasoning])
        self.assertEqual(archived[0]["content"], "A short answer.")
        self.assertEqual(archived[1]["id"], "reasoning-1")
        self.assertEqual(archived[1]["content"], reasoning_projection["content"])

    def test_harness_audits_reasoning_only_message_and_preserves_observed_node(self) -> None:
        harness = object.__new__(HarnessService)
        harness._lock = threading.RLock()
        harness._persist_and_notify = lambda _run: None
        run = AgentRun(
            id="run-1",
            deployment_id="deployment-1",
            task="Check the evidence.",
            enabled_tools=[],
            presented_tools=[],
            status=AgentRunStatus.running,
            created_at="2026-09-21T12:00:00Z",
            updated_at="2026-09-21T12:00:00Z",
        )
        reasoning = AIMessage(
            id="reasoning-2",
            content="",
            additional_kwargs={"reasoning_content": "I checked the available evidence."},
        )
        nodes: dict[str, str] = {}

        HarnessService._ingest_native_event(
            harness,
            run,
            {
                "method": "messages",
                "params": {
                    "namespace": [],
                    "data": ({"event": "message-start", "id": "reasoning-2"}, {"langgraph_node": "agent"}),
                },
            },
            set(),
            nodes,
        )
        HarnessService._ingest_native_values(harness, run, {"messages": [reasoning]}, set(), nodes)

        self.assertEqual(len(run.events), 1)
        self.assertEqual(run.events[0].kind, "assistant_message")
        self.assertEqual(run.events[0].detail["node"], "agent")
        self.assertEqual(run.events[0].detail["message_id"], "reasoning-2")
        self.assertEqual(
            run.events[0].detail["content_blocks"],
            [{"type": "reasoning", "reasoning": "I checked the available evidence."}],
        )

    def test_harness_does_not_fabricate_a_node_without_native_metadata(self) -> None:
        harness = object.__new__(HarnessService)
        harness._lock = threading.RLock()
        harness._persist_and_notify = lambda _run: None
        run = AgentRun(
            id="run-2",
            deployment_id="deployment-1",
            task="Check the evidence.",
            enabled_tools=[],
            presented_tools=[],
            status=AgentRunStatus.running,
            created_at="2026-09-21T12:00:00Z",
            updated_at="2026-09-21T12:00:00Z",
        )

        HarnessService._ingest_native_values(
            harness,
            run,
            {"messages": [AIMessage(id="plain-2", content="The answer is ready.")]},
            set(),
        )

        self.assertEqual(run.events[0].kind, "assistant_message")
        self.assertNotIn("node", run.events[0].detail)


if __name__ == "__main__":
    unittest.main()
