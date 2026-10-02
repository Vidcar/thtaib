"""Actual model schema and native dispatch contract regressions from the tools audit."""
from __future__ import annotations

import copy
import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

import httpx
from jsonschema import Draft202012Validator
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool, Tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError
from deepagents.backends import FilesystemBackend
from langgraph.prebuilt.tool_node import ToolCallRequest

from workbench_backend.agents.execution_policy import plan_tool_names
from workbench_backend.agents.harness_presentation import apply_disclosure_and_plan_filter
from workbench_backend.agents.harness_profile import ordinary_chat_profile
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import UserQuestion
from workbench_backend.agents.tool_catalogue import TOOL_PRESENTATIONS, CHECKLIST_DESCRIPTION
from workbench_backend.agents.tool_disclosure import LeanFilesystemMiddleware, ToolDisclosureMiddleware, compact_tool, input_tool_schemas
from workbench_backend.agents.tool_schema import model_tool_schema
from workbench_backend.connections.schemas import ConnectionSnapshot, ConnectionTool
from workbench_backend.connections.service import namespaced
from workbench_backend.inference.adapter import WorkbenchChatOpenAI
from workbench_backend.inference.request_projection import project_context_payload
from tests.test_tool_disclosure import call, run_for, SchemaRecordingModel, _Loader


SCHEMA = {
    "type": "object", "title": "Issue arguments",
    "$defs": {"titled": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}},
    "properties": {
        "title": {"type": "string"},
        "items": {"type": "array", "items": {"$ref": "#/$defs/titled"}},
        "choice": {"oneOf": [{"type": "string"}, {"$ref": "#/$defs/titled"}]},
        "optional": {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/titled"}]},
        "defaults": {"type": "object", "default": {"title": "literal default"}, "examples": [{"title": "literal example"}]},
        "constant": {"const": {"title": "literal constant"}},
        "enumeration": {"enum": [{"title": "literal enum"}]},
    }, "required": ["title", "items", "choice", "constant", "enumeration"],
}
VALID = {"title": "issue", "items": [{"title": "nested"}], "choice": {"title": "option"},
    "constant": {"title": "literal constant"}, "enumeration": {"title": "literal enum"}}


def connection(kind="public_web", remote_names=("search_web", "read_web_page"), ident="public"):
    return ConnectionSnapshot(id=ident, name="Public research", version=1, kind=kind,
        transport="builtin" if kind == "public_web" else "http", tools=[ConnectionTool(
            id=namespaced(ident, name), name=namespaced(ident, name), remote_name=name,
            description="Read public research", input_schema={"type": "object", "properties": {}}) for name in remote_names])


