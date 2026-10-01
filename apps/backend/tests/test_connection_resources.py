"""Real pinned MCP client resource protocol and selected-owner boundaries."""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastmcp import Client, FastMCP
from langchain.mcp import MCPAdapter
from mcp.server.mcpserver import MCPServer
from pydantic import ValidationError
from workbench_backend.agents.harness_presentation import load_connection_snapshots
from workbench_backend.agents.setup_schemas import AgentInputPolicy
from workbench_backend.agents.tool_disclosure import compact_tool, input_tool_schemas
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.agents.tool_results import OwnedToolResults
from workbench_backend.connections.resources import connection_resource_tools, MAX_RESOURCE_BYTES, MAX_OUTPUT_BYTES, _encode_cursor
from workbench_backend.connections.schemas import ConnectionSnapshot, ConnectionWrite
from workbench_backend.connections.service import ConnectionService
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore


class ConnectionResourceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.area = TemporaryDirectory()
        self.addCleanup(self.area.cleanup)
        self.paths = WorkbenchPaths(Path(self.area.name) / "data")
        self.server = FastMCP("audit resources")
        @self.server.resource("audit://long")
        def long_resource():
            return "café " * 5_000 + "LATE_EVIDENCE"
        for index in range(7):
            self.server.resource(f"audit://item{index}", name=f"item{index}")(lambda: "bounded reference data")
        self.snapshot = ConnectionSnapshot(id="selected-mcp", name="audit fixture", version=1, kind="mcp", transport="stdio")
        self.run = AgentRun(id="resource-run", deployment_id="fixture", task="Read selected resources", thread_id="resource-owner",
            connection_snapshots=[self.snapshot], enabled_tools=["list_connection_resources", "read_connection_resource"],
            presented_tools=["list_connection_resources", "read_connection_resource"], created_at="2026-10-01T00:00:00Z", updated_at="2026-10-01T00:00:00Z")
        self.active = True
        self.opens = 0
        @asynccontextmanager
        async def adapter(record, unsupported):
            self.opens += 1
            async with Client(self.server) as client:
                yield SimpleNamespace(client=client)
        def revalidate(snapshot):
            if not self.active:
                raise HarnessError("Connection revoked", code="connection_disabled", status_code=403)
            if snapshot.version != self.snapshot.version:
                raise HarnessError("Connection changed", code="connection_changed", status_code=409)
            return self.snapshot
        self.service = SimpleNamespace(application=SimpleNamespace(paths=self.paths), _adapter=adapter, _revalidate=revalidate)
        self.tools = {tool.name: tool for tool in connection_resource_tools(self.service, self.run)}

    async def test_frozen_selected_ids_names_and_versions_survive_compact_and_cold_schema_projection(self):
        # Resource-only selections have no remote tool manifest from which a
        # model could infer the owner ID.
        self.assertEqual(self.snapshot.tools, [])
        self.snapshot.credential_ref = "private-vault-identity"
        projected = input_tool_schemas(list(self.tools), extra_tools=list(self.tools.values()))
        for name, operation in self.tools.items():
            schema = compact_tool(operation).args_schema
            field = schema["properties"]["connection_id"]
            self.assertEqual(field.get("enum", [field.get("const")]), ["selected-mcp"])
            self.assertIn("audit fixture", field["description"])
            self.assertIn("version 1", field["description"])
            self.assertNotIn("private-vault", json.dumps(schema))
            self.assertNotIn("unselected", json.dumps(schema))
            self.assertIn("selected-mcp", json.dumps(projected[name]))
        self.snapshot.name = "Renamed after acceptance"
        self.snapshot.version = 2
        self.assertIn("audit fixture", self.tools["list_connection_resources"].args_schema.model_json_schema()["properties"]["connection_id"]["description"])
        with self.assertRaises(HarnessError):
            await self.tools["list_connection_resources"].ainvoke({"connection_id":self.snapshot.id})
        self.assertEqual(self.opens, 0)

    async def test_real_native_resource_pages_reach_all_matches_and_bind_version(self):
        operation = self.tools["list_connection_resources"]
        cursor, names = None, []
        while True:
            result = json.loads(await operation.ainvoke({"connection_id": self.snapshot.id, "cursor": cursor, "limit": 2}))
            names.extend(item["uri"] for item in result["resources"])
            cursor = result["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(len(names), 8)
        self.assertEqual(len(set(names)), 8)
        first = json.loads(await operation.ainvoke({"connection_id": self.snapshot.id, "limit": 2}))
        self.snapshot.version += 1
        with self.assertRaises(HarnessError):
            await operation.ainvoke({"connection_id": self.snapshot.id, "cursor": first["next_cursor"]})

    async def test_real_resource_text_retains_late_evidence_and_owner_isolation(self):
        result = json.loads(await self.tools["read_connection_resource"].ainvoke({"connection_id": self.snapshot.id, "uri": "audit://long"}))
        item = result["contents"][0]
        self.assertFalse(item["preview_complete"])
        self.assertNotIn("LATE_EVIDENCE", item["preview"])
        retained = OwnedToolResults(self.paths, self.run).read(item["result_path"], query="LATE_EVIDENCE")
        self.assertIn("LATE_EVIDENCE", retained["matches"][0]["content"])
        self.assertEqual(retained["result"]["source"]["uri"], "audit://long")
        other = self.run.model_copy(update={"thread_id": "another-owner"})
        with self.assertRaises(Exception):
            OwnedToolResults(self.paths, other).read(item["result_path"])

    async def test_actual_native_binary_resource_is_explicitly_unsupported(self):
        @self.server.resource("audit://binary", mime_type="application/octet-stream")
        def binary_resource():
            return b"\x00\xffprivate-binary-body"
        output = await self.tools["read_connection_resource"].ainvoke({"connection_id":self.snapshot.id,"uri":"audit://binary"})
        result = json.loads(output)
        self.assertEqual(result["contents"][0]["status"], "binary_not_supported")
        self.assertEqual(result["acquired_text_bytes"], 0)
        self.assertNotIn("private-binary-body", output)
        self.assertNotIn("result_path", result["contents"][0])
        self.assertLessEqual(len(output.encode("utf-8")), MAX_OUTPUT_BYTES)

    async def test_actual_native_utf8_acquisition_bound_rejects_before_any_retention(self):
        @self.server.resource("audit://oversize")
        def oversize_resource():
            return "😀" * (MAX_RESOURCE_BYTES // 4 + 1)
        with patch.object(OwnedToolResults, "retain", side_effect=AssertionError("Oversize acquisition must retain nothing")):
            output = await self.tools["read_connection_resource"].ainvoke({"connection_id":self.snapshot.id,"uri":"audit://oversize"})
        self.assertIn("resource_size_limit", output)
        self.assertIn("no complete result", output)
        self.assertNotIn("result_path", output)
        # A handled read-only input error must not poison the next valid read.
        valid = json.loads(await self.tools["read_connection_resource"].ainvoke({"connection_id":self.snapshot.id,"uri":"audit://long"}))
        self.assertEqual(valid["contents"][0]["acquired_utf8_bytes"], len(("café "*5000+"LATE_EVIDENCE").encode("utf-8")))
        self.assertLessEqual(len(json.dumps(valid,ensure_ascii=False).encode("utf-8")), MAX_OUTPUT_BYTES)

    async def test_actual_native_utf8_exact_acquisition_bound_is_complete_and_retrievable(self):
        text = "😀" * (MAX_RESOURCE_BYTES // 4 - 1) + "LAST"
        self.assertEqual(len(text.encode("utf-8")), MAX_RESOURCE_BYTES)
        @self.server.resource("audit://boundary")
        def boundary_resource():
            return text
        output = await self.tools["read_connection_resource"].ainvoke({"connection_id":self.snapshot.id,"uri":"audit://boundary"})
        result = json.loads(output)
        self.assertEqual(result["acquired_text_bytes"], MAX_RESOURCE_BYTES)
        self.assertFalse(result["contents"][0]["preview_complete"])
        retained = OwnedToolResults(self.paths, self.run).read(result["contents"][0]["result_path"], query="LAST")
        self.assertIn("LAST", retained["matches"][0]["content"])
        self.assertTrue(retained["result"]["complete"])
        self.assertLessEqual(len(output.encode("utf-8")), MAX_OUTPUT_BYTES)

    async def test_native_post_read_revocation_and_version_changes_fail_closed_before_retention(self):
        @self.server.resource("audit://revoke")
        def revoke_resource():
            self.active = False
            return "Contents acquired after revoked authority"
        @self.server.resource("audit://change")
        def change_resource():
            self.snapshot.version += 1
            return "Contents acquired from changed authority"
        for uri, code in [("audit://revoke", "connection_disabled"), ("audit://change", "connection_changed")]:
            self.active = True
            with patch.object(OwnedToolResults, "retain", side_effect=AssertionError("Changed authority must retain nothing")):
                with self.assertRaises(HarnessError) as raised:
                    await self.tools["read_connection_resource"].ainvoke({"connection_id":self.snapshot.id,"uri":uri})
            self.assertEqual(raised.exception.code, code)

    async def test_native_unknown_resource_and_invalid_cursors_are_handled_inputs(self):
        read = self.tools["read_connection_resource"]
        missing = await read.ainvoke({"connection_id":self.snapshot.id,"uri":"audit://missing"})
        self.assertIn("resource_read_failed", missing)
        listing = self.tools["list_connection_resources"]
        opened = self.opens
        for cursor in ["not-json", _encode_cursor([]), _encode_cursor({"binding":"different-run","offset":0,"page":None})]:
            output = await listing.ainvoke({"connection_id":self.snapshot.id,"cursor":cursor})
            self.assertIn("resource_cursor_invalid", output)
        self.assertEqual(self.opens, opened)
        valid = json.loads(await listing.ainvoke({"connection_id":self.snapshot.id,"limit":1}))
        self.assertEqual(len(valid["resources"]), 1)

    async def test_deselection_plan_revocation_fail_before_adapter_call(self):
        operation = self.tools["list_connection_resources"]
        with self.assertRaises(ValidationError):
            await operation.ainvoke({"connection_id": "unselected"})
        # Runtime checks remain authoritative even if a caller bypasses schema
        # validation rather than inventing a model-visible choice.
        with self.assertRaises(HarnessError):
            await operation.coroutine(connection_id="unselected")
        self.run.work_mode = "plan"
        with self.assertRaises(HarnessError):
            await operation.ainvoke({"connection_id": self.snapshot.id})
        self.run.work_mode = "work"
        self.active = False
        with self.assertRaises(HarnessError):
            await operation.ainvoke({"connection_id": self.snapshot.id})
        self.assertEqual(self.opens, 0)


class ConnectionCapabilityAdmissionTests(unittest.IsolatedAsyncioTestCase):
    """Resource readiness follows a real test, not an empty or missing tool list."""

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ApplicationStore(WorkbenchPaths(Path(self.temp.name)))
        self.addCleanup(self.store.close)

    def _service(self, server):
        @asynccontextmanager
        async def factory(_record, _unsupported):
            async with MCPAdapter(Client(server)) as adapter:
                yield adapter
        return ConnectionService(self.store, adapter_factory=factory)

    def _create(self, service, name):
        return service.create(ConnectionWrite(name=name, kind="mcp", transport="http", url="https://example.test/mcp"))

    def _admit(self, service, connection_id, loading):
        request = SimpleNamespace(
            connection_ids=[connection_id],
            presented_tools=["list_connection_resources", "read_connection_resource", "read_tool_result"],
            input_policy=AgentInputPolicy(tool_loading=loading),
        )
        return load_connection_snapshots(SimpleNamespace(connections=service), request, request.input_policy, SimpleNamespace())

    def _run(self, snapshots):
        return AgentRun(
            id="resource-admission", deployment_id="fixture", task="Read the selected resource",
            thread_id="resource-owner", connection_ids=[item.id for item in snapshots], connection_snapshots=snapshots,
            enabled_tools=["list_connection_resources", "read_connection_resource", "read_tool_result"],
            presented_tools=["list_connection_resources", "read_connection_resource", "read_tool_result"],
            work_mode="work", created_at=utc_now(), updated_at=utc_now())

    async def test_resource_only_connection_is_ready_in_both_loading_modes(self):
        server = FastMCP("resource only")
        @server.resource("audit://note")
        def note():
            return ("n" * 9000) + "LATE_MARKER"
        service = self._service(server)
        created = self._create(service, "Resource only")
        tested = await service.test(created.id)
        self.assertIsNone(tested.last_error)
        self.assertEqual(tested.tools, [])
        self.assertEqual(tested.protocol_capabilities, ["tools", "resources"])
        reloaded = ConnectionService(self.store, adapter_factory=service.adapter_factory).get(tested.id)
        self.assertEqual(reloaded.tools, [])
        self.assertEqual(reloaded.protocol_capabilities, ["tools", "resources"])

        for loading in ("always", "when_needed"):
            snapshots, external = self._admit(service, tested.id, loading)
            self.assertEqual(external, [])
            self.assertEqual([item.id for item in snapshots], [tested.id])
            self.assertEqual(snapshots[0].tools, [])

        run = self._run(self._admit(service, tested.id, "always")[0])
        tools = {tool.name: tool for tool in connection_resource_tools(service, run)}
        listing = json.loads(await tools["list_connection_resources"].ainvoke({"connection_id": tested.id}))
        self.assertEqual([item["uri"] for item in listing["resources"]], ["audit://note"])
        read = json.loads(await tools["read_connection_resource"].ainvoke({"connection_id": tested.id, "uri": "audit://note"}))
        retained_path = read["contents"][0]["result_path"]
        self.assertNotIn("LATE_MARKER", read["contents"][0]["preview"])
        found = OwnedToolResults(service.application.paths, run).read(retained_path, query="LATE_MARKER")
        self.assertGreaterEqual(found["match_count"], 1)
        self.assertIn("LATE_MARKER", found["matches"][0]["content"])
        self.assertIn("read_tool_result", found["result"]["notice"])

        current = service.get(tested.id)
        service.store.put(current.model_copy(update={"version": current.version + 1}), expected_version=current.version)
        with self.assertRaises(HarnessError) as changed:
            await tools["list_connection_resources"].ainvoke({"connection_id": tested.id})
        self.assertEqual(changed.exception.code, "connection_changed")
        service.disconnect(tested.id)
        with self.assertRaises(HarnessError) as revoked:
            await tools["list_connection_resources"].ainvoke({"connection_id": tested.id})
        self.assertEqual(revoked.exception.code, "connection_disabled")

    async def test_empty_mixed_unsupported_and_failed_manifests_stay_distinct(self):
        empty = self._service(FastMCP("empty"))
        empty_record = await empty.test(self._create(empty, "Empty manifest").id)
        self.assertIsNone(empty_record.last_error)
        self.assertEqual(empty_record.tools, [])
        self.assertEqual(empty_record.protocol_capabilities, ["tools", "resources"])
        self.assertTrue(empty.available(empty_record.id))
        empty_run = self._run(self._admit(empty, empty_record.id, "when_needed")[0])
        empty_list = json.loads(await connection_resource_tools(empty, empty_run)[0].ainvoke({"connection_id": empty_record.id}))
        self.assertEqual(empty_list["resources"], [])

        mixed_server = FastMCP("mixed")
        @mixed_server.tool
        def ping() -> str:
            """Return a fixed ping."""
            return "pong"
        @mixed_server.resource("audit://mixed")
        def mixed_note():
            return "MIXED_NOTE"
        mixed = self._service(mixed_server)
        mixed_record = await mixed.test(self._create(mixed, "Mixed").id)
        self.assertEqual(mixed_record.protocol_capabilities, ["tools", "resources"])
        self.assertEqual([tool.remote_name for tool in mixed_record.tools], ["ping"])
        self.assertNotEqual(mixed_record.tools[0].name, "ping")
        mixed_run = self._run(self._admit(mixed, mixed_record.id, "always")[0])
        mixed_tools = {tool.name: tool for tool in connection_resource_tools(mixed, mixed_run)}
        mixed_read = json.loads(await mixed_tools["read_connection_resource"].ainvoke({"connection_id": mixed_record.id, "uri": "audit://mixed"}))
        self.assertIn("MIXED_NOTE", mixed_read["contents"][0]["preview"])
        self.assertEqual(len(mixed.get(mixed_record.id).tools), 1)

        tools_only = MCPServer(name="tools only")
        @tools_only.tool()
        def echo_note(text: str) -> str:
            """Return the note."""
            return text
        for method in ("resources/list", "resources/read", "resources/templates/list"):
            tools_only._lowlevel_server._request_handlers.pop(method, None)
        unsupported = self._service(tools_only)
        unsupported_record = await unsupported.test(self._create(unsupported, "Tools only").id)
        self.assertIsNone(unsupported_record.last_error, unsupported_record.last_error)
        self.assertEqual(unsupported_record.protocol_capabilities, ["tools"])
        self.assertEqual([tool.remote_name for tool in unsupported_record.tools], ["echo_note"])
        with self.assertRaises(HarnessError) as unsupported_error:
            unsupported.require_resource_capability(unsupported.get(unsupported_record.id))
        self.assertEqual(unsupported_error.exception.code, "resources_unsupported")
        unsupported_run = self._run(self._admit(unsupported, unsupported_record.id, "always")[0])
        with self.assertRaises(HarnessError) as listed:
            await connection_resource_tools(unsupported, unsupported_run)[0].ainvoke({"connection_id": unsupported_record.id})
        self.assertEqual(listed.exception.code, "resources_unsupported")

        @asynccontextmanager
        async def failing(_record, _unsupported):
            raise RuntimeError("fixture down")
            yield None
        failed = ConnectionService(self.store, adapter_factory=failing)
        failed_record = await failed.test(self._create(failed, "Down").id)
        self.assertIn("Could not connect", failed_record.last_error)
        self.assertNotIn("fixture down", failed_record.last_error)
        self.assertEqual(failed_record.protocol_capabilities, [])
        self.assertFalse(failed.available(failed_record.id))
        with self.assertRaises(HarnessError) as readiness:
            failed.snapshot([failed_record.id])
        self.assertEqual(readiness.exception.code, "connection_test_required")

        untested = self._create(empty, "Not tested")
        deferred, _external = self._admit(empty, untested.id, "when_needed")
        self.assertEqual(deferred[0].tools, [])
        with self.assertRaises(HarnessError) as eager:
            self._admit(empty, untested.id, "always")
        self.assertEqual(eager.exception.code, "connection_test_required")
        untested_run = self._run(deferred)
        with self.assertRaises(HarnessError) as not_ready:
            await connection_resource_tools(empty, untested_run)[0].ainvoke({"connection_id": untested.id})
        self.assertEqual(not_ready.exception.code, "connection_test_required")

    async def test_server_without_tools_list_is_ready_for_resources_only(self):
        server = MCPServer(name="resources only")
        @server.resource("audit://note")
        def note() -> str:
            """Return a retained note."""
            return ("n" * 9000) + "LATE_MARKER"
        for method in ("tools/list", "tools/call"):
            server._lowlevel_server._request_handlers.pop(method, None)
        service = self._service(server)
        created = self._create(service, "Resources without tools")
        tested = await service.test(created.id)
        self.assertIsNone(tested.last_error, tested.last_error)
        self.assertEqual(tested.tools, [])
        self.assertEqual(tested.protocol_capabilities, ["resources"])
        reloaded = ConnectionService(self.store, adapter_factory=service.adapter_factory).get(tested.id)
        self.assertEqual(reloaded.tools, [])
        self.assertEqual(reloaded.protocol_capabilities, ["resources"])
        self.assertTrue(service.available(tested.id))

        for loading in ("always", "when_needed"):
            snapshots, external = self._admit(service, tested.id, loading)
            self.assertEqual(external, [])
            self.assertEqual(snapshots[0].tools, [])
            self.assertEqual(service.get(tested.id).protocol_capabilities, ["resources"])

        run = self._run(self._admit(service, tested.id, "when_needed")[0])
        tools = {tool.name: tool for tool in connection_resource_tools(service, run)}
        listing = json.loads(await tools["list_connection_resources"].ainvoke({"connection_id": tested.id}))
        self.assertEqual([item["uri"] for item in listing["resources"]], ["audit://note"])
        read = json.loads(await tools["read_connection_resource"].ainvoke({"connection_id": tested.id, "uri": "audit://note"}))
        retained_path = read["contents"][0]["result_path"]
        self.assertNotIn("LATE_MARKER", read["contents"][0]["preview"])
        found = OwnedToolResults(service.application.paths, run).read(retained_path, query="LATE_MARKER")
        self.assertIn("LATE_MARKER", found["matches"][0]["content"])
        self.assertIn("read_tool_result", found["result"]["notice"])

        current = service.get(tested.id)
        service.store.put(current.model_copy(update={"version": current.version + 1}), expected_version=current.version)
        with self.assertRaises(HarnessError) as changed:
            await tools["list_connection_resources"].ainvoke({"connection_id": tested.id})
        self.assertEqual(changed.exception.code, "connection_changed")

    async def test_advertised_capability_failures_are_not_inferred_from_error_text(self):
        from mcp import MCPError
        from mcp_types import METHOD_NOT_FOUND

        class Client:
            def __init__(self, *, tools, resources, error):
                self.server_capabilities = SimpleNamespace(tools=tools, resources=resources)
                self.error = error
                self.tool_calls = 0
            async def list_tools(self):
                self.tool_calls += 1
                raise self.error
            async def list_resources_mcp(self):
                raise self.error

        def service_for(client):
            @asynccontextmanager
            async def factory(_record, _unsupported):
                yield SimpleNamespace(client=client, list_tools=client.list_tools)
            return ConnectionService(self.store, adapter_factory=factory)

        missing = Client(tools=object(), resources=None, error=MCPError(METHOD_NOT_FOUND, "Method not found"))
        missing_service = service_for(missing)
        missing_record = await missing_service.test(self._create(missing_service, "Advertised tools missing").id)
        self.assertIn("tools/list", missing_record.last_error)
        self.assertEqual(missing_record.protocol_capabilities, [])
        self.assertFalse(missing_service.available(missing_record.id))
        self.assertGreaterEqual(missing.tool_calls, 1)

        text = Client(tools=object(), resources=None, error=RuntimeError("method not found"))
        text_service = service_for(text)
        text_record = await text_service.test(self._create(text_service, "Unrelated method text").id)
        self.assertIn("Could not connect", text_record.last_error)
        self.assertNotIn("method not found", text_record.last_error)
        self.assertEqual(text_record.protocol_capabilities, [])

        resources = Client(tools=None, resources=object(), error=MCPError(METHOD_NOT_FOUND, "Method not found"))
        resource_service = service_for(resources)
        resource_record = await resource_service.test(self._create(resource_service, "Advertised resources missing").id)
        self.assertIn("resources/list", resource_record.last_error)
        self.assertEqual(resource_record.protocol_capabilities, [])
        self.assertEqual(resources.tool_calls, 0)

        neither = Client(tools=None, resources=None, error=RuntimeError("should not be called"))
        neither_service = service_for(neither)
        neither_record = await neither_service.test(self._create(neither_service, "No capabilities").id)
        self.assertIn("does not advertise tools or resources", neither_record.last_error)
        self.assertEqual(neither_record.protocol_capabilities, [])
        self.assertEqual(neither.tool_calls, 0)


if __name__ == "__main__":
    unittest.main()
