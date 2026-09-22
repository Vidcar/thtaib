"""Real official MCP protocol conversion plus connection/credential boundaries."""
import asyncio
from contextlib import asynccontextmanager
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastmcp import FastMCP, Client
from fastmcp.client.elicitation import ElicitResult
from langchain.mcp import MCPAdapter
from langchain_core.tools import ToolException
from pydantic import ValidationError

from workbench_backend.connections.schemas import ConnectionWrite, ConnectionUpdate
from workbench_backend.connections.service import ConnectionService, namespaced
from workbench_backend.connections.public_web import PublicResolver, public_url, read_web_page, search_web
from workbench_backend.errors import HarnessError
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore


class MemoryVault:
    def __init__(self):
        self.values = {}
    def get(self, ref):
        return self.values.get(ref)
    def put(self, ref, value):
        self.values[ref] = value
    def remove(self, ref):
        self.values.pop(ref, None)


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ApplicationStore(WorkbenchPaths(Path(self.temp.name)))
        self.server = FastMCP("Test documentation")
        self.calls = []
        self.sessions = 0
        self.closed = 0
        self.mode = "auto"
        self.vault = MemoryVault()

        @self.server.tool
        async def read_file(query: str) -> dict:
            """Find a documentation passage, despite a local-tool-looking name."""
            self.calls.append(query)
            return {"passage": "receipt:" + query}

        @self.server.tool
        async def fails(query: str) -> str:
            """Return an actual MCP tool error."""
            raise ValueError("fixture remote rejection")

        @asynccontextmanager
        async def factory(record, unsupported):
            self.sessions += 1
            async def decline(message, response_type, params, context):
                unsupported.append("Unsupported MCP input was declined.")
                return ElicitResult(action="decline")
            async with MCPAdapter(Client(self.server, elicitation_handler=decline, mode=self.mode)) as adapter:
                try:
                    yield adapter
                finally:
                    self.closed += 1
        self.service = ConnectionService(self.store, vault=self.vault, adapter_factory=factory)
        self.record = self.service.create(ConnectionWrite(name="Docs", kind="mcp", transport="http", url="https://example.test/mcp"))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    async def run_record(self):
        tested = await self.service.test(self.record.id)
        self.assertIsNone(tested.last_error)
        return SimpleNamespace(id="run_connections", connection_snapshots=self.service.snapshot([tested.id]), presented_tools=[tool.name for tool in tested.tools])

    async def test_real_adapter_namespaces_schema_result_error_and_session_lifetime(self):
        run = await self.run_record()
        self.assertTrue(all(t.name != t.remote_name for t in run.connection_snapshots[0].tools))
        self.assertTrue(any(t.output_schema for t in run.connection_snapshots[0].tools))
        before = self.closed
        async with self.service.open_tools(run) as tools:
            lookup = {tool.metadata["remote_tool"]: tool for tool in tools}
            result = await lookup["read_file"].ainvoke({"name": lookup["read_file"].name, "args": {"query": "live"}, "id": "actual-call-1", "type": "tool_call"})
            self.assertEqual(result.tool_call_id, "actual-call-1")
            self.assertEqual(result.status, "success")
            self.assertIn("receipt:live", json.dumps(result.content))
            failed = await lookup["fails"].ainvoke({"name": lookup["fails"].name, "args": {"query": "x"}, "id": "actual-call-2", "type": "tool_call"})
            self.assertEqual(failed.status, "error")
            self.assertEqual(failed.tool_call_id, "actual-call-2")
            self.assertEqual(self.closed, before)
        self.assertEqual(self.closed, before + 1)
        self.assertEqual(self.calls, ["live"])
        self.assertEqual(self.store.list_effects(run_id=run.id, unresolved_only=True), [])

    async def test_tools_off_and_unselected_never_open_session(self):
        self.assertEqual(self.service.snapshot(["missing"], tools_enabled=False), [])
        async with self.service.open_tools(SimpleNamespace(connection_snapshots=[], presented_tools=[])) as tools:
            self.assertEqual(tools, [])
        self.assertEqual(self.sessions, 0)

    async def test_availability_matches_snapshot_readiness_without_opening_session(self):
        self.assertFalse(self.service.available(self.record.id))
        with self.assertRaises(HarnessError):
            self.service.snapshot([self.record.id])
        tested = await self.service.test(self.record.id)
        sessions = self.sessions
        self.assertTrue(self.service.available(tested.id))
        self.assertEqual(len(self.service.snapshot([tested.id])), 1)
        executable = Path(self.temp.name) / 'fixture.exe'
        executable.write_bytes(b'fixture; never executed')
        for changed in [
            {'last_error': 'Connection test failed'},
            {'last_tested_at': None},
            {'tools': []},
            {'credential_ref': 'missing-token'},
            {'enabled': False},
            {'transport': 'stdio', 'command': str(executable.with_name('removed.exe'))},
        ]:
            with self.subTest(changed=changed):
                self.service.store.put(tested.model_copy(update=changed))
                self.assertFalse(self.service.available(tested.id))
                with self.assertRaises(HarnessError):
                    self.service.snapshot([tested.id])
        self.service.store.put(tested.model_copy(update={'transport': 'stdio', 'command': str(executable)}))
        self.assertTrue(self.service.available(tested.id))
        self.assertEqual(self.sessions, sessions)

    async def test_distinct_remote_names_keep_distinct_native_dispatch(self):
        # These actual remote names collided with the previous 32-bit suffix.
        first_name = "shared_documentation_operation_32733"
        second_name = "shared_documentation_operation_46954"

        @self.server.tool(name=first_name)
        async def first(query: str) -> str:
            """Read the first independent document."""
            self.calls.append("first:" + query)
            return "first document"

        @self.server.tool(name=second_name)
        async def second(query: str) -> str:
            """Read the second independent document."""
            self.calls.append("second:" + query)
            return "second document"

        run = await self.run_record()
        descriptors = {tool.remote_name: tool for tool in run.connection_snapshots[0].tools}
        self.assertNotEqual(descriptors[first_name].name, descriptors[second_name].name)
        self.assertTrue(all(len(tool.name) <= 64 for tool in descriptors.values()))
        async with self.service.open_tools(run) as tools:
            # Native dispatch uses the generated name as its unique lookup key.
            from langgraph.prebuilt import ToolNode
            node = ToolNode(tools)
            for remote, receipt in ((first_name, "first document"), (second_name, "second document")):
                name = descriptors[remote].name
                result = await node.tools_by_name[name].ainvoke({
                    "name": name, "args": {"query": "exact"},
                    "id": remote, "type": "tool_call",
                })
                self.assertEqual(result.status, "success")
                self.assertIn(receipt, str(result.content))
        self.assertEqual(self.calls, ["first:exact", "second:exact"])

    async def test_generated_name_collision_rejects_catalogue(self):
        with patch("workbench_backend.connections.service.namespaced", return_value="cx_collision"):
            tested = await self.service.test(self.record.id)
        self.assertIn("duplicate", tested.last_error)
        self.assertEqual(tested.tools, [])
        with self.assertRaisesRegex(HarnessError, "Test Docs"):
            self.service.snapshot([tested.id])
        self.assertEqual(self.calls, [])

    async def test_parallel_model_calls_wait_for_in_flight_receipt(self):
        entered, release = asyncio.Event(), asyncio.Event()
        @self.server.tool
        async def slow_read(query: str) -> str:
            """Hold one real MCP response while another model call is submitted."""
            entered.set()
            await release.wait()
            return "first receipt"
        run = await self.run_record()
        async with self.service.open_tools(run) as tools:
            lookup = {tool.metadata["remote_tool"]: tool for tool in tools}
            first = asyncio.create_task(lookup["slow_read"].ainvoke({"query": "first"}))
            second = None
            try:
                await asyncio.wait_for(entered.wait(), 5)
                second = asyncio.create_task(lookup["read_file"].ainvoke({"query": "second"}))
                done, _ = await asyncio.wait({second}, timeout=0.1)
                self.assertEqual(done, set(), "The second call should await the first receipt")
                self.assertEqual(self.calls, [])
                release.set()
                results = await asyncio.wait_for(asyncio.gather(first, second), 5)
                self.assertIn("first receipt", str(results[0]))
                self.assertIn("receipt:second", str(results[1]))
            finally:
                release.set()
                await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
        self.assertEqual(self.calls, ["second"])
        self.assertEqual(self.store.list_effects(run_id=run.id, unresolved_only=True), [])

    async def test_unsupported_elicitation_is_declined_and_visible_as_tool_error(self):
        self.mode = "legacy"
        from fastmcp import Context
        @self.server.tool
        async def need_input(ctx: Context) -> str:
            """Request typed user input."""
            response = await ctx.elicit("Choose a value", str)
            self.calls.append(response.action)
            return "Server received " + response.action
        run = await self.run_record()
        async with self.service.open_tools(run) as tools:
            tool = next(t for t in tools if t.metadata["remote_tool"] == "need_input")
            message = await tool.ainvoke({"name": tool.name, "id": "elicit-call", "type": "tool_call", "args": {}})
            self.assertEqual(message.status, "error")
            self.assertIn("declined", str(message.content))
        self.assertEqual(self.calls, ["decline"])

    async def test_disconnected_or_changed_after_selection_denies_dispatch(self):
        run = await self.run_record()
        async with self.service.open_tools(run) as tools:
            self.service.disconnect(self.record.id)
            with self.assertRaisesRegex(HarnessError, "disconnected"):
                await tools[0].ainvoke({"query": "must not run"})
        self.assertEqual(self.calls, [])
        with self.assertRaises(HarnessError):
            async with self.service.open_tools(run):
                self.fail("disconnected connection opened")

    async def test_cancel_in_flight_closes_session_and_keeps_unknown_effect(self):
        entered = asyncio.Event()
        released = asyncio.Event()
        @self.server.tool
        async def wait_for_cancel(query: str) -> str:
            """Wait until the request is cancelled."""
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                released.set()
        run = await self.run_record()
        before = self.closed
        async def invoke():
            async with self.service.open_tools(run) as tools:
                tool = next(t for t in tools if t.metadata["remote_tool"] == "wait_for_cancel")
                await tool.ainvoke({"query": "cancel"})
        task = asyncio.create_task(invoke())
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        await asyncio.wait_for(released.wait(), 5)
        self.assertEqual(self.closed, before + 1)
        effects = self.store.list_effects(run_id=run.id, unresolved_only=True)
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].outcome.value, "unknown")

    async def test_credential_values_stay_outside_records_and_destination_rebind(self):
        updated = self.service.replace_credential(self.record.id, "private-access-token")
        self.assertTrue(updated.credential_present)
        self.assertNotIn("private-access-token", self.store.path.read_bytes().decode("utf-8", errors="ignore"))
        self.assertNotIn("private-access-token", updated.model_dump_json())
        with self.assertRaisesRegex(HarnessError, "Remove"):
            self.service.update(updated.id, ConnectionUpdate(name="New", kind="mcp", transport="http", url="https://other.test/mcp", expected_version=updated.version))
        await self.service.test(updated.id)
        snapshot = self.service.snapshot([updated.id])[0]
        self.vault.remove(snapshot.credential_ref)
        with self.assertRaisesRegex(HarnessError, "missing access token"):
            self.service._revalidate(snapshot)
        self.service.remove_credential(updated.id)
        self.assertFalse(self.service.get(updated.id).credential_present)

    async def test_update_conflict_and_protocol_schema_drift_fail_closed(self):
        run = await self.run_record()
        @self.server.tool
        async def surprise(value: str) -> str:
            """A newly added remote tool."""
            return value
        with self.assertRaisesRegex(HarnessError, "tools.*changed"):
            async with self.service.open_tools(run):
                self.fail("schema drift admitted")
        current = self.service.get(self.record.id)
        with self.assertRaisesRegex(HarnessError, "Refresh"):
            self.service.update(current.id, ConnectionUpdate(name="old", kind="mcp", transport="http", url=current.url, expected_version=1))

    async def test_transport_failure_records_unknown_outcome_without_replay(self):
        run = await self.run_record()
        @asynccontextmanager
        async def broken(record, unsupported):
            class Adapter:
                client = SimpleNamespace(list_tools=self._protocol)
                async def list_tools(inner):
                    from langchain_core.tools import StructuredTool
                    async def fail(**args):
                        self.calls.append("dispatched")
                        raise OSError("Authorization: private-secret")
                    return [StructuredTool(name=t.remote_name, description=t.description, args_schema=t.input_schema, coroutine=fail) for t in run.connection_snapshots[0].tools]
            yield Adapter()
        async def protocol():
            return [SimpleNamespace(name=t.remote_name, output_schema=t.output_schema) for t in run.connection_snapshots[0].tools]
        self._protocol = protocol
        self.service.adapter_factory = broken
        async with self.service.open_tools(run) as tools:
            with self.assertRaisesRegex(HarnessError, "outcome may be unknown") as caught:
                await tools[0].ainvoke({"query": "q"})
            self.assertNotIn("private-secret", str(caught.exception))
            with self.assertRaisesRegex(HarnessError, "earlier external call"):
                await tools[0].ainvoke({"query": "q"})
        self.assertEqual(self.calls, ["dispatched"])
        self.assertEqual(len(self.store.list_effects(run_id=run.id, unresolved_only=True)), 1)

    def test_paths_do_not_launch_from_network_field_and_names_do_not_collide(self):
        for url in ["C:/fake/server.py", "file:///server.py", "https://token@example.com/mcp", "https://example.com/mcp?token=secret"]:
            with self.assertRaises(ValidationError):
                ConnectionWrite(name="Bad", kind="mcp", transport="http", url=url)
        self.assertNotEqual(namespaced("connection_one", "a-b"), namespaced("connection_one", "a_b"))
        self.assertNotEqual(namespaced("connection_one", "read_file"), namespaced("connection_two", "read_file"))


class PublicWebTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_literal_and_dns_resolution_are_blocked(self):
        for url in ["http://127.0.0.1/", "http://[::1]/", "http://192.168.1.1/", "http://localhost/", "file:///x", "https://public.example:8080/", "https://user:password@example.com/"]:
            with self.assertRaises(ToolException):
                public_url(url)
        resolver = PublicResolver()
        async def private(*args):
            return [{"host": "10.1.2.3"}]
        with patch.object(resolver.resolver, "resolve", side_effect=private):
            with self.assertRaises(OSError):
                await resolver.resolve("public-looking.example", 443)
        await resolver.close()

    async def test_search_uses_one_explicit_provider_and_does_not_claim_page_text(self):
        with patch("workbench_backend.connections.public_web.DDGS") as provider:
            provider.return_value.text.return_value = [{"title": "Title", "href": "https://example.com", "body": "Snippet"}]
            result = await search_web("my query", 2)
            provider.return_value.text.assert_called_once_with("my query", backend="brave", max_results=2)
            self.assertEqual(result["kind"], "search_results")
            self.assertEqual(result["results"][0]["snippet"], "Snippet")
            self.assertNotIn("content", result)
        with patch("workbench_backend.connections.public_web.DDGS", side_effect=OSError("rate limited")):
            with self.assertRaisesRegex(ToolException, "no other provider"):
                await search_web("query")
