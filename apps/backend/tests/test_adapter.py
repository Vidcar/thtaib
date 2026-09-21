"""MOD-005: LangChain adapter targets a deployment endpoint and starts no process."""

from __future__ import annotations

import json
import asyncio
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from typing import Any

import httpx
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from workbench_backend.errors import HarnessError
from workbench_backend.inference.adapter import (
    RecordingTransport,
    adapter_target,
    chat_model_for_deployment,
)
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import (
    Deployment,
    DeploymentStatus,
    ManagementScope,
    ServerProperties,
    SettingsBags,
)
from workbench_backend.inference.settings import resolve_bags


class _RecordingHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, Any]] = []
    response_payload: dict[str, Any] | None = None
    stream_chunks: list[dict[str, Any]] = []
    malformed_payload: dict[str, Any] | None = None

    def do_GET(self) -> None:  # noqa: N802
        self._json(200, {"data": [{"id": "fake-llama"}]})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        body = json.loads(raw.decode("utf-8")) if raw else {}
        self.requests.append({"path": self.path, "body": body})
        if self.malformed_payload is not None:
            self._json(200, self.malformed_payload)
            return
        if body.get("stream"):
            self._stream()
            return
        self._json(
            200,
            self.response_payload
            or {
                "id": "adapter-test",
                "object": "chat.completion",
                "model": "fake-llama",
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "pong",
                            "reasoning_content": "because-local",
                        },
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

    def _stream(self) -> None:
        chunks = self.stream_chunks or [
            {
                "id": "adapter-stream",
                "object": "chat.completion.chunk",
                "model": "fake-llama",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "po", "reasoning_content": "why-"},
                    }
                ],
            },
            {
                "id": "adapter-stream",
                "object": "chat.completion.chunk",
                "model": "fake-llama",
                "choices": [
                    {"index": 0, "delta": {"content": "ng", "reasoning_content": "stream"}}
                ],
            },
            {
                "id": "adapter-stream",
                "object": "chat.completion.chunk",
                "model": "fake-llama",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class _FlakyHandler(_RecordingHandler):
    statuses: list[int] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        body = json.loads(raw.decode("utf-8")) if raw else {}
        self.requests.append({"path": self.path, "body": body})
        status = self.statuses.pop(0) if self.statuses else 200
        if status >= 500:
            self._json(status, {"error": {"message": "synthetic server failure"}})
            return
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


class _RaisingTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("synthetic connect failure", request=request)


class _TimeoutTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic read timeout", request=request)


class _InterruptedStream(httpx.SyncByteStream):
    def __iter__(self):
        yield b'data: {"id":"partial","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant","content":"partial"}}]}\n\n'
        raise httpx.ReadError("synthetic interrupted stream")


class _InterruptedStreamTransport(httpx.BaseTransport):
    requests: int = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=_InterruptedStream(),
            request=request,
        )


class _CloseAwareStream(httpx.SyncByteStream):
    def __init__(self) -> None:
        self.closed = False

    def __iter__(self):
        index = 0
        while True:
            payload = {
                "id": "cancel",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": str(index)}}],
            }
            index += 1
            yield f"data: {json.dumps(payload)}\n\n".encode("utf-8")

    def close(self) -> None:
        self.closed = True


class _CloseAwareTransport(httpx.BaseTransport):
    def __init__(self, stream: _CloseAwareStream) -> None:
        self.stream = stream

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=self.stream,
            request=request,
        )


class _AsyncCancelledStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'data: {"id":"apartial","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant","content":"partial"}}]}\n\n'
        raise asyncio.CancelledError()


class _AsyncCancelledTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=_AsyncCancelledStream(),
            request=request,
        )


