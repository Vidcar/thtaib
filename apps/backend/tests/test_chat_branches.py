"""Chat branch and retry regressions."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage

from tests.scripted_model import (
    RECEIVED_PROMPTS,
    ScriptedChatModel,
    reset_received_prompts,
    set_generate_hold,
    wait_for_generate_hold,
)
from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.lab.store import LabStore
from workbench_backend.state.checkpointer import conversation_state, open_sqlite_checkpointer


class ChatBranchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "seed.txt").write_text("original", encoding="utf-8")
        self.app = create_app(data_root=self.root)
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "branch-fixture"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def install_model(self, script: list[AIMessage]) -> None:
        model = ScriptedChatModel(script)

        def factory(_run: AgentRun, _sink: list[dict]) -> ScriptedChatModel:
            return model

        self.app.state.harness._model_factory = factory

    def create_conversation(self) -> dict:
        response = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id, "project_path": str(self.project)},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def start_turn(self, conversation_id: str, task: str, **extra: object) -> dict:
        response = self.client.post(
            f"/v1/chat/conversations/{conversation_id}/start",
            json={"task": task, "presented_tools": [], **extra},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return wait_for_run(self.client, response.json()["current_run_id"])

    def wait_interaction_interrupt(self, thread_id: str) -> dict:
        deadline = time.monotonic() + 10
        body: dict = {}
        while time.monotonic() < deadline:
            response = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state")
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            if body.get("values", {}).get("workbench", {}).get("run", {}).get("pending_interrupt"):
                return body
            time.sleep(0.05)
        raise AssertionError(f"interrupt not observed: {body}")

    def test_retry_branch_clones_previous_checkpoint_and_leaves_original_unchanged(self) -> None:
        self.install_model([AIMessage(content="first answer"), AIMessage(content="second answer")])
        conversation = self.create_conversation()
        first = self.start_turn(conversation["id"], "first task")
        second = self.start_turn(conversation["id"], "second task")

        response = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/branches",
            json={"source_run_id": second["id"], "mode": "retry", "acknowledge_repeated_effects": True},
        )

        self.assertEqual(response.status_code, 200, response.text)
        branch = response.json()
        self.assertEqual(branch["source_conversation_id"], conversation["id"])
        self.assertEqual(branch["source_run_id"], second["id"])
        self.assertIn(branch["source_checkpoint_id"], first["checkpoint_ids"])
        self.assertEqual(branch["branch_head_checkpoint_id"], branch["source_checkpoint_id"])
        self.assertEqual(branch["run_ids"], [first["id"]])
        self.assertEqual(branch["draft"]["content"], "second task")
        branch_state = conversation_state(self.app.state.manager.paths.checkpoints_db, branch["thread_id"])
        self.assertIn("first answer", str(branch_state.get("messages")))
        self.assertNotIn("second answer", str(branch_state.get("messages")))

        original = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(original["run_ids"], [first["id"], second["id"]])
        self.assertNotEqual(original["thread_id"], branch["thread_id"])
        self.assertNotIn(branch["id"], [conversation["id"]])

    def test_branch_fault_cleans_workspace_record_directory_and_checkpoint_thread(self) -> None:
        self.install_model([AIMessage(content="answer")])
        conversation = self.create_conversation()
        run = self.start_turn(conversation["id"], "task")
        real_put_workspace = LabStore.put_workspace

        def put_then_fail(store, workspace):
            real_put_workspace(store, workspace)
            raise RuntimeError("boom after workspace record")

        with patch("workbench_backend.chat.branches.new_id", side_effect=["chat_fail", "thread_fail", "ws_fail"]):
            with patch.object(LabStore, "put_workspace", side_effect=put_then_fail, autospec=True):
                with self.assertRaises(RuntimeError):
                    self.client.post(
                        f"/v1/chat/conversations/{conversation['id']}/branches",
                        json={"source_run_id": run["id"]},
                    )

        self.assertIsNone(self.app.state.lab.store.get_workspace("ws_fail"))
        self.assertFalse((self.app.state.manager.paths.workspaces / "ws_fail").exists())
        saver = open_sqlite_checkpointer(self.app.state.manager.paths.checkpoints_db)
        self.assertEqual(list(saver.list({"configurable": {"thread_id": "thread_fail", "checkpoint_ns": ""}})), [])

    def test_archived_source_conversation_can_still_create_dependency_branch(self) -> None:
        self.install_model([AIMessage(content="archived answer")])
        conversation = self.create_conversation()
        run = self.start_turn(conversation["id"], "archived task")
        archived = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/archive",
            json={"archived": True},
        )
        self.assertEqual(archived.status_code, 200, archived.text)

        actions = self.client.get(
            f"/v1/chat/conversations/{conversation['id']}/replies/{run['id']}/actions"
        )
        self.assertEqual(actions.status_code, 200, actions.text)
        self.assertTrue(actions.json()["branch_available"])
        response = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/branches",
            json={"source_run_id": run["id"]},
        )

        self.assertEqual(response.status_code, 200, response.text)
        branch = response.json()
        self.assertEqual(branch["source_conversation_id"], conversation["id"])
        self.assertFalse(branch["archived"])

    def test_regenerate_reports_checkpoint_evidence_available(self) -> None:
        self.install_model([AIMessage(content="answer")])
        conversation = self.create_conversation()
        run = self.start_turn(conversation["id"], "task")

        response = self.client.get(
            f"/v1/chat/conversations/{conversation['id']}/replies/{run['id']}/actions"
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["regenerate_available"], body)
        self.assertIsNone(body["regenerate_reason"])

    def test_reply_actions_inspect_checkpoint_without_starting_runtime(self) -> None:
        self.install_model([AIMessage(content="answer")])
        conversation = self.create_conversation()
        run = self.start_turn(conversation["id"], "task")

        def fail_model_factory(_run, _sink):
            raise AssertionError("reply actions must not construct a model")

        self.app.state.harness._model_factory = fail_model_factory
        with patch.object(
            self.app.state.manager,
            "ensure_deployment_ready",
            side_effect=AssertionError("reply actions must not start deployment"),
        ):
            with patch(
                "workbench_backend.agents.harness_backend.harness_scratch_root",
                wraps=lambda *_args: self.root / "inspection-must-not-create",
            ):
                with patch(
                    "workbench_backend.agents.harness.materialize_onto_backend",
                    side_effect=AssertionError("reply actions must not materialize knowledge"),
                ):
                    response = self.client.get(
                        f"/v1/chat/conversations/{conversation['id']}/replies/{run['id']}/actions"
                    )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["regenerate_available"], body)
        self.assertIsNone(body["regenerate_reason"])
        self.assertFalse((self.root / "inspection-must-not-create").exists())

    def test_regenerate_unavailable_without_final_project_snapshot(self) -> None:
        self.install_model([AIMessage(content="answer")])
        conversation = self.create_conversation()
        run = AgentRun.model_validate(self.start_turn(conversation["id"], "task"))
        self.app.state.app_store.put_run(run.model_copy(update={"final_snapshot_id": None}))
        self.app.state.harness._runs[run.id] = run.model_copy(update={"final_snapshot_id": None})

        response = self.client.get(
            f"/v1/chat/conversations/{conversation['id']}/replies/{run.id}/actions"
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["regenerate_available"])
        self.assertEqual(body["regenerate_reason"], "This turn has no matching retained project snapshot.")

    def test_regenerate_replaces_answer_in_branch_without_new_human_or_tool_effects(self) -> None:
        self.install_model([
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "write_file", "args": {"file_path": "/written.txt", "content": "original effect"}, "id": "write_1"},
                    {"name": "execute", "args": {"command": "echo original"}, "id": "exec_1"},
                ],
            ),
            AIMessage(content="original answer"),
            AIMessage(content="regenerated answer"),
        ])
        conversation = self.create_conversation()
        run = self.start_turn(conversation["id"], "use tools then answer")
        self.assertEqual(run["status"], "completed", run)
        self.assertEqual(len(run["tool_invocations"]), 2)

        response = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/branches",
            json={"source_run_id": run["id"], "mode": "regenerate"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        branch = response.json()
        regen_run_id = branch["current_run_id"]
        regen = wait_for_run(self.client, regen_run_id)
        self.assertEqual(regen["status"], "completed", regen)
        self.assertEqual(regen["presented_tools"], [])
        self.assertEqual(regen["tool_invocations"], [])
        self.assertEqual(regen["parent_run_id"], run["id"])
        self.app.state.chat.observe_terminal_run(AgentRun.model_validate(regen))
        branch = self.client.get(f"/v1/chat/conversations/{branch['id']}").json()
        messages = branch["transcript"]
        self.assertEqual([item["role"] for item in messages].count("user"), 1)
        self.assertEqual([item["role"] for item in messages].count("assistant"), 1)
        self.assertEqual(messages[-1]["content"], "regenerated answer")
        self.assertNotIn("original answer", str(messages))
        state = conversation_state(self.app.state.manager.paths.checkpoints_db, branch["thread_id"])
        self.assertEqual(sum(1 for item in state.get("messages", []) if getattr(item, "type", None) == "human"), 1)
        original = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertIn("original answer", str(original["transcript"]))
        self.assertNotIn("regenerated answer", str(original["transcript"]))

    def test_regenerate_final_store_failure_preserves_accepted_run_resources(self) -> None:
        self.install_model([AIMessage(content="original answer"), AIMessage(content="regenerated answer")])
        conversation = self.create_conversation()
        run = self.start_turn(conversation["id"], "task")
        app_store = self.app.state.app_store
        real_put = type(app_store).put_conversation

        def put_or_fail(store, item):
            saved = real_put(store, item)
            if item.id == "chat_regen_fail" and item.current_run_id:
                raise RuntimeError("final branch store failed")
            return saved

        with patch("workbench_backend.chat.branches.new_id", side_effect=["chat_regen_fail", "thread_regen_fail", "ws_regen_fail"]):
            with patch.object(type(app_store), "put_conversation", side_effect=put_or_fail, autospec=True):
                with self.assertRaises(RuntimeError):
                    self.client.post(
                        f"/v1/chat/conversations/{conversation['id']}/branches",
                        json={"source_run_id": run["id"], "mode": "regenerate"},
                    )

        staged = self.app.state.app_store.get_conversation("chat_regen_fail")
        self.assertIsNotNone(staged)
        assert staged is not None
        accepted = [
            item for item in self.app.state.harness.list_runs()
            if item.parent_run_id == run["id"] and item.thread_id == "thread_regen_fail"
        ]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(staged.current_run_id, accepted[0].id)
        self.assertTrue((self.app.state.manager.paths.workspaces / "ws_regen_fail").exists())
        wait_for_run(self.client, accepted[0].id)
        saver = open_sqlite_checkpointer(self.app.state.manager.paths.checkpoints_db)
        self.assertTrue(list(saver.list({"configurable": {"thread_id": "thread_regen_fail", "checkpoint_ns": ""}})))

    def test_regenerate_branch_projection_excludes_source_pending_answer_writes(self) -> None:
        self.install_model([
            AIMessage(content="first answer", additional_kwargs={"reasoning_content": "First reasoning"}),
            AIMessage(content="original second answer", additional_kwargs={"reasoning_content": "Second reasoning"}),
            AIMessage(content="replacement answer", additional_kwargs={"reasoning_content": "Replacement reasoning"}),
        ])
        conversation = self.create_conversation()
        first = self.start_turn(conversation["id"], "first task", input_message_id="first-input")
        second = self.start_turn(conversation["id"], "second task", input_message_id="second-input")
        self.client.get(f"/v1/chat/conversations/{conversation['id']}")
        # Real older conversations retain answer text without the native ID or
        # reasoning blocks. Branching must still align this readable archive.
        saved = self.app.state.chat.store.get(conversation["id"])
        for message in saved.transcript:
            if message.role == "assistant":
                message.id = None
                message.content_blocks = None
        self.app.state.chat.store.put(saved)
        continuation = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/branches",
            json={"source_run_id": second["id"]},
        )
        self.assertEqual(continuation.status_code, 200, continuation.text)

        hold = threading.Event()
        set_generate_hold(hold)
        try:
            regenerated = self.client.post(
                f"/v1/chat/conversations/{continuation.json()['id']}/branches",
                json={"source_run_id": second["id"], "mode": "regenerate"},
            )
            self.assertEqual(regenerated.status_code, 200, regenerated.text)
            branch = regenerated.json()
            wait_for_generate_hold()
            registered = self.client.post(
                "/v1/agent-interaction/threads",
                json={"source_surface": "chat", "conversation_id": branch["id"]},
            )
            self.assertEqual(registered.status_code, 200, registered.text)
            pending_state = self.client.get(f"/v1/agent-interaction/threads/{branch['id']}/state").json()
            before = pending_state["values"]["messages"]
            self.assertEqual([message["type"] for message in before], ["human", "ai", "human"])
            self.assertNotIn("original second answer", str(before))
            self.assertIn("First reasoning", str(before))
        finally:
            hold.set()
            set_generate_hold(None)

        result = wait_for_run(self.client, branch["current_run_id"])
        self.assertEqual(result["status"], "completed", result)
        final = self.client.get(f"/v1/agent-interaction/threads/{branch['id']}/state").json()["values"]["messages"]
        self.assertEqual([message["type"] for message in final], ["human", "ai", "human", "ai"])
        self.assertNotIn("original second answer", str(final))
        self.assertIn("Replacement reasoning", str(final))
        self.assertEqual(final, self.app.state.app_store.get_interaction(branch["id"])["snapshot"]["messages"])
        original = conversation_state(self.app.state.manager.paths.checkpoints_db, first["thread_id"])
        self.assertIn("original second answer", str(original["messages"]))

    def test_regenerate_malicious_tool_call_has_no_execute_effect(self) -> None:
        marker = self.project / "malicious.txt"
        self.install_model([
            AIMessage(content="original answer"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "execute",
                        "args": {"command": f"echo bad > {marker.name}"},
                        "id": "malicious_execute",
                    }
                ],
            ),
            AIMessage(content="safe after blocked tool"),
        ])
        conversation = self.create_conversation()
        run = self.start_turn(conversation["id"], "task")

        response = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/branches",
            json={"source_run_id": run["id"], "mode": "regenerate"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        regen = wait_for_run(self.client, response.json()["current_run_id"])

        self.assertEqual(regen["presented_tools"], [])
        self.assertFalse(marker.exists())
        tool_results = [event["detail"] for event in regen["events"] if event["kind"] == "tool_result"]
        self.assertIn("Tools are explicitly off", str(tool_results))

    def test_regenerate_uses_latest_source_answer_checkpoint_in_multi_turn_thread(self) -> None:
        reset_received_prompts()
        self.install_model([
            AIMessage(content="first answer"),
            AIMessage(content="second answer"),
            AIMessage(content="second regenerated"),
        ])
        conversation = self.create_conversation()
        first = self.start_turn(conversation["id"], "first task")
        second = self.start_turn(conversation["id"], "second task")
        before_calls = len(RECEIVED_PROMPTS)

        response = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/branches",
            json={"source_run_id": second["id"], "mode": "regenerate"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        regen = wait_for_run(self.client, response.json()["current_run_id"])

        self.assertEqual(regen["status"], "completed", regen)
        self.assertEqual(len(RECEIVED_PROMPTS), before_calls + 1)
        self.assertIn("second task", RECEIVED_PROMPTS[-1])
        self.assertNotEqual(response.json()["source_checkpoint_id"], first["checkpoint_ids"][0])

    def test_regenerate_preserves_source_per_request_overrides(self) -> None:
        self.install_model([AIMessage(content="original answer"), AIMessage(content="regenerated answer")])
        conversation = self.create_conversation()
        run = self.start_turn(
            conversation["id"],
            "task",
            per_request_overrides={"temperature": 0.17, "reasoning_effort": "medium"},
        )

        response = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/branches",
            json={"source_run_id": run["id"], "mode": "regenerate"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        regen = wait_for_run(self.client, response.json()["current_run_id"])

        stored = self.app.state.app_store.get_run(regen["id"])
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertIsNotNone(stored.effective_setup)
        assert stored.effective_setup is not None
        self.assertEqual(
            stored.effective_setup.bags.per_request.requested,
            {"temperature": 0.17, "reasoning_effort": "medium"},
        )

    def test_typed_ask_user_cancel_resumes_with_cancelled_payload(self) -> None:
        self.install_model([
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "ask_user", "args": {"prompt": "Need input", "answer_type": "text"}, "id": "ask_1"}
                ],
            ),
            AIMessage(content="cancel handled"),
        ])
        registered = self.client.post("/v1/agent-interaction/threads", json={"source_surface": "agent"})
        self.assertEqual(registered.status_code, 200, registered.text)
        thread_id = registered.json()["thread_id"]
        started = self.client.post(
            f"/v1/agent-interaction/threads/{thread_id}/commands",
            json={
                "id": "start",
                "method": "run.start",
                "params": {
                    "assistant_id": "local-ai-workbench",
                    "input": {"messages": [{"type": "human", "id": "input-1", "content": "ask"}]},
                    "metadata": {"workbench": {"deployment_id": self.deployment_id, "presented_tools": ["ask_user"]}},
                },
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        state = self.wait_interaction_interrupt(thread_id)
        interrupt = state["values"]["__interrupt__"][0]
        blank = self.client.post(
            f"/v1/agent-interaction/threads/{thread_id}/commands",
            json={
                "id": "blank",
                "method": "input.respond",
                "params": {
                    "namespace": interrupt.get("namespace", []),
                    "interrupt_id": interrupt["id"],
                    "response": {"answer": ""},
                },
            },
        )
        self.assertEqual(blank.status_code, 400)
        cancelled = self.client.post(
            f"/v1/agent-interaction/threads/{thread_id}/commands",
            json={
                "id": "cancel",
                "method": "input.respond",
                "params": {
                    "namespace": interrupt.get("namespace", []),
                    "interrupt_id": interrupt["id"],
                    "response": {"answer": "", "cancelled": True},
                },
            },
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        run_id = cancelled.json()["result"]["run_id"]
        final = wait_for_run(self.client, run_id)
        self.assertEqual(final["status"], "completed", final)
        tool_results = [event["detail"] for event in final["events"] if event["kind"] == "tool_result"]
        self.assertIn("cancelled", str(tool_results).lower())

    def test_public_starts_cannot_request_checkpoint_resume(self) -> None:
        response = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "nope",
                "presented_tools": [],
                "resume_checkpoint_id": "checkpoint_external",
            },
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("internal branch operation", response.text)

        registered = self.client.post("/v1/agent-interaction/threads", json={"source_surface": "agent"})
        self.assertEqual(registered.status_code, 200, registered.text)
        thread_id = registered.json()["thread_id"]
        command = self.client.post(
            f"/v1/agent-interaction/threads/{thread_id}/commands",
            json={
                "id": "start",
                "method": "run.start",
                "params": {
                    "assistant_id": "local-ai-workbench",
                    "input": {"messages": [{"type": "human", "id": "input-1", "content": "hello"}]},
                    "metadata": {"workbench": {"deployment_id": self.deployment_id, "resume_checkpoint_id": "checkpoint_external"}},
                },
            },
        )
        self.assertEqual(command.status_code, 400, command.text)


if __name__ == "__main__":
    unittest.main()
