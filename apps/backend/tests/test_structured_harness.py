"""Harness-level structured-output integration regressions."""

from __future__ import annotations

import http.server
import json
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.inference.capabilities import setup_fingerprint
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import ServerProperties

from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run


class _ThreadingHttpServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _NativeHandler(http.server.BaseHTTPRequestHandler):
    requests: list[dict[str, Any]] = []

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/props":
            self.send_response(404)
            self.end_headers()
            return
        self._json(
            200,
            {
                "model_alias": "native-fixture",
                "default_generation_settings": {"n_ctx": 8192, "params": {}},
                "chat_template_caps": {"supports_tools": True, "supports_tool_calls": True},
                "modalities": {"vision": False},
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        body = json.loads(raw.decode("utf-8")) if raw else {}
        self.requests.append({"path": self.path, "body": body})
        self._json(
            200,
            {
                "id": "native-structured-test",
                "object": "chat.completion",
                "created": 1,
                "model": "native-fixture",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "plain answer"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    def log_message(self, *_args: object) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class RecordingStructuredModel(BaseChatModel):
    """Scripted model that records bound tools for each model request."""

    _script: list[AIMessage] = PrivateAttr(default_factory=list)
    _index: int = PrivateAttr(default=0)
    _bind_calls: list[list[str]] = PrivateAttr(default_factory=list)
    _generate_messages: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    def __init__(self, script: list[AIMessage]) -> None:
        super().__init__()
        self._script = list(script)
        self._index = 0
        self._bind_calls = []
        self._generate_messages = []

    @property
    def bind_calls(self) -> list[list[str]]:
        return self._bind_calls

    @property
    def generate_messages(self) -> list[list[BaseMessage]]:
        return self._generate_messages

    @property
    def _llm_type(self) -> str:
        return "recording-structured"

    def bind_tools(self, tools: list[Any], **_kwargs: Any) -> "RecordingStructuredModel":
        self._bind_calls.append([_tool_name(item) for item in tools])
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **_kwargs: Any,
    ) -> ChatResult:
        self._generate_messages.append(list(messages))
        if self._index >= len(self._script):
            message = AIMessage(content="done")
        else:
            message = self._script[self._index]
            self._index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


class StructuredHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "structured-fixture"},
        ).json()["id"]
        self._set_props()
        self.harnesses: list[HarnessService] = []

    def tearDown(self) -> None:
        for harness in self.harnesses:
            harness.close(timeout=1.0)
            if harness._app_store is not None:
                harness._app_store.close()
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def _install_harness(self, model: RecordingStructuredModel) -> HarnessService:
        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> RecordingStructuredModel:
            return model

        harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
        )
        self.app.state.harness = harness
        self.harnesses.append(harness)
        return harness

    def _set_props(self) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        self.manager.store.put_deployment(
            deployment.model_copy(
                update={
                    "server_props": ServerProperties(
                        fetched=utc_now(),
                        source_url="http://127.0.0.1:9/props",
                        model_alias="structured-fixture",
                        n_ctx=8192,
                        chat_template_caps={"supports_tools": True, "supports_tool_calls": True},
                        modalities={"vision": False},
                    )
                }
            )
        )

    def _record_capabilities(self, *capabilities: str) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        fingerprint = setup_fingerprint(deployment)
        for capability in capabilities:
            self.manager.store.put_capability_evidence(
                {
                    "schema_version": 1,
                    "id": f"probe_{capability}_{len(deployment.capability_evidence)}",
                    "deployment_id": deployment.id,
                    "capability": capability,
                    "status": "passed",
                    "fingerprint": fingerprint,
                    "setup": {},
                    "tested_at": utc_now(),
                    "inputs": {},
                    "observations": {},
                }
            )

    def _schema(self, *, name: str = "AnswerShape") -> dict[str, Any]:
        return {
            "schema_version": 1,
            "name": name,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
        }

    def _start(self, **extra: Any) -> dict[str, Any]:
        response = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Produce the requested structured answer.",
                **extra,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_effectful_tool_then_invalid_structured_call_repairs_once_without_repeating_effect(self) -> None:
        self._record_capabilities("tools", "structured_tools", "structured_tools_with_tools")
        model = RecordingStructuredModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "echo", "args": {"text": "first-effect"}, "id": "call_echo"}],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "AnswerShape", "args": {"answer": "bad-a"}, "id": "call_bad_a"},
                        {"name": "AnswerShape", "args": {"answer": "bad-b"}, "id": "call_bad_b"},
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "AnswerShape", "args": {"answer": "repaired"}, "id": "call_good"}],
                ),
            ]
        )
        self._install_harness(model)

        body = wait_for_run(
            self.client,
            self._start(presented_tools=["echo"], output_schema=self._schema())["id"],
        )

        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertEqual(body["structured_output"]["validation_status"], "valid")
        self.assertEqual(body["structured_output"]["repair_attempts"], 1)
        self.assertEqual(body["structured_output"]["result"], {"answer": "repaired"})
        self.assertEqual(
            [item["name"] for item in body["tool_invocations"]].count("echo"),
            1,
        )
        self.assertEqual(
            [event["kind"] for event in body["events"]].count("structured_output_repair_attempted"),
            1,
        )
        self.assertTrue(any("AnswerShape" in names for names in model.bind_calls))

    def test_malicious_effectful_tool_call_during_repair_does_not_execute(self) -> None:
        self._record_capabilities("tools", "structured_tools", "structured_tools_with_tools")
        model = RecordingStructuredModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "echo", "args": {"text": "first-effect"}, "id": "call_echo"}],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "AnswerShape", "args": {"answer": "bad-a"}, "id": "call_bad_a"},
                        {"name": "AnswerShape", "args": {"answer": "bad-b"}, "id": "call_bad_b"},
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "AnswerShape", "args": {"answer": "repaired"}, "id": "call_good"},
                        {"name": "echo", "args": {"text": "repeat-effect"}, "id": "call_malicious"},
                    ],
                ),
            ]
        )
        self._install_harness(model)

        body = wait_for_run(
            self.client,
            self._start(presented_tools=["echo"], output_schema=self._schema())["id"],
        )

        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["structured_output"]["repair_attempts"], 1)
        self.assertEqual(
            [item["name"] for item in body["tool_invocations"]].count("echo"),
            1,
        )
        self.assertIn("Formatting recovery cannot execute", body["error"])

    def test_write_todos_strategy_matches_actual_structured_tool_binding(self) -> None:
        self._record_capabilities("tools", "structured_tools", "structured_tools_with_tools")
        model = RecordingStructuredModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "AnswerShape", "args": {"answer": "planned"}, "id": "call_answer"}],
                )
            ]
        )
        self._install_harness(model)

        body = wait_for_run(
            self.client,
            self._start(presented_tools=["write_todos"], output_schema=self._schema())["id"],
        )

        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertEqual(body["structured_output"]["strategy"], "tool")
        self.assertTrue(
            any("AnswerShape" in names for names in model.bind_calls),
            model.bind_calls,
        )

    def test_schema_valid_wrong_answer_is_structurally_valid_not_factually_checked(self) -> None:
        self._record_capabilities("tools", "structured_tools", "structured_tools_with_tools")
        model = RecordingStructuredModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "AnswerShape", "args": {"answer": "2 + 2 = 5"}, "id": "call_answer"}],
                )
            ]
        )
        self._install_harness(model)

        body = wait_for_run(
            self.client,
            self._start(presented_tools=["echo"], output_schema=self._schema())["id"],
        )

        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertEqual(body["structured_output"]["validation_status"], "valid")
        self.assertEqual(body["structured_output"]["result"], {"answer": "2 + 2 = 5"})
        self.assertIn("not factual correctness", body["structured_output"]["note"])

    def test_native_tools_off_wire_omits_tools_and_missing_structured_response_fails(self) -> None:
        _NativeHandler.requests = []
        server = _ThreadingHttpServer(("127.0.0.1", 0), _NativeHandler)
        self.addCleanup(server.server_close)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.shutdown)
        native = self.client.post(
            "/v1/deployments/connected",
            json={
                "endpoint": f"http://127.0.0.1:{server.server_address[1]}/v1",
                "display_name": "native-fixture",
            },
        ).json()
        self.deployment_id = native["id"]
        deployment = self.manager.get_deployment(self.deployment_id)
        self.manager.store.put_deployment(
            deployment.model_copy(
                update={
                    "server_props": ServerProperties(
                        fetched=utc_now(),
                        source_url=f"http://127.0.0.1:{server.server_address[1]}/props",
                        model_alias="native-fixture",
                        n_ctx=8192,
                        chat_template_caps={"supports_tools": True, "supports_tool_calls": True},
                        modalities={"vision": False},
                    )
                }
            )
        )
        self._record_capabilities("structured_native")
        harness = HarnessService(lambda: self.manager, knowledge_provider=lambda: self.app.state.knowledge)
        self.app.state.harness = harness
        self.harnesses.append(harness)

        body = wait_for_run(
            self.client,
            self._start(presented_tools=[], output_schema={**self._schema(), "strategy": "native"})["id"],
        )

        self.assertEqual(body["status"], "failed")
        self.assertIn(body["stop_reason"], {"failed", "structured_output_invalid"})
        self.assertNotEqual(body["structured_output"]["validation_status"], "valid")
        self.assertTrue(_NativeHandler.requests)
        wire = _NativeHandler.requests[-1]["body"]
        self.assertNotIn("tools", wire)
        self.assertIn("response_format", wire)


def _tool_name(item: Any) -> str:
    if isinstance(item, dict):
        function = item.get("function")
        if isinstance(function, dict):
            return str(function.get("name") or "")
        return str(item.get("name") or item.get("type") or "")
    return str(getattr(item, "name", type(item).__name__))


if __name__ == "__main__":
    unittest.main()
