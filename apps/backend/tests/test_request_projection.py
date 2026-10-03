"""Real outbound serialization, native overflow, and request attribution regressions."""

import asyncio
from contextlib import nullcontext
import base64
import json
from io import BytesIO
from PIL import Image
import unittest
from unittest.mock import patch

import httpx
from deepagents.backends import StateBackend
from deepagents.middleware.summarization import _is_context_overflow, create_summarization_middleware
from langchain.agents import create_agent
from langchain.agents.structured_output import OutputToolBinding, ProviderStrategy, ToolStrategy
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.tools import tool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

from workbench_backend.agents.context import (
    SummaryDispatchModel, ContextObservation, estimate_payload, observe_payload,
    token_counter_for_model, validate_retained_messages,
)
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.agents.tool_schema import model_tool_schema
from workbench_backend.errors import HarnessError
from workbench_backend.inference.adapter import WorkbenchChatOpenAI, _raise_for_invalid_completed_tool_calls
from workbench_backend.inference.configuration_options import bundle_configuration_options, validate_model_reasoning
from workbench_backend.inference.request_projection import TOOL_CONTEXT_MARKER, project_context_payload
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


class PageReport(BaseModel):
    """Report the page inspected in this request."""

    page: str


class RequestProjectionTests(unittest.TestCase):
    def _exercise_sdk_structured_count_matches_generation(self, *, provider):
        self.maxDiff = None
        counts, generations = [], []
        strategy = ProviderStrategy(PageReport, strict=True) if provider else ToolStrategy(PageReport)

        def endpoint(request):
            body = json.loads(request.content)
            if request.url.path.endswith("/chat/completions/input_tokens"):
                counts.append(body)
                return httpx.Response(200, json={"input_tokens": 301})
            self.assertTrue(request.url.path.endswith("/chat/completions"))
            generations.append(body)
            answer = {"page": f"page-{len(generations)}"}
            message = {"role": "assistant", "content": json.dumps(answer)}
            if not provider:
                message = {"role": "assistant", "content": "", "tool_calls": [{
                    "id": f"report-{len(generations)}", "type": "function", "function": {
                        "name": strategy.schema_specs[0].name, "arguments": json.dumps(answer),
                    },
                }]}
            return httpx.Response(200, json={"id": f"response-{len(generations)}",
                "object": "chat.completion", "created": 1, "model": "fixture",
                "choices": [{"index": 0, "message": message,
                    "finish_reason": "stop" if provider else "tool_calls"}]})

        @tool
        def lookup(query: str) -> str:
            """Look up a selected fixture without changing it."""
            self.fail("Structured response must not execute the ordinary lookup tool")

        run = AgentRun(id="counted-sdk", deployment_id="fixture", task="Inspect the page",
            enabled_tools=["lookup"], presented_tools=["lookup"],
            browser_observation="Stale page before the graph was compiled",
            project_outline={"snapshot_text": "", "included": False},
            created_at="now", updated_at="now")
        workbench = WorkbenchHarnessMiddleware(run)
        value = model(replay=True, transport=httpx.MockTransport(endpoint))
        value.profile = {"max_input_tokens": 32768}
        value.max_tokens = -1
        value.extra_body = {"chat_template_kwargs": {"enable_thinking": True, "preserve_reasoning": True}}
        value.set_input_token_counting(value.http_client, "http://127.0.0.1:9/v1", native=True)
        counter = token_counter_for_model(value,
            response_format=value.bind_tools([], response_format=strategy.to_model_kwargs()["response_format"], strict=True).kwargs["response_format"] if provider else None,
            message_projection=workbench.tool_image_messages_for_count,
            request_message_projection=workbench.browser_messages_for_count,
            extra_tools=[] if provider else [OutputToolBinding.from_schema_spec(spec).tool
                for spec in strategy.schema_specs],
            tools_projection=(lambda selected: [model_tool_schema(item, strict=True)
                for item in selected]) if provider else None,
            request_settings=None if provider else {"tool_choice": "required"})
        summarization = create_summarization_middleware(value, StateBackend(), token_counter=counter)
        agent = create_agent(value, tools=[lookup], system_prompt="Inspect the current page.",
            response_format=strategy, middleware=[summarization, workbench],
            checkpointer=InMemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=[PageReport])))
        config = {"configurable": {"thread_id": "counted-sdk"}}
        try:
            for index, page in enumerate(("Fresh page with current coordinates", "Another refreshed page"), start=1):
                # Compile once, then change the observation before each new dispatch.
                run.browser_observation = page
                user = HumanMessage(content=f"Inspect page {index}", id=f"user-{index}")
                before = user.model_dump()
                result = agent.invoke({"messages": [user]}, config=config)
                self.assertEqual(result["structured_response"], PageReport(page=f"page-{index}"))
                self.assertEqual(len(generations), index)
                self.assertEqual(len(counts), index)
                self.assertEqual(counts[-1], generations[-1],
                    "Native SDK count must include the same tools, schema, browser state and template settings as generation")
                self.assertIn(page, generations[-1]["messages"][-1]["content"])
                self.assertNotIn("Stale page", json.dumps(counts[-1]))
                self.assertEqual(counts[-1]["max_tokens"], -1)
                self.assertEqual(user.model_dump(), before)
                checkpoint = agent.get_state(config).values["messages"]
                retained_users = [message for message in checkpoint if isinstance(message, HumanMessage)
                    and not message.additional_kwargs.get(TOOL_CONTEXT_MARKER)]
                self.assertEqual([message.id for message in retained_users],
                    [f"user-{number}" for number in range(1, index + 1)])
                observations = [message for message in checkpoint
                    if message.additional_kwargs.get("workbench_browser_observation")]
                self.assertEqual(len(observations), index)
                self.assertEqual(observations[-1].content, generations[-1]["messages"][-1]["content"])
                self.assertTrue(all(message.additional_kwargs.get(TOOL_CONTEXT_MARKER) for message in observations))
            if provider:
                self.assertTrue(counts[-1]["tools"][0]["function"]["strict"])
                self.assertIs(counts[-1]["tools"][0]["function"]["parameters"]["additionalProperties"], False)
                self.assertTrue(counts[-1]["response_format"]["json_schema"]["strict"])
            else:
                self.assertEqual([item["function"]["name"] for item in counts[-1]["tools"]],
                    ["lookup", "PageReport"])
                self.assertEqual(counts[-1]["tool_choice"], "required")
                for number in (1, 2):
                    calls = [message for message in checkpoint if isinstance(message, AIMessage)
                        and any(call["id"] == f"report-{number}" for call in message.tool_calls)]
                    results = [message for message in checkpoint if isinstance(message, ToolMessage)
                        and message.tool_call_id == f"report-{number}"]
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(len(results), 1)
                    self.assertLess(checkpoint.index(calls[0]), checkpoint.index(results[0]))
        finally:
            value.close()

    def test_sdk_tool_strategy_native_count_matches_generation_and_fresh_browser_state(self):
        self._exercise_sdk_structured_count_matches_generation(provider=False)

    def test_sdk_provider_strategy_native_count_matches_strict_tools_and_schema(self):
        self._exercise_sdk_structured_count_matches_generation(provider=True)

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

    def test_string_template_preserves_sdk_text_and_mirrored_tool_call_history(self):
        call = {"type": "tool_call", "id": "write-1", "name": "write_file",
                "args": {"file_path": "/hello.txt", "content": "hello 漢字😀"}}
        messages = [HumanMessage(content="Write the greeting."),
            AIMessage(content=[call], tool_calls=[call]),
            ToolMessage(content="Updated file /hello.txt", tool_call_id="write-1"),
            AIMessage(content=[{"type": "text", "text": "Written 漢字😀", "index": 0}])]
        original = [item.model_dump() for item in messages]
        setup = deployment(chat_template_caps={"supports_typed_content": False,
            "supports_string_content": True, "supports_tools": True, "supports_tool_calls": True})
        validate_retained_messages(setup, messages)
        projected = project_context_payload(messages)["messages"]
        self.assertIsNone(projected[1]["content"])
        self.assertEqual(projected[1]["tool_calls"][0]["function"]["arguments"],
                         json.dumps(call["args"], ensure_ascii=False))
        self.assertEqual(projected[-1]["content"], [{"type": "text", "text": "Written 漢字😀"}])
        self.assertEqual([item.model_dump() for item in messages], original)
        with self.assertRaises(HarnessError) as caught:
            validate_retained_messages(setup, messages[:2])
        self.assertEqual(caught.exception.code, "context_tool_pair_invalid")

    def test_string_template_still_denies_nontext_malformed_and_unmirrored_blocks(self):
        setup = deployment(chat_template_caps={"supports_typed_content": False})
        for block in ({"type": "text", "text": 123}, {"type": "audio", "data": "unsupported"},
                      {"type": "image_url", "image_url": {"url": "unsupported"}},
                      {"type": "unknown", "text": "must not disappear"},
                      {"type": "tool_call", "id": "missing", "name": "write_file", "args": {}}):
            message = AIMessage(content=[block])
            original = message.model_dump()
            with self.subTest(block=block), self.assertRaises(HarnessError) as caught:
                validate_retained_messages(setup, [message])
            self.assertEqual(caught.exception.code, "context_content_unsupported")
            self.assertEqual(message.model_dump(), original)
        call = {"type": "tool_call", "id": "same", "name": "write_file", "args": {"content": "x"}}
        conflicting = AIMessage(content=[{**call, "args": {"content": "different"}}], tool_calls=[call])
        with self.assertRaises(HarnessError) as caught:
            validate_retained_messages(setup, [conflicting, ToolMessage(content="done", tool_call_id="same")])
        self.assertEqual(caught.exception.code, "context_content_unsupported")

    def test_estimated_input_is_observation_and_cannot_establish_a_fit(self):
        base = ContextObservation(capacity_tokens=100)
        payload = {"messages": [{"role": "user", "content": "large text " * 200}]}
        estimated = observe_payload(base, payload)
        self.assertGreater(estimated.input_tokens, 100)
        self.assertIsNone(estimated.fits)
        self.assertEqual(estimated.counting_basis, "estimated")
        native = observe_payload(base, payload, native_counter=lambda _: 110)
        self.assertEqual(native.input_tokens, 110)
        self.assertFalse(native.fits)
        self.assertEqual(native.counting_basis, "native")


    def test_summary_scope_preserves_native_metadata_and_restores_after_success_and_failure(self):
        value = model()
        decorated = SummaryDispatchModel(delegate=value, profile=value.profile, dispatch=nullcontext)
        config = {"metadata": {"lc_source": "summarization", "native_internal_marker": "untouched"}}
        def summary(input, config=None, **kwargs):
            self.assertEqual(current_request_purpose(), "summary")
            self.assertEqual(config, {"metadata": {"lc_source": "summarization", "native_internal_marker": "untouched"}})
            return AIMessage(content="Summary")
        async def failure(input, config=None, **kwargs):
            self.assertEqual(current_request_purpose(), "summary")
            self.assertEqual(config, {"metadata": {"lc_source": "summarization", "native_internal_marker": "untouched"}})
            raise RuntimeError("summary unavailable")
        try:
            with patch.object(WorkbenchChatOpenAI, "invoke", side_effect=summary):
                self.assertEqual(decorated.invoke([HumanMessage(content="old")], config=config).content, "Summary")
            self.assertEqual(current_request_purpose(), "work")
            with patch.object(WorkbenchChatOpenAI, "ainvoke", side_effect=failure):
                with self.assertRaisesRegex(RuntimeError, "unavailable"):
                    asyncio.run(decorated.ainvoke([HumanMessage(content="old")], config=config))
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
