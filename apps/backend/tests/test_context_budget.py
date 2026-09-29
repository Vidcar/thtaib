"""Context preflight, retained checkpoint, and upstream compaction regressions."""

from __future__ import annotations

import asyncio
import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from deepagents.middleware.summarization import SummarizationMiddleware, compute_summarization_defaults, create_summarization_middleware

from workbench_backend.agents.context import (
    ContextObservation,
    SummaryDispatchModel,
    count_context_tokens,
    observe_context,
    observe_payload,
    validate_retained_messages,
)
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.errors import HarnessError
from workbench_backend.inference.adapter import chat_model_for_deployment
from workbench_backend.inference.capabilities import setup_fingerprint
from workbench_backend.inference.request_projection import project_context_payload
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.telemetry import current_request_purpose
from workbench_backend.inference.schemas import ServerProperties
from workbench_backend.inference.schemas import SettingsBag
from workbench_backend.state.checkpointer import conversation_state, run_checkpoint_task

from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run
from workbench_backend.agents.tools import tools_for_names
from tests.scripted_model import ScriptedChatModel


def _fake_png_data_url() -> str:
    # The boundary validates the declared type and signature; no network or file is needed.
    return "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfixture-image").decode("ascii")


class ContextBudgetHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.client = offline_workbench_client(self.app)
        deployment = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "context-fixture"},
        ).json()
        self.deployment_id = deployment["id"]
        self._set_context(n_ctx=8192, vision=True)
        self.chat_payloads: list[dict] = []
        self.chat_responses: list[str] = []
        self.http_requests: list[dict] = []
        self.mock_async_clients: list[httpx.AsyncClient] = []
        self.harness = HarnessService(
            lambda: self.manager,
            model_factory=self._mock_transport_model,
            knowledge_provider=lambda: self.app.state.knowledge,
        )
        self.app.state.harness = self.harness

    def tearDown(self) -> None:
        self.harness.close(timeout=1.0)
        for client in self.mock_async_clients:
            run_checkpoint_task(self.manager.paths.checkpoints_db, client.aclose())
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def _set_context(self, *, n_ctx: int | None, vision: bool) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        props = ServerProperties(
            fetched=utc_now(),
            source_url="http://127.0.0.1:9/props",
            build_info="fixture-build",
            model_alias="fixture-model",
            model_path="fixture.gguf",
            n_ctx=n_ctx,
            modalities={"vision": vision},
            chat_template_caps={
                "supports_system_role": True,
                "supports_tools": True,
                "supports_tool_calls": True,
            },
        )
        self.manager.store.put_deployment(deployment.model_copy(update={"server_props": props}))

    def _mock_openai(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            self.http_requests.append({"path": request.url.path})
            return httpx.Response(200, json={"data": [{"id": "fixture-model"}]}, request=request)
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404, request=request)
        payload = json.loads(request.content.decode("utf-8"))
        self.chat_payloads.append(payload)
        if payload.get("stream"):
            reply = "fixture summary" if current_request_purpose() == "summary" else "fixture reply"
            self.chat_responses.append(reply)
            events = [
                {
                    "id": "context-budget-stream",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "fixture-model",
                    "choices": [{"index": 0, "delta": {"role": "assistant", "content": reply}, "finish_reason": None}],
                },
                {
                    "id": "context-budget-stream",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "fixture-model",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
            ]
            body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=body.encode("utf-8"),
                request=request,
            )
        self.chat_responses.append("fixture summary")
        return httpx.Response(
            200,
            json={
                "id": "context-budget-completion",
                "object": "chat.completion",
                "created": 1,
                "model": "fixture-model",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "fixture summary"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
            request=request,
        )

    def _mock_transport_model(self, run: AgentRun, sink: list[dict]):
        deployment = self.manager.ensure_deployment_ready(run.deployment_id)
        client = httpx.Client(transport=httpx.MockTransport(self._mock_openai), timeout=15.0)
        async_client = httpx.AsyncClient(transport=httpx.MockTransport(self._mock_openai), timeout=15.0)
        self.mock_async_clients.append(async_client)
        with self.harness._lock:
            self.harness._model_clients[run.id] = client
        per_request = run.effective_setup.bags.per_request if run.effective_setup else None
        return chat_model_for_deployment(
            deployment,
            per_request=per_request,
            capture_sink=sink,
            timeout=15.0,
            http_client=client,
            http_async_client=async_client,
        )

    def _start(self, *, thread_id: str, task: str, **extra: object):
        response = self.client.post(
            "/v1/agent-runs",
            json={"deployment_id": self.deployment_id, "thread_id": thread_id, "task": task, **extra},
        )
        return response

    def _complete(self, started: dict) -> dict:
        return wait_for_run(self.client, started["id"], timeout=20.0)

    def test_tools_off_mock_transport_keeps_structured_user_image_and_switch_is_rejected(self) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        self.manager.store.put_capability_evidence({
            "schema_version": 1, "id": "probe_fixture_user_image",
            "deployment_id": deployment.id, "capability": "image", "status": "passed",
            "fingerprint": setup_fingerprint(deployment), "setup": {},
            "tested_at": utc_now(), "inputs": {}, "observations": {},
        })
        image_url = _fake_png_data_url()
        started = self._start(
            thread_id="thread-image-context",
            task="Describe the image.",
            presented_tools=[],
            content_blocks=[{"type": "image_url", "image_url": {"url": image_url}}],
        )
        self.assertEqual(started.status_code, 200, started.text)
        completed = self._complete(started.json())
        self.assertEqual(completed["status"], "completed", completed.get("error"))
        self.assertEqual(completed["presented_tools"], [])
        self.assertEqual(len(self.chat_payloads), 1)
        self.assertFalse(self.chat_payloads[0].get("tools"))
        user_messages = [item for item in self.chat_payloads[0]["messages"] if item.get("role") == "user"]
        self.assertTrue(user_messages)
        image_blocks = [block for block in user_messages[-1]["content"] if block.get("type") == "image_url"]
        self.assertEqual(len(image_blocks), 1)
        self.assertEqual(image_blocks[0]["image_url"]["url"], image_url)

        checkpoint_before = conversation_state(self.manager.paths.checkpoints_db, "thread-image-context")
        self.assertTrue(any(
            isinstance(message.content, list)
            and any(isinstance(block, dict) and block.get("type") == "image_url" for block in message.content)
            for message in checkpoint_before.get("messages", [])
        ), f"checkpoint values={list(checkpoint_before)} run thread={completed.get('thread_id')} checkpoints={completed.get('checkpoint_ids')}")
        self._set_context(n_ctx=8192, vision=False)

        rejected = self._start(thread_id="thread-image-context", task="What did the picture show?", presented_tools=[])
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["code"], "context_image_unsupported")
        self.assertEqual(len(self.chat_payloads), 1, "incompatible retained image must be rejected before model dispatch")
        checkpoint_after = conversation_state(self.manager.paths.checkpoints_db, "thread-image-context")
        self.assertEqual(checkpoint_after.get("messages"), checkpoint_before.get("messages"))

    def test_irreducible_smaller_context_fails_before_dispatch_and_retains_history(self) -> None:
        thread_id = "thread-smaller-context"
        self._set_context(n_ctx=32768, vision=True)
        started = self._start(thread_id=thread_id, task="long-context " + ("older material " * 900), presented_tools=[])
        self.assertEqual(started.status_code, 200, started.text)
        completed = self._complete(started.json())
        self.assertEqual(completed["status"], "completed", completed.get("error"))
        self.assertEqual(completed["presented_tools"], [])
        self.assertEqual(len(self.chat_payloads), 1)
        checkpoint_before = conversation_state(self.manager.paths.checkpoints_db, thread_id)
        messages_before = checkpoint_before.get("messages", [])
        self.assertGreaterEqual(
            len(messages_before),
            2,
            f"checkpoint values={list(checkpoint_before)} run thread={completed.get('thread_id')} checkpoints={completed.get('checkpoint_ids')}",
        )
        self._set_context(n_ctx=512, vision=True)
        original = self._mock_openai
        def reject_native_overflow(request):
            if request.url.path.endswith("/chat/completions") and current_request_purpose() == "work":
                return httpx.Response(400, json={"error": {"message": "the prompt exceeds the context size", "type": "invalid_request_error", "code": "context_length_exceeded"}}, request=request)
            return original(request)
        self._mock_openai = reject_native_overflow

        accepted = self._start(thread_id=thread_id, task="Continue briefly.", presented_tools=[])
        self.assertEqual(accepted.status_code, 200, accepted.text)
        failed = self._complete(accepted.json())
        self.assertEqual(failed["status"], "failed")
        self.assertFalse(failed["context_observation"]["fits"])
        self.assertEqual(failed["context_observation"]["purpose"], "work")
        self.assertEqual(failed["failure"]["recovery_action"], "change_limit")
        self.assertTrue(all("fixture summary" == reply for reply in self.chat_responses[1:]),
            "the SDK may summarize but must not complete rejected irreducible work")
        checkpoint_after = conversation_state(self.manager.paths.checkpoints_db, thread_id)
        self.assertEqual(checkpoint_after.get("messages", [])[:len(messages_before)], messages_before,
                         "native failure must preserve retained messages even when the new turn is checkpointed")

    def test_smaller_context_continues_retained_history_through_native_compaction(self) -> None:
        thread_id = "thread-reducible-smaller-context"
        self._set_context(n_ctx=32768, vision=True)
        first = self._start(thread_id=thread_id, task="Preserve the important details. " + "older detail " * 1800,
            presented_tools=[])
        self.assertEqual(first.status_code, 200, first.text)
        completed = self._complete(first.json())
        self.assertEqual(completed["status"], "completed", completed.get("error"))
        before = conversation_state(self.manager.paths.checkpoints_db, thread_id)
        retained_ids = [message.id for message in before["messages"]]
        self._set_context(n_ctx=8192, vision=True)
        second = self._start(thread_id=thread_id, task="Continue and retain the important facts. " + "recent detail " * 450,
            presented_tools=[])
        self.assertEqual(second.status_code, 200, second.text)
        reduced = self._complete(second.json())
        self.assertEqual(reduced["status"], "completed", reduced.get("error"))
        self.assertEqual(reduced["context_observation"]["capacity_tokens"], 8192)
        self.assertIsNone(reduced["context_observation"]["fits"])
        self.assertTrue(any(event["kind"] == "context_compacted" for event in reduced["events"]))
        after = conversation_state(self.manager.paths.checkpoints_db, thread_id)
        self.assertEqual([message.id for message in after["messages"]][:len(retained_ids)], retained_ids,
            "Native summaries must retain canonical checkpoint history")
        outbound = json.dumps(self.chat_payloads[-1])
        self.assertIn("<summary>", outbound)
        self.assertNotIn("older detail", outbound, "Only native active-prompt reduction excludes covered history")

    def test_retained_tool_result_pair_is_preserved_and_incomplete_pairs_are_rejected(self) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        pair = [
            HumanMessage(content="Use the echo tool."),
            AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "x"}, "id": "call-x"}]),
            ToolMessage(content="x", tool_call_id="call-x"),
        ]
        original = [message.model_copy(deep=True) for message in pair]
        validate_retained_messages(deployment, pair)
        self.assertEqual(pair, original)

        with self.assertRaises(HarnessError) as caught:
            validate_retained_messages(deployment, pair[:-1])
        self.assertEqual(caught.exception.code, "context_tool_pair_invalid")
        self.assertEqual(pair[:-1], original[:-1], "rejected history must remain intact")

    def test_actual_tool_schema_is_counted_and_sdk_reserves_explicit_output_once(self) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        tools = tools_for_names(["echo"])
        capacity, output = 4096, 300
        observation = observe_context(
            deployment=deployment.model_copy(update={"server_props": deployment.server_props.model_copy(update={"n_ctx": capacity})}),
            per_request=SettingsBag(applied={"max_tokens": output}), system_prompt="Answer the request.",
            task="Say hello.", content_blocks=None, tool_count=len(tools), output_schema=None,
            continuing_thread=False, tools=tools)
        messages = [SystemMessage(content="Answer the request."), HumanMessage(content="Say hello.")]
        self.assertGreater(count_context_tokens(messages, tools=tools), count_context_tokens(messages))
        self.assertEqual(observation.capacity_tokens, capacity)
        self.assertEqual(observation.configured_output_tokens, output)
        self.assertEqual(observation.counting_basis, "estimated")
        self.assertIsNone(observation.fits)
        payload = project_context_payload(messages, tools=tools)
        observed = observe_payload(observation, payload, native_counter=lambda actual: 123 if actual == payload else None)
        self.assertEqual(observed.input_tokens, 123)
        self.assertEqual(observed.counting_basis, "native")
        self.assertTrue(observed.fits)
        self.assertNotIn("usable_input_tokens", observed.model_dump())
        model = ScriptedChatModel([], profile={"max_input_tokens": capacity})
        native = create_summarization_middleware(model, backend=lambda _: None, token_counter=count_context_tokens)
        request = ModelRequest(model=model, messages=messages[1:], system_message=messages[0], tools=tools,
            model_settings={"max_completion_tokens": output})
        self.assertEqual(native._input_budget(request), int(capacity * .95) - output)


    def test_approximate_observation_cannot_reject_or_trim_a_model_request(self) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        client = httpx.Client(transport=httpx.MockTransport(self._mock_openai), timeout=5.0)
        self.addCleanup(client.close)
        model = chat_model_for_deployment(deployment, http_client=client, capture_sink=[])
        baseline = ContextObservation(capacity_tokens=256, capacity_source="server_props.n_ctx",
            configured_output_tokens=-1)
        observations = []
        model.set_context_guard(lambda payload: observations.append(observe_payload(baseline, payload)))
        history = [SystemMessage(content="Summarize all retained facts."),
            HumanMessage(content="unchanged retained context " * 60)]
        before = [message.model_copy(deep=True) for message in history]
        model.invoke(history)
        self.assertEqual(history, before)
        self.assertEqual(len(self.chat_payloads), 1)
        self.assertGreater(observations[0].input_tokens, 256)
        self.assertIsNone(observations[0].fits)
        self.assertEqual(observations[0].counting_basis, "estimated")


    def test_tools_off_compaction_uses_one_stock_sdk_middleware_and_records_event(self) -> None:
        self._set_context(n_ctx=16384, vision=True)
        thread_id = "thread-compaction-tools-off"
        budgets = []
        original = SummarizationMiddleware._input_budget
        def observe_budget(middleware, request):
            value = original(middleware, request)
            budgets.append(value)
            return value
        with patch("workbench_backend.agents.harness.create_summarization_middleware",
            wraps=create_summarization_middleware) as factory, patch.object(SummarizationMiddleware,
            "_input_budget", observe_budget):
            first = self._start(thread_id=thread_id,
                task="Preserve this earlier material. " + "historic detail " * 1100, presented_tools=[])
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(self._complete(first.json())["status"], "completed")
            previous = factory.call_count
            second = self._start(thread_id=thread_id,
                task="Preserve the important later details. " + "recent detail " * 2800, presented_tools=[])
            self.assertEqual(second.status_code, 200, second.text)
            completed = self._complete(second.json())
        self.assertEqual(completed["status"], "completed", completed.get("error"))
        self.assertEqual(factory.call_count, previous + 1)
        configured = factory.call_args.kwargs
        self.assertEqual(configured["model"].profile["max_input_tokens"], 16384)
        self.assertNotIn("trigger", configured)
        self.assertNotIn("keep", configured)
        self.assertEqual(compute_summarization_defaults(configured["model"])["trigger"], ("fraction", .85))
        self.assertGreaterEqual(len(self.chat_payloads), 3)
        self.assertTrue(all(not payload.get("tools") for payload in self.chat_payloads))
        compacted = [event for event in completed["events"] if event["kind"] == "context_compacted"]
        self.assertEqual(len(compacted), 1)
        self.assertGreater(compacted[0]["detail"]["cutoff_index"], 0)
        self.assertEqual(compacted[0]["detail"]["owner"], "deepagents-upstream")
        self.assertTrue(budgets)
        self.assertTrue(all(value == int(16384 * .95) for value in budgets))
        self.assertEqual(completed["context_observation"]["capacity_tokens"], 16384)
        self.assertEqual(completed["housekeeping_context"]["summary"]["purpose"], "summary")

    def test_cancel_joins_stock_summary_request_without_work_or_purpose_leak(self) -> None:
        self._set_context(n_ctx=16384, vision=True)
        thread_id = "thread-cancel-stock-summary"
        first = self._start(thread_id=thread_id,
            task="Preserve this earlier material. " + "historic detail " * 1100, presented_tools=[])
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self._complete(first.json())["status"], "completed")
        retained = conversation_state(self.manager.paths.checkpoints_db, thread_id)["messages"]
        entered, cancelled, settled = threading.Event(), threading.Event(), threading.Event()
        blocked: dict = {}
        purposes, restored, summary_metadata = [], [], []

        async def blocking_transport(request: httpx.Request) -> httpx.Response:
            if not request.url.path.endswith("/chat/completions"):
                return self._mock_openai(request)
            purpose = current_request_purpose()
            purposes.append(purpose)
            if purpose != "summary":
                return self._mock_openai(request)
            release = asyncio.Event()
            blocked.update(loop=asyncio.get_running_loop(), release=release)
            entered.set()
            try:
                await release.wait()
                return self._mock_openai(request)
            except asyncio.CancelledError:
                cancelled.set()
                raise
            finally:
                settled.set()

        def blocking_model(run: AgentRun, sink: list[dict]):
            deployment = self.manager.ensure_deployment_ready(run.deployment_id)
            client = httpx.Client(transport=httpx.MockTransport(self._mock_openai), timeout=15.0)
            async_client = httpx.AsyncClient(transport=httpx.MockTransport(blocking_transport), timeout=15.0)
            self.mock_async_clients.append(async_client)
            with self.harness._lock:
                self.harness._model_clients[run.id] = client
            return chat_model_for_deployment(deployment,
                per_request=run.effective_setup.bags.per_request if run.effective_setup else None,
                capture_sink=sink, timeout=15.0, http_client=client, http_async_client=async_client)

        original = SummaryDispatchModel.ainvoke
        async def observe_summary(model, input, config=None, **kwargs):
            summary_metadata.append(dict((config or {}).get("metadata", {})))
            try:
                return await original(model, input, config=config, **kwargs)
            finally:
                restored.append(current_request_purpose())

        self.harness._model_factory = blocking_model
        started = None
        with patch("workbench_backend.agents.harness.create_summarization_middleware",
            wraps=create_summarization_middleware) as factory, patch.object(
                SummaryDispatchModel, "ainvoke", observe_summary):
            try:
                second = self._start(thread_id=thread_id,
                    task="Preserve the important later details. " + "recent detail " * 2800,
                    presented_tools=[])
                self.assertEqual(second.status_code, 200, second.text)
                started = second.json()
                self.assertTrue(entered.wait(5), "Stock compaction did not dispatch its summary")
                with self.harness._lock:
                    worker = self.harness._threads[started["id"]]
                    control = self.harness._execution_controls[started["id"]]
                self.assertEqual(control._active_models, 1, "Summary must own dispatch authority")
                self.harness.cancel(started["id"])
                final = self._complete(started)
                worker.join(timeout=5)
                self.assertEqual(final["status"], "cancelled", final.get("error"))
                self.assertFalse(worker.is_alive(), "Cancellation must join the owning worker")
                self.assertTrue(cancelled.is_set(), "The summary transport must receive cancellation")
                self.assertTrue(settled.is_set(), "The summary request must settle before terminal publication")
                self.assertEqual(control._active_models, 0, "Cancelled summary must release dispatch authority")
                self.assertEqual(purposes, ["summary"], "Cancellation must not retry or dispatch work")
                self.assertEqual(restored, ["work"], "Summary purpose must unwind in the cancelled graph task")
                self.assertEqual(summary_metadata[0]["lc_source"], "summarization")
                self.assertEqual(factory.call_count, 1)
                self.assertNotIn("trigger", factory.call_args.kwargs)
                self.assertNotIn("keep", factory.call_args.kwargs)
                self.assertEqual(final["tool_invocations"], [])
                self.assertFalse(any(event["kind"] == "context_compacted" for event in final["events"]))
                after = conversation_state(self.manager.paths.checkpoints_db, thread_id)["messages"]
                self.assertEqual(after[:len(retained)], retained, "Interrupted summary must preserve canonical history")
            finally:
                if started is not None:
                    self.harness.cancel(started["id"])
                if blocked:
                    blocked["loop"].call_soon_threadsafe(blocked["release"].set)
                    self.assertTrue(settled.wait(5), "Cleanup must release the blocked fake request")


    def test_long_reasoning_continues_then_compacts_readable_native_history(self) -> None:
        self._set_context(n_ctx=98304, vision=True)
        deployment = self.manager.get_deployment(self.deployment_id)
        props = deployment.server_props.model_copy(deep=True)
        props.chat_template_caps["supports_preserve_reasoning"] = True
        self.manager.store.put_deployment(deployment.model_copy(update={
            "server_props": props, "applied_startup": {"reasoning_preserve": True}}))
        normal_endpoint = self._mock_openai
        reason = "bounded-history-thought " * 6500
        first = True

        def endpoint(request):
            nonlocal first
            payload = json.loads(request.content)
            if payload.get("stream") and first:
                first = False
                self.chat_payloads.append(payload)
                return self._stream_fixture(request, {"role": "assistant", "content": "First reply.", "reasoning_content": reason})
            return normal_endpoint(request)

        self._mock_openai = endpoint
        thread_id = "thread-long-reasoning"
        first_run = self._complete(self._start(thread_id=thread_id, task="original-history-marker", presented_tools=["echo"], per_request_overrides={"max_tokens": 512}).json())
        self.assertEqual(first_run["status"], "completed", first_run.get("error"))
        second_run = self._complete(self._start(thread_id=thread_id, task="Continue briefly.", presented_tools=["echo"], per_request_overrides={"max_tokens": 512}).json())
        self.assertEqual(second_run["status"], "completed", second_run.get("error"))
        self.assertFalse(any(event["kind"] == "context_compacted" for event in second_run["events"]))
        self.assertLess(second_run["context_observation"]["input_tokens"], 50000)
        self.assertEqual(sum(json.dumps(payload).count(reason) for payload in self.chat_payloads), 1)
        third_run = self._complete(self._start(thread_id=thread_id, task="new material " * 15000,
                                              presented_tools=["echo"], per_request_overrides={"max_tokens": 512}).json())
        self.assertEqual(third_run["status"], "completed", third_run.get("error"))
        compacted = [event for event in third_run["events"] if event["kind"] == "context_compacted"]
        self.assertEqual(len(compacted), 1)
        path = compacted[0]["detail"]["history_preserved_at"]
        self.assertTrue(path.startswith("/conversation_history/"))
        from workbench_backend.agents.harness_backend import build_run_backend
        backend = build_run_backend(AgentRun.model_validate(third_run), self.manager.paths, prepare_storage=False)
        saved = backend.download_files([path])[0]
        self.assertIsNone(saved.error)
        self.assertIn("original-history-marker", saved.content.decode())
        self.assertIn(reason, saved.content.decode())
        self.assertIsNone(backend.read(path, offset=0, limit=5).error)
        self.assertEqual(third_run["context_observation"]["purpose"], "work")
        self.assertEqual(third_run["housekeeping_context"]["summary"]["purpose"], "summary")
        self.assertIsNone(third_run["context_observation"]["fits"])

    @staticmethod
    def _stream_fixture(request, delta, finish="stop"):
        events = [
            {"id": "budget-fixture", "object": "chat.completion.chunk", "created": 1,
             "model": "fixture-model", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {"id": "budget-fixture", "object": "chat.completion.chunk", "created": 1,
             "model": "fixture-model", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
        ]
        body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=body.encode(), request=request)

    def test_response_limit_partial_call_never_executes_and_next_turn_continues(self) -> None:
        normal_endpoint = self._mock_openai
        first = True
        project = self.root / "partial-project"
        project.mkdir()

        def endpoint(request):
            nonlocal first
            payload = json.loads(request.content)
            if payload.get("stream") and first:
                first = False
                self.chat_payloads.append(payload)
                return self._stream_fixture(request, {"role": "assistant", "tool_calls": [
                    {"index": 0, "id": "ready-write", "type": "function", "function": {
                        "name": "write_file", "arguments": '{"file_path":"/ready.txt","content":"ready"}'}},
                    {"index": 1, "id": "partial-write", "type": "function", "function": {
                        "name": "write_file", "arguments": '{"file_path":"/never.txt","content":"cut'}}]}, "length")
            return normal_endpoint(request)

        self._mock_openai = endpoint
        first_run = self._complete(self._start(thread_id="thread-partial-output", task="Write a file",
            project_path=str(project), presented_tools=["write_file"], approval_mode="full_access",
            per_request_overrides={"reasoning_budget_tokens": 32, "max_tokens": 128}).json())
        self.assertEqual(first_run["status"], "failed")
        self.assertEqual(first_run["dispatched_tool_calls"], 0)
        self.assertEqual(first_run["failure"]["code"], "response_limit_reached")
        self.assertEqual(first_run["failure"]["recovery_action"], "change_limit")
        outcome = first_run["tool_outcomes"]["partial-write"]
        self.assertEqual(outcome["outcome"], "incomplete_arguments")
        self.assertEqual(outcome["name"], "write_file")
        self.assertEqual(first_run["tool_outcomes"]["ready-write"]["outcome"], "not_dispatched")
        self.assertEqual(first_run["tool_invocations"], [])
        self.assertFalse((project / "never.txt").exists())
        self.assertFalse((project / "ready.txt").exists())
        self.assertEqual(self.chat_payloads[0]["max_tokens"], 128)
        self.assertEqual(self.chat_payloads[0]["reasoning_budget_tokens"], 32)
        resumed = self._start(thread_id="thread-partial-output", task="Continue without writing.",
            project_path=str(project), presented_tools=["write_file"], approval_mode="full_access")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        second_run = self._complete(resumed.json())
        self.assertEqual(second_run["status"], "completed", second_run.get("error"))
        self.assertFalse((project / "never.txt").exists())
        self.assertFalse((project / "ready.txt").exists())

    def test_unknown_capacity_preserves_stock_sdk_fallback(self) -> None:
        self._set_context(n_ctx=None, vision=True)
        with patch("workbench_backend.agents.harness.create_summarization_middleware",
            wraps=create_summarization_middleware) as factory:
            started = self._start(thread_id="thread-unknown-context", task="Reply briefly.", presented_tools=[])
            self.assertEqual(started.status_code, 200, started.text)
            completed = self._complete(started.json())
        self.assertEqual(completed["status"], "completed", completed.get("error"))
        configured = factory.call_args.kwargs
        self.assertNotIn("max_input_tokens", configured["model"].profile)
        defaults = compute_summarization_defaults(configured["model"])
        self.assertEqual(defaults["trigger"], ("tokens", 170000))
        self.assertEqual(defaults["keep"], ("messages", 6))



if __name__ == "__main__":
    unittest.main()
