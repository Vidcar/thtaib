"""Interaction protocol streaming regressions."""

from __future__ import annotations

from contextlib import contextmanager
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Iterator

from fastapi.testclient import TestClient
import httpx
from langchain_core.messages import AIMessage
import uvicorn

from workbench_backend.agents.schemas import AgentRun, GenerationObservation
from workbench_backend.app import create_app
from workbench_backend.contracts.auth import WORKBENCH_LOCAL_TOKEN_HEADER
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.interaction.projection import event

from tests.scripted_model import ScriptedChatModel, set_generate_hold, wait_for_generate_hold
from tests.support import close_workbench_sqlite, offline_workbench_client


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
    return events


def _finish_sse(fields: dict[str, str]) -> dict[str, Any]:
    data = fields.get("data")
    return {
        "event": fields.get("event"),
        "id": fields.get("id"),
        "data": json.loads(data) if data else None,
        "comment": fields.get("comment"),
    }


@contextmanager
def loopback_app_server(app: Any) -> Iterator[str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    host, port = sock.getsockname()
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5.0
        while not server.started:
            if not thread.is_alive():
                raise RuntimeError("uvicorn test server stopped before startup")
            if time.monotonic() > deadline:
                raise TimeoutError("uvicorn test server did not start")
            time.sleep(0.01)
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)
        sock.close()
        if thread.is_alive():
            raise TimeoutError("uvicorn test server did not stop")