class _TrackingAsyncClient(httpx.AsyncClient):
    instances: list["_TrackingAsyncClient"] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.close_started = False
        self.close_finished = False
        self.__class__.instances.append(self)

    async def aclose(self) -> None:
        self.close_started = True
        await super().aclose()
        self.close_finished = True


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingHandler.requests = []
        _RecordingHandler.response_payload = None
        _RecordingHandler.stream_chunks = []
        _RecordingHandler.malformed_payload = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.endpoint = f"http://{host}:{port}/v1"
        self.start_calls = 0

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _deployment(
        self,
        *,
        endpoint: str | None | bool = True,
        server_props: ServerProperties | None = None,
        applied_startup: dict[str, Any] | None = None,
    ) -> Deployment:
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
            server_props=server_props,
            applied_startup=applied_startup or {},
        )

    def test_adapter_posts_only_to_deployment_endpoint(self) -> None:
        sink: list[dict[str, Any]] = []
        model = chat_model_for_deployment(self._deployment(), capture_sink=sink)
        try:
            result = model.invoke([HumanMessage(content="ping")])
            self.assertEqual(result.content, "pong")
            self.assertEqual(result.response_metadata["model_name"], "fake-llama")
            self.assertEqual(result.usage_metadata["total_tokens"], 5)
            self.assertEqual(result.additional_kwargs["reasoning_content"], "because-local")
            self.assertEqual(self.start_calls, 0)
            self.assertTrue(_RecordingHandler.requests)
            posted = _RecordingHandler.requests[0]
            self.assertTrue(posted["path"].endswith("/chat/completions"))
            self.assertEqual(posted["body"]["messages"][0]["content"], "ping")
            self.assertTrue(sink)
            self.assertIn("/chat/completions", sink[0]["url"])
            self.assertEqual(sink[0]["body"]["messages"][0]["content_preview"], "ping")
            self.assertTrue(sink[0]["response_received"])
            self.assertEqual(sink[0]["response_status_code"], 200)
            self.assertTrue(sink[0]["observations"]["converted_messages"])
            self.assertEqual(model.profile, {})
        finally:
            model.close()

    def test_adapter_posts_selected_request_settings_and_stream_usage(self) -> None:
        bags = resolve_bags(
            per_request={
                "temperature": 0.2,
                "top_p": 0.8,
                "top_k": 40,
                "min_p": 0.1,
                "typical_p": 0.9,
                "repeat_penalty": 1.1,
                "presence_penalty": 0.3,
                "frequency_penalty": 0.4,
                "max_tokens": 17,
                "stop": ["END"],
                "seed": 42,
                "reasoning": "auto",
                "reasoning_format": "deepseek",
                "reasoning_effort": "low",
            }
        )
        model = chat_model_for_deployment(self._deployment(), per_request=bags.per_request)
        try:
            chunks = list(model.stream([HumanMessage(content="ping")]))
            self.assertEqual("".join(chunk.content for chunk in chunks), "pong")
        finally:
            model.close()

        body = _RecordingHandler.requests[0]["body"]
        self.assertTrue(body["stream"])
        self.assertEqual(body["stream_options"], {"include_usage": True})
        self.assertEqual(body["temperature"], 0.2)
        self.assertEqual(body["top_p"], 0.8)
        self.assertEqual(body["max_tokens"], 17)
        self.assertNotIn("max_completion_tokens", body)
        self.assertEqual(body["presence_penalty"], 0.3)
        self.assertEqual(body["frequency_penalty"], 0.4)
        self.assertEqual(body["stop"], ["END"])
        self.assertEqual(body["seed"], 42)
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual(body["top_k"], 40)
        self.assertEqual(body["min_p"], 0.1)
        self.assertEqual(body["typical_p"], 0.9)
        self.assertEqual(body["repeat_penalty"], 1.1)
        self.assertEqual(body["reasoning"], "auto")
        self.assertEqual(body["reasoning_format"], "deepseek")

    def test_adapter_uses_observed_model_alias_without_cloud_default(self) -> None:
        props = ServerProperties(
            fetched=utc_now(),
            source_url=f"{self.endpoint}/props",
            model_alias="observed-qwen",
        )
        model = chat_model_for_deployment(self._deployment(server_props=props))
        try:
            model.invoke([HumanMessage(content="ping")])
        finally:
            model.close()

        self.assertEqual(_RecordingHandler.requests[0]["body"]["model"], "observed-qwen")

    def test_adapter_rejects_ambiguous_endpoint_model_identity(self) -> None:
        class AmbiguousHandler(_RecordingHandler):
            def do_GET(self) -> None:  # noqa: N802
                self._json(
                    200,
                    {"data": [{"id": "first-model"}, {"id": "second-model"}]},
                )

        self.server.shutdown()
        self.server.server_close()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), AmbiguousHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.endpoint = f"http://{host}:{port}/v1"

        with self.assertRaises(HarnessError) as raised:
            chat_model_for_deployment(self._deployment())
        self.assertEqual(raised.exception.code, "ambiguous_model_identity")

    def test_construction_failure_in_running_loop_closes_owned_async_client(self) -> None:
        class EmptyModelsHandler(_RecordingHandler):
            def do_GET(self) -> None:  # noqa: N802
                self._json(200, {"data": []})

        self.server.shutdown()
        self.server.server_close()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), EmptyModelsHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.endpoint = f"http://{host}:{port}/v1"

        async def exercise() -> None:
            _TrackingAsyncClient.instances = []
            with patch("workbench_backend.inference.adapter.httpx.AsyncClient", _TrackingAsyncClient):
                with self.assertRaises(HarnessError) as raised:
                    chat_model_for_deployment(self._deployment(), capture_sink=[])
                self.assertEqual(raised.exception.code, "model_identity_unavailable")
                self.assertEqual(len(_TrackingAsyncClient.instances), 1)
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                self.assertTrue(_TrackingAsyncClient.instances[0].close_started)
                self.assertTrue(_TrackingAsyncClient.instances[0].close_finished)

        asyncio.run(exercise())

    def test_reasoning_replay_uses_template_supported_reasoning_content(self) -> None:
        props = ServerProperties(
            fetched=utc_now(),
            source_url=f"{self.endpoint}/props",
            model_alias="reasoning-model",
            chat_template_caps={"supports_preserve_reasoning": True},
        )
        model = chat_model_for_deployment(
            self._deployment(
                server_props=props,
                applied_startup={"reasoning_preserve": True},
            )
        )
        try:
            model.invoke(
                [
                    AIMessage(
                        content="previous answer",
                        additional_kwargs={"reasoning_content": "private chain"},
                    ),
                    HumanMessage(content="continue"),
                ]
            )
        finally:
            model.close()

        body = _RecordingHandler.requests[0]["body"]
        self.assertEqual(body["messages"][0]["reasoning_content"], "private chain")

    def test_reasoning_replay_is_omitted_without_template_support(self) -> None:
        model = chat_model_for_deployment(self._deployment())
        try:
            model.invoke(
                [
                    AIMessage(
                        content="previous answer",
                        additional_kwargs={"reasoning_content": "private chain"},
                    ),
                    HumanMessage(content="continue"),
                ]
            )
        finally:
            model.close()

        body = _RecordingHandler.requests[0]["body"]
        self.assertNotIn("reasoning_content", body["messages"][0])

    def test_context_guard_sees_final_payload_and_can_block_dispatch(self) -> None:
        props = ServerProperties(
            fetched=utc_now(),
            source_url=f"{self.endpoint}/props",
            model_alias="context-model",
            n_ctx=1000,
        )
        bags = resolve_bags(per_request={"max_tokens": 100})
        model = chat_model_for_deployment(
            self._deployment(server_props=props),
            per_request=bags.per_request,
        )
        seen: list[dict[str, Any]] = []
        model.set_context_guard(lambda payload: seen.append(payload.copy()))
        try:
            model.invoke([HumanMessage(content="ping")])
        finally:
            model.close()

        self.assertEqual(model.profile["max_input_tokens"], 820)
        self.assertEqual(seen[0]["model"], "context-model")
        self.assertEqual(seen[0]["messages"][0]["content"], "ping")

        blocked = chat_model_for_deployment(self._deployment(server_props=props))
        blocked.set_context_guard(
            lambda payload: (_ for _ in ()).throw(
                HarnessError("blocked by test guard", code="context_capacity_exceeded")
            )
        )
        _RecordingHandler.requests = []
        try:
            with self.assertRaises(HarnessError) as raised:
                blocked.invoke([HumanMessage(content="ping")])
            self.assertEqual(raised.exception.code, "context_capacity_exceeded")
            self.assertEqual(_RecordingHandler.requests, [])
        finally:
            blocked.close()

    def test_capture_redacts_embedded_media_before_preview(self) -> None:
        sink: list[dict[str, Any]] = []
        model = chat_model_for_deployment(self._deployment(), capture_sink=sink)
        media_url = "data:image/png;base64," + ("A" * 400)
        try:
            model.invoke(
                [
                    HumanMessage(
                        content=[
                            {"type": "text", "text": "describe"},
                            {"type": "image_url", "image_url": {"url": media_url}},
                        ]
                    )
                ]
            )
        finally:
            model.close()

        preview = sink[0]["body"]["messages"][0]["content_preview"]
        self.assertIn("embedded-media-redacted", preview)
        self.assertNotIn("data:image", preview)
        self.assertNotIn("AAAA", preview)

    def test_capture_redacts_reasoning_and_tool_argument_previews(self) -> None:
        secret = "sk-test-secret-value"
        media_url = "data:image/png;base64," + ("B" * 400)
        props = ServerProperties(
            fetched=utc_now(),
            source_url=f"{self.endpoint}/props",
            model_alias="sensitive-model",
            chat_template_caps={"supports_preserve_reasoning": True},
        )
        sink: list[dict[str, Any]] = []
        model = chat_model_for_deployment(
            self._deployment(
                server_props=props,
                applied_startup={"reasoning_preserve": True},
            ),
            capture_sink=sink,
        )
        try:
            model.invoke(
                [
                    AIMessage(
                        content="",
                        additional_kwargs={"reasoning_content": f"internal token {secret}"},
                        tool_calls=[
                            {
                                "id": "call_sensitive",
                                "name": "lookup",
                                "args": {
                                    "api_key": secret,
                                    "token": secret,
                                    "image": media_url,
                                },
                            }
                        ],
                    ),
                    ToolMessage(content="ok", tool_call_id="call_sensitive"),
                    HumanMessage(content="continue"),
                ]
            )
        finally:
            model.close()

        message = sink[0]["body"]["messages"][0]
        reasoning_preview = message["reasoning_content_preview"]
        args_preview = message["tool_calls"][0]["function"]["arguments_preview"]
        serialized = json.dumps(message)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("data:image", serialized)
        self.assertIn("REDACTED", reasoning_preview)
        self.assertIn("<redacted>", args_preview)
        self.assertIn("embedded-media-redacted", args_preview)

    def test_stream_capture_is_bounded_but_keeps_latest_summary(self) -> None:
        _RecordingHandler.stream_chunks = [
            {
                "id": "many",
                "object": "chat.completion.chunk",
                "model": "fake-llama",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant" if index == 0 else None, "content": "x"},
                    }
                ],
            }
            for index in range(70)
        ]
        _RecordingHandler.stream_chunks.append(
            {
                "id": "many",
                "object": "chat.completion.chunk",
                "model": "fake-llama",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 70, "total_tokens": 71},
            }
        )
        sink: list[dict[str, Any]] = []
        model = chat_model_for_deployment(self._deployment(), capture_sink=sink)
        try:
            text = "".join(chunk.content for chunk in model.stream([HumanMessage(content="ping")]))
        finally:
            model.close()

        self.assertEqual(text, "x" * 70)
        observations = sink[0]["observations"]
        self.assertEqual(len(observations["converted_chunks"]), 64)
        self.assertGreater(observations["converted_chunks_dropped_count"], 0)
        self.assertEqual(observations["chunks_seen"], 71)
        self.assertEqual(observations["latest_finish_reason"], "stop")

    def test_interrupted_partial_stream_records_error_without_retry(self) -> None:
        props = ServerProperties(
            fetched=utc_now(),
            source_url=f"{self.endpoint}/props",
            model_alias="stream-model",
        )
        sink: list[dict[str, Any]] = []
        transport = _InterruptedStreamTransport()
        client = httpx.Client(transport=RecordingTransport(sink, inner=transport))
        model = chat_model_for_deployment(
            self._deployment(server_props=props),
            capture_sink=sink,
            http_client=client,
        )
        try:
            with self.assertRaises(Exception) as raised:
                list(model.stream([HumanMessage(content="ping")]))
            self.assertIn("connection", str(raised.exception).lower())
        finally:
            model.close()
            client.close()

        self.assertEqual(transport.requests, 1)
        self.assertTrue(sink[0]["observations"]["converted_chunks"])
        self.assertEqual(sink[0]["observations"]["stream_error"]["converted_chunks"], 1)

    def test_async_cancelled_stream_records_partial_diagnostics(self) -> None:
        props = ServerProperties(
            fetched=utc_now(),
            source_url=f"{self.endpoint}/props",
            model_alias="async-cancel-model",
        )
        sink: list[dict[str, Any]] = []

        async def exercise() -> None:
            client = httpx.AsyncClient(transport=AsyncRecordingTransport(sink, inner=_AsyncCancelledTransport()))
            model = chat_model_for_deployment(
                self._deployment(server_props=props),
                capture_sink=sink,
                http_async_client=client,
            )
            try:
                with self.assertRaises(asyncio.CancelledError):
                    async for _chunk in model.astream([HumanMessage(content="ping")]):
                        pass
            finally:
                await model.aclose()
                await client.aclose()

        from workbench_backend.inference.adapter import AsyncRecordingTransport

        asyncio.run(exercise())
        self.assertEqual(sink[0]["observations"]["stream_error"]["error_type"], "CancelledError")
        self.assertEqual(sink[0]["observations"]["stream_error"]["converted_chunks"], 1)

    def test_incomplete_streamed_tool_call_fails_after_final_assembly(self) -> None:
        _RecordingHandler.stream_chunks = [
            {
                "id": "bad-tool",
                "object": "chat.completion.chunk",
                "model": "fake-llama",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_incomplete",
                                    "type": "function",
                                    "function": {"name": "alpha", "arguments": "{\"x\""},
                                }
                            ],
                        },
                    }
                ],
            },
            {
                "id": "bad-tool",
                "object": "chat.completion.chunk",
                "model": "fake-llama",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
            },
        ]
        sink: list[dict[str, Any]] = []
        model = chat_model_for_deployment(self._deployment(), capture_sink=sink)
        try:
            with self.assertRaises(HarnessError) as raised:
                list(model.stream([HumanMessage(content="tools")]))
            self.assertEqual(raised.exception.code, "adapter_incomplete_tool_call")
        finally:
            model.close()
        self.assertEqual(sink[0]["observations"]["stream_error"]["error_type"], "HarnessError")

    def test_cancelled_stream_closes_response_and_owned_clients(self) -> None:
        props = ServerProperties(
            fetched=utc_now(),
            source_url=f"{self.endpoint}/props",
            model_alias="cancel-model",
        )
        stream = _CloseAwareStream()
        client = httpx.Client(transport=_CloseAwareTransport(stream))
        model = chat_model_for_deployment(self._deployment(server_props=props), http_client=client)
        chunks = model.stream([HumanMessage(content="ping")])
        next(chunks)
        chunks.close()
        model.close()
        client.close()
        self.assertTrue(stream.closed)

    def test_close_does_not_close_caller_owned_sync_client(self) -> None:
        props = ServerProperties(
            fetched=utc_now(),
            source_url=f"{self.endpoint}/props",
            model_alias="owned-model",
        )
        client = httpx.Client()
        model = chat_model_for_deployment(self._deployment(server_props=props), http_client=client)
        model.close()
        self.assertFalse(client.is_closed)
        client.close()

    def test_tool_call_and_tool_result_identities_round_trip(self) -> None:
        _RecordingHandler.response_payload = {
            "id": "adapter-tools",
            "object": "chat.completion",
            "model": "fake-llama",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_one",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "{\"q\":\"one\"}"},
                            },
                            {
                                "id": "call_bad",
                                "type": "function",
                                "function": {"name": "broken", "arguments": "{\"q\":"},
                            },
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }
        model = chat_model_for_deployment(self._deployment())
        try:
            result = model.invoke([HumanMessage(content="use a tool")])
            self.assertEqual(result.content, "")
            self.assertEqual(result.tool_calls[0]["id"], "call_one")
            self.assertEqual(result.tool_calls[0]["name"], "lookup")
            self.assertEqual(result.tool_calls[0]["args"], {"q": "one"})
            self.assertEqual(result.invalid_tool_calls[0]["id"], "call_bad")

            model.invoke(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {"id": "call_one", "name": "lookup", "args": {"q": "one"}}
                        ],
                    ),
                    ToolMessage(content="found", tool_call_id="call_one"),
                ]
            )
        finally:
            model.close()

        sent_messages = _RecordingHandler.requests[-1]["body"]["messages"]
        self.assertEqual(sent_messages[0]["tool_calls"][0]["id"], "call_one")
        self.assertEqual(sent_messages[1]["role"], "tool")
        self.assertEqual(sent_messages[1]["tool_call_id"], "call_one")

    def test_stream_preserves_fragmented_tool_calls_and_reasoning(self) -> None:
        _RecordingHandler.stream_chunks = [
            {
                "id": "adapter-stream",
                "object": "chat.completion.chunk",
                "model": "fake-llama",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "reasoning_content": "r1",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_a",
                                    "type": "function",
                                    "function": {"name": "alpha", "arguments": "{\"x\""},
                                },
                                {
                                    "index": 1,
                                    "id": "call_b",
                                    "type": "function",
                                    "function": {"name": "beta", "arguments": "{\"y\""},
                                },
                            ],
                        },
                    }
                ],
            },
            {
                "id": "adapter-stream",
                "object": "chat.completion.chunk",
                "model": "fake-llama",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "reasoning_content": "r2",
                            "tool_calls": [
                                {"index": 1, "function": {"arguments": ":2}"}},
                                {"index": 0, "function": {"arguments": ":1}"}},
                            ],
                        },
                    }
                ],
            },
            {
                "id": "adapter-stream",
                "object": "chat.completion.chunk",
                "model": "fake-llama",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
            },
        ]
        model = chat_model_for_deployment(self._deployment())
        try:
            chunks = list(model.stream([HumanMessage(content="tools")]))
            combined = chunks[0]
            for chunk in chunks[1:]:
                combined += chunk
        finally:
            model.close()

        self.assertEqual(combined.tool_calls[0]["id"], "call_a")
        self.assertEqual(combined.tool_calls[0]["args"], {"x": 1})
        self.assertEqual(combined.tool_calls[1]["id"], "call_b")
        self.assertEqual(combined.tool_calls[1]["args"], {"y": 2})
        self.assertIn("reasoning_content", chunks[0].additional_kwargs)

    def test_async_invoke_and_stream_match_sync_path(self) -> None:
        async def exercise() -> tuple[str, str]:
            model = chat_model_for_deployment(self._deployment())
            try:
                normal = await model.ainvoke([HumanMessage(content="ping")])
                chunks = [chunk async for chunk in model.astream([HumanMessage(content="ping")])]
                return normal.content, "".join(chunk.content for chunk in chunks)
            finally:
                await model.aclose()

        normal, streamed = __import__("asyncio").run(exercise())
        self.assertEqual(normal, "pong")
        self.assertEqual(streamed, "pong")

    def test_malformed_response_and_timeout_remain_failures(self) -> None:
        _RecordingHandler.malformed_payload = {"object": "chat.completion"}
        model = chat_model_for_deployment(self._deployment())
        try:
            with self.assertRaises((KeyError, TypeError)):
                model.invoke([HumanMessage(content="ping")])
        finally:
            model.close()

        sink: list[dict[str, Any]] = []
        client = httpx.Client(transport=RecordingTransport(sink, inner=_TimeoutTransport()))
        props = ServerProperties(
            fetched=utc_now(),
            source_url=f"{self.endpoint}/props",
            model_alias="timeout-model",
        )
        model = chat_model_for_deployment(self._deployment(server_props=props), http_client=client)
        try:
            with self.assertRaises(Exception) as raised:
                model.invoke([HumanMessage(content="ping")])
            self.assertIn("timed out", str(raised.exception).lower())
        finally:
            model.close()
            client.close()
        self.assertEqual(sink[-1]["transport_error"]["type"], "ReadTimeout")

    def test_http_500_is_recorded_without_automatic_retry(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        _FlakyHandler.requests = []
        _FlakyHandler.statuses = [500, 200]
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FlakyHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.endpoint = f"http://{host}:{port}/v1"
        sink: list[dict[str, Any]] = []

        model = chat_model_for_deployment(self._deployment(), capture_sink=sink)
        try:
            with self.assertRaises(Exception) as raised:
                model.invoke([HumanMessage(content="ping")])
            self.assertIn("synthetic server failure", str(raised.exception))
        finally:
            model.close()

        self.assertEqual(len(_FlakyHandler.requests), 1)
        self.assertEqual(len([item for item in sink if "response_status_code" in item]), 1)
        self.assertTrue(sink[0]["response_received"])
        self.assertEqual(sink[0]["response_status_code"], 500)

    def test_recording_transport_records_transport_exception(self) -> None:
        sink: list[dict[str, Any]] = []
        client = httpx.Client(transport=RecordingTransport(sink, inner=_RaisingTransport()))

        with self.assertRaises(httpx.ConnectError):
            client.post(f"{self.endpoint}/chat/completions", json={"messages": []})

        self.assertEqual(len(sink), 1)
        self.assertFalse(sink[0]["response_received"])
        self.assertEqual(sink[0]["transport_error"]["type"], "ConnectError")
        client.close()

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
