"""MOD-005: LangChain adapter targets a deployment endpoint and starts no process."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from langchain_core.messages import HumanMessage

from workbench_backend.errors import HarnessError
from workbench_backend.inference.adapter import adapter_target, chat_model_for_deployment
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import (
    Deployment,
    DeploymentStatus,
    ManagementScope,
    SettingsBags,
)


class _RecordingHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, Any]] = []

    def do_GET(self) -> None:  # noqa: N802
        self._json(200, {"data": [{"id": "fake-llama"}]})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        body = json.loads(raw.decode("utf-8")) if raw else {}
        self.requests.append({"path": self.path, "body": body})
        self._json(
            200,
            {
                "id": "adapter-test",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "pong"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.endpoint = f"http://{host}:{port}/v1"
        self.start_calls = 0

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _deployment(self, *, endpoint: str | None | bool = True) -> Deployment:
        now = utc_now()
        chosen = self.endpoint if endpoint is True else endpoint
        return Deployment(
            id="deploy_adapter",
            display_name="adapter-test",
            scope=ManagementScope.connected,
            status=DeploymentStatus.running,
            endpoint=None if chosen is None else str(chosen),
            created_at=now,
            updated_at=now,
            settings=SettingsBags(),
        )

    def test_adapter_posts_only_to_deployment_endpoint(self) -> None:
        sink: list[dict[str, Any]] = []
        model = chat_model_for_deployment(self._deployment(), capture_sink=sink)
        result = model.invoke([HumanMessage(content="ping")])
        self.assertEqual(result.content, "pong")
        self.assertEqual(self.start_calls, 0)
        self.assertTrue(_RecordingHandler.requests)
        posted = _RecordingHandler.requests[0]
        self.assertTrue(posted["path"].endswith("/chat/completions"))
        self.assertEqual(posted["body"]["messages"][0]["content"], "ping")
        self.assertTrue(sink)
        self.assertIn("/chat/completions", sink[0]["url"])
        self.assertEqual(sink[0]["body"]["messages"][0]["content"], "ping")

    def test_adapter_starts_no_inference_process(self) -> None:
        target = adapter_target(self._deployment())
        self.assertFalse(target["starts_inference"])
        self.assertEqual(target["endpoint"], self.endpoint)
        self.assertEqual(self.start_calls, 0)
        # Creating the model must not spawn llama-server or any other process.
        chat_model_for_deployment(self._deployment())
        self.assertEqual(self.start_calls, 0)

    def test_missing_endpoint_is_not_a_successful_adapter(self) -> None:
        with self.assertRaises(HarnessError) as raised:
            chat_model_for_deployment(self._deployment(endpoint=None))
        self.assertEqual(raised.exception.code, "no_endpoint")
        self.assertEqual(self.start_calls, 0)


if __name__ == "__main__":
    unittest.main()
