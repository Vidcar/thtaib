"""Versioned external tool selection with one supported MCP adapter session per run."""
from __future__ import annotations

import asyncio
import hashlib
import re
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from langchain_core.tools import ToolException

from workbench_backend.connections.credentials import CredentialVault
from workbench_backend.connections.schemas import ConnectionRecord, ConnectionSnapshot, ConnectionTool
from workbench_backend.connections.store import ConnectionStore
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import new_id, utc_now


class UnsupportedMCPInput(ToolException):
    """Application-declined elicitation, separate from remote tool errors."""


def connection_error_handler(original):
    def handle(error):
        if isinstance(error, UnsupportedMCPInput):
            return str(error)
        if callable(original):
            return original(error)
        if original:
            return str(error)
        raise error
    return handle


def namespaced(connection_id, remote_name):
    suffix = hashlib.sha256(remote_name.encode()).hexdigest()[:16]
    readable = re.sub(r"[^a-zA-Z0-9_]", "_", remote_name)[:20]
    return f"cx_{connection_id.removeprefix('connection_')}_{readable}_{suffix}"


class ConnectionService:
    def __init__(self, application, *, vault=None, adapter_factory=None):
        self.application = application
        self.store = ConnectionStore(application)
        self.vault = vault or CredentialVault(application.paths.root)
        self.adapter_factory = adapter_factory

    def _view(self, record):
        present = bool(record.credential_ref and self.vault.get(record.credential_ref))
        return record.model_copy(update={"credential_present": present})

    def list(self):
        return [self._view(r) for r in self.store.list()]

    def get(self, connection_id):
        record = self.store.get(connection_id)
        if record is None:
            raise HarnessError("This connection is missing.", code="connection_missing", status_code=404)
        return self._view(record)

    def available(self, connection_id):
        try:
            record = self.get(connection_id)
            self._require_ready(record)
            return True
        except HarnessError:
            return False

    def create(self, request):
        if request.transport == "stdio" and not Path(request.command).is_file():
            raise HarnessError("The selected MCP executable is missing.", code="connection_runtime_missing")
        now = utc_now()
        record = ConnectionRecord(**request.model_dump(), id=new_id("connection"), version=1, created_at=now, updated_at=now)
        return self._view(self.store.put(record))

    def update(self, connection_id, request):
        current = self.get(connection_id)
        if request.transport == "stdio" and not Path(request.command).is_file():
            raise HarnessError("The selected MCP executable is missing.", code="connection_runtime_missing")
        fields = request.model_dump(exclude={"expected_version"})
        if current.credential_ref and (request.transport != "http" or request.url != current.url):
            raise HarnessError("Remove this connection's credential before changing its destination.", code="credential_destination_changed", status_code=409)
        updated = current.model_copy(update={**fields, "version": current.version + 1, "tools": [], "last_tested_at": None, "last_error": None, "updated_at": utc_now()})
        return self._view(self.store.put(updated, expected_version=request.expected_version))

    def disconnect(self, connection_id):
        with self.application._lock:
            record = self.get(connection_id)
            return self._view(self.store.put(record.model_copy(update={"enabled": False, "version": record.version + 1, "updated_at": utc_now()}), expected_version=record.version))

    def replace_credential(self, connection_id, secret):
        if any(c in secret for c in "\r\n\x00"):
            raise HarnessError("The access token contains invalid characters.", code="credential_invalid")
        with self.application._lock:
            record = self.get(connection_id)
            if record.transport != "http":
                raise HarnessError("Access tokens apply to HTTP MCP connections.", code="credential_transport_invalid")
            reference = new_id("credential")
            self.vault.put(reference, secret)
            try:
                updated = self.store.put(record.model_copy(update={"credential_ref": reference, "version": record.version + 1, "updated_at": utc_now(), "last_tested_at": None}), expected_version=record.version)
            except BaseException:
                self.vault.remove(reference)
                raise
            if record.credential_ref:
                self.vault.remove(record.credential_ref)
            return self._view(updated)

    def remove_credential(self, connection_id):
        with self.application._lock:
            record = self.get(connection_id)
            if record.credential_ref:
                self.vault.remove(record.credential_ref)
            return self._view(self.store.put(record.model_copy(update={"credential_ref": None, "version": record.version + 1, "last_tested_at": None, "updated_at": utc_now()}), expected_version=record.version))

    def _require(self, record):
        if not record.enabled:
            raise HarnessError(f"{record.name} is disconnected. Update the connection selection.", code="connection_disabled", status_code=409)
        if record.credential_ref and not record.credential_present:
            raise HarnessError(f"Replace the missing access token for {record.name}.", code="credential_missing", status_code=409)
        if record.transport == "stdio" and not Path(record.command or "").is_file():
            raise HarnessError(f"The executable for {record.name} is missing.", code="connection_runtime_missing", status_code=409)

    def snapshot(self, connection_ids, *, tools_enabled=True):
        if not tools_enabled:
            return []
        snapshots = []
        for connection_id in dict.fromkeys(connection_ids or []):
            record = self.get(connection_id)
            self._require_ready(record)
            snapshots.append(ConnectionSnapshot.model_validate(record.model_dump()))
        return snapshots

    def _require_ready(self, record):
        self._require(record)
        if not record.last_tested_at or not record.tools or record.last_error:
            raise HarnessError(f"Test {record.name} in Settings before using it.", code="connection_test_required", status_code=409)

    def _revalidate(self, snapshot):
        current = self.get(snapshot.id)
        self._require(current)
        if current.version != snapshot.version or current.credential_ref != snapshot.credential_ref:
            raise HarnessError(f"{current.name} changed. Start a new message with the current connection.", code="connection_changed", status_code=409)
        return current

    @asynccontextmanager
    async def _adapter(self, record, unsupported):
        if self.adapter_factory:
            async with self.adapter_factory(record, unsupported) as adapter:
                yield adapter
            return
        from fastmcp import Client
        from fastmcp.client.transports import StreamableHttpTransport, StdioTransport
        from fastmcp.client.elicitation import ElicitResult
        from langchain.mcp import MCPAdapter

        async def decline_elicitation(message, response_type, params, context):
            unsupported.append("The server requested input that this connection does not support. The request was declined; no approval or credentials were supplied.")
            return ElicitResult(action="decline")

        if record.transport == "http":
            secret = self.vault.get(record.credential_ref)
            transport = StreamableHttpTransport(record.url, headers={"Authorization": "Bearer " + secret} if secret else {})
        else:
            transport = StdioTransport(record.command, args=record.args, env={}, keep_alive=False)
        client = Client(transport, timeout=45, init_timeout=20, elicitation_handler=decline_elicitation)
        async with MCPAdapter(client) as adapter:
            yield adapter

    async def _discover(self, record, adapter):
        if record.kind == "public_web":
            from workbench_backend.connections.public_web import public_web_tools
            tools = public_web_tools()
            outputs = {}
        else:
            tools = await adapter.list_tools()
            # Use the protocol's actual output schema, never infer one from Python wrappers.
            protocol_tools = await adapter.client.list_tools()
            outputs = {item.name: getattr(item, "output_schema", None) for item in protocol_tools}
        if len({tool.name for tool in tools}) != len(tools):
            raise HarnessError("This connection returned duplicate tool names.", code="connection_tool_collision", status_code=409)
        records = []
        generated_names = set()
        for tool in tools:
            name = namespaced(record.id, tool.name)
            if name in generated_names:
                raise HarnessError("This connection produced duplicate tool identifiers. Its tools cannot be selected safely.", code="connection_tool_collision", status_code=409)
            generated_names.add(name)
            schema = tool.args_schema if isinstance(tool.args_schema, dict) else tool.args_schema.model_json_schema()
            records.append(ConnectionTool(id=name, name=name, remote_name=tool.name, description=tool.description, input_schema=schema, output_schema=outputs.get(tool.name)))
        return records, tools

    async def test(self, connection_id):
        record = self.get(connection_id)
        self._require(record)
        try:
            async with AsyncExitStack() as stack:
                adapter = await stack.enter_async_context(self._adapter(record, [])) if record.kind == "mcp" else None
                catalog, _ = await self._discover(record, adapter)
                if record.kind == "public_web":
                    from workbench_backend.connections.public_web import search_web, read_web_page
                    await search_web("LangChain documentation", 1)
                    await read_web_page("https://docs.langchain.com/")
            changed = catalog != record.tools
            updated = record.model_copy(update={"tools": catalog, "version": record.version + int(changed), "last_tested_at": utc_now(), "last_error": None, "updated_at": utc_now()})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Transport errors can contain request headers. Persist only a bounded classification.
            message = str(exc) if isinstance(exc, (HarnessError, ToolException)) else "Could not connect or list tools. Check the address, executable and access token, then test again."
            updated = record.model_copy(update={"last_tested_at": utc_now(), "last_error": message, "updated_at": utc_now()})
        return self._view(self.store.put(updated, expected_version=record.version))

    @asynccontextmanager
    async def open_tools(self, run):
        snapshots = getattr(run, "connection_snapshots", [])
        selected = set(run.presented_tools)
        if not snapshots or not selected:
            yield []
            return
        async with AsyncExitStack() as stack:
            applied = []
            for snapshot in snapshots:
                wanted = {tool.name for tool in snapshot.tools} & selected
                if not wanted:
                    continue
                record = await asyncio.to_thread(self._revalidate, snapshot)
                unsupported = []
                try:
                    adapter = await stack.enter_async_context(self._adapter(record, unsupported)) if record.kind == "mcp" else None
                    discovered, actual = await self._discover(record, adapter)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    raise HarnessError(f"{record.name} could not connect or list tools. Test the connection in Settings.", code="connection_transport_failed", status_code=409) from None
                if discovered != snapshot.tools:
                    raise HarnessError(f"The tools from {record.name} changed. Test the connection and start a new message.", code="connection_schema_changed", status_code=409)
                # One session can serve many model tool calls. Serialize MCP dispatch
                # through acknowledgement so an in-flight call is never mistaken
                # for a recovered unknown outcome, and elicitation belongs to one call.
                call_lock = asyncio.Lock()
                for descriptor, tool in zip(discovered, actual):
                    if descriptor.name not in wanted:
                        continue
                    def bind(_tool, _snapshot, _descriptor, _unsupported, _lock):
                        async def invoke(**arguments):
                            await asyncio.to_thread(self._revalidate, _snapshot)
                            effect = None
                            effects = None
                            if _snapshot.kind == "mcp":
                                from workbench_backend.state.effects import EffectService, DispatchEffectRequest
                                effects = EffectService(self.application)
                                unresolved = await asyncio.to_thread(effects.list_effects, run_id=run.id, unresolved_only=True)
                                if any(e.adapter_id == _snapshot.id for e in unresolved):
                                    raise HarnessError("An earlier external call has an unknown outcome. Review it before making another call; it was not retried.", code="connection_outcome_unknown", status_code=409)
                                effect = await asyncio.to_thread(effects.dispatch, DispatchEffectRequest(run_id=run.id, adapter_id=_snapshot.id, operation=_descriptor.remote_name, payload={"connection_version": _snapshot.version, "tool": _descriptor.name}))
                            count = len(_unsupported)
                            try:
                                result = await _tool.coroutine(**arguments)
                            except ToolException:
                                if effect:
                                    await asyncio.to_thread(effects.acknowledge, effect.id)
                                if len(_unsupported) > count:
                                    raise UnsupportedMCPInput(_unsupported[-1]) from None
                                raise
                            except BaseException as exc:
                                if effect:
                                    # Synchronous durable write also runs on cancellation; never replay.
                                    effects.recover(effect.id)
                                if isinstance(exc, asyncio.CancelledError):
                                    raise
                                raise HarnessError("The external connection failed during this call. Its outcome may be unknown; the call was not retried.", code="connection_call_failed", status_code=502) from None
                            if effect:
                                await asyncio.to_thread(effects.acknowledge, effect.id)
                            if len(_unsupported) > count:
                                raise UnsupportedMCPInput(_unsupported[-1])
                            return result
                        async def serialized_invoke(**arguments):
                            async with _lock:
                                return await invoke(**arguments)
                        return serialized_invoke if _snapshot.kind == "mcp" else invoke
                    applied.append(tool.model_copy(update={"name": descriptor.name, "description": f"{record.name}: {tool.description}", "coroutine": bind(tool, snapshot, descriptor, unsupported, call_lock), "handle_tool_error": connection_error_handler(tool.handle_tool_error), "metadata": {**(tool.metadata or {}), "connection_id": record.id, "connection_version": record.version, "remote_tool": descriptor.remote_name}}))
            yield applied
