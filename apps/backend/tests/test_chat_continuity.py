"""Issue #56: Chat follow-ups resume the conversation LangGraph thread."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app

from tests.scripted_model import RECEIVED_PROMPTS, ScriptedChatModel, reset_received_prompts
from tests.support import close_workbench_sqlite, workbench_client, offline_workbench_client

UNIQUE_DETAIL = "TOKEN-ALPHA-7F3Q-ISSUE56"
TURN_ONE = f"Remember this unique detail for later: {UNIQUE_DETAIL}"
TURN_TWO = "Continue. Repeat the unique detail I already gave you."
HUMAN = {"actor": "human", "note": "continuity-test"}


def wait_for_chat(client: TestClient, conversation_id: str, *, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/chat/conversations/{conversation_id}")
        body = response.json()
        run = body.get("current_run") or {}
        if run.get("status") in {"completed", "cancelled", "failed"}:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"chat {conversation_id} did not finish: {body}")


def flatten_model_request_text(run: dict[str, Any] | None) -> str:
    parts: list[str] = []
    for capture in (run or {}).get("model_requests") or []:
        for message in capture.get("messages") or []:
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif content is not None:
                parts.append(str(content))
    return "\n".join(parts)


def flatten_received_prompts() -> str:
    return "\n".join(RECEIVED_PROMPTS)


class ChatContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_received_prompts()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project-workspace"
        self.project.mkdir()
        (self.project / "keep.md").write_text("retain-me", encoding="utf-8")
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.scripted = ScriptedChatModel(
            [
                AIMessage(content="Noted the unique detail."),
                AIMessage(content="Continuing the same thread."),
            ]
        )

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "continuity-a"},
        ).json()["id"]
        self.other_deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "continuity-b"},
        ).json()["id"]
        self.profile_id = self.client.post(
            "/v1/profiles",
            json={"display_name": "continuity-profile", "startup": {}, "per_request": {}, "agent": {}},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(
            self.app,
            getattr(self, "client", None),
            getattr(self, "restarted", None),
        )
        self.tmp.cleanup()

    def _create(self, **extra: Any) -> dict[str, Any]:
        payload = {
            "deployment_id": self.deployment_id,
            "profile_id": self.profile_id,
            "project_path": str(self.project),
            **extra,
        }
        response = self.client.post("/v1/chat/conversations", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _start(self, conversation_id: str, task: str, **extra: Any) -> dict[str, Any]:
        response = self.client.post(
            f"/v1/chat/conversations/{conversation_id}/start",
            json={"task": task, **extra},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _knowledge(self, content: str = "permitted durable knowledge") -> dict[str, Any]:
        response = self.client.post(
            "/v1/knowledge/entries",
            json={
                "scope": "project",
                "kind": "memory",
                "content": content,
                "scope_id": "proj-continuity",
                "display_name": "continuity-memory",
                "provenance": HUMAN,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_create_allocates_conversation_thread_distinct_from_id(self) -> None:
        conversation = self._create()
        self.assertTrue(conversation["thread_id"])
        self.assertNotEqual(conversation["thread_id"], conversation["id"])
        self.assertTrue(conversation["thread_id"].startswith("thread_"))
        continuity = conversation["continuity"]
        self.assertEqual(continuity["conversation_id"], conversation["id"])
        self.assertEqual(continuity["thread_id"], conversation["thread_id"])
        self.assertEqual(continuity["history_edit_effect"], "display_only")
        self.assertEqual(continuity["model_switch_effect"], "same_thread_new_run")
        self.assertEqual(
            continuity["fresh_conversation_effect"],
            "new_thread_retain_project_and_knowledge",
        )
        self.assertFalse(continuity["transcript_is_harness_context"])

    def test_two_turn_unique_detail_reaches_next_model_request(self) -> None:
        conversation = self._create()
        first = self._start(conversation["id"], TURN_ONE)
        self.assertEqual(first["current_run"]["thread_id"], conversation["thread_id"])
        self.assertEqual(first["current_run"]["id"], first["current_run_id"])
        self.assertNotEqual(first["current_run"]["id"], conversation["thread_id"])
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "completed", body["current_run"].get("error"))
        first_run_id = body["current_run"]["id"]

        second = self._start(conversation["id"], TURN_TWO)
        self.assertEqual(second["thread_id"], conversation["thread_id"])
        self.assertEqual(second["current_run"]["thread_id"], conversation["thread_id"])
        self.assertNotEqual(second["current_run"]["id"], first_run_id)
        self.assertEqual(second["run_ids"], [first_run_id, second["current_run"]["id"]])
        finished = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(
            finished["current_run"]["status"],
            "completed",
            finished["current_run"].get("error"),
        )
        harness_text = flatten_model_request_text(finished["current_run"])
        adapter_text = flatten_received_prompts()
        self.assertIn(UNIQUE_DETAIL, harness_text)
        self.assertIn(UNIQUE_DETAIL, adapter_text)
        self.assertIn(TURN_TWO, harness_text)
        transcript_blob = "\n".join(item["content"] for item in finished["transcript"])
        self.assertIn(UNIQUE_DETAIL, transcript_blob)
        self.assertNotEqual(harness_text, transcript_blob)

    def test_reopen_after_backend_restart_resumes_same_thread(self) -> None:
        conversation = self._create()
        self._start(conversation["id"], TURN_ONE)
        first = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(first["current_run"]["status"], "completed", first["current_run"].get("error"))
        thread_id = first["thread_id"]
        conversation_id = first["id"]
        first_run_id = first["current_run"]["id"]

        close_workbench_sqlite(self.app, self.client)
        reset_received_prompts()
        restarted = create_app(data_root=self.root)
        self.restarted = restarted
        scripted = ScriptedChatModel([AIMessage(content="Resumed after restart.")])

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return scripted

        restarted.state.harness = HarnessService(
            lambda: restarted.state.manager,
            model_factory=factory,
            knowledge_provider=lambda: restarted.state.knowledge,
            app_store=restarted.state.app_store,
        )
        client = workbench_client(restarted)
        reopened = client.get(f"/v1/chat/conversations/{conversation_id}")
        self.assertEqual(reopened.status_code, 200, reopened.text)
        body = reopened.json()
        self.assertEqual(body["id"], conversation_id)
        self.assertEqual(body["thread_id"], thread_id)
        self.assertEqual(body["continuity"]["thread_id"], thread_id)
        self.assertEqual(body["continuity"]["run_ids"], [first_run_id])
        self.assertEqual(body["current_run"]["id"], first_run_id)
        self.assertEqual(body["current_run"]["thread_id"], thread_id)

        started = client.post(
            f"/v1/chat/conversations/{conversation_id}/start",
            json={"task": TURN_TWO},
        )
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["thread_id"], thread_id)
        self.assertEqual(started.json()["current_run"]["thread_id"], thread_id)
        self.assertNotEqual(started.json()["current_run"]["id"], first_run_id)
        finished = wait_for_chat(client, conversation_id)
        self.assertEqual(
            finished["current_run"]["status"],
            "completed",
            finished["current_run"].get("error"),
        )
        self.assertEqual(finished["thread_id"], thread_id)
        self.assertIn(UNIQUE_DETAIL, flatten_model_request_text(finished["current_run"]))
        self.assertIn(UNIQUE_DETAIL, flatten_received_prompts())

    def test_fresh_conversation_resets_active_context_and_retains_project_knowledge(self) -> None:
        knowledge = self._knowledge("keep-this-knowledge")
        first = self._create()
        self._start(first["id"], TURN_ONE)
        wait_for_chat(self.client, first["id"])
        (self.project / "keep.md").write_text("retain-me", encoding="utf-8")
        fingerprints_before = {
            path.relative_to(self.project).as_posix(): path.read_text(encoding="utf-8")
            for path in self.project.rglob("*")
            if path.is_file()
        }

        reset_received_prompts()
        fresh = self._create()
        self.assertNotEqual(fresh["id"], first["id"])
        self.assertNotEqual(fresh["thread_id"], first["thread_id"])
        self.assertEqual(fresh["transcript"], [])
        self.assertEqual(fresh["run_ids"], [])
        started = self._start(fresh["id"], "Start a new conversation with no prior token.")
        finished = wait_for_chat(self.client, fresh["id"])
        self.assertEqual(
            finished["current_run"]["status"],
            "completed",
            finished["current_run"].get("error"),
        )
        self.assertEqual(finished["current_run"]["thread_id"], fresh["thread_id"])
        harness_text = flatten_model_request_text(finished["current_run"])
        adapter_text = flatten_received_prompts()
        self.assertNotIn(UNIQUE_DETAIL, harness_text)
        self.assertNotIn(UNIQUE_DETAIL, adapter_text)
        fingerprints_after = {
            path.relative_to(self.project).as_posix(): path.read_text(encoding="utf-8")
            for path in self.project.rglob("*")
            if path.is_file()
        }
        self.assertEqual(fingerprints_after, fingerprints_before)
        listed = self.client.get("/v1/knowledge/entries").json()
        ids = {item["id"] for item in listed}
        self.assertIn(knowledge["id"], ids)
        current = self.client.get(f"/v1/knowledge/entries/{knowledge['id']}").json()
        self.assertEqual(current["content"], "keep-this-knowledge")

    def test_model_switch_uses_new_deployment_on_same_thread(self) -> None:
        conversation = self._create()
        self._start(conversation["id"], TURN_ONE)
        first = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(first["current_run"]["deployment_id"], self.deployment_id)
        second = self._start(
            conversation["id"],
            TURN_TWO,
            deployment_id=self.other_deployment_id,
        )
        self.assertEqual(second["deployment_id"], self.other_deployment_id)
        self.assertEqual(second["thread_id"], conversation["thread_id"])
        self.assertEqual(second["current_run"]["thread_id"], conversation["thread_id"])
        self.assertEqual(second["current_run"]["deployment_id"], self.other_deployment_id)
        finished = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(
            finished["current_run"]["status"],
            "completed",
            finished["current_run"].get("error"),
        )
        self.assertEqual(finished["current_run"]["deployment_id"], self.other_deployment_id)
        self.assertIn(UNIQUE_DETAIL, flatten_model_request_text(finished["current_run"]))

    def test_history_edit_is_display_only_and_does_not_reset_thread(self) -> None:
        conversation = self._create()
        self._start(conversation["id"], TURN_ONE)
        first = wait_for_chat(self.client, conversation["id"])
        thread_id = first["thread_id"]
        fingerprints_before = {
            path.relative_to(self.project).as_posix(): path.read_text(encoding="utf-8")
            for path in self.project.rglob("*")
            if path.is_file()
        }
        knowledge = self._knowledge("history-edit-knowledge")

        replaced = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/transcript",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "rewritten displayed history without the token",
                        "at": "2026-01-01T00:00:00+00:00",
                    }
                ]
            },
        )
        self.assertEqual(replaced.status_code, 200, replaced.text)
        self.assertTrue(replaced.json()["history_replaced"])
        self.assertEqual(replaced.json()["thread_id"], thread_id)
        self.assertEqual(replaced.json()["continuity"]["history_edit_effect"], "display_only")
        self.assertEqual(
            replaced.json()["transcript"][0]["content"],
            "rewritten displayed history without the token",
        )
        fingerprints_after_edit = {
            path.relative_to(self.project).as_posix(): path.read_text(encoding="utf-8")
            for path in self.project.rglob("*")
            if path.is_file()
        }
        self.assertEqual(fingerprints_after_edit, fingerprints_before)
        self.assertEqual(
            self.client.get(f"/v1/knowledge/entries/{knowledge['id']}").json()["content"],
            "history-edit-knowledge",
        )

        second = self._start(conversation["id"], TURN_TWO)
        self.assertEqual(second["thread_id"], thread_id)
        finished = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(
            finished["current_run"]["status"],
            "completed",
            finished["current_run"].get("error"),
        )
        harness_text = flatten_model_request_text(finished["current_run"])
        self.assertIn(UNIQUE_DETAIL, harness_text)
        transcript_blob = "\n".join(item["content"] for item in finished["transcript"])
        self.assertNotIn(UNIQUE_DETAIL, transcript_blob)
        fingerprints_after_turn = {
            path.relative_to(self.project).as_posix(): path.read_text(encoding="utf-8")
            for path in self.project.rglob("*")
            if path.is_file()
        }
        self.assertEqual(fingerprints_after_turn, fingerprints_before)

    def test_agent_run_without_thread_id_still_owns_its_own_thread(self) -> None:
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "One-shot agent-run, not Chat.",
                "presented_tools": ["echo"],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        run = started.json()
        self.assertEqual(run["thread_id"], run["id"])
        self.assertEqual(run["source_surface"], "agent-run")


if __name__ == "__main__":
    unittest.main()
