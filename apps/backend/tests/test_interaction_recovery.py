"""Interaction migration and recovery projection tests."""

from __future__ import annotations

import tempfile
import sqlite3
import time
from contextlib import closing
import unittest
from pathlib import Path
from unittest.mock import patch
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.app import create_app
from workbench_backend.chat.schemas import ChatConversation, ChatMessage
from workbench_backend.interaction.projection import event
from workbench_backend.inference.ids import utc_now

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client


def display_id(conversation_id: str, index: int, role: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{conversation_id}:{index}:{role}"))


class InteractionRecoveryTests(unittest.TestCase):
    def test_branch_seed_aligns_queued_identity_and_structured_answer_without_duplicate(self) -> None:
        now = utc_now()
        conversation = ChatConversation(id="chat_branch_structured", deployment_id=self.deployment_id,
            thread_id="branch_structured", created_at=now, updated_at=now,
            transcript=[
                ChatMessage(role="user", content="Old prompt", at=now),
                ChatMessage(role="assistant", content="Same answer", at=now),
                ChatMessage(id="queue:input", role="user", content="Reply again", at=now,
                    content_blocks=[{"type": "workbench_submission", "submission": {"task": "Reply again"}}]),
                ChatMessage(role="assistant", content="Same answer", at=now),
            ])
        self.app.state.app_store.put_conversation(conversation)
        blocks = [{"type": "reasoning", "reasoning": "Follow exact response"},
                  {"type": "text", "text": "Same answer"}]
        with patch("workbench_backend.interaction.service.conversation_state", return_value={"messages": [
            HumanMessage(id="queue:input", content="Reply again"),
            AIMessage(id="saved-answer", content=blocks),
        ]}):
            response = self.client.post("/v1/agent-interaction/threads",
                json={"source_surface": "chat", "conversation_id": conversation.id})
        self.assertEqual(response.status_code, 200, response.text)
        messages = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()["values"]["messages"]
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[1]["content"], "Same answer", "earlier repeated answer must survive")
        self.assertEqual(messages[-1]["id"], "saved-answer")
        self.assertEqual(messages[-1]["content"], blocks, "native reasoning must survive alignment")

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

    def test_chat_registration_preserves_repeated_legacy_text_chronology(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_repeated_legacy_text",
            deployment_id=self.deployment_id,
            project_path=str(self.project),
            thread_id="thread_repeated_legacy_text",
            transcript=[
                ChatMessage(role="user", content="Continue", at=now, run_id="run_old"),
                ChatMessage(role="assistant", content="First answer", at=now, run_id="run_old"),
                ChatMessage(role="user", content="Continue", at=now, run_id="run_current"),
                ChatMessage(role="assistant", content="Second answer", at=now, run_id="run_current"),
            ],
            run_ids=["run_old", "run_current"],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        checkpoint_values = {
            "messages": [
                HumanMessage(id="current-user", content="Continue"),
                AIMessage(id="current-ai", content="Second answer"),
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
        state = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state")
        self.assertEqual(state.status_code, 200, state.text)
        messages = state.json()["values"]["messages"]
        self.assertEqual(
            [(message["type"], message["content"]) for message in messages],
            [
                ("human", "Continue"),
                ("ai", "First answer"),
                ("human", "Continue"),
                ("ai", "Second answer"),
            ],
        )
        self.assertEqual([message["id"] for message in messages[-2:]], ["current-user", "current-ai"])
        self.assertEqual(len(messages), 4)

    def test_chat_registration_preserves_repeated_assistant_text_chronology(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_repeated_assistant_text",
            deployment_id=self.deployment_id,
            project_path=str(self.project),
            thread_id="thread_repeated_assistant_text",
            transcript=[
                ChatMessage(role="user", content="First prompt", at=now, run_id="run_old"),
                ChatMessage(role="assistant", content="Same answer", at=now, run_id="run_old"),
                ChatMessage(role="user", content="Second prompt", at=now, run_id="run_current"),
                ChatMessage(role="assistant", content="Same answer", at=now, run_id="run_current"),
            ],
            run_ids=["run_old", "run_current"],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        checkpoint_values = {
            "messages": [
                HumanMessage(id="current-user", content="Second prompt"),
                AIMessage(id="current-ai", content="Same answer"),
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
        state = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
        messages = state["values"]["messages"]
        self.assertEqual(
            [(message["type"], message["content"]) for message in messages],
            [
                ("human", "First prompt"),
                ("ai", "Same answer"),
                ("human", "Second prompt"),
                ("ai", "Same answer"),
            ],
        )
        self.assertEqual(messages[1]["id"], display_id(conversation.id, 1, "assistant"))
        self.assertEqual(messages[3]["id"], "current-ai")

    def test_chat_registration_preserves_idless_tool_and_reasoning_suffix(self) -> None:
        now = utc_now()
        reasoning_blocks = [
            {"type": "reasoning", "reasoning": "checked the lookup"},
            {"type": "text", "text": "Tool-backed answer"},
        ]
        conversation = ChatConversation(
            id="chat_idless_tool_reasoning_suffix",
            deployment_id=self.deployment_id,
            project_path=str(self.project),
            thread_id="thread_idless_tool_reasoning_suffix",
            transcript=[
                ChatMessage(role="user", content="Earlier", at=now, run_id="run_old"),
                ChatMessage(role="assistant", content="Earlier answer", at=now, run_id="run_old"),
                ChatMessage(role="user", content="Use the tool", at=now, run_id="run_current"),
                ChatMessage(role="assistant", content="Tool-backed answer", content_blocks=reasoning_blocks,
                            at=now, run_id="run_current"),
            ],
            run_ids=["run_old", "run_current"],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        checkpoint_values = {
            "messages": [
                HumanMessage(id="current-user", content="Use the tool"),
                AIMessage(id="tool-call-ai", content="", tool_calls=[
                    {"id": "call_reasoning", "name": "lookup", "args": {"q": "blocks"}},
                ]),
                ToolMessage(id="tool-result", tool_call_id="call_reasoning", name="lookup", content="block result"),
                AIMessage(id="current-ai", content=reasoning_blocks),
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
        state = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
        ids = [message["id"] for message in state["values"]["messages"]]
        self.assertEqual(
            ids,
            [
                display_id(conversation.id, 0, "user"),
                display_id(conversation.id, 1, "assistant"),
                "current-user",
                "tool-call-ai",
                "tool-result",
                "current-ai",
            ],
        )
        self.assertEqual(state["values"]["messages"][ids.index("current-ai")]["content"], reasoning_blocks)
        self.assertEqual(state["values"]["messages"][ids.index("tool-result")]["tool_call_id"], "call_reasoning")

    def test_chat_registration_repairs_existing_repeated_text_projection_once(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_repeated_repair",
            deployment_id=self.deployment_id,
            project_path=str(self.project),
            thread_id="thread_repeated_repair",
            transcript=[
                ChatMessage(role="user", content="Continue", at=now, run_id="run_old"),
                ChatMessage(role="assistant", content="First answer", at=now, run_id="run_old"),
                ChatMessage(role="user", content="Continue", at=now, run_id="run_current"),
                ChatMessage(role="assistant", content="Second answer", at=now, run_id="run_current"),
            ],
            run_ids=["run_old", "run_current"],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        old_user_id = display_id(conversation.id, 2, "user")
        old_ai_id = display_id(conversation.id, 1, "assistant")
        faulty_snapshot = {
            "messages": [
                {"id": old_ai_id, "type": "ai", "content": "First answer"},
                {"id": old_user_id, "type": "human", "content": "Continue"},
                {"id": "current-user", "type": "human", "content": "Continue"},
                {"id": "current-ai", "type": "ai", "content": "Second answer"},
            ],
            "workbench": {"run": None, "conversation_id": conversation.id},
        }
        self.app.state.app_store.register_interaction(
            conversation.id,
            "chat",
            conversation.thread_id,
            conversation.id,
            faulty_snapshot,
        )
        self.app.state.app_store.append_interaction(
            conversation.id,
            [event("values", faulty_snapshot)],
            snapshot=faulty_snapshot,
        )
        checkpoint_values = {
            "messages": [
                HumanMessage(id="current-user", content="Continue"),
                AIMessage(id="current-ai", content="Second answer"),
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
        state = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
        self.assertEqual(
            [(message["type"], message["content"]) for message in state["values"]["messages"]],
            [
                ("human", "Continue"),
                ("ai", "First answer"),
                ("human", "Continue"),
                ("ai", "Second answer"),
            ],
        )
        self.assertEqual(
            [message["id"] for message in state["values"]["messages"][-2:]],
            ["current-user", "current-ai"],
        )
        self.assertEqual(self.app.state.app_store.get_interaction(conversation.id)["seq"], 2)

        with patch(
            "workbench_backend.interaction.service.conversation_state",
            return_value=checkpoint_values,
        ):
            reopened = self.client.post(
                "/v1/agent-interaction/threads",
                json={"source_surface": "chat", "conversation_id": conversation.id},
            )
        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertEqual(self.app.state.app_store.get_interaction(conversation.id)["seq"], 2)

    def test_chat_registration_repairs_faulty_seed_prefix_and_preserves_later_output(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_repeated_repair_with_later",
            deployment_id=self.deployment_id,
            project_path=str(self.project),
            thread_id="thread_repeated_repair_with_later",
            transcript=[
                ChatMessage(role="user", content="Continue", at=now, run_id="run_old"),
                ChatMessage(role="assistant", content="First answer", at=now, run_id="run_old"),
                ChatMessage(role="user", content="Continue", at=now, run_id="run_current"),
                ChatMessage(role="assistant", content="Second answer", at=now, run_id="run_current"),
            ],
            run_ids=["run_old", "run_current"],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        old_user_id = display_id(conversation.id, 2, "user")
        old_ai_id = display_id(conversation.id, 1, "assistant")
        run = self._run(
            "run_later",
            conversation.thread_id,
            AgentRunStatus.cancelled,
            input_message_id="later-user",
            task="Later turn",
        )
        self.app.state.app_store.put_run(run)
        later_partial = {"id": "partial-ai", "type": "ai", "content": [{"type": "text", "text": "Later partial"}]}
        faulty_snapshot = {
            "messages": [
                {"id": old_ai_id, "type": "ai", "content": "First answer"},
                {"id": old_user_id, "type": "human", "content": "Continue"},
                {"id": "current-user", "type": "human", "content": "Continue"},
                {"id": "current-ai", "type": "ai", "content": "Second answer"},
                later_partial,
            ],
            "workbench": {
                "run": run.model_dump(mode="json"),
                "conversation_id": conversation.id,
                "incomplete_message_ids": ["partial-ai"],
            },
        }
        self.app.state.app_store.register_interaction(
            conversation.id,
            "chat",
            conversation.thread_id,
            conversation.id,
            faulty_snapshot,
        )
        self.app.state.app_store.append_interaction(
            conversation.id,
            [event("values", faulty_snapshot)],
            snapshot=faulty_snapshot,
        )
        checkpoint_values = {
            "messages": [
                HumanMessage(id="current-user", content="Continue"),
                AIMessage(id="current-ai", content="Second answer"),
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
        state = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
        self.assertEqual(
            [(message["type"], message["content"]) for message in state["values"]["messages"]],
            [
                ("human", "Continue"),
                ("ai", "First answer"),
                ("human", "Continue"),
                ("ai", "Second answer"),
                ("ai", [{"type": "text", "text": "Later partial"}]),
            ],
        )
        self.assertEqual(state["values"]["messages"][-1], later_partial)
        self.assertEqual(state["values"]["workbench"]["run"]["id"], "run_later")
        self.assertEqual(state["values"]["workbench"]["incomplete_message_ids"], ["partial-ai"])

    def test_chat_registration_keeps_mismatched_block_content_display_only(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_block_ambiguous",
            deployment_id=self.deployment_id,
            project_path=str(self.project),
            thread_id="thread_block_ambiguous",
            transcript=[
                ChatMessage(role="assistant", content="", content_blocks=[
                    {"type": "image", "source": {"type": "url", "url": "file-a.png"}},
                ], at=now),
                ChatMessage(role="assistant", content="", content_blocks=[
                    {"type": "image", "source": {"type": "url", "url": "file-b.png"}},
                ], at=now),
            ],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        checkpoint_values = {
            "messages": [
                AIMessage(id="retained-image", content=[
                    {"type": "image", "source": {"type": "url", "url": "file-c.png"}},
                ]),
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
        state = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
        messages = state["values"]["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["content"][0]["source"]["url"], "file-a.png")
        self.assertEqual(messages[1]["content"][0]["source"]["url"], "file-b.png")
        self.assertEqual(messages[1]["id"], display_id(conversation.id, 1, "assistant"))

    def test_chat_registration_does_not_repair_display_edit_cutover(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_repair_guard",
            deployment_id=self.deployment_id,
            project_path=str(self.project),
            thread_id="thread_repair_guard",
            transcript=[
                ChatMessage(role="user", content="Continue", at=now),
                ChatMessage(role="assistant", content="First answer", at=now),
                ChatMessage(role="user", content="Continue", at=now),
                ChatMessage(role="assistant", content="Second answer", at=now),
            ],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        snapshot = {
            "messages": [
                {"id": "edited-user", "type": "human", "content": "Edited"},
                {"id": "extra-ai", "type": "ai", "content": "Extra output"},
            ],
            "workbench": {
                "run": None,
                "conversation_id": conversation.id,
                "display_cutover_seq": 7,
            },
        }
        self.app.state.app_store.register_interaction(
            conversation.id,
            "chat",
            conversation.thread_id,
            conversation.id,
            snapshot,
        )
        checkpoint_values = {
            "messages": [
                HumanMessage(id="current-user", content="Continue"),
                AIMessage(id="current-ai", content="Second answer"),
            ]
        }

        with patch(
            "workbench_backend.interaction.service.conversation_state",
            return_value=checkpoint_values,
        ):
            reopened = self.client.post(
                "/v1/agent-interaction/threads",
                json={"source_surface": "chat", "conversation_id": conversation.id},
            )

        self.assertEqual(reopened.status_code, 200, reopened.text)
        state = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
        self.assertEqual(state["values"]["messages"], snapshot["messages"])
        self.assertEqual(self.app.state.app_store.get_interaction(conversation.id)["seq"], 0)

    def test_chat_registration_does_not_repair_same_content_with_established_different_ids(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_repair_established_ids_guard",
            deployment_id=self.deployment_id,
            project_path=str(self.project),
            thread_id="thread_repair_established_ids_guard",
            transcript=[
                ChatMessage(role="user", content="Repeat", at=now),
                ChatMessage(role="assistant", content="Answer", at=now),
                ChatMessage(role="user", content="Repeat", at=now),
                ChatMessage(role="assistant", content="Answer", at=now),
            ],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        snapshot = {
            "messages": [
                {
                    "id": "established-ai-first",
                    "type": "ai",
                    "content": "Answer",
                    "tool_calls": [{"id": "call_existing", "name": "lookup", "args": {"q": "keep"}}],
                },
                {"id": "established-user-first", "type": "human", "content": "Repeat", "name": "kept-user"},
                {"id": "established-user-second", "type": "human", "content": "Repeat"},
                {"id": "established-ai-second", "type": "ai", "content": "Answer", "status": "success"},
            ],
            "workbench": {"run": None, "conversation_id": conversation.id},
        }
        self.app.state.app_store.register_interaction(
            conversation.id,
            "chat",
            conversation.thread_id,
            conversation.id,
            snapshot,
        )
        checkpoint_values = {
            "messages": [
                HumanMessage(id="current-user", content="Repeat"),
                AIMessage(id="current-ai", content="Answer"),
            ]
        }

        with patch(
            "workbench_backend.interaction.service.conversation_state",
            return_value=checkpoint_values,
        ):
            reopened = self.client.post(
                "/v1/agent-interaction/threads",
                json={"source_surface": "chat", "conversation_id": conversation.id},
            )

        self.assertEqual(reopened.status_code, 200, reopened.text)
        state = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
        self.assertEqual(state["values"]["messages"], snapshot["messages"])
        self.assertEqual(self.app.state.app_store.get_interaction(conversation.id)["seq"], 0)

    def test_chat_registration_repairs_old_seed_prefix_when_later_turn_is_in_transcript_and_checkpoint(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_repair_later_durable_turn",
            deployment_id=self.deployment_id,
            project_path=str(self.project),
            thread_id="thread_repair_later_durable_turn",
            transcript=[
                ChatMessage(role="user", content="Continue", at=now, run_id="run_old"),
                ChatMessage(role="assistant", content="First answer", at=now, run_id="run_old"),
                ChatMessage(role="user", content="Continue", at=now, run_id="run_current"),
                ChatMessage(role="assistant", content="Second answer", at=now, run_id="run_current"),
                ChatMessage(id="later-user", role="user", content="Next question", at=now, run_id="run_later"),
                ChatMessage(id="later-ai", role="assistant", content="Later answer", at=now, run_id="run_later"),
            ],
            run_ids=["run_old", "run_current", "run_later"],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        faulty_snapshot = {
            "messages": [
                {"id": display_id(conversation.id, 1, "assistant"), "type": "ai", "content": "First answer"},
                {"id": display_id(conversation.id, 2, "user"), "type": "human", "content": "Continue"},
                {"id": "current-user", "type": "human", "content": "Continue"},
                {"id": "current-ai", "type": "ai", "content": "Second answer"},
                {"id": "later-user", "type": "human", "content": "Next question"},
                {"id": "later-tool-call", "type": "ai", "content": "", "tool_calls": [
                    {"id": "call_later", "name": "lookup", "args": {"q": "later"}},
                ]},
                {"id": "later-tool", "type": "tool", "content": "found later", "tool_call_id": "call_later",
                 "name": "lookup"},
                {"id": "later-ai", "type": "ai", "content": "Later answer", "status": "success"},
            ],
            "workbench": {"run": None, "conversation_id": conversation.id},
        }
        self.app.state.app_store.register_interaction(
            conversation.id,
            "chat",
            conversation.thread_id,
            conversation.id,
            faulty_snapshot,
        )
        self.app.state.app_store.append_interaction(
            conversation.id,
            [event("values", faulty_snapshot)],
            snapshot=faulty_snapshot,
        )
        checkpoint_values = {
            "messages": [
                HumanMessage(id="current-user", content="Continue"),
                AIMessage(id="current-ai", content="Second answer"),
                HumanMessage(id="later-user", content="Next question"),
                AIMessage(id="later-tool-call", content="", tool_calls=[
                    {"id": "call_later", "name": "lookup", "args": {"q": "later"}},
                ]),
                ToolMessage(id="later-tool", tool_call_id="call_later", name="lookup", content="found later"),
                AIMessage(id="later-ai", content="Later answer"),
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
        state = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
        ids = [message["id"] for message in state["values"]["messages"]]
        self.assertEqual(
            ids,
            [
                display_id(conversation.id, 0, "user"),
                display_id(conversation.id, 1, "assistant"),
                "current-user",
                "current-ai",
                "later-user",
                "later-tool-call",
                "later-tool",
                "later-ai",
            ],
        )
        self.assertEqual(ids.count("later-tool"), 1)
        self.assertEqual(state["values"]["messages"][ids.index("later-tool-call")]["tool_calls"][0]["id"], "call_later")

    def test_isolated_existing_faulty_projection_copy_repairs_without_touching_source(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_faulty_projection_copy",
            deployment_id=self.deployment_id,
            project_path=str(self.project),
            thread_id="thread_faulty_projection_copy",
            transcript=[
                ChatMessage(role="user", content="Continue", at=now, run_id="run_old"),
                ChatMessage(role="assistant", content="First answer", at=now, run_id="run_old"),
                ChatMessage(role="user", content="Continue", at=now, run_id="run_current"),
                ChatMessage(role="assistant", content="Second answer", at=now, run_id="run_current"),
            ],
            run_ids=["run_old", "run_current"],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        marker = self.project / "faulty-copy-kept.txt"
        marker.write_text("untouched", encoding="utf-8")
        faulty_snapshot = {
            "messages": [
                {"id": display_id(conversation.id, 1, "assistant"), "type": "ai", "content": "First answer"},
                {"id": display_id(conversation.id, 2, "user"), "type": "human", "content": "Continue"},
                {"id": "current-user", "type": "human", "content": "Continue"},
                {"id": "current-ai", "type": "ai", "content": "Second answer"},
            ],
            "workbench": {"run": None, "conversation_id": conversation.id},
        }
        self.app.state.app_store.register_interaction(
            conversation.id,
            "chat",
            conversation.thread_id,
            conversation.id,
            faulty_snapshot,
        )
        self.app.state.app_store.append_interaction(
            conversation.id,
            [event("values", faulty_snapshot)],
            snapshot=faulty_snapshot,
        )
        copy_root = self.root / "faulty-projection-copy"
        copy_root.mkdir()
        with closing(sqlite3.connect(self.root / "application.sqlite")) as source:
            with closing(sqlite3.connect(copy_root / "application.sqlite")) as target:
                source.backup(target)

        copied_app = create_app(data_root=copy_root)
        copied_client = offline_workbench_client(copied_app)
        checkpoint_values = {
            "messages": [
                HumanMessage(id="current-user", content="Continue"),
                AIMessage(id="current-ai", content="Second answer"),
            ]
        }
        try:
            with patch(
                "workbench_backend.interaction.service.conversation_state",
                return_value=checkpoint_values,
            ):
                registered = copied_client.post(
                    "/v1/agent-interaction/threads",
                    json={"source_surface": "chat", "conversation_id": conversation.id},
                )
                reopened = copied_client.post(
                    "/v1/agent-interaction/threads",
                    json={"source_surface": "chat", "conversation_id": conversation.id},
                )

            self.assertEqual(registered.status_code, 200, registered.text)
            self.assertEqual(reopened.status_code, 200, reopened.text)
            state = copied_client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
            self.assertEqual(
                [(message["type"], message["content"]) for message in state["values"]["messages"]],
                [
                    ("human", "Continue"),
                    ("ai", "First answer"),
                    ("human", "Continue"),
                    ("ai", "Second answer"),
                ],
            )
            copied_binding = copied_app.state.app_store.get_interaction(conversation.id)
            self.assertEqual(copied_binding["graph_thread_id"], conversation.thread_id)
            self.assertEqual(copied_binding["seq"], 2)
            self.assertEqual(marker.read_text(encoding="utf-8"), "untouched")
            source_binding = self.app.state.app_store.get_interaction(conversation.id)
            self.assertEqual(source_binding["snapshot"], faulty_snapshot)
            self.assertEqual(source_binding["seq"], 1)
            self.assertEqual(self.app.state.app_store.get_conversation(conversation.id).thread_id, conversation.thread_id)
        finally:
            close_workbench_sqlite(copied_app, copied_client)

    def test_chat_registration_matches_explicit_ids_and_preserves_unmatched_newer_tool_tail(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_explicit_ids_newer_tail",
            deployment_id=self.deployment_id,
            project_path=str(self.project),
            thread_id="thread_explicit_ids_newer_tail",
            transcript=[
                ChatMessage(id="matched-user", role="user", content="Known question", at=now, run_id="run_known"),
                ChatMessage(id="matched-ai", role="assistant", content="Known answer", at=now, run_id="run_known"),
            ],
            run_ids=["run_known"],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        checkpoint_values = {
            "messages": [
                HumanMessage(id="matched-user", content="Known question"),
                AIMessage(id="matched-ai", content="Known answer"),
                HumanMessage(id="tail-user", content="Checkpoint-only newer question"),
                AIMessage(id="tail-tool-call", content="", tool_calls=[
                    {"id": "call_tail", "name": "lookup", "args": {"q": "tail"}},
                ]),
                ToolMessage(id="tail-tool", tool_call_id="call_tail", name="lookup", content="tail result"),
                AIMessage(id="tail-ai", content="Checkpoint-only newer answer"),
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
        state = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
        ids = [message["id"] for message in state["values"]["messages"]]
        self.assertEqual(
            ids,
            ["matched-user", "matched-ai", "tail-user", "tail-tool-call", "tail-tool", "tail-ai"],
        )
        self.assertEqual(ids.count("tail-tool"), 1)
        self.assertEqual(state["values"]["messages"][ids.index("tail-tool")]["tool_call_id"], "call_tail")


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
            return_value=checkpoint_values,
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
        self.assertEqual(self.app.state.app_store.get_interaction(conversation.id)["seq"], 0)

    def test_chat_registration_repair_does_not_execute_and_continuation_uses_saved_thread(self) -> None:
        now = utc_now()
        conversation = ChatConversation(
            id="chat_repair_continue_saved_thread",
            deployment_id=self.deployment_id,
            project_path=str(self.project),
            thread_id="thread_repair_continue_saved_thread",
            transcript=[
                ChatMessage(role="user", content="Continue", at=now, run_id="run_old"),
                ChatMessage(role="assistant", content="First answer", at=now, run_id="run_old"),
                ChatMessage(role="user", content="Continue", at=now, run_id="run_current"),
                ChatMessage(role="assistant", content="Second answer", at=now, run_id="run_current"),
            ],
            run_ids=["run_old", "run_current"],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_conversation(conversation)
        faulty_snapshot = {
            "messages": [
                {"id": display_id(conversation.id, 1, "assistant"), "type": "ai", "content": "First answer"},
                {"id": display_id(conversation.id, 2, "user"), "type": "human", "content": "Continue"},
                {"id": "current-user", "type": "human", "content": "Continue"},
                {"id": "current-ai", "type": "ai", "content": "Second answer"},
            ],
            "workbench": {"run": None, "conversation_id": conversation.id},
        }
        self.app.state.app_store.register_interaction(
            conversation.id,
            "chat",
            conversation.thread_id,
            conversation.id,
            faulty_snapshot,
        )
        self.app.state.app_store.append_interaction(
            conversation.id,
            [event("values", faulty_snapshot)],
            snapshot=faulty_snapshot,
        )
        checkpoint_values = {
            "messages": [
                HumanMessage(id="current-user", content="Continue"),
                AIMessage(id="current-ai", content="Second answer"),
            ]
        }
        model = self._install_model([AIMessage(id="followup-ai", content="Follow-up answer")])

        with patch.object(self.app.state.harness, "start", wraps=self.app.state.harness.start) as start_spy:
            with patch(
                "workbench_backend.interaction.service.conversation_state",
                return_value=checkpoint_values,
            ):
                registered = self.client.post(
                    "/v1/agent-interaction/threads",
                    json={"source_surface": "chat", "conversation_id": conversation.id},
                )
                reopened = self.client.post(
                    "/v1/agent-interaction/threads",
                    json={"source_surface": "chat", "conversation_id": conversation.id},
                )
            self.assertEqual(registered.status_code, 200, registered.text)
            self.assertEqual(reopened.status_code, 200, reopened.text)
            self.assertEqual(start_spy.call_count, 0)

            started = self._run_start(registered.json()["thread_id"], message_id="followup-user", content="Follow up")
            self.assertEqual(started.status_code, 200, started.text)
            self._wait_state_status(conversation.id, "completed")

        self.assertEqual(model._index, 1)
        self.assertEqual(start_spy.call_count, 1)
        start_request = start_spy.call_args.args[0]
        self.assertEqual(start_request.thread_id, conversation.thread_id)
        stored = self.app.state.app_store.get_conversation(conversation.id)
        self.assertEqual(stored.thread_id, conversation.thread_id)
        self.assertEqual(stored.current_run_id, started.json()["result"]["run_id"])
        state = self.client.get(f"/v1/agent-interaction/threads/{conversation.id}/state").json()
        self.assertIn("Follow up", [message.get("content") for message in state["values"]["messages"]])
        self.assertIn("Follow-up answer", [message.get("content") for message in state["values"]["messages"]])

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
            response = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state")
            self.assertEqual(response.status_code, 200, response.text)
            last = response.json()
            run = last.get("values", {}).get("workbench", {}).get("run") or {}
            if run.get("status") == status:
                return last
            time.sleep(0.05)
        raise AssertionError(f"interaction thread {thread_id} did not reach {status}: {last}")

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
