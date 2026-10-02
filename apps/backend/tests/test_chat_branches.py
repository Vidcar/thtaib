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
        before = (self.project / "seed.txt").read_text(encoding="utf-8")
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
        self.assertEqual((self.project / "seed.txt").read_text(encoding="utf-8"), before)
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
        self.assertIn("First request", str(body["transcript"]))
        self.assertIn("Second request", str(body["transcript"]))
        self.assertEqual(body["queue"][0]["task"], "Waiting follow-up")
        self.assertEqual(body["current_run_id"], second["id"])

    def test_live_turn_refuses_rewind(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        self.install_model([AIMessage(content="held answer")])
        conversation = self.create_conversation()
        started = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Hold this", "presented_tools": []},
        )
        self.assertEqual(started.status_code, 200, started.text)
        try:
            wait_for_generate_hold()
            response = self.rewind(conversation["id"], started.json()["current_run_id"], "retry", "Hold this")
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(response.json()["code"], "chat_turn_active")
            body = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
            self.assertIn("Hold this", str(body["transcript"]))
            self.assertEqual(body["current_run_id"], started.json()["current_run_id"])
        finally:
            hold.set()
            set_generate_hold(None)
            wait_for_run(self.client, started.json()["current_run_id"])

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