class ToolSchemaContractTests(unittest.TestCase):
    def test_custom_tool_final_binding_preserves_pinned_native_type_and_extras(self):
        tool = Tool(name="custom_probe", description="Native custom format", func=lambda value: value,
            metadata={"type": "custom_tool"}, extras={"defer_loading": True, "async": True})
        native = ChatOpenAI(model="fixture", api_key="fixture")
        workbench = WorkbenchChatOpenAI(model="fixture", api_key="fixture")
        expected = native.bind_tools([tool]).kwargs["tools"]
        self.assertEqual(expected[0]["type"], "custom")
        self.assertTrue(expected[0]["defer_loading"])
        self.assertTrue(expected[0]["async"])
        self.assertEqual(workbench.bind_tools([tool]).kwargs["tools"], expected)
        self.assertEqual(model_tool_schema(tool), expected[0])
        workbench.close()

    def tool(self):
        return StructuredTool(name="create_issue", description="Create an issue", args_schema=copy.deepcopy(SCHEMA))

    def assert_fidelity(self, schema):
        expected = copy.deepcopy(SCHEMA); expected.pop("title")
        self.assertEqual(schema, expected)
        self.assertTrue(Draft202012Validator(schema).is_valid(VALID))
        for invalid in ({**VALID, "title": 7}, {**VALID, "items": [{}]}, {**VALID, "constant": {}}):
            self.assertEqual(Draft202012Validator(schema).is_valid(invalid), Draft202012Validator(SCHEMA).is_valid(invalid))

    def test_cold_capture_and_context_projection_preserve_schema_and_literal_data(self):
        tool = self.tool(); original = copy.deepcopy(tool.args_schema)
        projected = compact_tool(tool)
        self.assertEqual(tool.args_schema, original)
        self.assert_fidelity(model_tool_schema(projected)["function"]["parameters"])
        self.assert_fidelity(input_tool_schemas([tool.name], extra_tools=[tool])[tool.name]["function"]["parameters"])
        self.assert_fidelity(project_context_payload([HumanMessage(content="create")], tools=[projected])["tools"][0]["function"]["parameters"])

    def test_final_openai_adapter_transport_keeps_literal_title_values(self):
        posted = []
        def respond(request):
            posted.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "fixture", "object": "chat.completion", "created": 1, "model": "fixture",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "done"}, "finish_reason": "stop"}]})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        model = WorkbenchChatOpenAI(model="fixture", api_key="fixture", base_url="https://model.test/v1", http_client=client)
        try:
            result = model.bind_tools([compact_tool(self.tool())]).invoke([HumanMessage(content="create")])
            self.assertEqual(result.content, "done")
            self.assert_fidelity(posted[0]["tools"][0]["function"]["parameters"])
        finally:
            model.close(); client.close()

    def test_question_schema_and_executor_share_enum_bounds_and_choice_validation(self):
        schema = input_tool_schemas(["ask_user"])["ask_user"]["function"]["parameters"]
        self.assertEqual(set(schema["properties"]["answer_type"]["enum"]), {"text", "choice", "file", "folder"})
        self.assertEqual(schema["properties"]["prompt"]["maxLength"], 4000)
        for args in ({"prompt": "pick", "answer_type": "unknown"}, {"prompt": "pick", "answer_type": "choice"}, {"prompt": ""}):
            with self.assertRaises(ValidationError):
                UserQuestion.model_validate(args)

    def test_application_overlay_projects_same_native_semantics(self):
        profile = ordinary_chat_profile()
        for name in ("write_file", "edit_file"):
            self.assertEqual(profile.tool_description_overrides[name], TOOL_PRESENTATIONS[name].model_description)
            self.assertIn("tool-call batch", profile.tool_description_overrides[name])
            self.assertIn("sequential", profile.tool_description_overrides[name])
        self.assertNotIn("once per response", CHECKLIST_DESCRIPTION)
        for name, row in TOOL_PRESENTATIONS.items():
            self.assertTrue(row.label and row.description and row.group, name)
            for companion in row.companions:
                self.assertIn(companion, TOOL_PRESENTATIONS, name)

    def test_native_guard_blocks_same_batch_mutation_but_allows_sequential_repairs(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = FilesystemBackend(root_dir=directory, virtual_mode=True)
            middleware = LeanFilesystemMiddleware(backend=backend)
            calls = [{"name": "write_file", "args": {"file_path": "/notes.txt", "content": "first"}, "id": "first"},
                {"name": "edit_file", "args": {"file_path": "/notes.txt", "old_string": "first", "new_string": "second"}, "id": "second"}]
            state = {"messages": [AIMessage(content="", tool_calls=calls)]}
            executed = []
            def mutate(request):
                current = request.tool_call; args = current["args"]
                executed.append(current["id"])
                result = backend.write(args["file_path"], args["content"]) if current["name"] == "write_file" else backend.edit(args["file_path"], args["old_string"], args["new_string"])
                return ToolMessage(content=result.error or "changed", name=current["name"], tool_call_id=current["id"], status="error" if result.error else "success")
            outcomes = [middleware.wrap_tool_call(ToolCallRequest(tool_call=current, tool=None, state=state, runtime=None), mutate) for current in calls]
            self.assertEqual(executed, ["first", "second"])
            self.assertEqual([item.status for item in outcomes], ["success", "success"])
            self.assertEqual(Path(directory, "notes.txt").read_text(), "second")
            for step, replacement in enumerate(("second", "third"), 2):
                before = Path(directory, "notes.txt").read_text()
                self.assertEqual(backend.read("/notes.txt").error, None)
                current = {"name": "edit_file", "args": {"file_path": "/notes.txt", "old_string": before, "new_string": replacement}, "id": f"sequential-{step}"}
                state["messages"].append(AIMessage(content="", tool_calls=[current]))
                result = middleware.wrap_tool_call(ToolCallRequest(tool_call=current, tool=None, state=state, runtime=None), mutate)
                self.assertEqual(result.status, "success")
            self.assertEqual(Path(directory, "notes.txt").read_text(), "third")


class NativeAuditContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_compiled_request_and_native_conforming_call_keep_title(self):
        effects, posted = [], []
        async def create_issue(**args):
            effects.append(args)
            return "created"
        tool = StructuredTool.from_function(name="create_issue", description="Create an issue", coroutine=create_issue, args_schema=copy.deepcopy(SCHEMA))
        def respond(request):
            posted.append(json.loads(request.content))
            message = {"role": "assistant", "content": "done"}
            if len(posted) == 1:
                message = {"role": "assistant", "content": "", "tool_calls": [{"id": "create", "type": "function", "function": {"name": tool.name, "arguments": json.dumps(VALID)}}]}
            return httpx.Response(200, json={"id": "fixture", "object": "chat.completion", "created": 1, "model": "fixture",
                "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if len(posted) == 1 else "stop"}]})
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        model = WorkbenchChatOpenAI(model="fixture", api_key="fixture", base_url="https://model.test/v1", http_async_client=client)
        run = run_for([tool.name]); run.input_policy.tool_loading = "always"
        graph = create_agent(model, tools=[tool], middleware=[ToolDisclosureMiddleware(run)])
        try:
            result = await graph.ainvoke({"messages": [HumanMessage(content="create")]})
            self.assertEqual(effects, [VALID])
            expected = copy.deepcopy(SCHEMA); expected.pop("title")
            self.assertEqual(posted[0]["tools"][0]["function"]["parameters"], expected)
            self.assertEqual(result["messages"][-1].content, "done")
        finally:
            await model.aclose(); await client.aclose()

    async def test_more_than_five_matches_reachable_by_cursor_and_repeated_search(self):
        async def operation():
            return "done"
        definitions = [StructuredTool.from_function(name=f"external_{i}", description="External operation", coroutine=operation) for i in range(12)]
        run = run_for(["find_tools", *(tool.name for tool in definitions)])
        disclosure = ToolDisclosureMiddleware(run, loader=_Loader(definitions))
        state = {"disclosed_tools": []}
        async def search(cursor=None, query="external", group=None):
            result = await disclosure._find_tools(query, SimpleNamespace(state=state, tool_call_id="search"), cursor=cursor, group=group)
            if "disclosed_tools" in result.update:
                state["disclosed_tools"] = result.update["disclosed_tools"]
            return json.loads(result.update["messages"][0].content)
        first = await search(); self.assertTrue(first["has_more"])
        second = await search(cursor=first["next_cursor"])
        third = await search(cursor=second["next_cursor"])
        self.assertFalse(third["has_more"])
        self.assertEqual(len(state["disclosed_tools"]), 12)
        self.assertEqual(len({item["name"] for page in (first, second, third) for item in page["results"]}), 12)
        state["disclosed_tools"] = []
        pages = [await search() for _ in range(3)]
        self.assertEqual(len({item["name"] for page in pages for item in page["results"]}), 12)
        exact = await search(query="external_0")
        self.assertTrue(exact["results"][0]["already_disclosed"])
        denied = await disclosure._find_tools("different", SimpleNamespace(state=state, tool_call_id="bad"), cursor=first["next_cursor"])
        self.assertEqual(denied.update["messages"][0].status, "error")
        run.input_policy.excluded_sources = ["tool:external_9"]
        denied = await disclosure._find_tools("external", SimpleNamespace(state=state, tool_call_id="changed"), cursor=first["next_cursor"])
        self.assertEqual(denied.update["messages"][0].status, "error")

    async def test_human_connection_group_and_full_remote_operation_name_discover_stable_id(self):
        snap = connection("mcp", ("read_very_long_document_title_metadata",), "docs")
        descriptor = snap.tools[0]
        tool = StructuredTool(name=descriptor.name, description=descriptor.description, args_schema=descriptor.input_schema)
        run = run_for(["find_tools", tool.name], snapshots=[snap])
        disclosure = ToolDisclosureMiddleware(run, loader=_Loader([tool]))
        result = await disclosure._find_tools(descriptor.remote_name, SimpleNamespace(state={}, tool_call_id="alias"), group=snap.name)
        self.assertEqual(result.update["disclosed_tools"], [descriptor.name])
        body = json.loads(result.update["messages"][0].content)
        self.assertEqual(body["results"][0]["label"], descriptor.remote_name)
        wrong = await disclosure._find_tools(descriptor.remote_name, SimpleNamespace(state={}, tool_call_id="wrong"), group="browser")
        self.assertEqual(json.loads(wrong.update["messages"][0].content)["results"], [])


class TrustedPlanContractTests(unittest.TestCase):
    def test_only_selected_builtin_public_operations_are_eligible_at_each_projection(self):
        trusted = connection(); external = connection("mcp", ("search_web", "read_web_page"), "remote")
        forged = connection(remote_names=("delete_everything",), ident="other")
        all_names = [*(tool.name for snap in (trusted, external, forged) for tool in snap.tools), "execute", "write_file", "browser_navigate"]
        names = plan_tool_names([trusted, external, forged])
        self.assertTrue({tool.name for tool in trusted.tools}.issubset(names))
        self.assertFalse(set(all_names[2:]).intersection(names))
        request = SimpleNamespace(work_mode="plan", presented_tools=all_names)
        filtered = apply_disclosure_and_plan_filter(request, None, [], None, all_names, [trusted, external, forged])
        self.assertEqual(set(filtered), {tool.name for tool in trusted.tools})
        run = run_for(filtered, mode="plan", snapshots=[trusted, external, forged])
        middleware = WorkbenchHarnessMiddleware(run)
        effects = []
        for name in all_names:
            result = middleware.wrap_tool_call(SimpleNamespace(tool_call={"name": name, "args": {}, "id": name}),
                lambda _, current=name: effects.append(current) or ToolMessage(content="read", name=current, tool_call_id=current))
            self.assertEqual(result.status, "success" if name in filtered else "error")
        self.assertEqual(set(effects), set(filtered))


if __name__ == "__main__":
    unittest.main()
