"""Real outbound serialization, native overflow, and request attribution regressions."""

import asyncio
import base64
import json
from io import BytesIO
from PIL import Image
import unittest
from unittest.mock import patch

import httpx
from deepagents.middleware.summarization import _is_context_overflow
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk

from workbench_backend.agents.context import (
    BudgetedSummarizationMiddleware, ContextObservation, estimate_payload,
    require_context_fit, token_counter_for_model, validate_retained_messages,
)
from workbench_backend.errors import HarnessError
from workbench_backend.inference.adapter import WorkbenchChatOpenAI, _raise_for_invalid_completed_tool_calls
from workbench_backend.inference.configuration_options import bundle_configuration_options, validate_model_reasoning
from workbench_backend.inference.request_projection import project_context_payload
from workbench_backend.inference.schemas import Deployment, GgufRuntimeMetadata, ServerProperties, SettingsBag
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.inference.telemetry import LatestGenerationPublisher, RequestTelemetry, current_request_purpose, request_purpose


def deployment(**props):
    return Deployment(id="fixture", display_name="fixture", scope="connected", status="running",
        created_at="now", updated_at="now", server_props=ServerProperties(fetched="now", source_url="fixture", **props))


def model(*, replay=False, transport=None):
    client = httpx.Client(transport=transport or httpx.MockTransport(lambda r: httpx.Response(500)))
    value = WorkbenchChatOpenAI(model="fixture", api_key="local", base_url="http://127.0.0.1:9/v1",
                              use_responses_api=False, http_client=client, max_retries=0)
    value.set_adapter_ownership(http_client=client, async_http_client=None, prefer_max_tokens=True,
                                reasoning_replay_scope="full_history" if replay else "none", capture_sink=None)
    return value


