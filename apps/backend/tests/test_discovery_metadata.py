"""Discovery uses accepted tools and advertised labels without inventing schemas."""
from __future__ import annotations

import json
from types import SimpleNamespace
import unittest

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.agents.setup_schemas import AgentInputPolicy
from workbench_backend.agents.tool_catalogue import TOOL_PRESENTATIONS
from workbench_backend.agents.tool_disclosure import ToolDisclosureMiddleware, selected_tools_index
from workbench_backend.browser.service import BROWSER_TOOL_NAMES
from workbench_backend.connections.schemas import ConnectionSnapshot, ConnectionTool
from workbench_backend.connections.service import namespaced
from tests.test_tool_disclosure import SchemaRecordingModel, call


def run_for(names, *, policy=None, mode="work"):
    return AgentRun(id="discovery-fixture", deployment_id="fixture", task="Use selected tools",
        enabled_tools=list(names), presented_tools=list(names), input_policy=policy or AgentInputPolicy(pinned_tools=[]),
        work_mode=mode, created_at="2026-10-03T00:00:00+00:00", updated_at="2026-10-03T00:00:00+00:00")


class SchemaLoader:
    def __init__(self, names, *, cold=False):
        self.effects = []
        self.loads = []

        async def navigate(url):
            self.effects.append(url)
            return "fixture navigation"

        self.actual = {name: StructuredTool(name=name, description=TOOL_PRESENTATIONS[name].description,
            args_schema={"type": "object", "properties": {}}) for name in names}
        if "browser_navigate" in names:
            self.actual["browser_navigate"] = StructuredTool.from_function(name="browser_navigate",
                description=TOOL_PRESENTATIONS["browser_navigate"].description, coroutine=navigate)
        self.definitions = {} if cold else self.actual.copy()

    def owns(self, name):
        return name in self.actual

    async def load(self, name):
        self.loads.append(name)
        return self.actual[name]


