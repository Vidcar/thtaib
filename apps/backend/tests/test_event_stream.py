"""API-006: GET /v1/events SSE for run and Chat conversation records."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel, set_generate_hold, wait_for_generate_hold
from tests.support import close_workbench_sqlite, workbench_client


def echo_then_reply() -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "echo", "args": {"text": "harness-ok"}, "id": "call_echo"}],
        ),
        AIMessage(content="The echo tool returned harness-ok. Looks correct."),
    ]


def parse_sse_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line == "":
            if current:
                events.append(_finish_sse(current))
                current = {}
            continue
        if line.startswith(":"):
            current.setdefault("comment", "")
            current["comment"] += line[1:].lstrip()
            continue
        name, _, value = line.partition(":")
        current[name] = value.lstrip()
    if current:
        events.append(_finish_sse(current))
    return events


def _finish_sse(fields: dict[str, str]) -> dict[str, Any]:
    data = fields.get("data")
    parsed: dict[str, Any] | None = None
    if data:
        loaded = json.loads(data)
        parsed = loaded if isinstance(loaded, dict) else {"raw": loaded}
    return {
        "event": fields.get("event"),
        "id": fields.get("id"),
        "data": parsed,
        "comment": fields.get("comment"),
    }


def read_stream_until_end(
    client: TestClient,
    *,
    params: dict[str, str],
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    deadline = time.time() + timeout
    collected: list[dict[str, Any]] = []
    with client.stream("GET", "/v1/events", params=params, headers=headers) as response:
        if response.status_code != 200:
            body = response.read().decode("utf-8", errors="replace")
            raise AssertionError(f"stream HTTP {response.status_code}: {body}")
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            if "\n\n" not in buffer and "\r\n\r\n" not in buffer:
                if time.time() > deadline:
                    raise TimeoutError(f"SSE timed out; so far={collected!r} buffer={buffer!r}")
                continue
            events = parse_sse_events(buffer)
            if events and events[-1].get("event") is None and events[-1].get("data") is None:
                events = events[:-1]
            collected = events
            if any(item.get("event") == "stream_end" for item in collected):
                return collected
            if time.time() > deadline:
                raise TimeoutError(f"SSE timed out; so far={collected!r}")
    return collected


class EventStreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manager = ModelManager(WorkbenchPaths(self.root).ensure())
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        self.scripted = ScriptedChatModel(echo_then_reply())

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        self.client = workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "stream-fixture"},
        ).json()["id"]

    def tearDown(self) -> None:
        set_generate_hold(None)
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _start(self, **extra: Any) -> dict[str, Any]:
        payload = {
            "deployment_id": self.deployment_id,
            "task": "Echo the text harness-ok using the echo tool.",
            **extra,
        }
        response = self.client.post("/v1/agent-runs", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_requires_exactly_one_target(self) -> None:
        neither = self.client.get("/v1/events")
        self.assertEqual(neither.status_code, 400, neither.text)
        self.assertEqual(neither.json()["code"], "event_target_required")
        both = self.client.get(
            "/v1/events",
            params={"run_id": "agent_missing", "conversation_id": "chat_missing"},
        )
        self.assertEqual(both.status_code, 400, both.text)
        self.assertEqual(both.json()["code"], "event_target_required")

    def test_unknown_run_is_404(self) -> None:
        response = self.client.get("/v1/events", params={"run_id": "agent_missing"})
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["code"], "run_missing")

    def test_stream_follows_run_to_completion(self) -> None:
        started = self._start()
        events = read_stream_until_end(self.client, params={"run_id": started["id"]})
        names = [item["event"] for item in events if item["event"]]
        self.assertEqual(names[0], "snapshot")
        self.assertIn("stream_end", names)
        kinds = [
            item["data"]["event"]["kind"]
            for item in events
            if item["event"] == "run_event" and item["data"] and item["data"].get("event")
        ]
        snapshot = events[0]["data"]
        self.assertIsNotNone(snapshot)
        recorded = snapshot["snapshot"]["events"] if snapshot and snapshot.get("snapshot") else []
        recorded_kinds = [item["kind"] for item in recorded]
        if kinds:
            self.assertTrue(set(kinds) <= set(recorded_kinds) | {"started", "tool_call", "tool_result", "assistant_message", "completed"})
        final = next(item for item in reversed(events) if item["event"] == "snapshot")
        self.assertEqual(final["data"]["status"], "completed")
        body = self.client.get(f"/v1/agent-runs/{started['id']}").json()
        self.assertEqual(body["status"], "completed")
        persisted = [item["kind"] for item in body["events"]]
        self.assertIn("started", persisted)
        self.assertIn("tool_call", persisted)
        self.assertIn("completed", persisted)

    def test_last_event_id_skips_earlier_run_events(self) -> None:
        started = self._start()
        first = read_stream_until_end(self.client, params={"run_id": started["id"]})
        run_events = [item for item in first if item["event"] == "run_event"]
        if not run_events:
            replay = read_stream_until_end(
                self.client,
                params={"run_id": started["id"]},
                headers={"Last-Event-ID": "0"},
            )
            self.assertEqual(replay[0]["event"], "snapshot")
            self.assertEqual(replay[-1]["event"], "stream_end")
            return
        skip_id = run_events[0]["id"]
        self.assertIsNotNone(skip_id)
        replay = read_stream_until_end(
            self.client,
            params={"run_id": started["id"]},
            headers={"Last-Event-ID": str(skip_id)},
        )
        self.assertEqual(replay[0]["event"], "snapshot")
        replayed_ids = [item["id"] for item in replay if item["event"] == "run_event"]
        self.assertNotIn(skip_id, replayed_ids)
        self.assertEqual(replay[-1]["event"], "stream_end")

    def test_subscriber_wait_does_not_cancel_run(self) -> None:
        """A waiting consumer is not a run end. TestClient buffers SSE until the
        generator advances, so this checks the harness wait used by GET /v1/events.
        """

        hold = threading.Event()
        set_generate_hold(hold)
        self.addCleanup(set_generate_hold, None)
        self.addCleanup(hold.set)
        started = self._start()
        wait_for_generate_hold()
        run, extra = self.app.state.harness.wait_after(started["id"], 0, timeout=0.3)
        self.assertTrue(is_run_lifecycle_live(run.status), run.status)
        self.assertTrue(extra)
        observed = self.client.get(f"/v1/agent-runs/{started['id']}").json()
        self.assertIn(observed["status"], {"queued", "running", "cancel_requested"})
        hold.set()
        deadline = time.time() + 15
        body = observed
        while time.time() < deadline:
            body = self.client.get(f"/v1/agent-runs/{started['id']}").json()
            if body["status"] in {"completed", "cancelled", "failed"}:
                break
            time.sleep(0.05)
        self.assertEqual(body["status"], "completed", body)

    def test_chat_conversation_stream_completes(self) -> None:
        created = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id},
        )
        self.assertEqual(created.status_code, 200, created.text)
        conversation_id = created.json()["id"]
        started = self.client.post(
            f"/v1/chat/conversations/{conversation_id}/start",
            json={"task": "Echo the text harness-ok using the echo tool."},
        )
        self.assertEqual(started.status_code, 200, started.text)
        events = read_stream_until_end(
            self.client,
            params={"conversation_id": conversation_id},
        )
        self.assertEqual(events[0]["event"], "snapshot")
        self.assertEqual(events[0]["data"]["conversation_id"], conversation_id)
        final = next(item for item in reversed(events) if item["event"] == "snapshot")
        snapshot = final["data"]["snapshot"]
        self.assertEqual(snapshot["current_run"]["status"], "completed")
        self.assertEqual(events[-1]["event"], "stream_end")
