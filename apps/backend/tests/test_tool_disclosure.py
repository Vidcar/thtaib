"""Lean disclosure uses native graph state, tool execution and interrupts."""
from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack, asynccontextmanager
from types import SimpleNamespace
from typing import ClassVar
import unittest

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from workbench_backend.agents.host_shell import pending_interrupt_from_raw, validated_decision_payloads
from workbench_backend.agents.schemas import AgentRun, InterruptDecision
from workbench_backend.agents.setup_schemas import AgentInputPolicy
from workbench_backend.agents.tool_disclosure import (
    CapabilitySetupBoundary, DeferredToolCollection, ToolDisclosureMiddleware,
    authorized_tool_names, bootstrap_tool_names, compact_tool, input_tool_schemas,
)
from workbench_backend.connections.schemas import ConnectionSnapshot, ConnectionTool
from workbench_backend.errors import HarnessError
from tests.scripted_model import ScriptedChatModel


class SchemaRecordingModel(ScriptedChatModel):
    offered: ClassVar[list[set[str]]] = []

    def bind_tools(self, tools, **kwargs):
        type(self).offered.append({convert_to_openai_tool(item)["function"]["name"] for item in tools})
        return super().bind_tools(tools, **kwargs)


def run_for(names, *, policy=None, mode="work", snapshots=()):
    return AgentRun(id="lean-fixture", deployment_id="fixture", task="Use selected tools",
        enabled_tools=names, presented_tools=names, input_policy=policy or AgentInputPolicy(),
        connection_snapshots=list(snapshots), work_mode=mode, created_at="2026-09-28T00:00:00+00:00",
        updated_at="2026-09-28T00:00:00+00:00")


def call(name, args=None, ident=None):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": ident or "call_" + name}])


class _Loader:
    def __init__(self, definitions):
        self.actual = {tool.name: tool for tool in definitions}
        self.definitions = {name: StructuredTool(name=name, description=tool.description,
            args_schema=tool.tool_call_schema) for name, tool in self.actual.items()}
        self.loads = []
        self.ready = True

    def owns(self, name):
        return name in self.actual

    async def load(self, name):
        self.loads.append(name)
        if not self.ready:
            raise HarnessError("Install the selected worker.", code="browser_worker_missing", status_code=409)
        return self.actual[name]


class NativeToolDisclosureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        SchemaRecordingModel.offered.clear()

    async def test_bounded_discovery_native_dynamic_runtime_and_next_turn_reset(self):
        effects = []
        async def invoke(runtime: ToolRuntime):
            effects.append(runtime.tool_call_id)
            self.assertIn("messages", runtime.state)
            return "native-runtime-ok"
        definitions = [StructuredTool.from_function(name="external_" + str(index),
            description="External operation " + str(index), coroutine=invoke) for index in range(8)]
        loader = _Loader(definitions)
        run = run_for(["find_tools", *loader.actual])
        disclosure = ToolDisclosureMiddleware(run, loader=loader)
        # The tool is absent from create_agent's static ToolNode registry.
        model = SchemaRecordingModel([call("find_tools", {"query": "external"}, "discovery"),
            call("external_0", ident="dynamic"), AIMessage(content="done"), AIMessage(content="next")])
        graph = create_agent(model, tools=[], middleware=[disclosure], checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "native-dynamic"}}
        result = await graph.ainvoke({"messages": [{"role": "user", "content": "do task"}]}, config)
        self.assertEqual(SchemaRecordingModel.offered[0], {"find_tools"})
        saved = await graph.aget_state(config)
        self.assertEqual(len(saved.values["disclosed_tools"]), 5)
        self.assertEqual(SchemaRecordingModel.offered[1], {"find_tools", *("external_" + str(i) for i in range(5))})
        self.assertEqual(effects, ["dynamic"])
        self.assertEqual([message.content for message in result["messages"] if isinstance(message, ToolMessage)][-1], "native-runtime-ok")
        await graph.ainvoke({"messages": [{"role": "user", "content": "next task"}]}, config)
        self.assertEqual(SchemaRecordingModel.offered[-1], {"find_tools"})

    async def test_native_approval_still_precedes_dynamic_effect_and_rejection(self):
        effects = []
        async def operation():
            effects.append("effect")
            return "finished"
        tool = StructuredTool.from_function(name="external_write", description="Write selected external data", coroutine=operation)
        run = run_for(["find_tools", tool.name])
        loader = _Loader([tool])
        disclosure = ToolDisclosureMiddleware(run, loader=loader)
        approval = HumanInTheLoopMiddleware({tool.name: {"allowed_decisions": ["approve", "reject"]}})
        model = SchemaRecordingModel([call(tool.name), AIMessage(content="rejected")])
        graph = create_agent(model, middleware=[disclosure, approval], checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "native-approval"}}
        paused = await graph.ainvoke({"messages": [{"role": "user", "content": "do task"}]}, config)
        self.assertTrue(paused["__interrupt__"])
        self.assertEqual(loader.loads, [])
        self.assertEqual(effects, [])
        await graph.ainvoke(Command(resume={"decisions": [{"type": "reject"}]}), config)
        self.assertEqual(effects, [])
        self.assertEqual(loader.loads, [])

    async def test_setup_pause_repairs_same_native_call_and_preserves_discovery(self):
        effects = []
        async def operation():
            effects.append("effect")
            return "finished"
        tool = StructuredTool.from_function(name="browser_snapshot", description="Inspect the browser page", coroutine=operation)
        run = run_for(["find_tools", tool.name])
        loader = _Loader([tool])
        loader.ready = False
        disclosure = ToolDisclosureMiddleware(run, loader=loader, on_setup=CapabilitySetupBoundary(run, lambda: None))
        model = SchemaRecordingModel([call("find_tools", {"query": "browser_snapshot"}, "setup-call"),
            call(tool.name), AIMessage(content="finished")])
        graph = create_agent(model, middleware=[disclosure], checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "native-setup"}}
        paused = await graph.ainvoke({"messages": [{"role": "user", "content": "inspect page"}]}, config)
        pending = pending_interrupt_from_raw(paused["__interrupt__"][0])
        self.assertEqual(pending.kind, "capability_setup")
        self.assertEqual(pending.action_requests[0].setup.capability, "browser")
        self.assertEqual(effects, [])
        loader.ready = True
        result = await graph.ainvoke(Command(resume={"decisions": [{"type": "respond", "message": "continue"}]}), config)
        saved = await graph.aget_state(config)
        self.assertIn(tool.name, saved.values["disclosed_tools"])
        self.assertEqual(effects, ["effect"])
        self.assertEqual(len([event for event in run.events if event.kind == "capability_setup_requested"]), 1)

    async def test_setup_reject_does_not_disclose_or_execute(self):
        async def operation():
            self.fail("rejected setup must not execute")
        tool = StructuredTool.from_function(name="browser_snapshot", description="Inspect browser", coroutine=operation)
        run = run_for(["find_tools", tool.name])
        loader = _Loader([tool]); loader.ready = False
        disclosure = ToolDisclosureMiddleware(run, loader=loader, on_setup=CapabilitySetupBoundary(run, lambda: None))
        graph = create_agent(SchemaRecordingModel([call("find_tools", {"query": "browser_snapshot"}), call(tool.name), AIMessage(content="skipped")]),
            middleware=[disclosure], checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "reject-setup"}}
        await graph.ainvoke({"messages": [{"role": "user", "content": "inspect"}]}, config)
        result = await graph.ainvoke(Command(resume={"decisions": [{"type": "reject"}]}), config)
        saved = await graph.aget_state(config)
        self.assertEqual(saved.values["disclosed_tools"], [tool.name])
        self.assertEqual(len(loader.loads), 1)

    async def test_plan_and_excluded_names_cannot_dispatch_even_from_history(self):
        async def operation():
            self.fail("out-of-envelope tool must not execute")
        tool = StructuredTool.from_function(name="execute", description="Execute", coroutine=operation)
        run = run_for(["find_tools", "execute"], mode="plan")
        disclosure = ToolDisclosureMiddleware(run, loader=_Loader([tool]))
        graph = create_agent(SchemaRecordingModel([call("execute"), AIMessage(content="blocked")]), middleware=[disclosure])
        result = await graph.ainvoke({"messages": [{"role": "user", "content": "run"}]})
        self.assertEqual(result["messages"][-2].status, "error")
        self.assertEqual(SchemaRecordingModel.offered[0], {"find_tools"})

    async def test_parallel_discovery_merges_native_activation_state(self):
        async def operation():
            return "result"
        definitions = [StructuredTool.from_function(name=name, description=name, coroutine=operation)
            for name in ("external_alpha", "external_beta")]
        run = run_for(["find_tools", *(tool.name for tool in definitions)])
        disclosure = ToolDisclosureMiddleware(run, loader=_Loader(definitions))
        model = SchemaRecordingModel([AIMessage(content="", tool_calls=[
            {"name": "find_tools", "args": {"query": "external_alpha"}, "id": "alpha"},
            {"name": "find_tools", "args": {"query": "external_beta"}, "id": "beta"}]), AIMessage(content="done")])
        graph = create_agent(model, middleware=[disclosure], checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "parallel-discovery"}}
        await graph.ainvoke({"messages": [{"role": "user", "content": "find both"}]}, config)
        saved = await graph.aget_state(config)
        self.assertCountEqual(saved.values["disclosed_tools"], ["external_alpha", "external_beta"])
        self.assertEqual(SchemaRecordingModel.offered[-1], {"find_tools", "external_alpha", "external_beta"})