class RequestProjectionTests(unittest.TestCase):
    def test_partial_stream_failure_preserves_exact_batch_outcomes_without_bodies(self):
        chunk = ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[
            {"index": 0, "id": "complete-sibling", "name": "write_file", "args": '{"file_path":"ready.txt","content":"PRIVATE BODY"}'},
            {"index": 1, "id": "incomplete-sibling", "name": "write_file", "args": '{"file_path":"partial.txt","content":"PRIVATE CUT'},
        ]), generation_info={"finish_reason": "length"})
        with self.assertRaises(HarnessError) as failure:
            _raise_for_invalid_completed_tool_calls(chunk)
        self.assertEqual(failure.exception.code, "response_limit_reached")
        self.assertEqual(failure.exception.details["tool_calls"], [
            {"call_id": "complete-sibling", "name": "write_file", "outcome": "not_dispatched", "file_path": "ready.txt"},
            {"call_id": "incomplete-sibling", "name": "write_file", "outcome": "incomplete_arguments", "file_path": "partial.txt"},
        ])
        self.assertNotIn("PRIVATE", json.dumps(failure.exception.details))

    def test_long_native_reasoning_is_counted_once_and_equals_real_wire(self):
        reasoning = "reason " * 17248  # Comparable to the observed 120,730-character failure.
        ai = AIMessage(content="Prepared.", additional_kwargs={"reasoning_content": reasoning},
                       response_metadata={"reasoning_content": reasoning},
                       tool_calls=[{"id": "call1", "name": "write_file", "args": {"path": "a.txt", "content": "hello"}}])
        ai = ai.model_copy(update={"content": ai.content_blocks, "response_metadata": {**ai.response_metadata, "output_version": "v1"}})
        messages = [SystemMessage(content="Assist."), HumanMessage(content="Write a file."), ai,
                    ToolMessage(content="Written.", tool_call_id="call1")]
        original = ai.model_dump()
        for replay in (False, True):
            with self.subTest(replay=replay):
                sent = []
                def endpoint(request):
                    sent.append(json.loads(request.content))
                    return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 1,
                        "model": "fixture", "choices": [{"index": 0, "message": {"role": "assistant", "content": "Done"}, "finish_reason": "stop"}]})
                value = model(replay=replay, transport=httpx.MockTransport(endpoint))
                try:
                    projected = value.project_context_payload(messages)
                    count = token_counter_for_model(value)(messages)
                    value.invoke(messages)
                    self.assertEqual(projected["messages"], sent[0]["messages"])
                    self.assertEqual(count, estimate_payload(projected))
                    self.assertEqual(json.dumps(projected).count(reasoning), int(replay))
                    self.assertLess(count, 42000 if replay else 300)
                    self.assertEqual(ai.model_dump(), original)
                finally:
                    value.close()

    def test_image_projection_does_not_shift_later_reasoning_or_mutate_messages(self):
        output = BytesIO()
        Image.new("RGB", (1, 1), "red").save(output, format="PNG")
        image = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()
        messages = [AIMessage(content="", tool_calls=[{"id": "img", "name": "capture", "args": {}}]),
                    ToolMessage(tool_call_id="img", content=[{"type": "image_url", "image_url": {"url": image}}]),
                    AIMessage(content="Seen", additional_kwargs={"reasoning_content": "unique thought"})]
        projected = project_context_payload(messages, reasoning_scope="full_history")
        self.assertEqual(projected["messages"][-1]["reasoning_content"], "unique thought")
        self.assertEqual(projected["messages"][-2]["role"], "user")
        self.assertTrue(projected["messages"][-2]["content"][0]["text"].startswith("<tool_response>"))
        self.assertTrue(projected["messages"][-2]["content"][-1]["text"].endswith("</tool_response>"))
        self.assertNotIn("reasoning_content", projected["messages"][-2])
        self.assertEqual(len(messages), 3)

    def test_recovery_preview_closes_partial_call_without_mutation_or_execution(self):
        ai = AIMessage(content="", invalid_tool_calls=[{"id": "partial", "name": "write_file", "args": '{"path":', "error": "truncated"}])
        messages = [ai]
        with self.assertRaises(HarnessError):
            validate_retained_messages(deployment(), messages)
        validate_retained_messages(deployment(), messages, allow_recovery=True)
        self.assertEqual(len(messages), 1)
        failed = ToolMessage(content="Arguments were truncated; nothing executed.", tool_call_id="partial", status="error")
        validate_retained_messages(deployment(), [ai, failed])
        projected = project_context_payload([ai, failed])
        self.assertEqual(projected["messages"][0]["tool_calls"][0]["function"]["arguments"], "{}")
        self.assertEqual(ai.invalid_tool_calls[0]["args"], '{"path":')
        unnamed = AIMessage(content="", invalid_tool_calls=[{"id": "partial", "name": None, "args": None, "error": "truncated"}])
        self.assertEqual(project_context_payload([unnamed, failed])["messages"][0]["tool_calls"][0]["function"],
                         {"name": "unknown", "arguments": "{}"})
        with self.assertRaises(HarnessError):
            validate_retained_messages(deployment(), [ToolMessage(content="orphan", tool_call_id="missing")], allow_recovery=True)

    def test_fit_error_is_native_overflow_and_keeps_budget_evidence(self):
        observation = ContextObservation(capacity_tokens=100, estimated_input_tokens=110, usable_input_tokens=80, fits=False)
        with self.assertRaises(HarnessError) as captured:
            require_context_fit(observation)
        self.assertTrue(_is_context_overflow(captured.exception))
        self.assertEqual(captured.exception.details["estimated_input_tokens"], 110)

    def test_summary_scope_is_restored_on_success_and_failure(self):
        value = model()
        try:
            middleware = BudgetedSummarizationMiddleware(model=value, backend=lambda _: None, trigger=("tokens", 200), keep=("messages", 1))
            with patch.object(middleware._lc_helper, "_create_summary", side_effect=lambda _: current_request_purpose()):
                self.assertEqual(middleware._create_summary([HumanMessage(content="old")]), "summary")
            async def fail(_):
                self.assertEqual(current_request_purpose(), "summary")
                raise RuntimeError("summary unavailable")
            with patch.object(middleware._lc_helper, "_acreate_summary", side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, "unavailable"):
                    asyncio.run(middleware._acreate_summary([HumanMessage(content="old")]))
            self.assertEqual(current_request_purpose(), "work")
        finally:
            value.close()


