"""Issue #64: Knowledge capture policy on model_requests and case export.

Synthetic credentials only. The detector is incomplete; these tests do not
claim perfect secret detection.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.messages import HumanMessage
from langchain.agents.middleware import ModelRequest, ModelResponse

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import AgentRun, ModelRequestCapture
from workbench_backend.app import create_app
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.knowledge.diagnostics import apply_capture_policy
from workbench_backend.knowledge.redaction import DETECTOR_LIMITATIONS, REDACTION_MARK
from workbench_backend.knowledge.schemas import ContextCaptureSettings
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel, set_capture_sink
from tests.support import close_workbench_sqlite, offline_workbench_client

# Synthetic fixtures only — never real secrets.
SYNTH_API_KEY = "wb_synth_api_key_0001"
SYNTH_ASSIGNMENT = f"API_KEY={SYNTH_API_KEY}"
SYNTH_TOKEN = "wb_synth_token_0001"
SYNTH_TOKEN_ASSIGNMENT = f"token={SYNTH_TOKEN}"


def wait_for_run(client: TestClient, run_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/agent-runs/{run_id}")
        body = response.json()
        if body.get("status") in {"completed", "cancelled", "failed"}:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not finish: {body}")


def echo_secret_then_reply() -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "echo",
                    "args": {"text": SYNTH_ASSIGNMENT},
                    "id": "call_echo_synth",
                }
            ],
        ),
        AIMessage(content="The echo tool returned a synthetic credential marker."),
    ]


class CapturePolicyUnitTests(unittest.TestCase):
    def test_redact_secrets_applies_to_messages_and_http_payload(self) -> None:
        capture = ModelRequestCapture(
            at=utc_now(),
            instructions=f"system {SYNTH_ASSIGNMENT}",
            messages=[{"role": "human", "content": f"please use {SYNTH_ASSIGNMENT}"}],
            available_tools=["echo"],
            presented_tools=["echo"],
            http_payload={"body": {"messages": [{"content": SYNTH_TOKEN_ASSIGNMENT}]}},
        )
        applied = apply_capture_policy(capture, ContextCaptureSettings())
        self.assertTrue(applied.retained)
        self.assertTrue(applied.redacted)
        self.assertFalse(applied.discarded)
        self.assertIn(REDACTION_MARK, applied.instructions or "")
        self.assertNotIn(SYNTH_API_KEY, json.dumps(applied.model_dump()))
        self.assertNotIn(SYNTH_TOKEN, json.dumps(applied.http_payload))
        self.assertEqual(applied.available_tools, ["echo"])
        self.assertEqual(applied.presented_tools, ["echo"])

    def test_discard_drops_diagnostic_bodies_but_keeps_provenance(self) -> None:
        capture = ModelRequestCapture(
            at=utc_now(),
            instructions=SYNTH_ASSIGNMENT,
            messages=[{"role": "tool", "content": SYNTH_ASSIGNMENT}],
            available_tools=["echo"],
            presented_tools=["echo"],
            memory_versions=["knv_synth"],
            http_payload={"body": SYNTH_ASSIGNMENT},
            capture_gaps=["no retrieval / RAG (OQ-006 unresolved)"],
        )
        applied = apply_capture_policy(
            capture, ContextCaptureSettings(redaction_mode="discard")
        )
        self.assertTrue(applied.discarded)
        self.assertFalse(applied.retained)
        self.assertIsNone(applied.instructions)
        self.assertEqual(applied.messages, [])
        self.assertIsNone(applied.http_payload)
        self.assertEqual(applied.available_tools, ["echo"])
        self.assertEqual(applied.memory_versions, ["knv_synth"])
        self.assertIn("discarded by Knowledge capture policy", " ".join(applied.capture_gaps))
        self.assertNotIn(SYNTH_API_KEY, applied.model_dump_json())

    def test_retention_zero_expires_and_drops_content(self) -> None:
        capture = ModelRequestCapture(
            at=utc_now(),
            messages=[{"role": "human", "content": SYNTH_ASSIGNMENT}],
            http_payload={"raw": SYNTH_ASSIGNMENT},
        )
        applied = apply_capture_policy(
            capture,
            ContextCaptureSettings(redaction_mode="redact_secrets", retention_seconds=0),
        )
        self.assertTrue(applied.expired)
        self.assertFalse(applied.retained)
        self.assertEqual(applied.messages, [])
        self.assertIsNone(applied.http_payload)
        self.assertNotIn(SYNTH_API_KEY, applied.model_dump_json())

    def test_discard_drops_failed_transport_evidence_bodies(self) -> None:
        capture = ModelRequestCapture(
            at=utc_now(),
            http_payload={"body": {"messages": [{"content": SYNTH_ASSIGNMENT}]}},
            http_payloads=[
                {"body": {"messages": [{"content": SYNTH_ASSIGNMENT}]}},
            ],
            transport_attempted=True,
            transport_attempt_count=1,
            response_observed=False,
            failure={"type": "RuntimeError", "message": SYNTH_ASSIGNMENT},
        )
        applied = apply_capture_policy(
            capture, ContextCaptureSettings(redaction_mode="discard")
        )
        self.assertTrue(applied.discarded)
        self.assertIsNone(applied.http_payload)
        self.assertEqual(applied.http_payloads, [])
        self.assertIsNone(applied.failure)
        self.assertTrue(applied.transport_attempted)
        self.assertEqual(applied.transport_attempt_count, 1)
        self.assertFalse(applied.response_observed)
        self.assertNotIn(SYNTH_API_KEY, applied.model_dump_json())


class CaptureFailureMiddlewareTests(unittest.TestCase):
    def _run(self) -> AgentRun:
        now = utc_now()
        return AgentRun(
            id="run_capture_failure",
            deployment_id="deploy_capture_failure",
            task="fail",
            enabled_tools=["echo"],
            presented_tools=["echo"],
            created_at=now,
            updated_at=now,
        )

    def _request(self) -> ModelRequest:
        return ModelRequest(
            model=ScriptedChatModel([AIMessage(content="unused")]),
            messages=[HumanMessage(content="please fail")],
            tools=[],
            model_settings={"temperature": 0.4},
        )

    def test_sync_failure_before_transport_preserves_original_exception(self) -> None:
        run = self._run()
        sink: list[dict[str, Any]] = []
        middleware = WorkbenchHarnessMiddleware(run, http_sink=sink)
        original = RuntimeError(f"synthetic transport failure {SYNTH_ASSIGNMENT}")

        def handler(_request: ModelRequest) -> ModelResponse:
            raise original

        with self.assertRaises(RuntimeError) as raised:
            middleware.wrap_model_call(self._request(), handler)
        self.assertIs(raised.exception, original)
        self.assertEqual(len(run.model_requests), 1)
        capture = run.model_requests[0]
        self.assertTrue(capture.request_prepared)
        self.assertFalse(capture.transport_attempted)
        self.assertEqual(capture.transport_attempt_count, 0)
        self.assertFalse(capture.response_observed)
        self.assertFalse(capture.handler_returned)
        self.assertEqual(capture.failure["type"], "RuntimeError")
        self.assertIn(REDACTION_MARK, capture.failure["message"])
        self.assertNotIn(SYNTH_API_KEY, capture.model_dump_json())

    def test_async_failure_capture_records_all_retry_payloads(self) -> None:
        run = self._run()
        sink: list[dict[str, Any]] = []
        middleware = WorkbenchHarnessMiddleware(run, http_sink=sink)
        original = RuntimeError("async failure")

        async def handler(_request: ModelRequest) -> ModelResponse:
            sink.append({"body": {"messages": [{"content": "attempt one"}]}})
            sink.append({"body": {"messages": [{"content": "attempt two"}]}})
            raise original

        async def invoke() -> None:
            with self.assertRaises(RuntimeError) as raised:
                await middleware.awrap_model_call(self._request(), handler)
            self.assertIs(raised.exception, original)

        asyncio.run(invoke())
        self.assertEqual(len(run.model_requests), 1)
        capture = run.model_requests[0]
        self.assertTrue(capture.request_prepared)
        self.assertTrue(capture.transport_attempted)
        self.assertEqual(capture.transport_attempt_count, 2)
        self.assertFalse(capture.response_observed)
        self.assertFalse(capture.handler_returned)
        self.assertEqual(len(capture.http_payloads), 2)
        self.assertEqual(capture.http_payload, capture.http_payloads[-1])

    def test_success_capture_distinguishes_handler_return_from_transport_response(self) -> None:
        run = self._run()
        sink: list[dict[str, Any]] = []
        middleware = WorkbenchHarnessMiddleware(run, http_sink=sink)

        def handler(_request: ModelRequest) -> ModelResponse:
            return ModelResponse(result=[AIMessage(content="ok")])

        response = middleware.wrap_model_call(self._request(), handler)

        self.assertEqual(response.result[0].content, "ok")
        capture = run.model_requests[0]
        self.assertTrue(capture.request_prepared)
        self.assertFalse(capture.transport_attempted)
        self.assertEqual(capture.transport_attempt_count, 0)
        self.assertFalse(capture.response_observed)
        self.assertTrue(capture.handler_returned)

    def test_async_prepared_failure_does_not_reuse_previous_attempt(self) -> None:
        run = self._run()
        middleware = WorkbenchHarnessMiddleware(run, http_sink=[{"body": {"old": True}}])
        original = RuntimeError("failed before transport")

        async def handler(_request: ModelRequest) -> ModelResponse:
            raise original

        async def invoke() -> None:
            with self.assertRaises(RuntimeError) as caught:
                await middleware.awrap_model_call(self._request(), handler)
            self.assertIs(caught.exception, original)

        asyncio.run(invoke())
        capture = run.model_requests[0]
        self.assertTrue(capture.request_prepared)
        self.assertFalse(capture.transport_attempted)
        self.assertFalse(capture.response_observed)
        self.assertFalse(capture.handler_returned)
        self.assertEqual(capture.http_payloads, [])
        self.assertIsNone(capture.http_payload)

    def test_capture_failure_does_not_mask_handler_exception(self) -> None:
        run = self._run()
        middleware = WorkbenchHarnessMiddleware(
            run,
            http_sink=[],
            settings_provider=lambda: (_ for _ in ()).throw(RuntimeError("capture failed")),
        )
        original = RuntimeError("handler failed")

        def handler(_request: ModelRequest) -> ModelResponse:
            raise original

        with self.assertRaises(RuntimeError) as raised:
            middleware.wrap_model_call(self._request(), handler)

        self.assertIs(raised.exception, original)
        self.assertEqual(run.model_requests, [])
        self.assertEqual(run.events[-1].kind, "model_request_capture_failed")


class _FailingChatHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, Any]] = []

    def do_GET(self) -> None:  # noqa: N802
        self._json(200, {"data": [{"id": "fake-llama"}]})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        body = json.loads(raw.decode("utf-8")) if raw else {}
        self.requests.append({"path": self.path, "body": body})
        self._json(500, {"error": {"message": f"failed {SYNTH_ASSIGNMENT}"}})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class PrivacyDiagnosticsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.manager = ModelManager(self.paths)
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager

        def factory(_run: AgentRun, sink: list[dict[str, Any]]) -> ScriptedChatModel:
            # Append during generate so #57 per-call HTTP observation sees this
            # payload on the call that produced it (not a stale factory preload).
            set_capture_sink(sink, {"body": {"messages": [{"content": SYNTH_ASSIGNMENT}]}})
            return ScriptedChatModel(echo_secret_then_reply())

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        self.app.state.lab._manager_provider = lambda: self.manager
        self.app.state.lab._harness_provider = lambda: self.app.state.harness
        self.app.state.lab._knowledge_provider = lambda: self.app.state.knowledge
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "privacy-diag"},
        ).json()["id"]

    def tearDown(self) -> None:
        set_capture_sink(None)
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _start(self, **extra: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "deployment_id": self.deployment_id,
            "task": "Echo the synthetic marker using the echo tool.",
            "presented_tools": ["echo"],
            **extra,
        }
        response = self.client.post("/v1/agent-runs", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return wait_for_run(self.client, response.json()["id"])

    def _sqlite_run(self, run_id: str) -> dict[str, Any]:
        # sqlite3 connection context managers do not close; Windows then cannot
        # delete application.sqlite in TemporaryDirectory.cleanup().
        conn = sqlite3.connect(self.paths.application_db)
        try:
            row = conn.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        return json.loads(row[0])

    def test_default_redaction_applies_to_persisted_model_requests(self) -> None:
        body = self._start()
        self.assertTrue(body["model_requests"])
        capture = body["model_requests"][0]
        dumped = json.dumps(body["model_requests"])
        self.assertNotIn(SYNTH_API_KEY, dumped)
        self.assertTrue(capture["redacted"] or capture["discarded"])
        self.assertIn("echo", capture["available_tools"])
        self.assertEqual(capture["presented_tools"], ["echo"])
        stored = self._sqlite_run(body["id"])
        self.assertNotIn(SYNTH_API_KEY, json.dumps(stored["model_requests"]))
        http_payload = stored["model_requests"][0].get("http_payload")
        if http_payload is not None:
            self.assertNotIn(SYNTH_API_KEY, json.dumps(http_payload))

    def test_discard_does_not_retain_model_requests_or_http_payload(self) -> None:
        updated = self.client.put(
            "/v1/knowledge/config",
            json={"context_captures": {"redaction_mode": "discard"}},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        body = self._start()
        self.assertTrue(body["model_requests"])
        for capture in body["model_requests"]:
            self.assertTrue(capture["discarded"])
            self.assertFalse(capture["retained"])
            self.assertIsNone(capture["instructions"])
            self.assertEqual(capture["messages"], [])
            self.assertIsNone(capture["http_payload"])
            self.assertIn("echo", capture["available_tools"])
        stored = self._sqlite_run(body["id"])
        for capture in stored["model_requests"]:
            self.assertIsNone(capture.get("http_payload"))
            self.assertEqual(capture.get("messages"), [])
            self.assertNotIn(SYNTH_API_KEY, json.dumps(capture))

    def test_retention_expiry_drops_persisted_diagnostic_bodies(self) -> None:
        updated = self.client.put(
            "/v1/knowledge/config",
            json={
                "context_captures": {
                    "redaction_mode": "redact_secrets",
                    "retention_seconds": 0,
                }
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        body = self._start()
        self.assertTrue(body["model_requests"])
        for capture in body["model_requests"]:
            self.assertTrue(capture["expired"])
            self.assertFalse(capture["retained"])
            self.assertEqual(capture["messages"], [])
            self.assertIsNone(capture["http_payload"])
        stored = self._sqlite_run(body["id"])
        self.assertNotIn(SYNTH_API_KEY, json.dumps(stored["model_requests"]))


class FailedTransportDiagnosticsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _FailingChatHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FailingChatHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.endpoint = f"http://{host}:{port}/v1"
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.app = create_app(data_root=self.root)
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": self.endpoint, "display_name": "failing-diag"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def _sqlite_run(self, run_id: str) -> dict[str, Any]:
        conn = sqlite3.connect(self.paths.application_db)
        try:
            row = conn.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        return json.loads(row[0])

    def test_failed_harness_run_persists_redacted_transport_evidence(self) -> None:
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": f"Use this synthetic credential marker: {SYNTH_ASSIGNMENT}",
                "presented_tools": ["echo"],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_run(self.client, started.json()["id"])

        self.assertEqual(body["status"], "failed")
        self.assertTrue(body["model_requests"])
        capture = body["model_requests"][0]
        self.assertTrue(capture["request_prepared"])
        self.assertTrue(capture["transport_attempted"])
        self.assertGreaterEqual(capture["transport_attempt_count"], 1)
        self.assertTrue(capture["response_observed"])
        self.assertFalse(capture["handler_returned"])
        self.assertEqual(capture["http_payloads"][0]["response_status_code"], 500)
        self.assertNotIn(SYNTH_API_KEY, json.dumps(capture))
        stored = self._sqlite_run(body["id"])
        self.assertNotIn(SYNTH_API_KEY, json.dumps(stored["model_requests"]))
        stored_capture = stored["model_requests"][0]
        self.assertTrue(stored_capture["response_observed"])
        self.assertGreaterEqual(stored_capture["transport_attempt_count"], 1)


class PrivacyExportApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.manager = ModelManager(self.paths)
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel(echo_secret_then_reply())

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        self.app.state.lab._manager_provider = lambda: self.manager
        self.app.state.lab._harness_provider = lambda: self.app.state.harness
        self.app.state.lab._knowledge_provider = lambda: self.app.state.knowledge
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "privacy-export"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _workspace(self, files: dict[str, str] | None = None) -> dict[str, Any]:
        return self.client.post(
            "/v1/lab/workspaces",
            json={
                "display_name": "privacy-export",
                "files": files or {"notes.md": "safe notes"},
            },
        ).json()

    def _capture(self, workspace_id: str, **extra: Any) -> dict[str, Any]:
        payload = {
            "workspace_id": workspace_id,
            "deployment_id": self.deployment_id,
            "task": extra.pop("task", "Echo a harmless phrase."),
            **extra,
        }
        response = self.client.post("/v1/lab/cases/capture", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _assert_shareable(self, export: dict[str, Any]) -> None:
        dumped = json.dumps(export)
        self.assertNotIn(SYNTH_API_KEY, dumped)
        self.assertNotIn(SYNTH_TOKEN, dumped)
        self.assertIn("incomplete", export["detector_limitations"].lower())
        self.assertEqual(export["detector_limitations"], DETECTOR_LIMITATIONS)
        if export["secret_scan_clean"]:
            self.assertEqual(export["export_status"], "clean")
            self.assertNotIn(SYNTH_ASSIGNMENT, dumped)
        else:
            self.assertEqual(export["export_status"], "sanitized")
            self.assertTrue(export["sanitized_fields"])

    def test_export_sanitizes_synthetic_credential_in_task(self) -> None:
        workspace = self._workspace()
        case = self._capture(workspace["id"], task=f"Document {SYNTH_ASSIGNMENT} in the task.")
        self.assertIn(SYNTH_API_KEY, case["task"])
        response = self.client.get(f"/v1/lab/cases/{case['id']}/export")
        self.assertEqual(response.status_code, 200, response.text)
        export = response.json()
        self.assertFalse(export["secret_scan_clean"])
        self.assertEqual(export["export_status"], "sanitized")
        self.assertIn("task", export["sanitized_fields"])
        self.assertNotEqual(export["case"]["task"], case["task"])
        self.assertIn(REDACTION_MARK, export["case"]["task"])
        stored = self.client.get(f"/v1/lab/cases/{case['id']}").json()
        self.assertIn(SYNTH_API_KEY, stored["task"])
        self._assert_shareable(export)

    def test_export_sanitizes_synthetic_credential_in_tool_fixtures(self) -> None:
        workspace = self._workspace()
        case = self._capture(workspace["id"])
        loaded = self.app.state.lab.get_case(case["id"])
        loaded.tool_fixtures = [
            {
                "name": "echo",
                "args": {"text": SYNTH_TOKEN_ASSIGNMENT},
                "result": SYNTH_ASSIGNMENT,
            }
        ]
        self.app.state.lab.store.put_case(loaded)
        response = self.client.get(f"/v1/lab/cases/{case['id']}/export")
        self.assertEqual(response.status_code, 200, response.text)
        export = response.json()
        self.assertFalse(export["secret_scan_clean"])
        self.assertEqual(export["export_status"], "sanitized")
        self.assertIn("tool_fixtures", export["sanitized_fields"])
        self.assertNotIn(SYNTH_API_KEY, json.dumps(export["case"]["tool_fixtures"]))
        self.assertNotIn(SYNTH_TOKEN, json.dumps(export["case"]["tool_fixtures"]))
        stored = self.client.get(f"/v1/lab/cases/{case['id']}").json()
        self.assertIn(SYNTH_API_KEY, json.dumps(stored["tool_fixtures"]))
        self._assert_shareable(export)

    def test_export_sanitizes_ordinary_config_file(self) -> None:
        workspace = self._workspace(
            {
                "settings.json": f'endpoint=local\n{SYNTH_ASSIGNMENT}\n',
                "notes.md": "safe notes",
            }
        )
        case = self._capture(workspace["id"])
        response = self.client.get(f"/v1/lab/cases/{case['id']}/export")
        self.assertEqual(response.status_code, 200, response.text)
        export = response.json()
        self.assertFalse(export["secret_scan_clean"])
        self.assertEqual(export["export_status"], "sanitized")
        self.assertTrue(any(item.startswith("snapshot_file:") for item in export["sanitized_fields"]))
        self.assertIn("settings.json", export["exported_files"])
        self.assertNotIn(SYNTH_API_KEY, export["exported_files"]["settings.json"])
        self.assertIn(REDACTION_MARK, export["exported_files"]["settings.json"])
        on_disk = (self.paths.snapshots / case["snapshot_id"] / "tree" / "settings.json").read_text(
            encoding="utf-8"
        )
        self.assertIn(SYNTH_API_KEY, on_disk)
        self._assert_shareable(export)


if __name__ == "__main__":
    unittest.main()
