"""Interaction migration and recovery projection tests."""

from __future__ import annotations

import tempfile
import sqlite3
from contextlib import closing
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.app import create_app
from workbench_backend.chat.schemas import ChatConversation, ChatMessage
from workbench_backend.inference.ids import utc_now

from tests.support import close_workbench_sqlite, offline_workbench_client


class InteractionRecoveryTests(unittest.TestCase):
    def test_isolated_legacy_database_copy_upgrades_without_losing_records(self) -> None:
        now = utc_now()
        conversation = ChatConversation(id="chat_legacy_copy", deployment_id=self.deployment_id,
            thread_id="legacy-execution-thread", project_path=str(self.project),
            transcript=[ChatMessage(role="user", content="Retained legacy question", at=now),
                        ChatMessage(role="assistant", content="Retained legacy answer", at=now)],
            created_at=now, updated_at=now)
        self.app.state.app_store.put_conversation(conversation)
        marker = self.project / "kept.txt"
        marker.write_text("untouched", encoding="utf-8")
        copy_root = self.root / "legacy-copy"
        copy_root.mkdir()
        with closing(sqlite3.connect(self.root / "application.sqlite")) as source:
            with closing(sqlite3.connect(copy_root / "application.sqlite")) as target:
                source.backup(target)
                # These additive display tables did not exist before migration.
                target.execute("DROP TABLE interaction_events")
                target.execute("DROP TABLE interaction_threads")
                target.commit()
        copied_app = create_app(data_root=copy_root)
        copied_client = offline_workbench_client(copied_app)
        try:
            registered = copied_client.post("/v1/agent-interaction/threads",
                json={"source_surface": "chat", "conversation_id": conversation.id})
            self.assertEqual(registered.status_code, 200, registered.text)
            state = copied_client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
            self.assertEqual([m["content"] for m in state["values"]["messages"]],
                             ["Retained legacy question", "Retained legacy answer"])
            saved = copied_app.state.app_store.get_conversation(conversation.id)
            self.assertEqual(saved.thread_id, "legacy-execution-thread")
            self.assertEqual(saved.project_path, str(self.project))
            self.assertEqual(marker.read_text(encoding="utf-8"), "untouched")
            self.assertIsNone(self.app.state.app_store.get_interaction(conversation.id))
        finally:
            close_workbench_sqlite(copied_app, copied_client)

    def test_two_observer_registrations_converge_on_one_existing_run_binding(self) -> None:
        run = self._run("agent_observers", "graph_observers", AgentRunStatus.completed,
                        input_message_id="observer-input", task="Existing execution")
        self.app.state.app_store.put_run(run)
        register = self.app.state.app_store.register_interaction

        def race_register(thread_id, surface, graph_thread_id, conversation_id, snapshot):
            register("winning-observer", surface, graph_thread_id, conversation_id, snapshot)
            return register(thread_id, surface, graph_thread_id, conversation_id, snapshot)

        with patch.object(self.app.state.app_store, "register_interaction", side_effect=race_register):
            first = self.client.post("/v1/agent-interaction/threads", json={"source_surface": "agent", "run_id": run.id})
        second = self.client.post("/v1/agent-interaction/threads", json={"source_surface": "agent", "run_id": run.id})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), {"thread_id": "winning-observer"})
        self.assertEqual(second.json(), first.json())
        self.assertEqual(self.client.get("/v1/agent-interaction/threads/winning-observer/state").status_code, 200)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.app = create_app(data_root=self.root)
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "interaction-recovery"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def test_chat_registration_preserves_older_archive_and_checkpoint_tool_chronology(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_recovery_seed",
            deployment_id=self.deployment_id,
            profile_id="profile_existing",
            project_path=str(self.project),
            thread_id="thread_recovery_seed",
            transcript=[
                ChatMessage(id="old-user", role="user", content="Older question", at=now, run_id="run_old"),
                ChatMessage(id="old-ai", role="assistant", content="Older answer", at=now, run_id="run_old"),
                ChatMessage(id="current-user", role="user", content="Use the lookup tool", at=now, run_id="run_current"),
                ChatMessage(id="current-ai", role="assistant", content="Tool result answer", at=now, run_id="run_current"),
            ],
            run_ids=["run_old", "run_current"],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        checkpoint_values = {
            "messages": [
                HumanMessage(id="current-user", content="Use the lookup tool"),
                AIMessage(
                    id="ai-tool-call",
                    content="",
                    tool_calls=[{"id": "call_lookup", "name": "lookup", "args": {"q": "recovery"}}],
                ),
                ToolMessage(id="tool-result", tool_call_id="call_lookup", name="lookup", content="found"),
                AIMessage(id="current-ai", content="Tool result answer"),
            ]
        }

        with patch(
            "workbench_backend.interaction.service.conversation_state",
            return_value=checkpoint_values,
        ):
            registered = self.client.post(
                "/v1/agent-interaction/threads",
                json={"source_surface": "chat", "conversation_id": conversation.id},
            )

        self.assertEqual(registered.status_code, 200, registered.text)
        self.assertEqual(registered.json()["thread_id"], conversation.id)
        state = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state")
        self.assertEqual(state.status_code, 200, state.text)
        values = state.json()["values"]
        messages = values["messages"]
        ids = [message["id"] for message in messages]

        self.assertLess(ids.index("old-user"), ids.index("current-user"))
        self.assertLess(ids.index("old-ai"), ids.index("current-user"))
        self.assertLess(ids.index("current-user"), ids.index("ai-tool-call"))
        self.assertLess(ids.index("ai-tool-call"), ids.index("tool-result"))
        self.assertLess(ids.index("tool-result"), ids.index("current-ai"))
        self.assertEqual(ids.count("current-user"), 1)
        self.assertEqual(ids.count("current-ai"), 1)
        self.assertEqual(messages[ids.index("ai-tool-call")]["tool_calls"][0]["id"], "call_lookup")
        self.assertEqual(messages[ids.index("tool-result")]["tool_call_id"], "call_lookup")

        binding = self.app.state.app_store.get_interaction(conversation.id)
        self.assertEqual(binding["graph_thread_id"], conversation.thread_id)
        self.assertEqual(binding["conversation_id"], conversation.id)
        stored = self.app.state.app_store.get_conversation(conversation.id)
        self.assertEqual(stored.project_path, str(self.project))
        self.assertEqual(stored.profile_id, "profile_existing")
        self.assertEqual(stored.thread_id, "thread_recovery_seed")


    def test_chat_registration_reopen_is_idempotent_and_preserves_archive_ids(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_reopen_seed",
            deployment_id=self.deployment_id,
            profile_id="profile_reopen",
            project_path=str(self.project),
            thread_id="thread_reopen_seed",
            transcript=[
                ChatMessage(id="old-user", role="user", content="Older question", at=now, run_id="run_old"),
                ChatMessage(id="old-ai", role="assistant", content="Older answer", at=now, run_id="run_old"),
                ChatMessage(id="current-user", role="user", content="Use the lookup tool", at=now, run_id="run_current"),
                ChatMessage(id="current-ai", role="assistant", content="Tool result answer", at=now, run_id="run_current"),
            ],
            run_ids=["run_old", "run_current"],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        checkpoint_values = {
            "messages": [
                HumanMessage(id="current-user", content="Use the lookup tool"),
                AIMessage(
                    id="ai-tool-call",
                    content="",
                    tool_calls=[{"id": "call_lookup", "name": "lookup", "args": {"q": "reopen"}}],
                ),
                ToolMessage(id="tool-result", tool_call_id="call_lookup", name="lookup", content="found"),
                AIMessage(id="current-ai", content="Tool result answer"),
            ]
        }

        with patch(
            "workbench_backend.interaction.service.conversation_state",
            return_value=checkpoint_values,
        ):
            registered = self.client.post(
                "/v1/agent-interaction/threads",
                json={"source_surface": "chat", "conversation_id": conversation.id},
            )
        self.assertEqual(registered.status_code, 200, registered.text)
        before = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
        before_ids = [message["id"] for message in before["values"]["messages"]]
        self.assertEqual(before_ids, ["old-user", "old-ai", "current-user", "ai-tool-call", "tool-result", "current-ai"])

        close_workbench_sqlite(self.app, self.client)
        self.app = create_app(data_root=self.root)
        self.client = offline_workbench_client(self.app)
        with patch(
            "workbench_backend.interaction.service.conversation_state",
            side_effect=AssertionError("existing interaction should reopen without reseeding"),
        ):
            reopened = self.client.post(
                "/v1/agent-interaction/threads",
                json={"source_surface": "chat", "conversation_id": conversation.id},
            )

        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertEqual(reopened.json()["thread_id"], conversation.id)
        after = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
        after_ids = [message["id"] for message in after["values"]["messages"]]
        self.assertEqual(after_ids, before_ids)
        self.assertEqual(after_ids.count("current-user"), 1)
        self.assertEqual(after_ids.count("current-ai"), 1)
        self.assertEqual(after["values"]["messages"], before["values"]["messages"])

    def test_cancelled_partial_archive_survives_subsequent_run_update(self) -> None:
        registered = self.client.post("/v1/agent-interaction/threads", json={"source_surface": "agent"})
        self.assertEqual(registered.status_code, 200, registered.text)
        thread_id = registered.json()["thread_id"]
        graph_thread_id = self.app.state.app_store.get_interaction(thread_id)["graph_thread_id"]
        started = self._run(
            "agent_partial_cancelled",
            graph_thread_id,
            AgentRunStatus.running,
            input_message_id="partial-user",
            task="Start and cancel",
        )
        self.app.state.app_store.put_run(started)
        self.app.state.interaction.observe(started, None)
        for raw in [
            {"event": "message-start", "role": "ai", "id": "partial-ai"},
            {"event": "content-block-start", "index": 0, "content": {"type": "text", "text": ""}},
            {"event": "content-block-delta", "index": 0, "delta": {"type": "text-delta", "text": "partial text"}},
        ]:
            self.app.state.interaction.observe(
                started,
                {"method": "messages", "params": {"namespace": [], "timestamp": 1, "data": raw}},
            )
        cancelled = started.model_copy(update={
            "status": AgentRunStatus.cancelled,
            "stop_reason": "cancelled",
            "finished_at": utc_now(),
            "updated_at": utc_now(),
        })
        self.app.state.app_store.put_run(cancelled)
        self.app.state.interaction.observe(cancelled, None)

        state = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state").json()
        messages = state["values"]["messages"]
        partial = next(message for message in messages if message.get("id") == "partial-ai")
        self.assertEqual(partial["type"], "ai")
        self.assertEqual(partial["content"], [{"type": "text", "text": "partial text"}])
        self.assertIn("partial-ai", state["values"]["workbench"]["incomplete_message_ids"])

        followup = self._run(
            "agent_after_partial",
            graph_thread_id,
            AgentRunStatus.completed,
            input_message_id="after-partial-user",
            task="Continue after cancel",
        )
        self.app.state.app_store.put_run(followup)
        self.app.state.interaction.observe(followup.model_copy(update={"status": AgentRunStatus.running}), None)
        self.app.state.interaction.observe(followup, None)

        after = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state").json()
        after_messages = after["values"]["messages"]
        self.assertTrue(any(message.get("id") == "partial-ai" for message in after_messages))
        self.assertIn("partial-ai", after["values"]["workbench"]["incomplete_message_ids"])
        self.assertTrue(any(message.get("id") == "after-partial-user" for message in after_messages))
        self.assertEqual(after["values"]["workbench"]["run"]["id"], "agent_after_partial")

    def _run(
        self,
        run_id: str,
        thread_id: str,
        status: AgentRunStatus,
        *,
        input_message_id: str,
        task: str,
    ) -> AgentRun:
        now = utc_now()
        return AgentRun(
            id=run_id,
            status=status,
            deployment_id=self.deployment_id,
            task=task,
            input_message_id=input_message_id,
            enabled_tools=[],
            presented_tools=[],
            created_at=now,
            updated_at=now,
            thread_id=thread_id,
        )


if __name__ == "__main__":
    unittest.main()
