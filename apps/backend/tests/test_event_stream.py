"""API-006: GET /v1/events SSE for run and Chat conversation records."""

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
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
from langchain_core.messages import AIMessage
import uvicorn

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.contracts.auth import WORKBENCH_LOCAL_TOKEN_HEADER
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.event_stream import resume_after_snapshot

from tests.scripted_model import ScriptedChatModel, set_generate_hold, wait_for_generate_hold
from tests.support import close_workbench_sqlite, offline_workbench_client


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


def read_loopback_stream_until_idle(
    base_url: str,
    *,
    token: str,
    params: dict[str, str],
    headers: dict[str, str] | None = None,
    timeout: float = 8.0,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    collected: list[dict[str, Any]] = []
    saw_snapshot = False
    request_headers = {WORKBENCH_LOCAL_TOKEN_HEADER: token, **(headers or {})}
    http_timeout = httpx.Timeout(timeout)
    with httpx.stream(
        "GET",
        f"{base_url}/v1/events",
        params=params,
        headers=request_headers,
        timeout=http_timeout,
    ) as response:
        if response.status_code != 200:
            body = response.read().decode("utf-8", errors="replace")
            raise AssertionError(f"stream HTTP {response.status_code}: {body}")
        buffer = ""
        chunks = response.iter_text()
        while time.monotonic() < deadline:
            try:
                chunk = next(chunks)
            except StopIteration:
                raise AssertionError(f"SSE closed before snapshot and idle signal: {collected!r}")
            buffer += chunk
            events = parse_sse_events(buffer)
            if events and events[-1].get("event") is None and events[-1].get("data") is None and not events[-1].get("comment"):
                events = events[:-1]
            collected = events
            if any(item.get("event") == "snapshot" for item in collected):
                saw_snapshot = True
            idle = any(item.get("event") == "stream_end" for item in collected) or any(
                item.get("comment") == "keepalive" for item in collected
            )
            if saw_snapshot and idle:
                return collected
    raise TimeoutError(f"SSE idle timed out; so far={collected!r}")


def record_events(record: dict[str, Any] | None) -> list[Any]:
    if record is None:
        return []
    current_run = record.get("current_run")
    if isinstance(current_run, dict) and current_run.get("events") is not None:
        return list(current_run["events"])
    return list(record.get("events") or [])


def apply_snapshot_replace_then_append(
    current: dict[str, Any] | None,
    envelope: dict[str, Any] | None,
    event_name: str | None,
) -> dict[str, Any] | None:
    """Desktop merge without a seq guard: snapshot replaces, run_event appends.

    This is the client path that grew 5 → 9 when the server replayed snapshot
    rows after Last-Event-ID. The contract test uses it so a server regression
    cannot hide behind a client skip.
    """

    if envelope is None:
        return current
    etype = envelope.get("type") or event_name
    if etype == "snapshot":
        snapshot = envelope.get("snapshot")
        return snapshot if isinstance(snapshot, dict) else current
    if etype != "run_event" or envelope.get("event") is None or current is None:
        return current
    event = envelope["event"]
    merged = dict(current)
    merged["events"] = [*list(current.get("events") or []), event]
    if envelope.get("status") is not None and "status" in current:
        merged["status"] = envelope["status"]
    run = current.get("current_run")
    if isinstance(run, dict):
        next_run = dict(run)
        next_run["events"] = [*list(run.get("events") or []), event]
        if envelope.get("status") is not None:
            next_run["status"] = envelope["status"]
        merged["current_run"] = next_run
    return merged


class ResumeAfterSnapshotTests(unittest.TestCase):
    def test_cursor_is_snapshot_length_not_last_event_id(self) -> None:
        self.assertEqual(resume_after_snapshot(5), 5)
        self.assertEqual(resume_after_snapshot(1), 1)
        self.assertEqual(resume_after_snapshot(0), 0)


class EventStreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.scripted = ScriptedChatModel(echo_then_reply())

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
        snapshot_count = len(replay[0]["data"]["snapshot"]["events"])
        replayed_ids = [item["id"] for item in replay if item["event"] == "run_event"]
        self.assertNotIn(skip_id, replayed_ids)
        for item in replay:
            if item.get("event") == "run_event":
                self.assertGreater(item["data"]["seq"], snapshot_count, item)
        self.assertEqual(replay[-1]["event"], "stream_end")

    def test_snapshot_plus_resume_does_not_duplicate_events(self) -> None:
        """Reconnect with Last-Event-ID must not append snapshot rows again.

        Applies the desktop replace-then-append merge after every frame so a
        wire-id-only check cannot stay green while Chat / Agent-run grow.
        """

        started = self._start()
        first = read_stream_until_end(self.client, params={"run_id": started["id"]})
        self.assertEqual(first[0]["event"], "snapshot")
        persisted = self.client.get(f"/v1/agent-runs/{started['id']}").json()
        persisted_events = persisted["events"]
        self.assertGreaterEqual(len(persisted_events), 2, persisted_events)

        replay = read_stream_until_end(
            self.client,
            params={"run_id": started["id"]},
            headers={"Last-Event-ID": "1"},
        )
        self.assertEqual(replay[0]["event"], "snapshot")
        snapshot = replay[0]["data"]["snapshot"]
        snapshot_events = snapshot["events"]
        self.assertEqual(len(snapshot_events), len(persisted_events), snapshot_events)

        merged: dict[str, Any] | None = None
        for item in replay:
            merged = apply_snapshot_replace_then_append(merged, item.get("data"), item.get("event"))
            seen = record_events(merged)
            self.assertLessEqual(
                len(seen),
                len(persisted_events),
                f"snapshot-plus-resume duplicated events after {item.get('event')} "
                f"id={item.get('id')}: {len(seen)} > {len(persisted_events)}",
            )
            if item.get("event") == "run_event":
                seq = item["data"]["seq"] if item.get("data") else None
                self.assertIsNotNone(seq)
                self.assertGreater(
                    seq,
                    len(snapshot_events),
                    f"replayed snapshot row seq={seq} after a {len(snapshot_events)}-event snapshot",
                )

        self.assertEqual(record_events(merged), persisted_events)

    def test_live_snapshot_plus_resume_does_not_duplicate_events(self) -> None:
        """While the run is still live there is no terminal snapshot to heal a dup.

        Cancel while generate is held adds a second live row so Last-Event-ID: 1
        is behind the snapshot (the 5 → 9 shape). A later real row is allowed
        only when its seq is greater than the snapshot count.
        """

        hold = threading.Event()
        set_generate_hold(hold)
        self.addCleanup(set_generate_hold, None)
        self.addCleanup(hold.set)
        started = self._start()
        wait_for_generate_hold()
        cancelled = self.client.post(f"/v1/agent-runs/{started['id']}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        persisted = self.client.get(f"/v1/agent-runs/{started['id']}").json()
        persisted_events = persisted["events"]
        self.assertGreaterEqual(len(persisted_events), 2, persisted)
        self.assertTrue(is_run_lifecycle_live(persisted["status"]), persisted["status"])

        with loopback_app_server(self.app) as base_url:
            try:
                with patch("workbench_backend.event_stream.WAIT_TIMEOUT_SECONDS", 0.2):
                    replay = read_loopback_stream_until_idle(
                        base_url,
                        token=self.app.state.local_trust_token,
                        params={"run_id": started["id"]},
                        headers={"Last-Event-ID": "1"},
                        timeout=5.0,
                    )
                self.assertEqual(replay[0]["event"], "snapshot")
                self.assertTrue(any(item.get("comment") == "keepalive" for item in replay), replay)
                snapshot_events = replay[0]["data"]["snapshot"]["events"]
                self.assertGreaterEqual(len(snapshot_events), 2, snapshot_events)

                merged: dict[str, Any] | None = None
                newer = 0
                for item in replay:
                    merged = apply_snapshot_replace_then_append(merged, item.get("data"), item.get("event"))
                    seen = record_events(merged)
                    if item.get("event") == "run_event":
                        seq = item["data"]["seq"] if item.get("data") else None
                        self.assertIsNotNone(seq)
                        self.assertGreater(
                            seq,
                            len(snapshot_events),
                            f"live reconnect replayed snapshot row seq={seq} after a "
                            f"{len(snapshot_events)}-event snapshot",
                        )
                        newer += 1
                    self.assertEqual(
                        len(seen),
                        len(snapshot_events) + newer,
                        f"live reconnect duplicated events after {item.get('event')} "
                        f"id={item.get('id')}: {len(seen)} != {len(snapshot_events) + newer}",
                    )

                latest_body = self.client.get(f"/v1/agent-runs/{started['id']}").json()
                self.assertTrue(is_run_lifecycle_live(latest_body["status"]), latest_body["status"])
                latest = latest_body["events"]
                self.assertEqual(record_events(merged), latest[: len(record_events(merged))])
            finally:
                hold.set()

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