class DiscoveryMetadataTests(unittest.IsolatedAsyncioTestCase):
    def make_disclosure(self, *, names=BROWSER_TOOL_NAMES, policy=None, mode="work", cold=False):
        loader = SchemaLoader(names, cold=cold)
        run = run_for(["find_tools", *names], policy=policy, mode=mode)
        return ToolDisclosureMiddleware(run, loader=loader), loader

    async def search(self, disclosure, query, *, state=None, group="browser", cursor=None):
        result = await disclosure._find_tools(query, SimpleNamespace(state=state or {}, tool_call_id="search"), group=group, cursor=cursor)
        message = result.update["messages"][0]
        return result, json.loads(message.content) if message.status != "error" else message

    async def test_reported_task_queries_return_native_tool_in_first_batch(self):
        disclosure, _ = self.make_disclosure()
        for query, expected in (("Open URL in browser", "browser_navigate"), ("navigate to URL", "browser_navigate"),
            ("browser_scroll", "browser_mouse_wheel"), ("Scroll browser", "browser_mouse_wheel"),
            ("Page structure", "browser_snapshot")):
            with self.subTest(query=query):
                result, body = await self.search(disclosure, query)
                self.assertEqual(body["results"][0]["name"], expected)
                self.assertLessEqual(len(body["results"]), 5)
                self.assertIn(expected, result.update["disclosed_tools"])
                self.assertNotIn("browser_scroll", result.update["disclosed_tools"])

    async def test_every_advertised_browser_label_resolves_to_its_native_call(self):
        disclosure, _ = self.make_disclosure()
        index = selected_tools_index(BROWSER_TOOL_NAMES, input_policy=disclosure.run.input_policy)
        for name in BROWSER_TOOL_NAMES:
            label = TOOL_PRESENTATIONS[name].label
            with self.subTest(name=name, label=label):
                self.assertIn(f"{name} ({label})", index)
                _, body = await self.search(disclosure, label)
                self.assertEqual(body["results"][0]["name"], name)

    async def test_exact_label_can_load_cold_selected_schema_without_action(self):
        disclosure, loader = self.make_disclosure(names=("browser_navigate",), cold=True)
        result, body = await self.search(disclosure, "Open page")
        self.assertEqual([row["name"] for row in body["results"]], ["browser_navigate"])
        self.assertEqual(loader.loads, ["browser_navigate"])
        self.assertEqual(loader.effects, [])
        self.assertEqual(result.update["disclosed_tools"], ["browser_navigate"])

    async def test_exact_registered_alias_loads_cold_native_schema_and_revisits_it(self):
        for alias, name in (("browser_scroll", "browser_mouse_wheel"), ("open url", "browser_navigate")):
            with self.subTest(alias=alias):
                disclosure, loader = self.make_disclosure(names=(name,), cold=True)
                result, body = await self.search(disclosure, alias)
                self.assertEqual([row["name"] for row in body["results"]], [name])
                self.assertEqual(loader.loads, [name])
                self.assertEqual(loader.effects, [])
                _, body = await self.search(disclosure, alias, state={"disclosed_tools": result.update["disclosed_tools"]})
                self.assertEqual([row["name"] for row in body["results"]], [name])
                self.assertTrue(body["results"][0]["already_disclosed"])
                self.assertEqual(loader.loads, [name])

    async def test_cold_alias_lookup_preserves_group_mode_and_exclusion_boundaries(self):
        for policy, mode, group in (
            (AgentInputPolicy(pinned_tools=[], excluded_sources=["tool:browser_mouse_wheel"]), "work", "browser"),
            (None, "plan", "browser"), (None, "work", "project")):
            with self.subTest(mode=mode, group=group):
                disclosure, loader = self.make_disclosure(names=("browser_mouse_wheel",), policy=policy, mode=mode, cold=True)
                result, body = await self.search(disclosure, "browser_scroll", group=group)
                self.assertEqual(body["results"], [])
                self.assertEqual(result.update["disclosed_tools"], [])
                self.assertEqual(loader.loads, [])
                self.assertEqual(loader.effects, [])

    async def test_weak_alias_prose_can_rank_but_cannot_load_cold_schema(self):
        disclosure, loader = self.make_disclosure(names=("browser_mouse_wheel",), cold=True)
        result, body = await self.search(disclosure, "scroll the long page")
        self.assertEqual(body["results"], [])
        self.assertIn("browser_mouse_wheel: selected; schema unavailable until setup.", body["notice"])
        self.assertEqual(result.update["disclosed_tools"], [])
        self.assertEqual(loader.loads, [])
        self.assertEqual(loader.effects, [])

    async def test_exact_label_revisit_keeps_disclosed_schema_reachable(self):
        disclosure, _ = self.make_disclosure()
        state = {"disclosed_tools": list(BROWSER_TOOL_NAMES)}
        _, body = await self.search(disclosure, "Page structure", state=state)
        self.assertEqual([row["name"] for row in body["results"]], ["browser_snapshot"])
        self.assertTrue(body["results"][0]["already_disclosed"])

    async def test_success_descriptions_appear_once_without_search_alias_prose(self):
        disclosure, _ = self.make_disclosure()
        _, body = await self.search(disclosure, "browser_navigate")
        description = TOOL_PRESENTATIONS["browser_navigate"].description
        self.assertEqual(json.dumps(body).count(description), 1)
        self.assertEqual(body["results"][0]["description"], description)
        self.assertNotIn(description, body["notice"])
        self.assertIn("available", body["notice"])

    async def test_aliases_labels_groups_and_plan_never_expand_accepted_scope(self):
        cases = (
            (("browser_click",), None, "work", "Open URL in browser", "browser"),
            (BROWSER_TOOL_NAMES, AgentInputPolicy(pinned_tools=[], excluded_sources=["tool:browser_navigate"]), "work", "Open page", "browser"),
            (BROWSER_TOOL_NAMES, None, "work", "browser_scroll", "project"),
            (BROWSER_TOOL_NAMES, None, "plan", "Open page", "browser"),
        )
        for names, policy, mode, query, group in cases:
            with self.subTest(mode=mode, query=query, group=group):
                disclosure, loader = self.make_disclosure(names=names, policy=policy, mode=mode)
                result, body = await self.search(disclosure, query, group=group)
                self.assertNotIn("browser_navigate", result.update["disclosed_tools"])
                self.assertNotIn("browser_navigate", [row["name"] for row in body["results"]])
                self.assertEqual(loader.loads, [])
                self.assertEqual(loader.effects, [])

    async def test_cursor_reaches_selected_catalogue_and_rejects_changed_inputs(self):
        disclosure, loader = self.make_disclosure()
        state = {"disclosed_tools": []}
        first, body = await self.search(disclosure, "browser", state=state)
        cursor = body["next_cursor"]
        self.assertTrue(body["has_more"])
        rows = list(body["results"])
        state["disclosed_tools"] = first.update["disclosed_tools"]
        for _ in range(6):
            if not body["has_more"]:
                break
            result, body = await self.search(disclosure, "browser", state=state, cursor=body["next_cursor"])
            rows.extend(body["results"])
            state["disclosed_tools"] = result.update["disclosed_tools"]
        self.assertFalse(body["has_more"])
        self.assertEqual({row["name"] for row in rows}, set(BROWSER_TOOL_NAMES))
        self.assertEqual(len(rows), len(BROWSER_TOOL_NAMES))
        for query, group in (("Open page", "browser"), ("browser", "project")):
            _, message = await self.search(disclosure, query, group=group, cursor=cursor)
            self.assertEqual(message.status, "error")
        disclosure.run.input_policy.excluded_sources = ["tool:browser_navigate"]
        _, message = await self.search(disclosure, "browser", cursor=cursor)
        self.assertEqual(message.status, "error")
        self.assertEqual(loader.effects, [])

    async def test_unavailable_schema_notice_survives_description_deduplication(self):
        disclosure = ToolDisclosureMiddleware(run_for(["find_tools", "browser_navigate"]))
        result, body = await self.search(disclosure, "browser_navigate")
        self.assertEqual(body["results"], [])
        self.assertIn("browser_navigate: unavailable for this run.", body["notice"])
        self.assertEqual(result.update["disclosed_tools"], [])

    async def test_remote_operation_cannot_borrow_unselected_local_label(self):
        name = namespaced("docs", "browser_snapshot")
        descriptor = ConnectionTool(id=name, name=name, remote_name="browser_snapshot", description="Read remote graph.",
            input_schema={"type": "object", "properties": {}})
        run = run_for(["find_tools", name])
        run.connection_snapshots = [ConnectionSnapshot(id="docs", name="Documents", version=1, kind="mcp", transport="http", tools=[descriptor])]
        disclosure = ToolDisclosureMiddleware(run)
        disclosure._definitions[name] = StructuredTool(name=name, description=descriptor.description, args_schema=descriptor.input_schema)
        result, body = await self.search(disclosure, "Page structure", group="Documents")
        self.assertEqual(body["results"], [])
        self.assertEqual(result.update["disclosed_tools"], [])
        _, body = await self.search(disclosure, "browser_snapshot", group="Documents")
        self.assertEqual([row["name"] for row in body["results"]], [name])
        self.assertEqual(body["results"][0]["label"], "browser_snapshot")

    async def test_remote_operation_cannot_borrow_unselected_local_alias(self):
        name = namespaced("docs", "browser_mouse_wheel")
        descriptor = ConnectionTool(id=name, name=name, remote_name="browser_mouse_wheel", description="Read remote graph.",
            input_schema={"type": "object", "properties": {}})
        run = run_for(["find_tools", name])
        run.connection_snapshots = [ConnectionSnapshot(id="docs", name="Documents", version=1, kind="mcp", transport="http", tools=[descriptor])]
        disclosure = ToolDisclosureMiddleware(run)
        disclosure._definitions[name] = StructuredTool(name=name, description=descriptor.description, args_schema=descriptor.input_schema)
        result, body = await self.search(disclosure, "scroll", group="Documents")
        self.assertEqual(body["results"], [])
        self.assertEqual(result.update["disclosed_tools"], [])

    async def test_native_graph_offers_schema_after_discovery_with_original_call_name(self):
        SchemaRecordingModel.offered.clear()
        SchemaRecordingModel.schemas.clear()
        disclosure, loader = self.make_disclosure()
        graph = create_agent(SchemaRecordingModel([
            call("find_tools", {"query": "Open URL in browser", "group": "browser"}),
            call("browser_navigate", {"url": "https://fixture.test/"}), AIMessage(content="done")]), middleware=[disclosure])
        result = await graph.ainvoke({"messages": [{"role": "user", "content": "Open the fixture URL."}]})
        self.assertEqual(SchemaRecordingModel.offered[0], {"find_tools"})
        self.assertIn("browser_navigate", SchemaRecordingModel.offered[1])
        self.assertNotIn("browser_scroll", SchemaRecordingModel.offered[1])
        schema = next(row["function"] for row in SchemaRecordingModel.schemas[1] if row["function"]["name"] == "browser_navigate")
        self.assertIn("url", schema["parameters"]["properties"])
        self.assertEqual(loader.effects, ["https://fixture.test/"])
        self.assertEqual(result["messages"][-1].content, "done")


if __name__ == "__main__":
    unittest.main()
