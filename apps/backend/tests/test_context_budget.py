"""Context preflight, retained checkpoint, and upstream compaction regressions."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from workbench_backend.agents.context import (
    BudgetedSummarizationMiddleware,
    ContextObservation,
    count_context_tokens,
    observe_context,
    observe_payload,
    require_context_fit,
    validate_retained_messages,
)
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.errors import HarnessError
from workbench_backend.inference.adapter import chat_model_for_deployment
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import ServerProperties
from workbench_backend.inference.schemas import SettingsBag
from workbench_backend.state.checkpointer import conversation_state

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
        self.harness = HarnessService(
            lambda: self.manager,
            model_factory=self._mock_transport_model,
            knowledge_provider=lambda: self.app.state.knowledge,
        )
        self.app.state.harness = self.harness

    def tearDown(self) -> None:
        self.harness.close(timeout=1.0)
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def _set_context(self, *, n_ctx: int, vision: bool) -> None:
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
            self.chat_responses.append("fixture reply")
            events = [
                {
                    "id": "context-budget-stream",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "fixture-model",
                    "choices": [{"index": 0, "delta": {"role": "assistant", "content": "fixture reply"}, "finish_reason": None}],
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
        with self.harness._lock:
            self.harness._model_clients[run.id] = client
        per_request = run.effective_setup.bags.per_request if run.effective_setup else None
        return chat_model_for_deployment(
            deployment,
            per_request=per_request,
            capture_sink=sink,
            timeout=15.0,
            http_client=client,
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

    def test_smaller_observed_context_blocks_long_retained_history_without_changing_checkpoint(self) -> None:
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

        rejected = self._start(thread_id=thread_id, task="Continue briefly.", presented_tools=[])
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["code"], "context_capacity_exceeded")
        self.assertEqual(len(self.chat_payloads), 1, "smaller context must block before another model request")
        checkpoint_after = conversation_state(self.manager.paths.checkpoints_db, thread_id)
        self.assertEqual(checkpoint_after.get("messages"), messages_before, "preflight must preserve retained checkpoint state")

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

    def test_actual_tool_schema_is_counted_and_output_reservation_is_subtracted_once(self) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        tools = tools_for_names(["echo"])
        schema = {
            "type": "json_schema",
            "json_schema": {"name": "answer", "strict": True, "schema": {"type": "object", "properties": {"answer": {"type": "string"}}}},
        }
        capacity = 4096
        output_reservation = 300
        per_request = SettingsBag(applied={"max_completion_tokens": output_reservation})
        observation = observe_context(
            deployment=deployment.model_copy(update={"server_props": deployment.server_props.model_copy(update={"n_ctx": capacity})}),
            per_request=per_request,
            system_prompt="Answer the request.",
            task="Say hello.",
            content_blocks=None,
            tool_count=len(tools),
            output_schema=schema,
            continuing_thread=False,
            tools=tools,
        )
        expected = count_context_tokens(
            [
                SystemMessage(content="Answer the request."),
                HumanMessage(content="Say hello."),
            ],
            tools=tools,
        )
        # The same structured schema is included separately from the tool definitions.
        from workbench_backend.agents.context import estimate_payload

        expected_with_schema = estimate_payload({
            "messages": [HumanMessage(content="Say hello.")],
            "system": "Answer the request.",
            "tools": tools,
            "response_format": schema,
        })
        self.assertGreater(expected_with_schema, estimate_payload({
            "messages": [HumanMessage(content="Say hello.")],
            "system": "Answer the request.",
            "tools": [],
            "response_format": schema,
        }))
        self.assertGreater(expected, count_context_tokens(
            [SystemMessage(content="Answer the request."), HumanMessage(content="Say hello.")],
            tools=[],
        ), "the actual enabled-tool schema must contribute to the estimate")
        self.assertEqual(observation.estimated_input_tokens, expected_with_schema)
        self.assertEqual(observation.output_reservation_tokens, output_reservation)
        self.assertEqual(observation.margin_tokens, int(capacity * 0.08))
        self.assertEqual(
            observation.usable_input_tokens,
            capacity - output_reservation - observation.margin_tokens,
        )

        live_payload = {
            "messages": [SystemMessage(content="Answer the request."), HumanMessage(content="Say hello.")],
            "tools": tools,
            "response_format": schema,
            "max_completion_tokens": output_reservation,
        }
        observed = observe_payload(observation, live_payload)
        expected_live = estimate_payload({key: value for key, value in live_payload.items() if key in {"messages", "tools", "response_format"}})
        self.assertEqual(observed.estimated_input_tokens, expected_live)
        self.assertGreater(observed.estimated_input_tokens, expected_with_schema)
        self.assertEqual(observed.fits, observed.estimated_input_tokens <= observation.usable_input_tokens)

        model = ScriptedChatModel([])
        model.profile = {"max_input_tokens": observation.usable_input_tokens}
        middleware = BudgetedSummarizationMiddleware(
            model=model,
            backend=lambda runtime: None,
            token_counter=count_context_tokens,
        )
        self.assertEqual(middleware.name, "SummarizationMiddleware")
        request = ModelRequest(
            model=model,
            messages=[HumanMessage(content="Say hello.")],
            system_message=SystemMessage(content="Answer the request."),
            tools=tools,
            model_settings={"max_completion_tokens": output_reservation},
        )
        self.assertEqual(
            middleware._input_budget(request),
            observation.usable_input_tokens,
            "upstream compaction must use the already-reserved profile budget without subtracting output again",
        )

    def test_oversized_summary_request_is_guarded_without_trimming_or_dispatch(self) -> None:
        deployment = self.manager.get_deployment(self.deployment_id)
        client = httpx.Client(transport=httpx.MockTransport(self._mock_openai), timeout=5.0)
        self.addCleanup(client.close)
        model = chat_model_for_deployment(deployment, http_client=client, capture_sink=[])
        baseline = ContextObservation(
            capacity_tokens=256,
            capacity_source="server_props.n_ctx",
            output_reservation_tokens=32,
            usable_input_tokens=80,
            margin_tokens=144,
        )
        model.set_context_guard(lambda payload: require_context_fit(observe_payload(baseline, payload)))
        history = [
            SystemMessage(content="Summarize the complete retained conversation without dropping facts."),
            HumanMessage(content="unchanged retained context " * 60),
        ]
        history_before = [message.model_copy(deep=True) for message in history]
        with self.assertRaises(HarnessError) as caught:
            model.invoke(history)
        self.assertEqual(caught.exception.code, "context_capacity_exceeded")
        self.assertEqual(history, history_before, "guard must reject rather than truncate the summary request")
        self.assertEqual(self.chat_payloads, [], "context guard must run before HTTP dispatch")

    def test_tools_off_compaction_uses_one_upstream_middleware_and_records_event(self) -> None:
        self._set_context(n_ctx=16384, vision=True)
        thread_id = "thread-compaction-tools-off"
        with patch(
            "workbench_backend.agents.harness.BudgetedSummarizationMiddleware",
            wraps=BudgetedSummarizationMiddleware,
        ) as middleware_factory:
            started = self._start(
                thread_id=thread_id,
                task="Preserve this earlier material. " + ("historic detail " * 1100),
                presented_tools=[],
            )
            self.assertEqual(started.status_code, 200, started.text)
            completed = self._complete(started.json())
            self.assertEqual(completed["status"], "completed", completed.get("error"))
            previous_middleware_count = middleware_factory.call_count

            started = self._start(
                thread_id=thread_id,
                task="Now preserve the important details from this later material. " + ("recent detail " * 1100),
                presented_tools=[],
            )
            self.assertEqual(started.status_code, 200, started.text)
            completed = self._complete(started.json())

        self.assertEqual(completed["status"], "completed", completed.get("error"))
        self.assertEqual(completed["presented_tools"], [])
        self.assertEqual(middleware_factory.call_count, previous_middleware_count + 1)
        self.assertGreaterEqual(len(self.chat_payloads), 3, "both turns and compaction should use the mock endpoint")
        self.assertTrue(all(not payload.get("tools") for payload in self.chat_payloads))
        compacted = [event for event in completed["events"] if event["kind"] == "context_compacted"]
        self.assertEqual(len(compacted), 1)
        self.assertGreater(compacted[0]["detail"]["cutoff_index"], 0)
        self.assertEqual(compacted[0]["detail"]["owner"], "deepagents-upstream")
        self.assertEqual(completed["context_observation"]["summarization_path"], "deepagents-upstream")


if __name__ == "__main__":
    unittest.main()
