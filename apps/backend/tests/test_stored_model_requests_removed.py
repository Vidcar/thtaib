"""A chat turn does not persist the model request body."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client


def wait_for_chat(client, conversation_id: str, *, timeout: float = 30.0) -> dict[str, Any]:
    import time

    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        body = client.get(f"/v1/chat/conversations/{conversation_id}").json()
        status = (body.get("current_run") or {}).get("status")
        if status in {"completed", "cancelled", "failed"}:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"chat {conversation_id} did not finish: {body}")


class PartialThenFailModel(BaseChatModel):
    """Yields one visible chunk, then fails. Does not buffer a finished reply."""

    @property
    def _llm_type(self) -> str:
        return "partial-then-fail"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> PartialThenFailModel:
        return self

    def _generate(self, messages: list[Any], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        raise RuntimeError("stream failed after partial output")

    def _stream(self, messages: list[Any], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any):
        yield ChatGenerationChunk(message=AIMessageChunk(content="partial answer"))
        raise RuntimeError("stream failed after partial output")


class StoredModelRequestRemovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project-workspace"
        self.project.mkdir()
        self.app = create_app(data_root=self.root)
        self.model: BaseChatModel = ScriptedChatModel([AIMessage(content="Visible reply")])

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> BaseChatModel:
            return self.model

        # Keep the app observer. A replacement harness without it never records
        # the stream chunks that a failed turn already showed the person.
        original = self.app.state.harness
        self.app.state.harness = HarnessService(
            lambda: self.app.state.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
            interaction_observer=original._interaction_observer,
            project_available_observer=original._project_available_observer,
            assets=original.assets,
            browser=original.browser,
            preview=original.preview,
            managed_commands=original.managed_commands,
            desktop_automation=original.desktop_automation,
        )
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "request-removal"},
        ).json()["id"]
        self.profile_id = self.client.post(
            "/v1/profiles",
            json={"display_name": "request-removal", "startup": {}, "per_request": {}, "agent": {}},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _create(self) -> dict[str, Any]:
        response = self.client.post(
            "/v1/chat/conversations",
            json={
                "deployment_id": self.deployment_id,
                "profile_id": self.profile_id,
                "project_path": str(self.project),
                "approval_mode": "full_access",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _capture_rows(self) -> list[str]:
        store = self.app.state.app_store
        with store._lock:
            table = store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'run_diagnostic_captures'"
            ).fetchone()
            run_payloads = [str(row[0]) for row in store._conn.execute("SELECT payload FROM runs").fetchall()]
        self.assertIsNone(table)
        for payload in run_payloads:
            body = json.loads(payload)
            self.assertNotIn("model_requests", body)
            self.assertNotIn("http_payload", payload)
        return run_payloads

    def test_chat_turn_writes_no_request_body(self) -> None:
        secret = "API_KEY=wb_synthetic_request_credential_1234"
        created = self._create()
        started = self.client.post(
            f"/v1/chat/conversations/{created['id']}/start",
            json={"task": f"Say hello. {secret}", "presented_tools": []},
        )
        self.assertEqual(started.status_code, 200, started.text)
        finished = wait_for_chat(self.client, created["id"])
        self.assertEqual(finished["current_run"]["status"], "completed", finished["current_run"].get("error"))
        transcript = " ".join(message.get("content") or "" for message in finished["transcript"])
        self.assertIn(secret, transcript)
        self.assertIn("Visible reply", transcript)
        diagnostic = self.client.get(f"/v1/agent-runs/{finished['current_run']['id']}")
        self.assertEqual(diagnostic.status_code, 200, diagnostic.text)
        self.assertEqual(diagnostic.json()["model_requests"], [])
        self._capture_rows()
        missing = self.client.post("/v1/knowledge/captures", json={"content": secret, "source": "debug"})
        self.assertEqual(missing.status_code, 404, missing.text)
        self.assertEqual(self.client.get("/v1/knowledge/captures").status_code, 404)
        updated = self.client.put(
            "/v1/knowledge/config",
            json={"context_captures": {"redaction_mode": "retain", "retention_seconds": 5}},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["context_captures"], {"retention_seconds": None, "redaction_mode": "redact_secrets"})
        self.assertFalse(list((self.root / "knowledge" / "captures").glob("kcap_*.json")))

    def test_failed_stream_keeps_partial_output_and_error(self) -> None:
        self.model = PartialThenFailModel()
        created = self._create()
        registered = self.client.post(
            "/v1/agent-interaction/threads",
            json={"source_surface": "chat", "conversation_id": created["id"]},
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        thread_id = registered.json()["thread_id"]
        started = self.client.post(
            f"/v1/chat/conversations/{created['id']}/start",
            json={"task": "Answer briefly.", "presented_tools": []},
        )
        self.assertEqual(started.status_code, 200, started.text)
        finished = wait_for_chat(self.client, created["id"])
        run = finished["current_run"]
        self.assertEqual(run["status"], "failed", run)
        self.assertNotEqual(run["status"], "completed")
        self.assertIn("stream failed after partial output", run.get("error") or "")
        state = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state")
        self.assertEqual(state.status_code, 200, state.text)
        body = state.json()
        messages = body["values"]["messages"]
        partials = [message for message in messages if "partial answer" in json.dumps(message)]
        self.assertTrue(partials, body["values"]["messages"])
        self.assertTrue(body["values"]["workbench"].get("incomplete_message_ids"), body["values"]["workbench"])
        self.assertIn("stream failed after partial output", json.dumps(body["values"]["workbench"].get("run")))
        diagnostic = self.client.get(f"/v1/agent-runs/{run['id']}")
        self.assertEqual(diagnostic.json()["model_requests"], [])
        self._capture_rows()


if __name__ == "__main__":
    unittest.main()