def read_loopback_interaction_events(
    base_url: str,
    *,
    token: str,
    thread_id: str,
    body: dict[str, Any],
    stop: Any,
    timeout: float = 8.0,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    collected: list[dict[str, Any]] = []
    headers = {WORKBENCH_LOCAL_TOKEN_HEADER: token}
    with httpx.stream(
        "POST",
        f"{base_url}/v1/agent-interaction/threads/{thread_id}/stream/events",
        json=body,
        headers=headers,
        timeout=httpx.Timeout(timeout),
    ) as response:
        if response.status_code != 200:
            payload = response.read().decode("utf-8", errors="replace")
            raise AssertionError(f"interaction stream HTTP {response.status_code}: {payload}")
        buffer = ""
        chunks = response.iter_text()
        while time.monotonic() < deadline:
            try:
                buffer += next(chunks)
            except StopIteration:
                return collected
            collected = parse_sse_events(buffer)
            if stop(collected):
                return collected
    raise TimeoutError(f"interaction stream timed out: {collected!r}")


def wait_for_state(client: TestClient, thread_id: str, status: str = "completed", *, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/v1/agent-interaction/threads/{thread_id}/state")
        response.raise_for_status()
        body = response.json()
        run = body.get("values", {}).get("workbench", {}).get("run") or {}
        if run.get("status") == status:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"interaction thread did not reach {status}: {body}")


class InteractionStreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "interaction-stream-fixture"},
        ).json()["id"]
        self._install_model([AIMessage(content="stream answer")])

    def tearDown(self) -> None:
        set_generate_hold(None)
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _install_model(self, script: list[AIMessage], *, hold: threading.Event | None = None) -> ScriptedChatModel:
        model = ScriptedChatModel(script, hold=hold)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return model

        # Keep the create_app harness so the interaction observer remains wired.
        self.app.state.harness._model_factory = factory
        return model

    def _register_agent(self) -> str:
        response = self.client.post("/v1/agent-interaction/threads", json={"source_surface": "agent"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["thread_id"]

    def _start_command(self, thread_id: str, *, message_id: str = "stream-input", content: str = "hello") -> dict[str, Any]:
        response = self.client.post(f"/v1/agent-interaction/threads/{thread_id}/commands", json={
            "id": f"cmd-{message_id}",
            "method": "run.start",
            "params": {
                "assistant_id": "local-ai-workbench",
                "input": {"messages": [{"type": "human", "id": message_id, "content": content}]},
                "metadata": {"workbench": {"deployment_id": self.deployment_id, "presented_tools": []}},
            },
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["result"]

    def test_unknown_thread_and_subscription_validation(self) -> None:
        missing = self.client.get("/v1/agent-interaction/threads/missing/state")
        self.assertEqual(missing.status_code, 404, missing.text)
        thread_id = self._register_agent()
        invalid = self.client.post(
            f"/v1/agent-interaction/threads/{thread_id}/stream/events",
            json={"channels": ["run_event"]},
        )
        self.assertEqual(invalid.status_code, 400, invalid.text)
        self.assertEqual(invalid.json()["code"], "not_supported")

    def test_stream_replays_durable_events_and_state_cursor(self) -> None:
        thread_id = self._register_agent()
        self._start_command(thread_id, message_id="stream-user-1", content="First")
        state = wait_for_state(self.client, thread_id)
        cursor = state["interaction_cursor"]
        self.assertGreater(cursor, 0)
        self.assertTrue(any(m.get("id") == "stream-user-1" for m in state["values"]["messages"]))
        self.assertTrue(any(m.get("type") == "ai" and m.get("content") == "stream answer" for m in state["values"]["messages"]))

        replay = self.app.state.app_store.interaction_events_after(thread_id, 0)
        seqs = [item["seq"] for item in replay]
        self.assertIn(cursor, seqs)
        self.assertEqual(seqs, sorted(set(seqs)))
        self.assertGreaterEqual(replay[-1]["seq"], cursor)
        self.assertTrue(any(item["method"] == "values" for item in replay))
        self.assertTrue(any(item["method"] == "lifecycle" for item in replay))
        self.assertEqual(self.app.state.app_store.interaction_events_after(thread_id, replay[-1]["seq"]), [])

    def test_live_loopback_stream_resume_does_not_duplicate_snapshot_values(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        self.addCleanup(hold.set)
        self._install_model([AIMessage(content="held answer")], hold=hold)
        thread_id = self._register_agent()
        self._start_command(thread_id, message_id="live-user", content="Hold")
        wait_for_generate_hold()
        state = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state").json()
        cursor = state["interaction_cursor"]
        self.assertGreater(cursor, 0)
        self.assertTrue(is_run_lifecycle_live(state["values"]["workbench"]["run"]["status"]))

        with loopback_app_server(self.app) as base_url:
            initial = read_loopback_interaction_events(
                base_url,
                token=self.app.state.local_trust_token,
                thread_id=thread_id,
                body={"channels": ["values", "lifecycle"], "namespaces": [[]], "since": 0},
                stop=lambda events: len([e for e in events if e.get("data")]) >= cursor,
                timeout=5.0,
            )
            seqs = [item["data"]["seq"] for item in initial if item.get("data")]
            self.assertEqual(seqs, sorted(set(seqs)))
            self.assertEqual(max(seqs), cursor)

            resumed = read_loopback_interaction_events(
                base_url,
                token=self.app.state.local_trust_token,
                thread_id=thread_id,
                body={"channels": ["values", "lifecycle"], "namespaces": [[]], "since": cursor},
                stop=lambda events: any((e.get("comment") == "keepalive") for e in events),
                timeout=12.0,
            )
            self.assertFalse([item for item in resumed if item.get("data")], resumed)
        hold.set()
        completed = wait_for_state(self.client, thread_id)
        self.assertEqual(completed["values"]["workbench"]["run"]["status"], "completed")

    def test_subscriber_disconnect_does_not_cancel_run(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        self.addCleanup(hold.set)
        self._install_model([AIMessage(content="disconnect answer")], hold=hold)
        thread_id = self._register_agent()
        result = self._start_command(thread_id, message_id="disconnect-user", content="Hold")
        wait_for_generate_hold()
        with loopback_app_server(self.app) as base_url:
            events = read_loopback_interaction_events(
                base_url,
                token=self.app.state.local_trust_token,
                thread_id=thread_id,
                body={"channels": ["values"], "namespaces": [[]], "since": 0},
                stop=lambda items: bool(items),
                timeout=5.0,
            )
            self.assertTrue(events)
        run = self.client.get(f"/v1/agent-runs/{result['run_id']}").json()
        self.assertTrue(is_run_lifecycle_live(run["status"]), run)
        hold.set()
        completed = wait_for_state(self.client, thread_id)
        self.assertEqual(completed["values"]["workbench"]["run"]["status"], "completed")

    def test_replay_gap_resynchronizes_saved_output_without_execution(self) -> None:
        thread_id = self._register_agent()
        started = self._start_command(thread_id)
        original = wait_for_state(self.client, thread_id)
        calls_before = len(self.app.state.harness.list_runs())
        store = self.app.state.app_store
        with store._lock:
            store._conn.execute("DELETE FROM interaction_events WHERE thread_id=? AND seq=1", (thread_id,))
            store._conn.commit()
        with loopback_app_server(self.app) as base_url:
            events = read_loopback_interaction_events(
                base_url, token=self.app.state.local_trust_token, thread_id=thread_id,
                body={"channels": ["values", "lifecycle"]},
                stop=lambda items: any((item.get("data") or {}).get("method") == "values" for item in items),
            )
        values = next(item["data"]["params"]["data"] for item in events if (item.get("data") or {}).get("method") == "values")
        self.assertEqual(values["messages"], original["values"]["messages"])
        self.assertEqual(values["workbench"]["recovery"]["kind"], "replay_gap")
        self.assertEqual(values["workbench"]["run"]["id"], started["run_id"])
        self.assertEqual(len(self.app.state.harness.list_runs()), calls_before)

    def test_reconnect_from_coalesced_measurement_keeps_native_events_without_recovery(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        self.addCleanup(hold.set)
        self._install_model([AIMessage(content="complete answer")], hold=hold)
        thread_id = self._register_agent()
        started = self._start_command(thread_id)
        wait_for_generate_hold()
        harness, store = self.app.state.harness, self.app.state.app_store

        def measure(count):
            with harness._lock:
                run = harness._require_run(started["run_id"])
                run.generation_observation = GenerationObservation(request_id="request", phase="generating",
                    input_tokens=100, output_tokens=count, context_used_tokens=100 + count,
                    elapsed_seconds=1, tokens_per_second=40, measured_at=run.updated_at,
                    basis="llama_cpp_timings", interval="current_model_call_generation")
                harness._persist_and_notify(run, telemetry=True)
            return store.get_interaction(thread_id)["seq"]

        cursor = measure(1)
        run = harness._require_run(started["run_id"])
        for raw in [event("messages", {"event": "message-start", "id": "retained-message"}),
                    event("tools", {"event": "tool-finished", "tool_call_id": "retained-tool", "output": "retained output"})]:
            self.app.state.interaction.observe(run, raw)
        second_cursor = measure(2)
        latest = measure(3)
        calls_before = len(harness.list_runs())
        with loopback_app_server(self.app) as base_url:
            for since in (cursor, second_cursor):
                received = read_loopback_interaction_events(base_url, token=self.app.state.local_trust_token,
                    thread_id=thread_id, body={"channels": ["values", "messages", "tools", "lifecycle"], "since": since},
                    stop=lambda items: any(int(item.get("id") or 0) == latest for item in items))
                wire = json.dumps(received)
                self.assertNotIn("after_seq", wire)
                self.assertNotIn("replaceable_measurement", wire)
                self.assertNotIn("replay_gap", wire)
                if since == cursor:
                    self.assertIn("retained-message", wire)
                    self.assertIn("retained output", wire)
                self.assertEqual(received[-1]["data"]["params"]["data"]["workbench"]["run"]["generation_observation"]["output_tokens"], 3)
        self.assertEqual(len(harness.list_runs()), calls_before)
        hold.set()
        wait_for_state(self.client, thread_id)


if __name__ == "__main__":
    unittest.main()
