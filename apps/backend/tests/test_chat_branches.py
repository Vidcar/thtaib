"""Same-chat rewind and the closed branch route."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from langchain_core.messages import AIMessage

from tests.scripted_model import (
    ScriptedChatModel,
    set_generate_hold,
    wait_for_generate_hold,
)
from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app


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

    def create_conversation(self, **extra: object) -> dict:
        response = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id, "project_path": str(self.project), **extra},
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

    def rewind(self, conversation_id: str, source_run_id: str, mode: str, task: str) -> object:
        return self.client.post(
            f"/v1/chat/conversations/{conversation_id}/start",
            json={
                "task": task,
                "presented_tools": [],
                "rewind_source_run_id": source_run_id,
                "rewind_mode": mode,
                "input_message_id": f"rewind-{mode}-{source_run_id}",
            },
        )

    def test_branch_route_is_unavailable(self) -> None:
        conversation = self.create_conversation()
        self.install_model([AIMessage(content="answer")])
        finished = self.start_turn(conversation["id"], "Hello")
        response = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/branches",
            json={"source_run_id": finished["id"], "mode": "continue"},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["code"], "branch_unavailable")
        actions = self.client.get(f"/v1/chat/conversations/{conversation['id']}/replies/{finished['id']}/actions")
        self.assertEqual(actions.status_code, 200, actions.text)
        self.assertFalse(actions.json()["branch_available"])
        self.assertFalse(actions.json()["retry_available"])
        self.assertFalse(actions.json()["regenerate_available"])
        self.assertEqual([item["id"] for item in self.client.get("/v1/chat/conversations").json()], [conversation["id"]])

    def test_edit_rewinds_the_same_chat_and_drops_later_work(self) -> None:
        self.install_model([
            AIMessage(content="first answer"),
            AIMessage(content="second answer"),
            AIMessage(content="edited answer"),
        ])
        conversation = self.create_conversation()
        first = self.start_turn(conversation["id"], "First request")
        second = self.start_turn(conversation["id"], "Second request")
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Waiting follow-up", "presented_tools": []},
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertTrue(queued.json()["queue"])
        (self.project / "seed.txt").write_text("changed-after-second", encoding="utf-8")
        response = self.rewind(conversation["id"], first["id"], "edit", "Edited request")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["id"], conversation["id"])
        finished = wait_for_run(self.client, response.json()["current_run_id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        body = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        transcript = str(body["transcript"])
        self.assertNotIn("Second request", transcript)
        self.assertNotIn("second answer", transcript)
        self.assertNotIn("first answer", transcript)
        self.assertIn("Edited request", transcript)
        self.assertIn("edited answer", transcript)
        self.assertEqual(body["queue"], [])
        self.assertEqual(body["thread_id"], conversation["thread_id"])
        self.assertNotEqual(body["current_run_id"], second["id"])
        self.assertEqual((self.project / "seed.txt").read_text(encoding="utf-8"), "changed-after-second")
        self.assertEqual(Path(body["project_path"]).resolve(), self.project.resolve())
        self.assertEqual(self.client.get("/v1/chat/conversations/search", params={"q": "Second request"}).json(), [])
        self.assertEqual([item["id"] for item in self.client.get("/v1/chat/conversations").json()], [conversation["id"]])

    def test_missing_checkpoint_leaves_the_chat_unchanged(self) -> None:
        self.install_model([AIMessage(content="first answer"), AIMessage(content="second answer")])
        conversation = self.create_conversation()
        self.start_turn(conversation["id"], "First request")
        second = self.start_turn(conversation["id"], "Second request")
        # get_run copies the live record. The refusal must see the id the harness will load.
        live = self.app.state.harness._runs[second["id"]]
        live.pre_run_checkpoint_id = "missing-checkpoint"
        self.app.state.app_store.put_run(live)
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Waiting follow-up", "presented_tools": []},
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        response = self.rewind(conversation["id"], second["id"], "retry", "Second request")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["code"], "rewind_checkpoint_missing")
        body = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        transcript = str(body["transcript"])
        self.assertIn("First request", transcript)
        self.assertIn("first answer", transcript)
        self.assertIn("Second request", transcript)
        self.assertIn("second answer", transcript)
        self.assertEqual(body["queue"][0]["task"], "Waiting follow-up")
        self.assertEqual(body["current_run_id"], second["id"])
        found = self.client.get("/v1/chat/conversations/search", params={"q": "Second request"})
        self.assertEqual(found.status_code, 200, found.text)
        self.assertEqual([item["conversation"]["id"] for item in found.json()], [conversation["id"]])

    def test_live_turn_refuses_rewind(self) -> None:
        self.install_model([AIMessage(content="first answer"), AIMessage(content="held answer")])
        conversation = self.create_conversation()
        first = self.start_turn(conversation["id"], "First request")
        hold = threading.Event()
        set_generate_hold(hold)
        started = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Hold this", "presented_tools": []},
        )
        self.assertEqual(started.status_code, 200, started.text)
        live_id = started.json()["current_run_id"]
        try:
            wait_for_generate_hold()
            queued = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/queue",
                json={"task": "Waiting follow-up", "presented_tools": []},
            )
            self.assertEqual(queued.status_code, 200, queued.text)
            response = self.rewind(conversation["id"], first["id"], "edit", "Should not apply")
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(response.json()["code"], "chat_turn_active")
            body = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
            transcript = str(body["transcript"])
            self.assertIn("First request", transcript)
            self.assertIn("first answer", transcript)
            self.assertIn("Hold this", transcript)
            self.assertNotIn("Should not apply", transcript)
            self.assertEqual(body["queue"][0]["task"], "Waiting follow-up")
            self.assertEqual(body["current_run_id"], live_id)
            live = self.client.get(f"/v1/agent-runs/{live_id}")
            self.assertEqual(live.status_code, 200, live.text)
            self.assertEqual(live.json()["status"], "running")
        finally:
            hold.set()
            set_generate_hold(None)
            wait_for_run(self.client, live_id)

    def test_first_turn_without_a_checkpoint_retries_in_place(self) -> None:
        self.install_model([AIMessage(content="first answer"), AIMessage(content="retried answer")])
        conversation = self.create_conversation()
        first = self.start_turn(conversation["id"], "First request")
        live = self.app.state.harness._runs[first["id"]]
        live.pre_run_checkpoint_id = None
        self.app.state.app_store.put_run(live)
        response = self.rewind(conversation["id"], first["id"], "retry", "ignored by server")
        self.assertEqual(response.status_code, 200, response.text)
        finished = wait_for_run(self.client, response.json()["current_run_id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        body = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        transcript = str(body["transcript"])
        self.assertNotIn("first answer", transcript)
        self.assertIn("First request", transcript)
        self.assertIn("retried answer", transcript)
        self.assertEqual(body["id"], conversation["id"])
        self.assertEqual([item["id"] for item in self.client.get("/v1/chat/conversations").json()], [conversation["id"]])

    def test_cleared_first_turn_clears_again_and_keeps_earlier_archive_rows(self) -> None:
        self.install_model([
            AIMessage(content="first answer"),
            AIMessage(content="retried answer"),
            AIMessage(content="cleared again"),
        ])
        conversation = self.create_conversation()
        first = self.start_turn(conversation["id"], "First request")
        registered = self.client.post(
            "/v1/agent-interaction/threads",
            json={"source_surface": "chat", "conversation_id": conversation["id"]},
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        from copy import deepcopy
        from workbench_backend.interaction.projection import event
        store = self.app.state.app_store
        binding = store.get_interaction(conversation["id"])
        self.assertIsNotNone(binding)
        snapshot = deepcopy(binding["snapshot"])
        snapshot["messages"] = [
            {"id": "kept-prefix", "type": "human", "content": "earlier readable row"},
            *snapshot.get("messages", []),
        ]
        store.append_interaction(binding["id"], [event("values", snapshot)], snapshot=snapshot)
        live = self.app.state.harness._runs[first["id"]]
        live.pre_run_checkpoint_id = None
        self.app.state.app_store.put_run(live)
        first_retry = self.rewind(conversation["id"], first["id"], "retry", "ignored by server")
        self.assertEqual(first_retry.status_code, 200, first_retry.text)
        retried = wait_for_run(self.client, first_retry.json()["current_run_id"])
        self.assertEqual(retried["status"], "completed", retried.get("error"))
        self.assertIsNone(self.app.state.harness._runs[retried["id"]].pre_run_checkpoint_id)
        painted = self.interaction_text(conversation["id"])
        self.assertIn("earlier readable row", painted)
        self.assertNotIn("first answer", painted)
        second_retry = self.rewind(conversation["id"], retried["id"], "retry", "ignored by server")
        self.assertEqual(second_retry.status_code, 200, second_retry.text)
        cleared = wait_for_run(self.client, second_retry.json()["current_run_id"])
        self.assertEqual(cleared["status"], "completed", cleared.get("error"))
        cleared_run = self.app.state.harness._runs[cleared["id"]]
        self.assertIsNone(cleared_run.pre_run_checkpoint_id)
        body = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        transcript = str(body["transcript"])
        self.assertNotIn("first answer", transcript)
        self.assertNotIn("retried answer", transcript)
        self.assertIn("cleared again", transcript)
        painted = self.interaction_text(conversation["id"])
        self.assertIn("earlier readable row", painted)
        self.assertNotIn("first answer", painted)
        self.assertNotIn("retried answer", painted)
        self.assertIn("cleared again", painted)
        if cleared_run.checkpoint_ids:
            values = self.app.state.harness.checkpoint_state_for_run(cleared_run, cleared_run.checkpoint_ids[0])
            checkpoint_text = str(values["values"].get("messages"))
            self.assertNotIn("first answer", checkpoint_text)
            self.assertNotIn("retried answer", checkpoint_text)
            self.assertIn("cleared again", checkpoint_text)

    def interaction_text(self, conversation_id: str) -> str:
        response = self.client.get(f"/v1/agent-interaction/threads/{conversation_id}/state")
        self.assertEqual(response.status_code, 200, response.text)
        return str(response.json()["values"].get("messages"))

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
                    "response": {"decisions": [{"type": "respond", "message": ""}]},
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
                    "response": {"decisions": [{"type": "reject", "message": "The user cancelled this question. Do not repeat it unless asked."}]},
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
        for extra in ({"fork_checkpoint_id": "checkpoint_external"}, {"rewind_clear_messages": True}):
            rejected = self.client.post(
                "/v1/agent-runs",
                json={"deployment_id": self.deployment_id, "task": "nope", "presented_tools": [], **extra},
            )
            self.assertEqual(rejected.status_code, 400, rejected.text)
            self.assertIn("internal branch operation", rejected.text)

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
