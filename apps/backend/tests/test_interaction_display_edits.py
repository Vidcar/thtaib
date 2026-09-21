"""Display-only Chat transcript edits must be reflected in SDK archives."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.app import create_app
from workbench_backend.chat.schemas import ChatConversation, ChatMessage
from workbench_backend.interaction.projection import event
from workbench_backend.inference.ids import utc_now

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client


class InteractionDisplayEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root)
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "display-edit"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _conversation(self, conversation_id: str, *, history_replaced: bool = False) -> ChatConversation:
        now = utc_now()
        conversation = ChatConversation(
            id=conversation_id,
            deployment_id=self.deployment_id,
            thread_id=f"thread_{conversation_id}",
            transcript=[
                ChatMessage(id="old-user", role="user", content="Old user text", at=now, run_id="run_old"),
                ChatMessage(id="old-ai", role="assistant", content="Old answer text", at=now, run_id="run_old"),
            ],
            run_ids=["run_old"],
            history_replaced=history_replaced,
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        return conversation

    def _register_chat(self, conversation_id: str) -> str:
        registered = self.client.post(
            "/v1/agent-interaction/threads",
            json={"source_surface": "chat", "conversation_id": conversation_id},
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        return registered.json()["thread_id"]

    def _message_contents(self, thread_id: str) -> list[str]:
        state = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state")
        self.assertEqual(state.status_code, 200, state.text)
        return [message.get("content") for message in state.json()["values"]["messages"]]

    def _state(self, thread_id: str) -> dict[str, Any]:
        state = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state")
        self.assertEqual(state.status_code, 200, state.text)
        return state.json()

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

    def _install_model(self, script: list[AIMessage]) -> ScriptedChatModel:
        model = ScriptedChatModel(script)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return model

        self.app.state.harness._model_factory = factory
        return model

    def _run_start(self, thread_id: str, *, message_id: str, content: str) -> Any:
        return self.client.post(
            f"/v1/agent-interaction/threads/{thread_id}/commands",
            json={
                "id": f"cmd-{message_id}",
                "method": "run.start",
                "params": {
                    "input": {"messages": [{"type": "human", "id": message_id, "content": content}]},
                    "metadata": {"workbench": {"deployment_id": self.deployment_id, "presented_tools": []}},
                    "multitaskStrategy": "reject",
                    "assistant_id": "_",
                },
            },
        )

    def _wait_state_status(self, thread_id: str, status: str, *, timeout: float = 10.0) -> dict[str, Any]:
        deadline = time.time() + timeout
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = self._state(thread_id)
            run = last.get("values", {}).get("workbench", {}).get("run") or {}
            if run.get("status") == status:
                return last
            time.sleep(0.05)
        raise AssertionError(f"interaction thread {thread_id} did not reach {status}: {last}")

    def test_put_transcript_updates_existing_sdk_archive_without_checkpoint_write(self) -> None:
        conversation = self._conversation("chat_display_edit_existing")
        with patch("workbench_backend.interaction.service.conversation_state", return_value={"messages": []}):
            thread_id = self._register_chat(conversation.id)
        self.assertEqual(self._message_contents(thread_id), ["Old user text", "Old answer text"])

        replacement = [
            {"id": "edited-user", "role": "user", "content": "Edited user text", "at": utc_now()},
            {"id": "edited-ai", "role": "assistant", "content": "Edited answer text", "at": utc_now()},
        ]
        edited = self.client.put(
            f"/v1/chat/conversations/{conversation.id}/transcript",
            json={"messages": replacement},
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertTrue(edited.json()["history_replaced"])

        contents = self._message_contents(thread_id)
        self.assertEqual(contents, ["Edited user text", "Edited answer text"])
        self.assertNotIn("Old user text", contents)
        self.assertNotIn("Old answer text", contents)

    def test_replay_from_before_display_edit_starts_at_cutover_values(self) -> None:
        conversation = self._conversation("chat_display_edit_sse")
        with patch("workbench_backend.interaction.service.conversation_state", return_value={"messages": []}):
            thread_id = self._register_chat(conversation.id)
        initial_snapshot = self.app.state.app_store.get_interaction(thread_id)["snapshot"]
        self.app.state.app_store.append_interaction(
            thread_id,
            [event("values", initial_snapshot)],
            snapshot=initial_snapshot,
        )

        edited = self.client.put(
            f"/v1/chat/conversations/{conversation.id}/transcript",
            json={"messages": [
                {"id": "edited-user", "role": "user", "content": "Edited user text", "at": utc_now()},
                {"id": "edited-ai", "role": "assistant", "content": "Edited answer text", "at": utc_now()},
            ]},
        )
        self.assertEqual(edited.status_code, 200, edited.text)

        binding = self.app.state.app_store.get_interaction(thread_id)
        cutover = binding["snapshot"]["workbench"]["display_cutover_seq"]
        page, _high_water = self.app.state.app_store.interaction_page(thread_id, cutover - 1)
        self.assertTrue(page)
        first_data = str(page[0])

        self.assertIn("Edited user text", first_data)
        self.assertIn("Edited answer text", first_data)
        self.assertNotIn("Old user text", first_data)
        self.assertNotIn("Old answer text", first_data)

    def test_history_replaced_seed_uses_display_transcript_not_erased_checkpoint_messages(self) -> None:
        conversation = self._conversation("chat_display_edit_seed", history_replaced=True)
        conversation.transcript = [
            ChatMessage(id="kept-user", role="user", content="Kept display user", at=utc_now(), run_id=None),
            ChatMessage(id="kept-ai", role="assistant", content="Kept display answer", at=utc_now(), run_id=None),
        ]
        self.app.state.app_store.put_conversation(conversation)
        checkpoint_values = {
            "messages": [
                HumanMessage(id="old-user", content="Old user text"),
                AIMessage(id="old-ai", content="Old answer text"),
            ]
        }

        with patch(
            "workbench_backend.interaction.service.conversation_state",
            return_value=checkpoint_values,
        ):
            thread_id = self._register_chat(conversation.id)

        contents = self._message_contents(thread_id)
        self.assertEqual(contents, ["Kept display user", "Kept display answer"])
        self.assertNotIn("Old user text", contents)
        self.assertNotIn("Old answer text", contents)

    def test_late_events_from_current_run_after_display_edit_are_hidden(self) -> None:
        conversation = self._conversation("chat_display_edit_late")
        conversation.current_run_id = "run_old"
        self.app.state.app_store.put_conversation(conversation)
        run = self._run(
            "run_old",
            conversation.thread_id,
            AgentRunStatus.running,
            input_message_id="old-user",
            task="Old user text",
        )
        self.app.state.app_store.put_run(run)
        with patch("workbench_backend.interaction.service.conversation_state", return_value={"messages": []}):
            thread_id = self._register_chat(conversation.id)

        edited = self.client.put(
            f"/v1/chat/conversations/{conversation.id}/transcript",
            json={"messages": [
                {"id": "edited-user", "role": "user", "content": "Edited user text", "at": utc_now()},
                {"id": "edited-ai", "role": "assistant", "content": "Edited answer text", "at": utc_now()},
            ]},
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        cursor = self._state(thread_id)["interaction_cursor"]

        self.app.state.interaction.observe(
            run,
            {"method": "messages", "params": {"namespace": [], "timestamp": 1, "data": {"event": "message-start", "role": "ai", "id": "late-ai"}}},
        )
        self.app.state.interaction.observe(
            run,
            {"method": "values", "params": {"namespace": [], "data": {"messages": [
                HumanMessage(id="old-user", content="Old user text"),
                AIMessage(id="late-ai", content="Late old answer"),
            ]}}},
        )
        finished = run.model_copy(update={"status": AgentRunStatus.completed, "finished_at": utc_now(), "updated_at": utc_now()})
        self.app.state.app_store.put_run(finished)
        self.app.state.interaction.observe(finished, None)

        state = self._state(thread_id)
        contents = [message.get("content") for message in state["values"]["messages"]]
        self.assertEqual(contents, ["Edited user text", "Edited answer text"])
        self.assertNotIn("Late old answer", contents)
        self.assertEqual(self.app.state.app_store.interaction_events_after(thread_id, cursor), [
            item for item in self.app.state.app_store.interaction_events_after(thread_id, cursor)
            if "Late old answer" not in str(item)
        ])

    def test_subsequent_run_does_not_resurrect_erased_checkpoint_values(self) -> None:
        conversation = self._conversation("chat_display_edit_next")
        checkpoint_values = {
            "messages": [
                HumanMessage(id="old-user", content="Old user text"),
                AIMessage(id="old-ai", content="Old answer text"),
            ]
        }
        with patch("workbench_backend.interaction.service.conversation_state", return_value=checkpoint_values):
            thread_id = self._register_chat(conversation.id)

        edited = self.client.put(
            f"/v1/chat/conversations/{conversation.id}/transcript",
            json={"messages": [
                {"id": "edited-user", "role": "user", "content": "Edited user text", "at": utc_now()},
                {"id": "edited-ai", "role": "assistant", "content": "Edited answer text", "at": utc_now()},
            ]},
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        model = self._install_model([AIMessage(id="new-ai", content="New answer")])

        started = self._run_start(thread_id, message_id="new-user", content="New question")
        self.assertEqual(started.status_code, 200, started.text)
        self._wait_state_status(thread_id, "completed")
        run_id = started.json()["result"]["run_id"]
        run = self.app.state.harness.get_run(run_id)
        self.app.state.interaction.observe(
            run,
            {"method": "values", "params": {"namespace": [], "data": {"messages": [
                HumanMessage(id="old-user", content="Old user text"),
                AIMessage(id="old-ai", content="Old answer text"),
                HumanMessage(id="new-user", content="New question"),
                AIMessage(id="new-ai", content="New answer"),
            ]}}},
        )

        contents = self._message_contents(thread_id)
        self.assertEqual(model._index, 1)
        self.assertIn("Edited user text", contents)
        self.assertIn("Edited answer text", contents)
        self.assertIn("New question", contents)
        self.assertIn("New answer", contents)
        self.assertNotIn("Old user text", contents)
        self.assertNotIn("Old answer text", contents)

    def test_put_transcript_does_not_start_execution_or_write_checkpoint(self) -> None:
        conversation = self._conversation("chat_display_edit_no_execute")
        checkpoint_path = self.root / "checkpoints.sqlite"
        before = checkpoint_path.stat().st_mtime_ns if checkpoint_path.exists() else None
        with patch.object(self.app.state.harness, "start", side_effect=AssertionError("display edit must not execute")):
            edited = self.client.put(
                f"/v1/chat/conversations/{conversation.id}/transcript",
                json={"messages": [
                    {"id": "edited-user", "role": "user", "content": "Edited user text", "at": utc_now()},
                ]},
            )
        self.assertEqual(edited.status_code, 200, edited.text)
        after = checkpoint_path.stat().st_mtime_ns if checkpoint_path.exists() else None
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
