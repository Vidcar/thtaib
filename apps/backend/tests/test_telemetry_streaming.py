"""Real adapter/graph streaming exposes attributed measurements through stored SDK state."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run
from workbench_backend.app import create_app
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import ServerProperties


class TelemetryStreamingTests(unittest.TestCase):
    def test_live_measurements_reset_between_tool_calls_and_reach_durable_projection(self):
        release_first, second_entered, start_second, release_second = [threading.Event() for _ in range(4)]
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                data = json.dumps({"data": [{"id": "telemetry-model"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                index = len(calls)
                if index == 2:
                    second_entered.set()
                    start_second.wait(10)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                delta = {"role": "assistant", "content": "finished"} if index == 2 else {
                    "role": "assistant", "tool_calls": [{"index": 0, "id": "todo-call", "type": "function",
                        "function": {"name": "write_todos", "arguments": json.dumps({"todos": [{"content": "Check telemetry", "status": "completed"}]})}}],
                }
                timings = {"cache_n": 80, "prompt_n": 20 * index, "predicted_n": 10 * index,
                           "predicted_ms": 250, "predicted_per_second": 36 if index == 1 else 76}
                base = {"id": f"call-{index}", "object": "chat.completion.chunk", "model": "telemetry-model"}
                self.wfile.write(("data: " + json.dumps({**base, "choices": [{"index": 0, "delta": delta}], "timings": timings}) + "\n\n").encode())
                self.wfile.flush()
                (release_first if index == 1 else release_second).wait(10)
                self.wfile.write(("data: " + json.dumps({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if index == 1 else "stop"}],
                    "usage": {"prompt_tokens": 80 + 20 * index, "completion_tokens": 10 * index, "total_tokens": 80 + 30 * index}}) + "\n\ndata: [DONE]\n\n").encode())
                self.wfile.flush()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        temporary = tempfile.TemporaryDirectory()
        app = create_app(data_root=Path(temporary.name))
        client = offline_workbench_client(app)
        try:
            endpoint = f"http://127.0.0.1:{server.server_port}/v1"
            deployment_id = client.post("/v1/deployments/connected", json={"endpoint": endpoint}).json()["id"]
            deployment = app.state.manager.get_deployment(deployment_id)
            deployment.server_props = ServerProperties(fetched=utc_now(), source_url=endpoint + "/props", n_ctx=8192,
                default_generation_settings={"timings_per_token": False})
            app.state.manager.store.put_deployment(deployment)
            conversation_id = client.post("/v1/chat/conversations", json={"deployment_id": deployment_id}).json()["id"]
            registered = client.post("/v1/agent-interaction/threads", json={"source_surface": "chat", "conversation_id": conversation_id})
            self.assertEqual(registered.status_code, 200, registered.text)
            response = client.post(f"/v1/chat/conversations/{conversation_id}/start", json={"task": "Check telemetry", "presented_tools": ["write_todos"]})
            self.assertEqual(response.status_code, 200, response.text)
            run_id = response.json()["current_run_id"]

            def observed(predicate):
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    # Live samples stay on the in-memory run and the interaction
                    # snapshot. They do not rewrite the captured model requests.
                    value = app.state.harness.get_run(run_id).generation_observation
                    if predicate(value):
                        return value
                    time.sleep(.01)
                self.fail("Expected telemetry did not reach the live run")

            first = observed(lambda value: value is not None and value.phase == "generating")
            self.assertEqual(first.context_used_tokens, 110)
            self.assertEqual(first.context_limit, 8192)
            binding = app.state.app_store.get_interaction(conversation_id)
            self.assertEqual(binding["snapshot"]["workbench"]["run"]["generation_observation"], first.model_dump(mode="json"))
            self.assertTrue(any(item["method"] == "values" and item["params"]["data"].get("workbench", {}).get("run", {}).get("generation_observation", {}).get("request_id") == first.request_id
                                for item in app.state.app_store.interaction_events_after(conversation_id, 0)
                                if item.get("params", {}).get("data", {}).get("workbench", {}).get("run", {}).get("generation_observation")))
            release_first.set()
            self.assertTrue(second_entered.wait(10), client.get(f"/v1/agent-runs/{run_id}").json().get("error"))
            self.assertIsNone(app.state.harness.get_run(run_id).generation_observation)
            self.assertIsNone(app.state.app_store.get_interaction(conversation_id)["snapshot"]["workbench"]["run"]["generation_observation"])
            start_second.set()
            second = observed(lambda value: value is not None and value.request_id != first.request_id)
            self.assertEqual(second.context_used_tokens, 140)
            self.assertEqual(second.tokens_per_second, 76)
            release_second.set()
            final = wait_for_run(client, run_id)
            self.assertEqual(final["status"], "completed", final.get("error"))
            self.assertEqual(final["generation_observation"]["phase"], "completed")
            self.assertEqual(final["generation_observation"]["request_id"], second.request_id)
            self.assertEqual(final["generation_observation"]["output_tokens"], 20)
            self.assertEqual(len(final["tool_invocations"]), 1)
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(call["timings_per_token"] and call["return_progress"] for call in calls))
            self.assertEqual(app.state.app_store.get_interaction(conversation_id)["snapshot"]["workbench"]["run"]["generation_observation"], final["generation_observation"])
        finally:
            for gate in (release_first, start_second, release_second):
                gate.set()
            close_workbench_sqlite(app, client)
            server.shutdown()
            server.server_close()
            temporary.cleanup()
