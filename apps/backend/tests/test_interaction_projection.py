"""Interaction display projection keeps native reasoning and message identity."""

from __future__ import annotations

import threading
import unittest

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.interaction.projection import archive_messages, message_dict, message_resume_seed, native_event, open_tool_starts


class InteractionProjectionTests(unittest.TestCase):
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