class ResponseBudgetTests(unittest.TestCase):
    def test_budget_is_persisted_and_sent_as_native_extra_body(self):
        from workbench_backend.inference.adapter import _extra_body
        bag = resolve_bags(per_request={"reasoning_budget_tokens": 2048, "max_tokens": 8192}).per_request
        self.assertNotIn("reasoning_budget_tokens", bag.unsupported)
        self.assertEqual(_extra_body(bag)["reasoning_budget_tokens"], 2048)
        validate_model_reasoning(deployment(), bag)
        for invalid in (True, 2.5, "2048", -2):
            with self.subTest(invalid=invalid), self.assertRaises(HarnessError):
                validate_model_reasoning(deployment(), SettingsBag(applied={"reasoning_budget_tokens": invalid}))

    def test_template_controls_do_not_invent_response_bundles(self):
        unknown = bundle_configuration_options(None, GgufRuntimeMetadata())
        self.assertEqual(unknown.response_presets, [])
        known = bundle_configuration_options(None, GgufRuntimeMetadata(), deployment=deployment(
            build_info="b11045-2b1847030", chat_template="{% if reasoning_effort == 'medium' %}medium{% elif reasoning_effort == 'xhigh' %}deep{% endif %}"))
        self.assertEqual(known.response_presets, [])
        unsupported = bundle_configuration_options(None, GgufRuntimeMetadata(), deployment=deployment(chat_template_caps={"supports_reasoning_budget": False}))
        self.assertEqual(unsupported.response_presets, [])
        toggle = bundle_configuration_options(None, GgufRuntimeMetadata(chat_template="{% if enable_thinking %}think{% endif %}"))
        self.assertEqual(toggle.response_presets, [])
        from workbench_backend.inference.schemas import HuggingFaceConfiguration
        publisher = bundle_configuration_options(None, GgufRuntimeMetadata(chat_template="{{ messages }}"),
            huggingface_configuration=HuggingFaceConfiguration(generation_defaults={"reasoning_effort": "xhigh", "reasoning": "off"}))
        self.assertIs(publisher.per_request_defaults["reasoning_effort"].supported, False)
        self.assertEqual(publisher.per_request_defaults["reasoning_effort"].options, [])
        self.assertEqual(publisher.response_presets, [])


class PurposeTelemetryTests(unittest.TestCase):
    def test_housekeeping_keeps_work_sample_and_cached_input_separate(self):
        publisher = LatestGenerationPublisher(lambda _: None)
        try:
            work = RequestTelemetry(publisher.publish)
            response = {"id": "work", "timings": {"cache_n": 80, "prompt_n": 20, "predicted_n": 40, "predicted_ms": 500, "predicted_per_second": 78}}
            work.receive(response)
            work.finish()
            with request_purpose("summary"):
                summary = RequestTelemetry(publisher.publish)
                summary.receive({**response, "id": "summary", "timings": {**response["timings"], "predicted_n": 5}})
                summary.finish()
            measured_work = publisher.latest_sample("work")
            self.assertEqual(measured_work["output_tokens"], 40)
            self.assertEqual(measured_work["cached_input_tokens"], 80)
            self.assertEqual(measured_work["processed_input_tokens"], 20)
            self.assertEqual(publisher.latest_sample("summary")["output_tokens"], 5)
            self.assertEqual(set(publisher.latest_samples()), {"work", "summary"})
        finally:
            publisher.close()
