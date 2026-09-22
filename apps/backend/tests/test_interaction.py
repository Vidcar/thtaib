"""Local interaction HTTP bridge contract tests."""

from __future__ import annotations

import base64
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from workbench_backend.agents.context import BudgetedSummarizationMiddleware
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.inference.capabilities import setup_fingerprint
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import ServerProperties

from tests.scripted_model import (
    RECEIVED_PROMPTS,
    ScriptedChatModel,
    reset_received_prompts,
    set_generate_hold,
    wait_for_generate_hold,
)
from tests.support import close_workbench_sqlite, offline_workbench_client, workbench_client
from tests.test_host_shell import write_marker_command


def _scripted_reply(text: str) -> list[AIMessage]:
    return [AIMessage(content=text)]


def _fake_png_data_url() -> str:
    return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


def _execute_then_reply(command: str, *, call_id: str = "call_interaction_exec") -> list[AIMessage]:
    return [
        AIMessage(content="", tool_calls=[{"name": "execute", "args": {"command": command}, "id": call_id}]),
        AIMessage(content="execution finished"),
    ]


class InteractionApiTests(unittest.TestCase):
    def test_checkpoint_branch_continues_saved_context_in_separate_workspace(self) -> None:
        conversation_id, thread = self._register_chat()
        self._install_model([AIMessage(content="Remembered first answer")])
        response = self._run_start(thread)
        self.assertEqual(response.status_code, 200, response.text)
        completed = self._wait_state(thread)
        source_run = completed["values"]["workbench"]["run"]
        source = self.client.get(f"/v1/chat/conversations/{conversation_id}").json()
        response = self.client.post(f"/v1/chat/conversations/{conversation_id}/branches", json={"source_run_id": source_run["id"]})
        self.assertEqual(response.status_code, 200, response.text)
        branch = response.json()
        self.assertNotEqual(branch["thread_id"], source["thread_id"])
        self.assertNotEqual(branch["project_path"], source["project_path"])
        self.assertEqual(branch["area_id"], source["area_id"])
        from workbench_backend.state.checkpointer import conversation_state
        state = conversation_state(self.app.state.manager.paths.checkpoints_db, branch["thread_id"])
        from workbench_backend.state.checkpointer import open_sqlite_checkpointer
        saver = open_sqlite_checkpointer(self.app.state.manager.paths.checkpoints_db)
        saved = saver.get_tuple({"configurable": {"thread_id": branch["thread_id"]}})
        self.assertIn("Remembered first answer", str(state["messages"]), str(saved))
        self._install_model([AIMessage(content="A separate follow-up")])
        following = self.client.post(f"/v1/chat/conversations/{branch['id']}/start", json={"task": "Continue", "presented_tools": []})
        self.assertEqual(following.status_code, 200, following.text)
        from tests.test_harness import wait_for_run
        finished = wait_for_run(self.client, following.json()["current_run_id"])
        self.assertEqual(finished["status"], "completed", finished)
        self.assertEqual(finished["project_id"], source["project_id"])
        self.assertEqual(Path(finished["project_path"]).resolve(), Path(branch["project_path"]).resolve())
        self.assertNotEqual(Path(finished["project_path"]).resolve(), Path(source["project_path"]).resolve())
        original = self.client.get(f"/v1/chat/conversations/{conversation_id}").json()
        self.assertEqual(original["current_run_id"], source_run["id"])
        self.assertNotIn("A separate follow-up", str(original["transcript"]))

    def test_typed_question_resumes_exact_interrupt_without_approval(self) -> None:
        self._install_model([
            AIMessage(content="", tool_calls=[{"name": "ask_user", "args": {"prompt": "Choose format", "answer_type": "choice", "choices": ["Text", "Code"]}, "id": "question1"}]),
            AIMessage(content="Here is the selected result."),
        ])
        thread = self._register_agent()
        started = self._run_start(thread, metadata={"presented_tools": ["ask_user"]})
        self.assertEqual(started.status_code, 200, started.text)
        state = self._wait_interrupt(thread)
        deadline = time.monotonic() + 10
        while not state["values"]["workbench"]["run"].get("pending_interrupt"):
            if time.monotonic() >= deadline:
                self.fail("Typed question did not become a durable interruption")
            time.sleep(0.01)
            state = self.client.get(f"/v1/agent-interaction/threads/{thread}/state").json()
        interrupt = state["values"]["__interrupt__"][0]
        run = state["values"]["workbench"]["run"]
        self.assertEqual(run["pending_interrupt"]["kind"], "ask_user")
        def answer(value, ident="answer1", interrupt_id=None):
            return self.client.post(f"/v1/agent-interaction/threads/{thread}/commands", json={
                "id": ident, "method": "input.respond", "params": {"namespace": interrupt.get("namespace", []),
                    "interrupt_id": interrupt_id or interrupt["id"], "response": {"answer": value}}})
        self.assertEqual(answer("Text", "stale", "wrong").status_code, 409)
        self.assertEqual(answer("Invalid", "invalid").status_code, 400)
        accepted = answer("Code")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        final = self._wait_state(thread)
        self.assertIsNone(final["values"]["workbench"]["run"].get("pending_interrupt"))
        self.assertEqual(answer("Text", "late").status_code, 409)

    def test_chat_interaction_start_accepts_once_when_bound_deploy_reports_unhealthy(self) -> None:
        self._install_model([AIMessage(content="silver-lake-42")])
        created = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id, "profile_id": self.profile_id},
        )
        self.assertEqual(created.status_code, 200, created.text)
        conversation_id = created.json()["id"]
        registered = self.client.post(
            "/v1/agent-interaction/threads",
            json={"source_surface": "chat", "conversation_id": conversation_id},
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        thread = registered.json()["thread_id"]
        message_id = "desktop-input-silver-lake"
        response = self._run_start(
            thread,
            message_id=message_id,
            content="Packet03 desktop check: remember the code silver-lake-42. Reply with that code only.",
            metadata={"project_path": None},
        )
        self.assertEqual(response.status_code, 200, response.text)
        accepted_run_id = response.json()["result"]["run_id"]
        state = self._wait_state(thread)
        run = state["values"]["workbench"]["run"]
        self.assertEqual(run["id"], accepted_run_id)
        self.assertEqual(run["status"], "completed", run)
        self.assertEqual(run["input_message_id"], message_id)

        duplicate = self._run_start(
            thread,
            command_id="cmd-duplicate",
            message_id=message_id,
            content="Packet03 desktop check: remember the code silver-lake-42. Reply with that code only.",
            metadata={"project_path": None},
        )

        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(duplicate.json()["error"], "duplicate_input")
        conversation = self.client.get(f"/v1/chat/conversations/{conversation_id}").json()
        self.assertEqual(conversation["run_ids"], [run["id"]])
        users = [item for item in conversation["transcript"] if item["role"] == "user"]
        self.assertEqual([item.get("id") for item in users], [message_id])
        self.assertEqual(conversation["queue"], [])

    def test_chat_interaction_start_preserves_missing_deployment_error_without_input(self) -> None:
        created = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id, "profile_id": self.profile_id},
        )
        self.assertEqual(created.status_code, 200, created.text)
        conversation_id = created.json()["id"]
        registered = self.client.post(
            "/v1/agent-interaction/threads",
            json={"source_surface": "chat", "conversation_id": conversation_id},
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        thread = registered.json()["thread_id"]
        self.manager.store.delete_deployment(self.deployment_id)

        response = self._run_start(thread, message_id="missing-deploy-input", metadata={"project_path": None})

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["error"], "deployment_missing")
        state = self.client.get(f"/v1/agent-interaction/threads/{thread}/state")
        self.assertEqual(state.status_code, 200, state.text)
        self.assertIsNone(state.json()["values"]["workbench"].get("run"))
        conversation = self.client.get(f"/v1/chat/conversations/{conversation_id}").json()
        self.assertEqual(conversation["run_ids"], [])
        self.assertEqual(conversation["transcript"], [])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.client = offline_workbench_client(self.app)
        self.anonymous = TestClient(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "interaction-fixture"},
        ).json()["id"]
        self.profile_id = self.client.post(
            "/v1/profiles",
            json={"display_name": "interaction-profile", "startup": {}, "per_request": {}, "agent": {}},
        ).json()["id"]
        self._install_model(_scripted_reply("ready"))

    def tearDown(self) -> None:
        set_generate_hold(None)
        close_workbench_sqlite(self.app, getattr(self, "client", None), getattr(self, "anonymous", None))
        self.tmp.cleanup()

    def _install_model(self, script: list[AIMessage], *, hold: threading.Event | None = None) -> ScriptedChatModel:
        model = ScriptedChatModel(script, hold=hold)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return model

        # Keep the create_app-installed harness so the interaction observer remains wired.
        self.app.state.harness._model_factory = factory
        return model

    def _register_agent(self) -> str:
        response = self.client.post("/v1/agent-interaction/threads", json={"source_surface": "agent"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["thread_id"]

    def _register_chat(self) -> tuple[str, str]:
        created = self.client.post(
            "/v1/chat/conversations",
            json={
                "deployment_id": self.deployment_id,
                "profile_id": self.profile_id,
                "project_path": str(self.project),
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        conversation_id = created.json()["id"]
        registered = self.client.post(
            "/v1/agent-interaction/threads",
            json={"source_surface": "chat", "conversation_id": conversation_id},
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        return conversation_id, registered.json()["thread_id"]

    def _run_start(
        self,
        thread_id: str,
        *,
        command_id: str = "cmd-start",
        message_id: str = "input-1",
        content: Any = "hello",
        metadata: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        assistant_id: str | None = "local-ai-workbench",
    ) -> Any:
        body: dict[str, Any] = {
            "id": command_id,
            "method": "run.start",
            "params": {
                "assistant_id": assistant_id,
                "input": {"messages": [{"type": "human", "id": message_id, "content": content}]},
                "metadata": {"workbench": {
                    "deployment_id": self.deployment_id,
                    "profile_id": self.profile_id,
                    "project_path": str(self.project),
                    "presented_tools": [],
                    **(metadata or {}),
                }},
            },
        }
        if config is not None:
            body["params"]["config"] = config
        return self.client.post(f"/v1/agent-interaction/threads/{thread_id}/commands", json=body)

    def _wait_state(self, thread_id: str, status: str = "completed", *, timeout: float = 20.0) -> dict[str, Any]:
        deadline = time.time() + timeout
        body: dict[str, Any] = {}
        while time.time() < deadline:
            response = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state")
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            run = body.get("values", {}).get("workbench", {}).get("run") or {}
            if run.get("status") == status:
                return body
            time.sleep(0.05)
        raise AssertionError(f"interaction thread {thread_id} did not reach {status}: {body}")

    def _wait_interrupt(self, thread_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
        deadline = time.time() + timeout
        body: dict[str, Any] = {}
        while time.time() < deadline:
            response = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state")
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            if body.get("tasks"):
                return body
            run = body.get("values", {}).get("workbench", {}).get("run") or {}
            if run.get("status") in {"completed", "cancelled", "failed"}:
                raise AssertionError(f"run finished before interrupt: {body}")
            time.sleep(0.05)
        raise AssertionError(f"interaction thread {thread_id} did not interrupt: {body}")

    def _events_after(self, thread_id: str, since: int = 0) -> list[dict[str, Any]]:
        return self.app.state.app_store.interaction_events_after(thread_id, since)

    def _set_server_props(self, *, n_ctx: int = 8192, vision: bool = False) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        self.manager.store.put_deployment(
            deployment.model_copy(
                update={
                    "server_props": ServerProperties(
                        fetched=utc_now(),
                        source_url="http://127.0.0.1:9/props",
                        model_alias="interaction-fixture",
                        n_ctx=n_ctx,
                        chat_template_caps={
                            "supports_system_role": True,
                            "supports_tools": True,
                            "supports_tool_calls": True,
                            "supports_typed_content": True,
                        },
                        modalities={"vision": vision},
                    )
                }
            )
        )

    def _record_capabilities(self, *capabilities: str) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        fingerprint = setup_fingerprint(deployment)
        for index, capability in enumerate(capabilities):
            self.manager.store.put_capability_evidence(
                {
                    "schema_version": 1,
                    "id": f"probe_{capability}_{index}",
                    "deployment_id": deployment.id,
                    "capability": capability,
                    "status": "passed",
                    "fingerprint": fingerprint,
                    "setup": {},
                    "tested_at": utc_now(),
                    "inputs": {},
                    "observations": {},
                }
            )

    def _schema(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "name": "AnswerShape",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
        }



    def test_command_content_list_preserves_text_once_image_order_and_tools_off(self) -> None:
        self._set_server_props(vision=True)
        reset_received_prompts()
        model = self._install_model(_scripted_reply("listed image answer"))
        thread_id = self._register_agent()
        image_url = _fake_png_data_url()
        content = [
            {"type": "text", "text": "Describe this command image."},
            {"type": "image_url", "image_url": {"url": image_url, "detail": "auto"}},
        ]

        response = self._run_start(
            thread_id,
            command_id="content-list",
            message_id="content-list-input",
            content=content,
            metadata={"presented_tools": []},
        )
        self.assertEqual(response.status_code, 200, response.text)
        state = self._wait_state(thread_id)

        run = state["values"]["workbench"]["run"]
        self.assertEqual(run["presented_tools"], [])
        self.assertEqual(run.get("task"), "")
        self.assertEqual(run.get("content_blocks"), content)
        self.assertEqual(model.bound_tools, [])
        self.assertTrue(RECEIVED_PROMPTS)
        self.assertEqual(RECEIVED_PROMPTS[-1].count("Describe this command image."), 1)
        human = next(message for message in state["values"]["messages"] if message["id"] == "content-list-input")
        self.assertEqual(human["content"], content)
        self.assertEqual(human["content"][0]["type"], "text")
        self.assertEqual(human["content"][1]["type"], "image_url")
        self.assertTrue(any(message.get("content") == "listed image answer" for message in state["values"]["messages"]))

    def test_chat_content_blocks_preserved_in_interaction_state_with_tools_off(self) -> None:
        self._set_server_props(vision=True)
        model = self._install_model(_scripted_reply("vision answer"))
        conversation_id, thread_id = self._register_chat()
        image_url = _fake_png_data_url()
        blocks = [{"type": "image_url", "image_url": {"url": image_url, "detail": "auto"}}]

        response = self.client.post(
            f"/v1/chat/conversations/{conversation_id}/start",
            json={
                "task": "Describe this local image.",
                "input_message_id": "content-input",
                "content_blocks": blocks,
                "presented_tools": [],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        state = self._wait_state(thread_id)

        run = state["values"]["workbench"]["run"]
        self.assertEqual(run["presented_tools"], [])
        self.assertEqual(run.get("content_blocks"), blocks)
        self.assertEqual(model.bound_tools, [])
        human = next(message for message in state["values"]["messages"] if message["id"] == "content-input")
        self.assertEqual(human["content"], [{"type": "text", "text": "Describe this local image."}] + blocks)
        self.assertTrue(any(message.get("content") == "vision answer" for message in state["values"]["messages"]))

    def test_command_structured_result_validation_updates_interaction_state(self) -> None:
        self._record_capabilities("tools", "structured_tools", "structured_tools_with_tools")
        self._install_model([
            AIMessage(
                content="",
                tool_calls=[{"name": "AnswerShape", "args": {"answer": "validated"}, "id": "call_answer"}],
            )
        ])
        thread_id = self._register_agent()

        response = self._run_start(
            thread_id,
            command_id="structured",
            message_id="structured-input",
            content="Return a structured answer.",
            metadata={"presented_tools": ["echo"], "output_schema": self._schema()},
        )
        self.assertEqual(response.status_code, 200, response.text)
        state = self._wait_state(thread_id)

        run = state["values"]["workbench"]["run"]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["structured_output"]["validation_status"], "valid")
        self.assertEqual(run["structured_output"]["result"], {"answer": "validated"})
        answer_messages = [message for message in state["values"]["messages"] if message.get("tool_calls")]
        self.assertEqual(answer_messages[-1]["tool_calls"][0]["id"], "call_answer")

    def test_command_context_preflight_rejects_before_second_execution(self) -> None:
        self._set_server_props(n_ctx=32768, vision=False)
        model = self._install_model([AIMessage(content="first retained"), AIMessage(content="should not run")])
        thread_id = self._register_agent()
        first = self._run_start(
            thread_id,
            command_id="context-first",
            message_id="context-input-1",
            content="long-context " + ("older material " * 900),
            metadata={"presented_tools": []},
        )
        self.assertEqual(first.status_code, 200, first.text)
        before = self._wait_state(thread_id)
        before_messages = list(before["values"]["messages"])
        self._set_server_props(n_ctx=512, vision=False)

        rejected = self._run_start(
            thread_id,
            command_id="context-second",
            message_id="context-input-2",
            content="Continue briefly.",
            metadata={"presented_tools": []},
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["error"], "context_capacity_exceeded")
        after = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state").json()
        self.assertEqual(after["values"]["messages"], before_messages)
        self.assertEqual(model._index, 1)

    def test_command_compaction_summary_is_not_archived_as_assistant_answer(self) -> None:
        self._set_server_props(n_ctx=16384, vision=False)
        self._install_model([
            AIMessage(content="first answer"),
            AIMessage(content="summary should stay internal"),
            AIMessage(content="second answer"),
        ])
        thread_id = self._register_agent()
        with patch(
            "workbench_backend.agents.harness.BudgetedSummarizationMiddleware",
            wraps=BudgetedSummarizationMiddleware,
        ) as middleware_factory:
            first = self._run_start(
                thread_id,
                command_id="compact-first",
                message_id="compact-input-1",
                content="Preserve this earlier material. " + ("historic detail " * 1100),
                metadata={"presented_tools": []},
            )
            self.assertEqual(first.status_code, 200, first.text)
            self._wait_state(thread_id)
            previous_middleware_count = middleware_factory.call_count
            second = self._run_start(
                thread_id,
                command_id="compact-second",
                message_id="compact-input-2",
                content="Now preserve the important details from this later material. " + ("recent detail " * 1100),
                metadata={"presented_tools": []},
            )
            self.assertEqual(second.status_code, 200, second.text)
            state = self._wait_state(thread_id)

        run = state["values"]["workbench"]["run"]
        self.assertEqual(run["status"], "completed", run.get("error"))
        self.assertEqual(run["presented_tools"], [])
        self.assertEqual(middleware_factory.call_count, previous_middleware_count + 1)
        self.assertTrue(any(event["kind"] == "context_compacted" for event in run["events"]))
        contents = [message.get("content") for message in state["values"]["messages"]]
        self.assertIn("second answer", contents)
        self.assertNotIn("summary should stay internal", contents)


    def test_chat_command_reasoning_only_assistant_archives_stable_id_and_blocks(self) -> None:
        reasoning_blocks = [{"type": "reasoning", "reasoning": "kept as an internal rationale"}]
        self._install_model([AIMessage(id="reasoning-ai-id", content=reasoning_blocks)])
        conversation_id, thread_id = self._register_chat()

        started = self.client.post(
            f"/v1/chat/conversations/{conversation_id}/start",
            json={"task": "Think briefly and answer through reasoning only.", "input_message_id": "reasoning-user-id"},
        )
        self.assertEqual(started.status_code, 200, started.text)
        state = self._wait_state(thread_id)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation_id}")
        self.assertEqual(fetched.status_code, 200, fetched.text)

        messages = state["values"]["messages"]
        archived = next(message for message in messages if message.get("id") == "reasoning-ai-id")
        self.assertEqual(archived["type"], "ai")
        self.assertEqual(archived["content"], reasoning_blocks)
        assistant_rows = [row for row in fetched.json()["transcript"] if row["role"] == "assistant"]
        self.assertEqual(len(assistant_rows), 1)
        self.assertEqual(assistant_rows[0]["id"], "reasoning-ai-id")
        self.assertEqual(assistant_rows[0]["content"], "")
        self.assertEqual(assistant_rows[0]["content_blocks"], reasoning_blocks)

    def test_agent_command_preserves_input_id_and_two_turn_context(self) -> None:
        thread_id = self._register_agent()
        self._install_model([AIMessage(content="first answer"), AIMessage(content="second answer")])

        first = self._run_start(thread_id, command_id="one", message_id="native-user-1", content="First")
        self.assertEqual(first.status_code, 200, first.text)
        first_result = first.json()["result"]
        self.assertIsInstance(first_result["applied_through_seq"], int)
        first_state = self._wait_state(thread_id)
        first_values = first_state["values"]
        self.assertEqual(first_values["workbench"]["run"]["input_message_id"], "native-user-1")
        self.assertEqual(first_values["workbench"]["run"]["thread_id"], self.app.state.app_store.get_interaction(thread_id)["graph_thread_id"])
        self.assertTrue(any(m["id"] == "native-user-1" and m["type"] == "human" for m in first_values["messages"]))
        self.assertTrue(any(m["type"] == "ai" and m["content"] == "first answer" for m in first_values["messages"]))

        second = self._run_start(thread_id, command_id="two", message_id="native-user-2", content="Second")
        self.assertEqual(second.status_code, 200, second.text)
        second_state = self._wait_state(thread_id)
        contents = [m.get("content") for m in second_state["values"]["messages"]]
        self.assertIn("First", contents)
        self.assertIn("first answer", contents)
        self.assertIn("Second", contents)
        self.assertIn("second answer", contents)
        persisted = self.app.state.app_store.get_interaction(thread_id)
        self.assertGreaterEqual(persisted["seq"], second_state["interaction_cursor"])

    def test_chat_registration_and_command_use_existing_setup_metadata(self) -> None:
        conversation_id, thread_id = self._register_chat()
        self._install_model(_scripted_reply("chat answer"))

        response = self._run_start(thread_id, message_id="chat-input-1", content="Chat turn")
        self.assertEqual(response.status_code, 200, response.text)
        state = self._wait_state(thread_id)

        run = state["values"]["workbench"]["run"]
        self.assertEqual(run["source_surface"], "chat")
        self.assertEqual(state["values"]["workbench"]["conversation_id"], conversation_id)
        self.assertTrue(any(m["id"] == "chat-input-1" and m["content"] == "Chat turn" for m in state["values"]["messages"]))
        self.assertTrue(any(m["type"] == "ai" and m["content"] == "chat answer" for m in state["values"]["messages"]))

    def test_installed_sdk_optimistic_message_metadata_is_empty_only(self) -> None:
        thread_id = self._register_agent()
        body = {"id": 2, "method": "run.start", "params": {
            "input": {"messages": [{"type": "human", "id": "optimistic-input", "content": "Hello",
                                     "additional_kwargs": {}, "response_metadata": {}}]},
            "metadata": {"workbench": {"deployment_id": self.deployment_id, "presented_tools": []}},
            "multitaskStrategy": "reject", "assistant_id": "_",
        }}
        message = body["params"]["input"]["messages"][0]
        for key in ("additional_kwargs", "response_metadata"):
            message[key] = {"untrusted": True}
            rejected = self.client.post(f"/v1/agent-interaction/threads/{thread_id}/commands", json=body)
            self.assertEqual(rejected.status_code, 400, rejected.text)
            message[key] = {}
        accepted = self.client.post(f"/v1/agent-interaction/threads/{thread_id}/commands", json=body)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        state = self._wait_state(thread_id)
        self.assertEqual(sum(m["id"] == "optimistic-input" for m in state["values"]["messages"]), 1)

    def test_control_fields_foreign_graph_overrides_and_invalid_filters_are_rejected(self) -> None:
        thread_id = self._register_agent()
        enveloped_cases = [
            self._run_start(thread_id, metadata={"task": "forbidden"}),
            self._run_start(thread_id, metadata={"thread_id": "foreign"}),
            self._run_start(thread_id, metadata={"source_surface": "chat"}),
            self._run_start(thread_id, metadata={"input_message_id": "foreign"}),
            self._run_start(thread_id, config={"configurable": {"thread_id": "foreign"}}),
            self._run_start(thread_id, assistant_id="foreign-graph"),
            self.client.post(f"/v1/agent-interaction/threads/{thread_id}/commands", json={"id": "bad", "method": "graph.update", "params": {}}),
            self.client.post(f"/v1/agent-interaction/threads/{thread_id}/stream/events", json={"channels": ["unknown"]}),
            self.client.post(f"/v1/agent-interaction/threads/{thread_id}/stream/events", json={"channels": ["values"], "namespaces": ["bad"]}),
            self.client.post(f"/v1/agent-interaction/threads/{thread_id}/stream/events", json={"channels": ["values"], "since": -1}),
            self.client.post(f"/v1/agent-interaction/threads/{thread_id}/stream/events", json={"channels": ["values"], "version": "v2"}),
        ]
        for response in enveloped_cases:
            self.assertIn(response.status_code, {400, 409}, response.text)
            payload = response.json()
            if "type" in payload:
                self.assertEqual(payload["type"], "error")
            else:
                self.assertIn("code", payload)

        missing = self.client.get("/v1/agent-interaction/threads/missing/state")
        self.assertEqual(missing.status_code, 404)

    def test_duplicate_input_and_active_run_rejections_do_not_start_second_execution(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        model = self._install_model([AIMessage(content="held"), AIMessage(content="extra")], hold=hold)
        thread_id = self._register_agent()

        accepted = self._run_start(thread_id, command_id="first", message_id="active-input", content="Hold")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        wait_for_generate_hold()
        duplicate = self._run_start(thread_id, command_id="duplicate", message_id="active-input", content="Hold")
        other = self._run_start(thread_id, command_id="other", message_id="other-input", content="Other")
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(duplicate.json()["error"], "duplicate_input")
        self.assertEqual(other.status_code, 409, other.text)
        self.assertEqual(other.json()["error"], "run_active")
        hold.set()
        self._wait_state(thread_id)

        run_ids = [item["id"] for item in self.client.get("/v1/agent-runs").json()]
        self.assertEqual(len(run_ids), 1)
        self.assertEqual(model._index, 1)

    def test_unauthenticated_interaction_post_state_and_stream_are_rejected(self) -> None:
        thread_id = self._register_agent()
        for method, path, kwargs in [
            ("post", "/v1/agent-interaction/threads", {"json": {"source_surface": "agent"}}),
            ("get", f"/v1/agent-interaction/threads/{thread_id}/state", {}),
            ("post", f"/v1/agent-interaction/threads/{thread_id}/stream/events", {"json": {"channels": ["not-a-channel"]}}),
        ]:
            response = getattr(self.anonymous, method)(path, **kwargs)
            self.assertEqual(response.status_code, 401, response.text)
            self.assertEqual(response.json()["code"], "unauthenticated")

        wrong = workbench_client(self.app, token="wrong")
        response = wrong.get(f"/v1/agent-interaction/threads/{thread_id}/state")
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["code"], "invalid_token")

    def test_register_after_direct_chat_interrupt_recovers_native_response_target(self) -> None:
        marker = self.project / "late-registration.txt"
        self._install_model(_execute_then_reply(write_marker_command(marker.name)))
        created = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.deployment_id, "project_path": str(self.project),
        })
        self.assertEqual(created.status_code, 200, created.text)
        conversation_id = created.json()["id"]
        started = self.client.post(f"/v1/chat/conversations/{conversation_id}/start", json={
            "task": "Create the marker", "presented_tools": ["execute"],
        })
        self.assertEqual(started.status_code, 200, started.text)
        run_id = started.json()["current_run_id"]
        deadline = time.monotonic() + 10
        while True:
            saved = self.app.state.harness.get_run(run_id)
            if saved.pending_interrupt:
                break
            if time.monotonic() >= deadline:
                self.fail("Direct Chat did not reach its durable approval")
            time.sleep(0.01)
        self.assertFalse(marker.exists())
        registered = self.client.post("/v1/agent-interaction/threads", json={
            "source_surface": "chat", "conversation_id": conversation_id,
        })
        self.assertEqual(registered.status_code, 200, registered.text)
        thread_id = registered.json()["thread_id"]
        state = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state").json()
        self.assertTrue(state["tasks"], "reopening a durable approval must expose its SDK response target")
        pending = state["tasks"][0]["interrupts"][0]
        self.assertEqual(pending["id"], saved.pending_interrupt.interrupt_id)
        self.assertEqual(state["values"]["workbench"]["interrupt_run_id"], run_id)
        approved = self.client.post(f"/v1/agent-interaction/threads/{thread_id}/commands", json={
            "id": "approve-recovered", "method": "input.respond", "params": {
                "interrupt_id": pending["id"], "namespace": pending.get("namespace", []),
                "response": {"decisions": [{"type": "approve"}]},
            },
        })
        self.assertEqual(approved.status_code, 200, approved.text)
        finished = self._wait_state(thread_id)
        self.assertEqual(finished["tasks"], [])
        self.assertTrue(marker.exists())

    def test_native_approval_identity_namespace_and_duplicates(self) -> None:
        marker = self.project / "approved-marker.txt"
        self._install_model(_execute_then_reply(write_marker_command(marker.name)))
        thread_id = self._register_agent()

        started = self._run_start(
            thread_id,
            message_id="approval-input",
            content="Run the approved command",
            metadata={"presented_tools": ["execute"]},
        )
        self.assertEqual(started.status_code, 200, started.text)
        interrupted = self._wait_interrupt(thread_id)
        task = interrupted["tasks"][0]
        interrupt = task["interrupts"][0]
        ident = interrupt["id"]
        namespace = interrupt.get("namespace", [])
        run_id = interrupted["values"]["workbench"]["run"]["id"]

        wrong_id = self.client.post(
            f"/v1/agent-interaction/threads/{thread_id}/commands",
            json={"id": "wrong-id", "method": "input.respond", "params": {
                "namespace": namespace,
                "interrupt_id": f"{ident}-wrong",
                "response": {"decisions": [{"type": "approve"}]},
            }},
        )
        self.assertEqual(wrong_id.status_code, 409, wrong_id.text)
        self.assertFalse(marker.exists())
        wrong_ns = self.client.post(
            f"/v1/agent-interaction/threads/{thread_id}/commands",
            json={"id": "wrong-ns", "method": "input.respond", "params": {
                "namespace": ["foreign"],
                "interrupt_id": ident,
                "response": {"decisions": [{"type": "approve"}]},
            }},
        )
        self.assertEqual(wrong_ns.status_code, 409, wrong_ns.text)
        self.assertFalse(marker.exists())

        approved = self.client.post(
            f"/v1/agent-interaction/threads/{thread_id}/commands",
            json={"id": "approve", "method": "input.respond", "params": {
                "namespace": namespace,
                "interrupt_id": ident,
                "response": {"decisions": [{"type": "approve"}]},
            }},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["result"]["run_id"], run_id)
        state = self._wait_state(thread_id)
        self.assertEqual(state["tasks"], [])
        self.assertTrue(marker.exists())

        duplicate = self.client.post(
            f"/v1/agent-interaction/threads/{thread_id}/commands",
            json={"id": "duplicate-approve", "method": "input.respond", "params": {
                "namespace": namespace,
                "interrupt_id": ident,
                "response": {"decisions": [{"type": "approve"}]},
            }},
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(duplicate.json()["error"], "stale_interrupt")
        self.assertEqual(marker.stat().st_size, 0 if os.name == "nt" else marker.stat().st_size)


if __name__ == "__main__":
    unittest.main()