class ToolDisclosurePolicyTests(unittest.TestCase):
    def test_bootstrap_pins_eager_and_tools_off(self):
        names = ["find_tools", "ask_user", "read_file", "echo", "write_todos", "execute"]
        run = run_for(names, policy=AgentInputPolicy(pinned_tools=["echo"]))
        self.assertEqual(bootstrap_tool_names(run), {"find_tools", "ask_user", "read_file", "echo"})
        run.input_policy.tool_loading = "always"
        self.assertEqual(bootstrap_tool_names(run), set(names))
        run.input_policy.excluded_sources = ["tool:echo"]
        self.assertNotIn("echo", authorized_tool_names(run))
        run.presented_tools = []
        self.assertEqual(bootstrap_tool_names(run), set())

    def test_projectless_knowledge_reader_does_not_describe_a_project_root(self):
        from deepagents.middleware.filesystem import LsSchema, ReadFileSchema

        routes = ["/memories/", "/skills/", "/large_tool_results/", "/conversation_history/", "/retrieved/"]
        reader = StructuredTool(name="read_file", description="read", args_schema=ReadFileSchema)
        listed = StructuredTool(name="ls", description="list", args_schema=LsSchema)
        virtual = compact_tool(reader, project_bound=False, virtual_read_paths=routes)
        listed_virtual = compact_tool(listed, project_bound=False, virtual_read_paths=routes)
        project = compact_tool(reader, project_bound=True)

        def schema_text(tool: StructuredTool) -> str:
            body = tool.args_schema if isinstance(tool.args_schema, dict) else tool.args_schema.model_json_schema()
            return tool.description + "\n" + json.dumps(body)

        virtual_text = schema_text(virtual)
        self.assertIn("/skills/", virtual_text)
        self.assertIn("is not a project root", virtual_text)
        self.assertIn("not authorized", virtual_text)
        self.assertNotIn("Project-relative", virtual_text)
        self.assertNotIn("/ is the project root", virtual_text)
        self.assertIn("/skills/", schema_text(listed_virtual))
        project_text = schema_text(project)
        self.assertIn("Project-relative", project_text)
        self.assertIn("/ is the project root", project_text)

    def test_cold_file_schema_removes_contradiction_preserves_validation(self):
        schema = input_tool_schemas(["read_file", "execute"])
        file_schema = schema["read_file"]["function"]
        self.assertIn("Project-relative", file_schema["parameters"]["properties"]["file_path"]["description"])
        self.assertEqual(file_schema["parameters"]["required"], ["file_path"])
        self.assertNotIn("title", file_schema["parameters"])
        self.assertIn("cmd.exe", schema["execute"]["function"]["parameters"]["properties"]["command"]["description"])

    def test_typed_setup_cannot_be_turned_into_saved_permission(self):
        run = run_for(["find_tools", "browser_snapshot"])
        from workbench_backend.agents.tool_disclosure import _setup_request
        setup = _setup_request(run, "browser_snapshot", HarnessError("Install worker", code="browser_worker_missing"))
        pending = pending_interrupt_from_raw({"kind": "capability_setup",
            "action_requests": [{"name": "find_tools", "args": {}, "setup": setup.model_dump()}],
            "review_configs": [{"action_name": "find_tools", "allowed_decisions": ["respond", "reject"]}]})
        with self.assertRaises(ValueError):
            validated_decision_payloads(pending, [InterruptDecision(type="respond", message="continue", scope="workspace")])


