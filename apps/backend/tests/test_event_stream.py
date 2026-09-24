"""Interaction protocol streaming regressions."""

from __future__ import annotations

from contextlib import contextmanager
import json
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
from langchain_core.messages import AIMessage
import uvicorn

from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, GenerationObservation
from workbench_backend.inference.ids import utc_now
from workbench_backend.app import create_app
from workbench_backend.chat.coordinator import ChatCoordinator
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
    opened: threading.Event | None = None,
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
        if opened is not None:
            opened.set()
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

    def test_native_write_failure_publishes_terminal_chat_and_pauses_queue(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        self._install_model([AIMessage(content="This answer must not complete.")], hold=hold)
        conversation = self.client.post("/v1/chat/conversations",
            json={"deployment_id": self.deployment_id})
        self.assertEqual(conversation.status_code, 200, conversation.text)
        thread_id = conversation.json()["id"]
        registered = self.client.post("/v1/agent-interaction/threads",
            json={"source_surface": "chat", "conversation_id": thread_id})
        self.assertEqual(registered.status_code, 200, registered.text)
        cursor = self.app.state.app_store.get_interaction(thread_id)["seq"]
        original_append = self.app.state.app_store.append_interaction
        original_observe = self.app.state.harness._observe_interaction
        failed = threading.Event()
        armed = threading.Event()
        native_observe = threading.local()
        self.app.state.chat_coordinator = ChatCoordinator(self.app)

        def fail_native_once(ident, events, **kwargs):
            if armed.is_set() and not failed.is_set() and getattr(native_observe, "active", False):
                failed.set()
                raise sqlite3.OperationalError("injected native interaction write failure")
            return original_append(ident, events, **kwargs)

        def marked_observe(run, event, *, telemetry=False):
            native_observe.active = event is not None
            try:
                return original_observe(run, event, telemetry=telemetry)
            finally:
                native_observe.active = False

        try:
            with patch.object(self.app.state.app_store, "append_interaction", side_effect=fail_native_once), \
                    patch.object(self.app.state.harness, "_observe_interaction", side_effect=marked_observe):
                started = self.client.post(f"/v1/chat/conversations/{thread_id}/start",
                    json={"task": "Answer once", "presented_tools": []})
                self.assertEqual(started.status_code, 200, started.text)
                run_id = started.json()["current_run_id"]
                wait_for_generate_hold()
                queued = self.client.post(f"/v1/chat/conversations/{thread_id}/queue",
                    json={"task": "Wait until the failure is handled"})
                self.assertEqual(queued.status_code, 200, queued.text)
                opened = threading.Event()
                streamed: list[dict[str, Any]] = []
                stream_errors: list[BaseException] = []
                with loopback_app_server(self.app) as base_url:
                    def receive() -> None:
                        try:
                            streamed.extend(read_loopback_interaction_events(
                                base_url, token=self.app.state.local_trust_token, thread_id=thread_id,
                                body={"channels": ["values", "lifecycle"], "namespaces": [[]], "since": cursor},
                                stop=lambda events: any(item.get("data", {}).get("method") == "lifecycle"
                                    and item["data"]["params"]["data"].get("event") == "failed"
                                    for item in events if isinstance(item.get("data"), dict)),
                                timeout=8.0, opened=opened,
                            ))
                        except BaseException as exc:
                            stream_errors.append(exc)

                    subscriber = threading.Thread(target=receive, daemon=True)
                    subscriber.start()
                    try:
                        self.assertTrue(opened.wait(timeout=5), "live subscriber did not connect")
                        armed.set()
                        hold.set()
                        self.assertTrue(failed.wait(timeout=10), "native event was not written")
                        deadline = time.monotonic() + 10
                        while time.monotonic() < deadline:
                            run = self.app.state.harness.get_run(run_id)
                            if not is_run_lifecycle_live(run.status):
                                break
                            time.sleep(0.02)
                        else:
                            self.fail("run did not settle after interaction failure")
                        self.assertEqual(run.status, AgentRunStatus.failed)
                        self.assertEqual(run.stop_reason, "interaction_persistence_failed")
                    finally:
                        hold.set()
                        subscriber.join(timeout=10)
                    self.assertFalse(subscriber.is_alive(), "live subscriber did not finish")
                    self.assertEqual(stream_errors, [])
                self.assertTrue(any(item.get("data", {}).get("method") == "lifecycle"
                    and item["data"]["params"]["data"].get("event") == "failed"
                    for item in streamed if isinstance(item.get("data"), dict)))

                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    saved = self.app.state.chat.store.get(thread_id)
                    if saved and saved.queue and saved.queue[0].status == "paused":
                        break
                    time.sleep(0.02)
                else:
                    self.fail("Chat coordinator did not pause the queued turn")
                self.assertEqual(saved.queue[0].pause_reason, "failed")
                self.assertEqual(saved.run_ids, [run_id])
        finally:
            hold.set()
            self.app.state.chat_coordinator.close()

    def test_stream_repairs_durable_terminal_after_display_write_failure(self) -> None:
        thread_id = self._register_agent()
        cursor = self.app.state.app_store.get_interaction(thread_id)["seq"]
        original_append = self.app.state.app_store.append_interaction
        failed = threading.Event()

        def fail_terminal_display(ident, events, **kwargs):
            if any(item.get("method") == "lifecycle"
                    and item.get("params", {}).get("data", {}).get("event") == "completed"
                    for item in events):
                failed.set()
                raise sqlite3.OperationalError("injected terminal display write failure")
            return original_append(ident, events, **kwargs)

        with patch.object(self.app.state.app_store, "append_interaction", side_effect=fail_terminal_display), \
                patch("workbench_backend.agents.harness.log.exception"):
            started = self._start_command(thread_id)
            self.assertTrue(failed.wait(timeout=10), "terminal display write was not attempted")
            run_id = started["run_id"]
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                run = self.app.state.harness.get_run(run_id)
                if not is_run_lifecycle_live(run.status):
                    break
                time.sleep(0.02)
            else:
                self.fail("run did not settle after terminal display failure")
            self.assertEqual(run.status, AgentRunStatus.completed)
            _seq, _cutover, projected, durable = self.app.state.app_store.interaction_stream_metadata(thread_id)
            self.assertEqual((projected, durable), ("running", "completed"))
            resume = self.app.state.interaction.resume_view(thread_id, cursor)
            with self.assertRaises(sqlite3.OperationalError):
                self.app.state.interaction.stream_poll(thread_id, cursor,
                    {"channels": ["values", "lifecycle"], "namespaces": [[]]}, resume)

        with loopback_app_server(self.app) as base_url:
            streamed = read_loopback_interaction_events(
                base_url, token=self.app.state.local_trust_token, thread_id=thread_id,
                body={"channels": ["values", "lifecycle"], "namespaces": [[]], "since": cursor},
                stop=lambda events: any(item.get("data", {}).get("method") == "lifecycle"
                    and item["data"]["params"]["data"].get("event") == "completed"
                    for item in events if isinstance(item.get("data"), dict)),
                timeout=8.0,
            )
        self.assertTrue(any(item.get("data", {}).get("method") == "lifecycle"
            and item["data"]["params"]["data"].get("event") == "completed"
            for item in streamed if isinstance(item.get("data"), dict)))
        self.assertEqual(self.app.state.app_store.interaction_stream_metadata(thread_id)[2:],
                         ("completed", "completed"))

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
                stop=lambda events: any(int(e.get("id") or 0) >= cursor for e in events if e.get("data")),
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

    def test_live_resume_shows_partial_text_without_replaying_earlier_tokens(self) -> None:
        thread_id = self._register_agent()
        graph_thread_id = self.app.state.app_store.get_interaction(thread_id)["graph_thread_id"]
        now = utc_now()
        run = AgentRun(
            id="stream-partial",
            status=AgentRunStatus.running,
            deployment_id=self.deployment_id,
            task="Say hello",
            input_message_id="partial-user",
            enabled_tools=[],
            presented_tools=[],
            created_at=now,
            updated_at=now,
            thread_id=graph_thread_id,
        )
        self.app.state.app_store.put_run(run)
        interaction = self.app.state.interaction
        interaction.observe(run, None)
        for data in (
            {"event": "message-start", "role": "ai", "id": "partial-ai"},
            {"event": "content-block-delta", "index": 0, "delta": {"type": "text-delta", "text": "Hello"}},
        ):
            interaction.observe(run, {"method": "messages", "params": {"namespace": [], "timestamp": 1, "data": data}})

        state = self.client.get(f"/v1/agent-interaction/threads/{thread_id}/state").json()
        partial = next(message for message in state["values"]["messages"] if message.get("id") == "partial-ai")
        self.assertEqual(partial["content"], [{"type": "text", "text": "Hello"}])
        self.assertIn("partial-ai", state["values"]["workbench"]["incomplete_message_ids"])
        cursor = state["interaction_cursor"]
        self.assertGreater(cursor, 0)

        interaction.observe(run, {"method": "messages", "params": {"namespace": [], "timestamp": 2, "data": {
            "event": "content-block-delta", "index": 0, "delta": {"type": "text-delta", "text": " world"},
        }}})
        interaction.observe(run, None)

        with loopback_app_server(self.app) as base_url:
            streamed = read_loopback_interaction_events(
                base_url,
                token=self.app.state.local_trust_token,
                thread_id=thread_id,
                body={"channels": ["messages", "values"], "namespaces": [[]], "since": cursor},
                stop=lambda events: any((event.get("data") or {}).get("method") == "values" for event in events),
                timeout=5.0,
            )
        payloads = [event["data"] for event in streamed if event.get("data")]
        message_events = [item["params"]["data"] for item in payloads if item["method"] == "messages"]
        self.assertEqual([item["event"] for item in message_events], ["message-start", "content-block-start", "content-block-delta"])
        self.assertEqual(message_events[0]["id"], "partial-ai")
        self.assertEqual(message_events[1]["content"], {"type": "text", "text": "Hello"})
        self.assertEqual(message_events[2]["delta"]["text"], " world")
        resumed = next(item["params"]["data"] for item in payloads if item["method"] == "values")
        resumed_partial = next(message for message in resumed["messages"] if message.get("id") == "partial-ai")
        self.assertEqual(resumed_partial["content"], [{"type": "text", "text": "Hello world"}])
        self.assertIn("partial-ai", resumed["workbench"]["incomplete_message_ids"])

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

    def test_missing_historical_detail_resynchronizes_saved_output_without_execution(self) -> None:
        thread_id = self._register_agent()
        started = self._start_command(thread_id)
        original = wait_for_state(self.client, thread_id)
        calls_before = len(self.app.state.harness.list_runs())
        store = self.app.state.app_store
        missing = store.append_interaction(thread_id, [event("tools", {
            "event": "tool-started", "tool_call_id": "lost-tool", "tool_name": "read_file",
        })])
        store.append_interaction(thread_id, [event("lifecycle", {"event": "completed"})])
        with store._lock:
            store._conn.execute("DELETE FROM interaction_events WHERE thread_id=? AND seq=?", (thread_id, missing))
            store._conn.commit()
        with loopback_app_server(self.app) as base_url:
            events = read_loopback_interaction_events(
                base_url, token=self.app.state.local_trust_token, thread_id=thread_id,
                body={"channels": ["values", "lifecycle"]},
                stop=lambda items: any((item.get("data") or {}).get("method") == "values" for item in items),
            )
        values = next(item["data"]["params"]["data"] for item in events if (item.get("data") or {}).get("method") == "values")
        self.assertEqual(values["messages"], original["values"]["messages"])
        self.assertEqual(values["workbench"]["recovery"]["kind"], "history_unavailable")
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
