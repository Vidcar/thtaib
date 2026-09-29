"""Run-start outline stability and native context counting boundaries."""
from __future__ import annotations

import tempfile
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain.agents.structured_output import OutputToolBinding, ProviderStrategy, ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from deepagents.middleware.summarization import SUMMARIZATION_EVENT_KEY, create_summarization_middleware
from deepagents.backends import StateBackend

from tests.scripted_model import ScriptedChatModel
from workbench_backend.agents.context import ContextObservation, count_context_tokens, estimate_payload, token_counter_for_model
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.tool_disclosure import LeanFilesystemMiddleware
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.adapter import WorkbenchChatOpenAI


class _ContextModel(ScriptedChatModel):
    def project_context_payload(self, messages, **kwargs):
        return {"messages": messages}


class PromptContinuityTests(unittest.TestCase):
    def test_sdk_retention_counts_omit_request_only_browser_schema_and_tools_without_shifting_history(self):
        schema = {"title": "Inspection", "type": "object", "properties": {"page": {"type": "string"}},
            "required": ["page"]}
        lookup = {"type": "function", "function": {"name": "lookup", "description": "Inspect the page",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}
        for provider in (False, True):
            with self.subTest(provider=provider):
                counted = []

                def endpoint(request):
                    self.assertTrue(request.url.path.endswith("/chat/completions/input_tokens"),
                        "Retention counting must never generate a summary or answer")
                    body = json.loads(request.content)
                    counted.append(body)
                    return httpx.Response(200, json={"input_tokens": estimate_payload(body)})

                client = httpx.Client(transport=httpx.MockTransport(endpoint))
                model = WorkbenchChatOpenAI(model="fixture", api_key="local", base_url="http://127.0.0.1:9/v1",
                    use_responses_api=False, http_client=client, max_retries=0, profile={"max_input_tokens": 32768})
                model.set_adapter_ownership(http_client=client, async_http_client=None, prefer_max_tokens=True,
                    reasoning_replay_scope="full_history", capture_sink=None)
                model.set_input_token_counting(client, "http://127.0.0.1:9/v1", native=True)
                run = AgentRun(id="retention", deployment_id="fixture", task="Inspect the page",
                    enabled_tools=["lookup"], presented_tools=["lookup"], browser_observation="Current page A",
                    project_outline={"snapshot_text": "", "included": False}, created_at="now", updated_at="now")
                workbench = WorkbenchHarnessMiddleware(run)
                strategy = ProviderStrategy(schema, strict=True) if provider else ToolStrategy(schema)
                counter = token_counter_for_model(model,
                    response_format=strategy.to_model_kwargs()["response_format"] if provider else None,
                    request_message_projection=workbench.browser_messages_for_count,
                    extra_tools=[] if provider else [OutputToolBinding.from_schema_spec(spec).tool
                        for spec in strategy.schema_specs],
                    tools_projection=(lambda tools: [convert_to_openai_tool(item, strict=True)
                        for item in tools]) if provider else None,
                    request_settings=None if provider else {"tool_choice": "required"})
                native = create_summarization_middleware(model, StateBackend(), token_counter=counter)
                raw = [HumanMessage(content="Old request", id="raw-0"), AIMessage(content="Old answer", id="raw-1"),
                    HumanMessage(content="Inspect " + "page " * 4000, id="raw-2"),
                    AIMessage(content="Checking", id="raw-3", tool_calls=[{"name": "lookup",
                        "args": {"query": "current"}, "id": "call-1"}]),
                    ToolMessage(content="Page inspected", name="lookup", tool_call_id="call-1", id="raw-4"),
                    HumanMessage(content="Continue", id="raw-5")]
                summary = HumanMessage(content="Old work summarized", id="summary")
                state = {SUMMARIZATION_EVENT_KEY: {"cutoff_index": 2,
                    "summary_message": summary, "file_path": None}}
                request = ModelRequest(model=model, messages=raw, state=state, tools=[lookup], model_settings={},
                    system_message=SystemMessage(content="Stable instructions"))
                before = [message.model_dump() for message in raw]
                before_summary = summary.model_dump()
                try:
                    prepared = workbench.prepare_context_request(request)
                    dispatched = []

                    def handler(current):
                        dispatched.append(current)
                        return ModelResponse(result=[AIMessage(content="Inspected")])

                    native.wrap_model_call(prepared, handler)
                    full = counted[-1]
                    self.assertEqual([message["function"]["name"] for message in full["tools"]],
                        ["lookup"] if provider else ["lookup", "Inspection"])
                    self.assertIn("Current page A", full["messages"][-1]["content"])
                    effective = dispatched[0].messages
                    self.assertEqual([message.id for message in effective], ["summary", "raw-2", "raw-3", "raw-4", "raw-5"])
                    first_partial = counter(effective)
                    partial_start = len(counted) - 1
                    cutoff_before = native._determine_cutoff_index(effective)
                    run.browser_observation = "Current page B " + "expanded observation " * 100
                    self.assertEqual(counter(effective), first_partial)
                    self.assertEqual(native._determine_cutoff_index(effective), cutoff_before,
                        "Recent-context retention must not change with ephemeral browser state")
                    self.assertGreater(cutoff_before, 0, "Exercise the SDK's partial suffix counts")
                    self.assertNotIsInstance(effective[cutoff_before], ToolMessage,
                        "Retention must keep an assistant tool call with its result")
                    for partial in counted[partial_start:]:
                        for key in ("tools", "response_format", "tool_choice"):
                            self.assertNotIn(key, partial)
                        self.assertFalse(any("browser state was refreshed" in str(message.get("content"))
                            for message in partial["messages"]))
                    native.wrap_model_call(prepared, handler)
                    self.assertIn("Current page B", counted[-1]["messages"][-1]["content"])
                    self.assertEqual([message.model_dump() for message in raw], before)
                    self.assertEqual(summary.model_dump(), before_summary)
                    self.assertEqual(prepared.messages, raw)
                    self.assertEqual(prepared.state[SUMMARIZATION_EVENT_KEY]["cutoff_index"], 2)
                finally:
                    model.close()

    def test_outline_survives_edit_pressure_and_reconstructed_run(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "workbench_backend.agents.project_outline.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout=b""),
        ):
            path = Path(directory) / "main.py"
            path.write_text("def original():\n    return 1\n")
            run = AgentRun(id="outline", deployment_id="model", task="Read main.py",
                project_path=directory, enabled_tools=["read_file"], presented_tools=["read_file"],
                context_observation=ContextObservation(capacity_tokens=10000),
                created_at=utc_now(), updated_at=utc_now())
            model = _ContextModel([])
            request = ModelRequest(model=model, messages=[HumanMessage(content="Read main.py")],
                system_message=SystemMessage(content="Stable instructions"), tools=[], model_settings={})
            middleware = WorkbenchHarnessMiddleware(run)
            first = middleware._with_outline(request)
            self.assertIn("original", first.system_message.content)
            self.assertIn("Initial project snapshot", first.system_message.content)
            path.write_text("def renamed():\n    return 2\n")
            middleware.outline_cache.invalidate(directory)
            pressure = request.override(messages=[*request.messages, AIMessage(content="x" * 60000)])
            with patch.object(middleware.outline_cache, "build", side_effect=AssertionError("Snapshot rebuilt")):
                self.assertEqual(middleware._with_outline(pressure).system_message, first.system_message)
            restored = WorkbenchHarnessMiddleware(AgentRun.model_validate_json(run.model_dump_json()))
            self.assertEqual(restored._with_outline(pressure).system_message, first.system_message)
            self.assertLessEqual(run.project_outline["estimated_tokens"], 1024)
            fresh_run = run.model_copy(update={"project_outline": None}, deep=True)
            fresh = WorkbenchHarnessMiddleware(fresh_run)._with_outline(request)
            self.assertIn("renamed", fresh.system_message.content)
            self.assertNotIn("original", fresh.system_message.content)

    def test_native_budget_sees_initial_outline_without_duplicate_insertion(self):
        run = AgentRun(id="outline", deployment_id="model", task="Read", project_outline={
            "snapshot_text": "Initial project snapshot\nmain.py: original", "included": True},
            enabled_tools=[], presented_tools=[],
            created_at=utc_now(), updated_at=utc_now())
        workbench = WorkbenchHarnessMiddleware(run)
        model = ScriptedChatModel([], profile={"max_input_tokens": 10000})
        native = LeanFilesystemMiddleware(backend=StateBackend(),
            request_preparer=workbench.prepare_context_request)
        request = ModelRequest(model=model, messages=[HumanMessage(content="Read")],
            system_message=SystemMessage(content="Instructions"), tools=[], model_settings={})
        prepared = native.prepare_request(request)
        self.assertIn("main.py", prepared.system_message.content)
        self.assertEqual(workbench._with_outline(prepared).system_message, prepared.system_message)

    def test_new_outline_admission_counts_active_summary_instead_of_raw_history(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "workbench_backend.agents.project_outline.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout=b""),
        ):
            (Path(directory) / "main.py").write_text("def current(): pass\n")
            run = AgentRun(id="follow-up", deployment_id="model", task="Read main.py", project_path=directory,
                enabled_tools=["read_file"], presented_tools=["read_file"],
                context_observation=ContextObservation(capacity_tokens=1000),
                created_at=utc_now(), updated_at=utc_now())
            model = _ContextModel([], profile={"max_input_tokens": 1000})
            workbench = WorkbenchHarnessMiddleware(run)
            native = LeanFilesystemMiddleware(backend=StateBackend(),
                request_preparer=workbench.prepare_context_request)
            raw = [HumanMessage(content="x"*6000), AIMessage(content="Old answer"), HumanMessage(content="Read main.py")]
            state = {SUMMARIZATION_EVENT_KEY: {"cutoff_index": 2,
                "summary_message": HumanMessage(content="Old work summarized"), "file_path": None}}
            request = ModelRequest(model=model, messages=raw, state=state,
                system_message=SystemMessage(content="Instructions"), tools=[], model_settings={})
            prepared = native.prepare_request(request)
            self.assertIn("current", prepared.system_message.content)
            self.assertEqual(prepared.messages, raw)
            self.assertEqual(prepared.state[SUMMARIZATION_EVENT_KEY]["cutoff_index"], 2)


if __name__ == "__main__":
    unittest.main()