class HarnessToolDisclosureTests(unittest.TestCase):
    # Reuse the established isolated application fixture without inheriting its
    # unrelated regression methods or creating another test stack.
    from tests.test_harness import HarnessApiTests as _Fixture
    setUp = _Fixture.setUp
    tearDown = _Fixture.tearDown
    _start = _Fixture._start
    _wait_for_pending_interrupt = _Fixture._wait_for_pending_interrupt

    def _always_skill(self, required_tool):
        content = ("---\nname: always-fixture\ndescription: Validation skill.\nrequired-tools:\n"
            f"  - {required_tool}\n---\nALWAYS_FROZEN_BODY_826\n")
        created = self.client.post("/v1/knowledge/entries", json={"scope": "user", "kind": "skill",
            "content": content, "display_name": "Always fixture",
            "provenance": {"actor": "human", "note": "fixture"}})
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()

    def test_always_skill_requires_selected_tools_before_any_model_request_without_pinning(self):
        from tests.support import wait_for_run
        skill = self._always_skill("echo")
        policy = {"reference_loading": {skill["id"]: "always"}}
        SchemaRecordingModel.offered.clear()
        self.scripted = SchemaRecordingModel([AIMessage(content="included")])
        for names, exclusions in (([], []), (["echo"], ["tool:echo"])):
            with self.subTest(names=names, exclusions=exclusions):
                blocked = self.client.post("/v1/agent-runs", json={"deployment_id": self.deployment_id,
                    "task": "Use the selected skill.", "skill_version_refs": [skill["current_version_id"]],
                    "presented_tools": names, "input_policy": {**policy, "excluded_sources": exclusions}})
                self.assertEqual(blocked.status_code, 409, blocked.text)
                self.assertEqual(blocked.json()["code"], "skill_selection_required")
                self.assertEqual(SchemaRecordingModel.offered, [], "No skill body may reach a model before dependencies are selected")
        started = self._start(skill_version_refs=[skill["current_version_id"]], presented_tools=["echo"], input_policy=policy)
        run = wait_for_run(self.client, started["id"])
        self.assertEqual(run["status"], "completed", run.get("error"))
        self.assertIn("ALWAYS_FROZEN_BODY_826", run["model_requests"][0]["instructions"])
        self.assertNotIn("echo", run["model_requests"][0]["presented_tools"], "Requirements must not implicitly pin schemas")
        self.assertEqual(run["input_policy"]["pinned_tools"], [])
        self.assertEqual(run["tool_outcomes"], {})

    def test_always_skill_plan_cannot_include_a_body_requiring_a_mutating_tool(self):
        skill = self._always_skill("write_file")
        SchemaRecordingModel.offered.clear()
        self.scripted = SchemaRecordingModel([AIMessage(content="included")])
        blocked = self.client.post("/v1/agent-runs", json={"deployment_id": self.deployment_id,
            "task": "Use the selected skill.", "work_mode": "plan", "presented_tools": ["write_file"],
            "skill_version_refs": [skill["current_version_id"]],
            "input_policy": {"reference_loading": {skill["id"]: "always"}}})
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["code"], "skill_selection_required")
        self.assertEqual(SchemaRecordingModel.offered, [])

    def test_always_skill_requires_optional_worker_before_body_but_deferred_does_not(self):
        from tests.support import wait_for_run
        skill = self._always_skill("browser_navigate")
        SchemaRecordingModel.offered.clear()
        self.scripted = SchemaRecordingModel([AIMessage(content="ordinary response")])
        blocked = self.client.post("/v1/agent-runs", json={"deployment_id": self.deployment_id,
            "task": "Ordinary response.", "presented_tools": ["browser_navigate"],
            "skill_version_refs": [skill["current_version_id"]],
            "input_policy": {"reference_loading": {skill["id"]: "always"}}})
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["code"], "browser_worker_missing")
        self.assertEqual(SchemaRecordingModel.offered, [])
        started = self._start(task="Ordinary response.", presented_tools=["browser_navigate"],
            skill_version_refs=[skill["current_version_id"]])
        run = wait_for_run(self.client, started["id"])
        self.assertEqual(run["status"], "completed", run.get("error"))
        self.assertNotIn("ALWAYS_FROZEN_BODY_826", run["model_requests"][0]["instructions"])
        self.assertEqual(run["tool_outcomes"], {})

    def test_always_required_connection_needs_usable_selected_tool_without_opening_adapter(self):
        from tests.support import wait_for_run
        from unittest.mock import patch
        from workbench_backend.connections.schemas import ConnectionWrite
        from workbench_backend.connections.service import ConnectionService, namespaced
        service = self.app.state.harness.connections
        record = service.create(ConnectionWrite(name="Always Docs", kind="mcp", transport="http", url="https://example.test/mcp"))
        name = namespaced(record.id, "read_document")
        descriptor = ConnectionTool(id=name, name=name, remote_name="read_document", description="Read a selected document.",
            input_schema={"type": "object", "properties": {}})
        service.store.put(record.model_copy(update={"tools": [descriptor], "last_tested_at": record.created_at}), expected_version=record.version)
        created = self.client.post("/v1/knowledge/entries", json={"scope": "user", "kind": "skill",
            "display_name": "Always connection fixture", "content": "---\nname: always-docs\ndescription: Validation skill.\n"
                f"required-connections:\n  - {record.id}\n---\nALWAYS_CONNECTION_BODY_831\n",
            "provenance": {"actor": "human", "note": "fixture"}})
        self.assertEqual(created.status_code, 200, created.text)
        skill = created.json()
        selection = {"deployment_id": self.deployment_id, "task": "Ordinary response.",
            "skill_version_refs": [skill["current_version_id"]], "connection_ids": [record.id],
            "input_policy": {"reference_loading": {skill["id"]: "always"}}}
        SchemaRecordingModel.offered.clear()
        self.scripted = SchemaRecordingModel([AIMessage(content="included")])
        with patch.object(ConnectionService, "_adapter", side_effect=AssertionError("Pre-including a skill must never open an adapter")):
            blocked = self.client.post("/v1/agent-runs", json={**selection, "presented_tools": ["echo"]})
            self.assertEqual(blocked.status_code, 409, blocked.text)
            self.assertEqual(blocked.json()["code"], "skill_selection_required")
            self.assertEqual(SchemaRecordingModel.offered, [])
            started = self._start(**selection, presented_tools=[name])
            run = wait_for_run(self.client, started["id"])
        self.assertEqual(run["status"], "completed", run.get("error"))
        self.assertIn("ALWAYS_CONNECTION_BODY_831", run["model_requests"][0]["instructions"])
        self.assertNotIn(name, run["model_requests"][0]["presented_tools"])
        self.assertEqual(run["tool_outcomes"], {})

    def test_child_graph_actual_envelope_rejects_always_skill_before_body_compilation(self):
        skill = self._always_skill("echo")
        run = run_for(["read_file", "find_tools"], policy=AgentInputPolicy(reference_loading={skill["id"]: "always"}))
        run.deployment_id = self.deployment_id
        run.parent_run_id = "parent-fixture"
        run.skill_version_refs = [skill["current_version_id"]]
        with self.assertRaises(HarnessError) as blocked:
            self.app.state.harness._create_compiled_agent(run, [], None, inspection_only=True, is_child=True)
        self.assertEqual(blocked.exception.code, "skill_selection_required")

    def test_actual_model_capture_tracks_discovered_schemas(self):
        from tests.support import wait_for_run
        self.scripted = SchemaRecordingModel([call("find_tools", {"query": "echo"}, "discover-echo"),
            call("echo", {"text": "hello"}), AIMessage(content="hello")])
        authored = "  Keep this authored instruction verbatim.\n\n"
        started = self._start(presented_tools=["echo"], input_policy={"instruction_override": authored})
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        first, second = body["model_requests"][:2]
        self.assertEqual(set(first["presented_tools"]), {"read_file", "find_tools"})
        self.assertNotIn("echo", first["presented_tools"])
        self.assertIn("echo", second["presented_tools"])
        self.assertEqual({tool["function"]["name"] for tool in first["tool_schemas"]}, set(first["presented_tools"]))
        self.assertEqual({tool["function"]["name"] for tool in second["tool_schemas"]}, set(second["presented_tools"]))
        first_source = next(row for row in first["input_sources"] if row["tool_name"] == "echo")
        second_source = next(row for row in second["input_sources"] if row["tool_name"] == "echo")
        self.assertEqual(first_source["estimated_tokens"], 0)
        self.assertIsNone(first_source["content"])
        self.assertTrue(second_source["available"])
        self.assertTrue(second_source["observed"])
        self.assertGreater(second_source["estimated_tokens"], 0)
        self.assertEqual(second_source["reason"], "Tool definition supplied in this request.")
        self.assertEqual(json.loads(second_source["content"]),
            next(tool for tool in second["tool_schemas"] if tool["function"]["name"] == "echo"))
        self.assertEqual(body["input_policy"]["tool_loading"], "when_needed")
        instruction_source = next(row for row in first["input_sources"] if row["id"] == "conversation_instructions")
        self.assertEqual(instruction_source["content"], authored)
        self.assertIn(instruction_source["content"], first["instructions"])
        core_source = next(row for row in first["input_sources"] if row["id"] == "workbench_core")
        self.assertTrue(core_source["observed"])
        self.assertIn(core_source["content"], first["instructions"])

    def test_local_file_discovery_does_not_set_up_unready_optional_features(self):
        from tests.support import wait_for_run
        from workbench_backend.connections.schemas import ConnectionWrite
        project = self.root / "lean-files"
        project.mkdir()
        connection = self.app.state.harness.connections.create(ConnectionWrite(name="My files",
            kind="mcp", transport="http", url="https://example.test/mcp"))
        self.scripted = SchemaRecordingModel([call("find_tools", {"query": "write file edit replace text"}), AIMessage(content="ready")])
        started = self._start(project_path=str(project), connection_ids=[connection.id],
            presented_tools=["read_file", "write_file", "edit_file", "glob", "grep", "browser_file_upload"])
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertIsNone(body["pending_interrupt"])
        self.assertFalse(any(event["kind"] == "capability_setup_requested" for event in body["events"]))
        disclosed = set(body["model_requests"][1]["presented_tools"])
        self.assertTrue({"read_file", "write_file", "edit_file"}.issubset(disclosed))
        self.assertFalse(any(name.startswith("browser_") for name in disclosed))

    def test_queued_connection_keeps_accepted_manifest_until_native_setup_boundary(self):
        from tests.support import wait_for_run
        from workbench_backend.connections.schemas import ConnectionWrite
        from workbench_backend.connections.service import namespaced
        service = self.app.state.harness.connections
        record = service.create(ConnectionWrite(name="Frozen Docs", kind="mcp", transport="http", url="https://example.test/mcp"))
        name = namespaced(record.id, "read_document")
        original = ConnectionTool(id=name, name=name, remote_name="read_document", description="Read a selected document.",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})
        record = record.model_copy(update={"tools": [original], "last_tested_at": record.created_at})
        service.store.put(record)
        self.scripted = SchemaRecordingModel([call("find_tools", {"query": name}),
            call(name, {"query": "accepted"}, "frozen-call"), AIMessage(content="skipped")])
        chat = self.client.post("/v1/chat/conversations", json={"deployment_id": self.deployment_id,
            "connection_ids": [record.id], "presented_tools": [name], "approval_mode": "full_access"}).json()
        queued = self.client.post(f"/v1/chat/conversations/{chat['id']}/queue", json={"task": "Read the selected document"})
        self.assertEqual(queued.status_code, 200, queued.text)
        snapshot = queued.json()["queue"][0]["execution_snapshot"]["connection_snapshots"]
        self.assertEqual(snapshot[0]["tools"][0]["input_schema"], original.input_schema)
        changed = original.model_copy(update={"input_schema": {"type": "object", "properties": {"different": {"type": "integer"}}, "required": ["different"]}})
        new_name = namespaced(record.id, "new_document")
        added = original.model_copy(update={"id": new_name, "name": new_name, "remote_name": "new_document"})
        service.store.put(record.model_copy(update={"tools": [changed, added], "version": record.version + 1}))
        resumed = self.client.post(f"/v1/chat/conversations/{chat['id']}/queue/resume", json={})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        run_id, = resumed.json()["run_ids"]
        paused = self._wait_for_pending_interrupt(run_id)
        self.assertEqual(paused["connection_snapshots"][0]["tools"][0]["input_schema"], original.input_schema)
        self.assertNotIn(new_name, paused["presented_tools"])
        self.assertEqual(paused["pending_interrupt"]["action_requests"][0]["setup"]["code"], "connection_changed")
        self.assertTrue(paused["pending_interrupt"]["action_requests"][0]["setup"]["requires_new_input"])
        self.assertEqual(self.app.state.app_store.list_effects(run_id=run_id), [])
        rejected = self.client.post(f"/v1/agent-runs/{run_id}/interrupt-decision", json={
            "interrupt_id": paused["pending_interrupt"]["interrupt_id"], "decisions": [{"type": "reject"}]})
        self.assertEqual(rejected.status_code, 200, rejected.text)
        final = wait_for_run(self.client, run_id)
        self.assertEqual(final["status"], "completed", final.get("error"))

    def test_projectless_selected_shell_pauses_only_when_used(self):
        from pathlib import Path
        from tests.support import wait_for_run
        home = str(Path.home().resolve())
        self.scripted = SchemaRecordingModel([call("find_tools", {"query": "execute"}, "discover-shell"),
            call("execute", {"command": "echo no-project"}, "need-project"), AIMessage(content="skipped")])
        started = self._start(presented_tools=["execute"], approval_mode="full_access")
        self.assertTrue(started["host_shell"]["available"])
        self.assertEqual(started["host_shell"]["cwd"], home)
        self.assertIsNone(started.get("pending_interrupt"))
        paused = self._wait_for_pending_interrupt(started["id"])
        pending = paused["pending_interrupt"]
        self.assertEqual(pending["kind"], "deepagents_interrupt_on")
        action = pending["action_requests"][0]
        self.assertEqual(action["name"], "execute")
        self.assertEqual(action["args"]["command"], "echo no-project")
        self.assertIsNone(action.get("setup"))
        self.assertEqual(paused["host_shell"]["cwd"], home)
        decision = self.client.post(f"/v1/agent-runs/{started['id']}/interrupt-decision", json={
            "interrupt_id": pending["interrupt_id"],
            "namespace": pending.get("namespace", []), "decisions": [{"type": "reject"}]})
        self.assertEqual(decision.status_code, 200, decision.text)
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertFalse(any(invocation["name"] == "execute" and invocation.get("status") == "succeeded" for invocation in body["tool_invocations"]))

    def test_frozen_reference_body_is_absent_until_native_read(self):
        from tests.support import wait_for_run
        created = self.client.post("/v1/knowledge/entries", json={"scope": "user", "kind": "memory",
            "content": "EXACT_FROZEN_REFERENCE_BYTES_123", "display_name": "Selected reference",
            "provenance": {"actor": "human", "note": "fixture"}})
        self.assertEqual(created.status_code, 200, created.text)
        reference = created.json()
        self.scripted = SchemaRecordingModel([call("read_reference", {"entry_id": reference["id"]}), AIMessage(content="read")])
        started = self._start(memory_version_refs=[reference["current_version_id"]], presented_tools=["echo"])
        body = wait_for_run(self.client, started["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        first, second = body["model_requests"][:2]
        self.assertNotIn("EXACT_FROZEN_REFERENCE_BYTES_123", first["instructions"])
        self.assertNotIn("EXACT_FROZEN_REFERENCE_BYTES_123", str(first["messages"]))
        self.assertIn("EXACT_FROZEN_REFERENCE_BYTES_123", str(second["messages"]))
        results = [event["detail"] for event in body["events"] if event["kind"] == "tool_result" and event["detail"].get("name") == "read_reference"]
        self.assertTrue(results)


class DeferredConnectionTests(unittest.IsolatedAsyncioTestCase):
    from tests.test_connections import ConnectionTests as _Fixture
    setUp = _Fixture.setUp
    tearDown = _Fixture.tearDown

    async def test_real_mcp_stays_cold_then_native_ask_preserves_effect_journal(self):
        tested = await self.service.test(self.record.id)
        descriptor = next(item for item in tested.tools if item.remote_name == "read_file")
        run = run_for(["find_tools", descriptor.name], snapshots=self.service.snapshot([tested.id]))
        before = self.sessions
        async with AsyncExitStack() as stack:
            loader = DeferredToolCollection(run, stack, connections=self.service)
            self.assertEqual(self.sessions, before)
            approval = HumanInTheLoopMiddleware({descriptor.name: {"allowed_decisions": ["approve", "reject"]}})
            disclosure = ToolDisclosureMiddleware(run, loader=loader,
                ensure_approval=lambda name: self.assertIn(name, approval.interrupt_on))
            graph = create_agent(SchemaRecordingModel([call("find_tools", {"query": descriptor.name}),
                call(descriptor.name, {"query": "native"}, "native-external"), AIMessage(content="done")]),
                middleware=[disclosure, approval], checkpointer=InMemorySaver())
            config = {"configurable": {"thread_id": "lazy-real-mcp"}}
            paused = await graph.ainvoke({"messages": [{"role": "user", "content": "read docs"}]}, config)
            self.assertTrue(paused["__interrupt__"])
            self.assertEqual(self.sessions, before)
            self.assertEqual(self.calls, [])
            self.assertEqual(self.store.list_effects(run_id=run.id), [])
            await graph.ainvoke(Command(resume={"decisions": [{"type": "approve"}]}), config)
            self.assertEqual(self.calls, ["native"])
            self.assertEqual(self.sessions, before + 1)
            effects = self.store.list_effects(run_id=run.id)
            self.assertEqual(len(effects), 1)
            self.assertEqual(self.store.list_effects(run_id=run.id, unresolved_only=True), [])
        self.assertEqual(self.closed, self.sessions)


    async def test_unavailable_selected_manifest_requires_new_input_without_session(self):
        snapshots = self.service.snapshot([self.record.id], allow_unready=True)
        run = run_for(["find_tools"], snapshots=snapshots)
        async with AsyncExitStack() as stack:
            loader = DeferredToolCollection(run, stack, connections=self.service)
            graph = create_agent(SchemaRecordingModel([call("find_tools", {"query": "Docs"}), AIMessage(content="skipped")]),
                middleware=[ToolDisclosureMiddleware(run, loader=loader,
                    on_setup=CapabilitySetupBoundary(run, lambda: None))], checkpointer=InMemorySaver())
            config = {"configurable": {"thread_id": "missing-manifest"}}
            paused = await graph.ainvoke({"messages": [{"role": "user", "content": "Docs"}]}, config)
            pending = pending_interrupt_from_raw(paused["__interrupt__"][0])
            self.assertEqual(pending.action_requests[0].setup.target_id, self.record.id)
            self.assertTrue(pending.action_requests[0].setup.requires_new_input)
            await graph.ainvoke(Command(resume={"decisions": [{"type": "reject"}]}), config)
        self.assertEqual(self.sessions, 0)
        self.assertEqual(self.calls, [])

    async def test_schema_drift_is_setup_pause_before_remote_effect(self):
        tested = await self.service.test(self.record.id)
        descriptor = next(item for item in tested.tools if item.remote_name == "read_file")
        run = run_for(["find_tools", descriptor.name], snapshots=self.service.snapshot([tested.id]))
        @self.server.tool
        async def new_manifest_tool() -> str:
            """This name was not in the accepted manifest."""
            self.fail("new names cannot execute in the old input")
        async with AsyncExitStack() as stack:
            loader = DeferredToolCollection(run, stack, connections=self.service)
            graph = create_agent(SchemaRecordingModel([call("find_tools", {"query": descriptor.name}), call(descriptor.name, {"query": "old-manifest"}), AIMessage(content="skipped")]),
                middleware=[ToolDisclosureMiddleware(run, loader=loader,
                    on_setup=CapabilitySetupBoundary(run, lambda: None))], checkpointer=InMemorySaver())
            config = {"configurable": {"thread_id": "manifest-drift"}}
            paused = await graph.ainvoke({"messages": [{"role": "user", "content": "Docs"}]}, config)
            pending = pending_interrupt_from_raw(paused["__interrupt__"][0])
            self.assertEqual(pending.action_requests[0].setup.code, "connection_schema_changed")
            self.assertTrue(pending.action_requests[0].setup.requires_new_input)
            await graph.ainvoke(Command(resume={"decisions": [{"type": "reject"}]}), config)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.closed, self.sessions)


class DeferredWindowsTests(unittest.IsolatedAsyncioTestCase):
    from tests.test_desktop_automation import DesktopAutomationTests as _Fixture
    setUp = _Fixture.setUp

    async def test_missing_runtime_pauses_selected_and_all_grants_before_action_then_repairs(self):
        from workbench_backend.desktop_automation.runtime import WinAppRuntimeError

        class MissingRuntime:
            def command_path(self):
                raise WinAppRuntimeError("The optional WinApp CLI worker is not installed.")

        original_runtime = self.service.runtime
        for scope in ("selected", "all"):
            with self.subTest(scope=scope):
                thread_id = "runtime-missing-" + scope
                self.service.runtime = original_runtime
                self.service.set_scope(thread_id, scope, hwnd=101 if scope == "selected" else None)
                self.commands.clear()
                self.service.runtime = MissingRuntime()
                run = run_for(["find_tools", "desktop_inspect"])
                run.thread_id, run.source_surface, run.desktop_access = thread_id, "chat", scope
                async with AsyncExitStack() as stack:
                    loader = DeferredToolCollection(run, stack, connections=None, desktop=self.service)
                    disclosure = ToolDisclosureMiddleware(run, loader=loader,
                        on_setup=CapabilitySetupBoundary(run, lambda: None))
                    graph = create_agent(SchemaRecordingModel([call("desktop_inspect", {"hwnd": 101}), AIMessage(content="done")]),
                        middleware=[disclosure], checkpointer=InMemorySaver())
                    config = {"configurable": {"thread_id": thread_id}}
                    paused = await graph.ainvoke({"messages": [{"role": "user", "content": "inspect authorized target"}]}, config)
                    pending = pending_interrupt_from_raw(paused["__interrupt__"][0])
                    self.assertEqual(pending.kind, "capability_setup")
                    self.assertEqual(pending.action_requests[0].setup.capability, "windows")
                    self.assertEqual(pending.action_requests[0].setup.code, "desktop_runtime_unavailable")
                    self.assertFalse(pending.action_requests[0].setup.requires_new_input)
                    self.assertEqual(self.commands, [], "Missing worker must pause before inspecting or controlling a window")
                    self.service.runtime = original_runtime
                    result = await graph.ainvoke(Command(resume={"decisions": [{"type": "respond", "message": "continue"}]}), config)
                    self.assertEqual(result["messages"][-1].content, "done")
                    actions = [args for args, _ in self.commands if args[1] == "inspect"]
                    self.assertEqual(len(actions), 1)
                    self.assertEqual(actions[0][actions[0].index("-w") + 1], "101")
                    self.assertEqual(len([event for event in run.events if event.kind == "capability_setup_requested"]), 1)

    async def test_selected_scope_repairs_once_and_binds_exact_target(self):
        from workbench_backend.desktop_automation.service import DESKTOP_TOOL_NAMES
        run = run_for(["find_tools", *DESKTOP_TOOL_NAMES])
        run.thread_id, run.source_surface, run.desktop_access = "thread-one", "chat", "selected"
        async with AsyncExitStack() as stack:
            loader = DeferredToolCollection(run, stack, connections=None, desktop=self.service)
            self.assertEqual(self.commands, [])
            self.assertIn("desktop_inspect", loader.definitions)
            with self.assertRaises(HarnessError) as missing:
                await loader.load("desktop_inspect")
            self.assertEqual(missing.exception.code, "desktop_grant_required")
            self.service.set_scope("thread-one", "selected", hwnd=101)
            tool = await loader.load("desktop_inspect")
            self.assertEqual(run.desktop_window["hwnd"], 101)
            result = await tool.ainvoke({"name": tool.name, "args": {}, "id": "inspect-selected", "type": "tool_call"})
            self.assertEqual(result.status, "success")
            self.assertIn("101", str(self.commands[-1][0]))
            before_actions = len([args for args, _ in self.commands if args[1] != "list-windows"])
            self.service.set_scope("thread-one", "selected", hwnd=202)
            with self.assertRaises(HarnessError) as changed:
                await loader.load("desktop_inspect")
            self.assertEqual(changed.exception.code, "desktop_window_changed")
            self.assertEqual(len([args for args, _ in self.commands if args[1] != "list-windows"]), before_actions)

    async def test_off_scope_cannot_borrow_later_live_grant(self):
        run = run_for(["find_tools", "desktop_inspect"])
        run.thread_id, run.source_surface, run.desktop_access = "thread-one", "chat", "off"
        self.service.set_scope("thread-one", "selected", hwnd=101)
        self.commands.clear()  # Authenticated picker work precedes the cold run.
        async with AsyncExitStack() as stack:
            loader = DeferredToolCollection(run, stack, connections=None, desktop=self.service)
            with self.assertRaises(HarnessError) as denied:
                await loader.load("desktop_inspect")
            self.assertEqual(denied.exception.code, "desktop_selection_required")
        self.assertEqual(self.commands, [])


if __name__ == "__main__":
    unittest.main()
