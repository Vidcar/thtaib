"""One owned Playwright MCP browser per conversation, shared across Chat turns.

The official MCPAdapter remains the only MCP translation layer. The worker is
optional and installed explicitly; no package download occurs during a run.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
import re
import shutil
import threading
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable
from urllib.parse import urlsplit

from langchain_core.tools import BaseTool, StructuredTool, ToolException

from workbench_backend.agents.harness_backend import sanitize_thread_id
from workbench_backend.agents.execution_policy import CURRENT_TOOL_CALL
from workbench_backend.browser.runtime import BrowserRuntime
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.image_validation import CANNOT_READ_IMAGE
from workbench_backend.paths import WorkbenchPaths

BROWSER_TOOL_NAMES = (
    "browser_navigate", "browser_navigate_back", "browser_tabs", "browser_snapshot",
    "browser_find", "browser_click", "browser_hover", "browser_press_key",
    "browser_type", "browser_select_option", "browser_fill_form", "browser_resize",
    "browser_console_messages", "browser_network_requests", "browser_take_screenshot",
    "browser_wait_for", "browser_handle_dialog",
    "browser_drag", "browser_mouse_move_xy", "browser_mouse_click_xy",
    "browser_mouse_drag_xy", "browser_mouse_down", "browser_mouse_up",
    "browser_mouse_wheel", "browser_file_upload",
)
BROWSER_READ_TOOLS = frozenset({
    "browser_snapshot", "browser_find", "browser_console_messages",
    "browser_network_requests", "browser_take_screenshot", "browser_wait_for",
})
BROWSER_IDLE_SECONDS = 30 * 60
_THREAD_ID = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_PAGE_TEXT_LIMIT = 12_000
_SNAPSHOT_LINK = re.compile(r"\[Snapshot\]\(([^)]+)\)")
_CONSENT_DIALOG = re.compile(
    r"""heading ["'][^"']*(?:cookie|consent)[^"']*["'][^\n]*\[active\]|dialog ["'][^"']*(?:cookie|consent)[^"']*["']""",
    re.IGNORECASE,
)
_BLOCKED_PAGE = re.compile(r"unusual traffic|captcha|rate-limit|google\.com/sorry|/sorry/index", re.IGNORECASE)
_PAGE_LINE = ("heading ", "link ", "button ", "Page URL", "Page Title")
_TOOL_GUIDANCE = {
    "browser_navigate": " Requires an HTTP(S) URL without embedded credentials; file:// and host file paths are not accepted. For project HTML, call start_preview with entry_path, then navigate to its exact loopback URL. Returns the page address, title, and headings and links to cite.",
    "browser_snapshot": " Use this to read and cite what the page says.",
    "browser_find": " Use this to locate one element on a large page.",
    "browser_take_screenshot": " Use this to look at the page and show the person. Read headlines from the page structure, not from the picture.",
}


def _safe_thread(thread_id: str | None) -> str:
    if not thread_id or not _THREAD_ID.fullmatch(thread_id):
        raise HarnessError("This browser requires a saved conversation.", code="browser_thread_required", status_code=409)
    return sanitize_thread_id(thread_id)


def _allowed_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return (parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            and not parsed.username and not parsed.password and (parsed.port is None or 0 < parsed.port <= 65535))
    except ValueError:
        return False


def _without_filename(tool: BaseTool) -> dict[str, Any]:
    schema = tool.args_schema
    schema = copy.deepcopy(schema if isinstance(schema, dict) else schema.model_json_schema())
    schema.get("properties", {}).pop("filename", None)
    if isinstance(schema.get("required"), list):
        schema["required"] = [name for name in schema["required"] if name != "filename"]
    return schema


def _text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, (list, tuple)):
        return "\n".join(_text(item) for item in result)
    if isinstance(result, dict):
        if result.get("type") == "text":
            return str(result.get("text", ""))
        return json.dumps(result, ensure_ascii=False)
    content = getattr(result, "content", None)
    return _text(content) if content is not None else str(result)


def _inline_snapshot_files(text: str, output_dir: Path) -> str:
    """Replace a worker snapshot link with that file when it stays in the capture folder."""

    root = output_dir.resolve()

    def replace(match: re.Match[str]) -> str:
        raw = match.group(1).strip().strip('"').strip("'")
        try:
            resolved = Path(raw).resolve()
            if resolved != root and root not in resolved.parents or not resolved.is_file():
                return match.group(0)
            body = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return match.group(0)
        return "\n" + body + "\n"

    return _SNAPSHOT_LINK.sub(replace, text)


def _bound_page_text(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= _PAGE_TEXT_LIMIT:
        return stripped
    kept: list[str] = []
    size = 0
    for line in stripped.splitlines():
        compact = line.strip()
        if not compact or not any(token in compact for token in _PAGE_LINE):
            continue
        if len(compact) > 300:
            compact = compact[:300]
        if size + len(compact) + 1 > _PAGE_TEXT_LIMIT:
            break
        kept.append(compact)
        size += len(compact) + 1
    kept.append("The rest of the page structure was omitted. Use browser_find to locate one element.")
    return "\n".join(kept)


def present_page(result: Any, output_dir: Path) -> str:
    """Page address and citable structure. A snapshot file path is not the page."""

    text = _inline_snapshot_files(_text(result), output_dir)
    url_match = re.search(r"(?:Page URL:|URL:)\s*(https?://[^\s]+)", text)
    url = url_match.group(1).rstrip("),]") if url_match else None
    title_match = re.search(r"Page Title:\s*(.+)", text)
    notes: list[str] = []
    if (url and _BLOCKED_PAGE.search(url)) or _BLOCKED_PAGE.search(text):
        notes.append("This site refused the automated browser. This is not a search-result page.")
    if _CONSENT_DIALOG.search(text):
        notes.append("A consent dialog is open. It was not clicked. Use the button refs below if it covers the results.")
    header = [line for line in (f"Page URL: {url}" if url else "", f"Page title: {title_match.group(1).strip()}" if title_match else "") if line]
    return "\n".join([*notes, *header, _bound_page_text(text)]).strip()


@dataclass
class _Session:
    thread_id: str
    tools: dict[str, BaseTool]
    output_dir: Path
    owner_task: asyncio.Task
    close_event: asyncio.Event
    io_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    idle_task: asyncio.Task | None = None
    last_url: str | None = None
    worker: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    control: str = "agent"
    viewers: int = 0
    last_run: Any = None
    downloads: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None
    download_ids: set[str] = field(default_factory=set)
    observer_task: asyncio.Task | None = None


class BrowserSessionService:
    def __init__(
        self,
        paths: WorkbenchPaths,
        *,
        capture_publisher: Callable[..., Any] | None = None,
        app_store: Any = None,
        runtime: BrowserRuntime | None = None,
        adapter_factory: Callable[..., Any] | None = None,
        idle_seconds: int = BROWSER_IDLE_SECONDS,
        screenshot_reader: Callable[[Any], bool] | None = None,
        assets: Any = None,
    ):
        self.paths = paths
        self.runtime = runtime or BrowserRuntime(paths)
        self.capture_publisher = capture_publisher
        self.app_store = app_store
        self.adapter_factory = adapter_factory
        self.screenshot_reader = screenshot_reader
        self.assets = assets
        self.state_invalidator = None
        self.idle_seconds = idle_seconds
        self._sessions: dict[str, _Session] = {}
        self._controls: dict[str, str] = {}
        self._handoff_locks: dict[str, asyncio.Lock] = {}
        self._terminating: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._status_lock = threading.RLock()
        self._state_root = paths.state / "browser-sessions"
        self._output_root = paths.state / "browser-captures"
        self._profile_root = paths.state / "browser-profiles"

    def status(self, thread_id: str) -> dict[str, Any]:
        key = _safe_thread(thread_id)
        if key not in self._controls and self.assets is not None:
            owner = self.assets.session_for_thread(key)
            run = self.app_store.get_run(owner.current_run_id) if self.app_store and owner and owner.current_run_id else None
            if run and getattr(run, "browser_control", "agent") != "agent":
                self._controls[key] = run.browser_control
        with self._status_lock:
            session = self._sessions.get(key)
            active = bool(session and (session.worker is None or session.metadata.get("session_id")))
        marker = self._marker(key)
        return {
            "thread_id": key,
            "state": "active" if active else ("lost" if marker.exists() else "closed"),
            "worker": self.runtime.status(),
            "session_id": session.metadata.get("session_id") if session else None,
            "tabs": session.metadata.get("tabs", []) if session else [],
            "active_page_id": session.metadata.get("active_page_id") if session else None,
            "revision": session.metadata.get("revision", 0) if session else 0,
            "viewport": session.metadata.get("viewport", {"width": 1440, "height": 900}) if session else {"width": 1440, "height": 900},
            "control": session.control if session else self._controls.get(key, "agent"),
            "dialog": session.metadata.get("dialog") if session else None,
            "file_chooser": session.metadata.get("file_chooser") if session else None,
            "downloads": session.downloads if session else [],
            "error": session.error if session else None,
        }

    def _marker(self, key: str) -> Path:
        return self._state_root / f"{key}.json"

    def _write_marker(self, key: str) -> None:
        self._state_root.mkdir(parents=True, exist_ok=True)
        marker = self._marker(key)
        staging = marker.with_suffix(".tmp")
        staging.write_text(json.dumps({"thread_id": key, "started_at": utc_now()}), encoding="utf-8")
        staging.replace(marker)

    @asynccontextmanager
    async def open_tools(self, run) -> AsyncIterator[list[BaseTool]]:
        selected = set(run.presented_tools) & set(BROWSER_TOOL_NAMES)
        if not selected or run.work_mode != "work" or getattr(run, "tool_mode", None) == "recorded-tool":
            yield []
            return
        key = _safe_thread(run.thread_id)
        if self.adapter_factory is None:
            # Upstream eagerly obtains a supplied persistent context at MCP
            # initialization. Use its installation-time catalogue for tool
            # presentation, and acquire the real adapter only on first action.
            # This is metadata from the pinned server, not another tool adapter.
            schemas = {definition["name"]: definition for definition in self.runtime.read_tool_schemas()}
            def lazy_tool(name: str) -> BaseTool:
                definition = schemas[name]
                args = copy.deepcopy(definition["inputSchema"])
                args.get("properties", {}).pop("filename", None)
                if "required" in args:
                    args["required"] = [item for item in args["required"] if item != "filename"]
                async def invoke(**arguments):
                    session = await self._get_or_create(key)
                    return await self._bind_tool(run, session, session.tools[name]).coroutine(**arguments)
                return StructuredTool(name=name, description="Chat Chrome browser: " + definition.get("description", name)
                    + _TOOL_GUIDANCE.get(name, "") + (" Paths must be project-relative or asset:<id> for a selected attachment." if name == "browser_file_upload" else ""),
                    args_schema=args, coroutine=invoke, response_format="content_and_artifact",
                    metadata={"browser_worker": True, "browser_read_only": name in BROWSER_READ_TOOLS}, handle_tool_error=True)
            yield [lazy_tool(name) for name in BROWSER_TOOL_NAMES if name in selected]
            return
        session = await self._get_or_create(key)
        self._refresh_idle(session)
        yield [self._bind_tool(run, session, session.tools[name]) for name in BROWSER_TOOL_NAMES if name in selected]

    async def _get_or_create(self, key: str) -> _Session:
        async with self._lock:
            existing = self._sessions.get(key)
            if existing:
                return existing
            if self._marker(key).exists():
                raise HarnessError("The previous browser session was lost. Reset it to start a fresh isolated browser.", code="browser_session_lost", status_code=409)
            node, cli = self.runtime.require_installed()
            output = self._output_root / key
            output.mkdir(parents=True, exist_ok=True)
            ready: asyncio.Future[_Session] = asyncio.get_running_loop().create_future()
            close_event = asyncio.Event()
            owner = asyncio.create_task(self._own_worker(key, node, cli, output, close_event, ready))
            try:
                session = await ready
                session.control = self._controls.get(key, "agent")
                if session.worker is None or session.metadata.get("session_id"):
                    self._write_marker(key)
                with self._status_lock:
                    self._sessions[key] = session
                if session.worker:
                    session.observer_task = asyncio.create_task(self._monitor(session))
                return session
            except BaseException:
                close_event.set()
                await asyncio.shield(owner)
                raise

    async def _own_worker(
        self, key: str, node: Path, cli: Path, output: Path,
        close_event: asyncio.Event, ready: asyncio.Future[_Session],
    ) -> None:
        # FastMCP's stdio transport owns an AnyIO cancel scope. Enter and exit
        # that scope in this one task, even when Chat runs and API calls close
        # or reset the same browser from other tasks.
        try:
            async with AsyncExitStack() as stack:
                if self.adapter_factory:
                    adapter = await stack.enter_async_context(self.adapter_factory(node, cli, output))
                    worker = None
                else:
                    from fastmcp import Client
                    from fastmcp.client.elicitation import ElicitResult
                    from langchain.mcp import MCPAdapter
                    from workbench_backend.browser.worker_client import BrowserWorkerClient

                    async def decline(*_args, **_kwargs):
                        return ElicitResult(action="decline")

                    worker = BrowserWorkerClient(node, cli, self._profile_root / key, output)
                    # Register cleanup before entering the transport so Chrome
                    # closes while its authenticated management channel is live.
                    stack.push_async_callback(worker.close)
                    adapter = await stack.enter_async_context(MCPAdapter(Client(
                        worker.transport, timeout=60, init_timeout=30, elicitation_handler=decline,
                    )))
                    await worker.connect()
                discovered = await adapter.list_tools()
                tools = {tool.name: tool for tool in discovered if tool.name in BROWSER_TOOL_NAMES}
                if len(tools) != len(set(tools)) or not {"browser_navigate", "browser_snapshot", "browser_take_screenshot"} <= tools.keys():
                    raise HarnessError("The pinned browser worker has an unexpected tool set.", code="browser_worker_schema_changed", status_code=409)
                session = _Session(key, tools, output, asyncio.current_task(), close_event, worker=worker)
                if worker:
                    session.metadata = await worker.get_state()
                ready.set_result(session)
                await close_event.wait()
                if worker:
                    await worker.close()
        except BaseException as exc:
            if not ready.done():
                ready.set_exception(exc)
            else:
                raise

    def _refresh_idle(self, session: _Session) -> None:
        if session.idle_task:
            session.idle_task.cancel()

        async def expire():
            try:
                await asyncio.sleep(self.idle_seconds)
                await self.close_session(session.thread_id)
            except asyncio.CancelledError:
                return

        session.idle_task = asyncio.create_task(expire())

    def _bind_tool(self, run, session: _Session, original: BaseTool, *, observation: bool = False) -> BaseTool:
        name = original.name

        def text_result(message: str):
            # MCPAdapter tools use LangChain's content_and_artifact contract.
            # The screenshot wrapper replaces the media with a retained path.
            return (message, None) if original.response_format == "content_and_artifact" else message

        async def invoke(**arguments):
            if self._sessions.get(session.thread_id) is not session:
                raise ToolException("This browser session expired or was reset. Start a new message with a fresh session.")
            if "filename" in arguments:
                raise ToolException("Browser file output is controlled by Workbench; omit filename.")
            if name == "browser_navigate" and not _allowed_url(str(arguments.get("url", ""))):
                raise ToolException("Browser navigation requires an HTTP(S) URL without embedded credentials.")
            if name == "browser_tabs" and arguments.get("action") == "new" and arguments.get("url") and not _allowed_url(str(arguments["url"])):
                raise ToolException("A new tab requires an HTTP(S) URL without embedded credentials.")
            if name == "browser_tabs" and arguments.get("action") not in {"list", "new", "close", "select"}:
                raise ToolException("Choose list, new, close, or select for browser tabs.")
            if name == "browser_wait_for" and float(arguments.get("time") or 0) > 30:
                raise ToolException("Wait for no more than 30 seconds per browser call.")
            if name == "browser_resize" and not (240 <= arguments.get("width", 0) <= 3840 and 240 <= arguments.get("height", 0) <= 2160):
                raise ToolException("Choose a viewport between 240–3840 pixels wide and 240–2160 pixels tall.")
            if name.startswith("browser_mouse_") and name != "browser_mouse_wheel" and self.screenshot_reader is not None:
                if not await asyncio.to_thread(self.screenshot_reader, run):
                    raise ToolException("Coordinate interaction requires verified screenshot reading for this model. Use page structure and element controls instead.")
            effect = None
            effects = None
            async with session.io_lock:
                if self._sessions.get(session.thread_id) is not session:
                    raise ToolException("The browser closed or changed while this interaction waited. Observe its current state before trying again.")
                if session.control != "agent" and not observation:
                    raise ToolException("Browser control belongs to the person. This interaction was not executed; observe the changed page after control returns.")
                session.last_run = run
                self._refresh_idle(session)
                if name == "browser_file_upload":
                    arguments["paths"] = await asyncio.to_thread(self._resolve_uploads, session, run, arguments.get("paths") or [])
                if name.startswith("browser_mouse_") and session.worker:
                    self._validate_coordinates(session, arguments)
                if session.worker:
                    await session.worker.set_attribution({"run_id": run.id, "tool_call_id": CURRENT_TOOL_CALL.get() or None, "tool_name": name})
                if name not in BROWSER_READ_TOOLS and not (name == "browser_tabs" and arguments.get("action") == "list") and self.app_store is not None:
                    from workbench_backend.state.effects import DispatchEffectRequest, EffectService
                    effects = EffectService(self.app_store)
                    effect = await asyncio.to_thread(effects.dispatch, DispatchEffectRequest(
                        run_id=run.id, adapter_id=f"browser:{session.thread_id}", operation=name,
                        payload={"tool": name, "thread_id": session.thread_id, "tool_call_id": CURRENT_TOOL_CALL.get() or None},
                    ))
                before = set(session.output_dir.iterdir()) if name == "browser_take_screenshot" else set()
                try:
                    result = await original.coroutine(**arguments)
                    if session.worker and name in {"browser_file_upload", "browser_handle_dialog"}:
                        await session.worker.acknowledge_modal("file_chooser" if name == "browser_file_upload" else "dialog")
                    await self._observe_session(session, reconcile=True)
                except ToolException:
                    if effect:
                        await asyncio.to_thread(effects.acknowledge, effect.id)
                    raise
                except BaseException as exc:
                    if effect:
                        effects.recover(effect.id)
                    await self._mark_lost(session)
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                    raise HarnessError("The browser worker stopped during this call. The action was not retried; reset the session after reviewing its outcome.", code="browser_call_outcome_unknown", status_code=502) from None
                if effect:
                    await asyncio.to_thread(effects.acknowledge, effect.id)
                if name == "browser_navigate":
                    session.last_url = self._observed_url(result)
                if name in {"browser_navigate", "browser_snapshot"}:
                    return text_result(present_page(result, session.output_dir))
                if name != "browser_take_screenshot":
                    return result
                created = [path for path in session.output_dir.iterdir() if path not in before and path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES]
                if len(created) != 1:
                    raise ToolException("The browser did not produce exactly one controlled screenshot.")
                path = created[0]
                page_source = result
                try:
                    page_source = await session.tools["browser_snapshot"].coroutine()
                except Exception:
                    # A screenshot can still be retained if the page text cannot
                    # be read. Never substitute an earlier URL.
                    page_source = result
                observed_url = self._observed_url(result) or self._observed_url(page_source)
                target = observed_url or "browser page (URL unavailable)"
                session.last_url = observed_url
                page = present_page(page_source, session.output_dir)
                if self.capture_publisher is None:
                    return text_result(f"Screenshot saved to {path}.\n{page}")
                try:
                    published = self.capture_publisher(
                        run, path, source_tool_name=name, source_tool_call_id=CURRENT_TOOL_CALL.get() or None,
                        target=target, controlled_root=session.output_dir,
                    )
                    if inspect.isawaitable(published):
                        published = await published
                except Exception:
                    raise ToolException("The browser captured an image, but Workbench could not retain it. The temporary capture was removed; try again after checking the conversation and asset store.") from None
                finally:
                    # The retained asset service has its own copy. This output
                    # directory is only a transient handoff from MCP.
                    path.unlink(missing_ok=True)
                virtual_path = published[1] if isinstance(published, tuple) else published
                readable = None
                if self.screenshot_reader is not None:
                    try:
                        readable = await asyncio.to_thread(self.screenshot_reader, run)
                    except Exception:
                        readable = False
                message = f"Screenshot captured from {target}.\n{page}\nSaved screenshot: {virtual_path}"
                if readable is False:
                    message = f"{message}\n{CANNOT_READ_IMAGE}"
                return text_result(message)

        return original.model_copy(update={
            "args_schema": _without_filename(original),
            "coroutine": invoke,
            "description": f"Chat Chrome browser: {original.description}{_TOOL_GUIDANCE.get(name, '')}" + (" Paths must be project-relative files or asset:<id> for a selected conversation attachment." if name == "browser_file_upload" else ""),
            "metadata": {**(original.metadata or {}), "browser_worker": True, "browser_read_only": name in BROWSER_READ_TOOLS},
            "handle_tool_error": True,
        })

    @staticmethod
    def _observed_url(result: Any) -> str | None:
        content = _text(result)
        match = re.search(r"(?:Page URL:|URL:)\s*(https?://[^\s]+)", content)
        return match.group(1).rstrip("),]") if match else None

    def _remove_profile(self, key: str) -> None:
        root = self._profile_root.resolve()
        target = (root / key).resolve()
        if target.parent != root:
            raise RuntimeError("Browser profile must be a direct child of its owned root")
        if target.is_dir():
            shutil.rmtree(target)

    async def delete_chat(self, thread_id: str) -> None:
        await self.reset(thread_id)
        self._controls.pop(_safe_thread(thread_id), None)

    async def start(self, thread_id: str) -> dict[str, Any]:
        key = _safe_thread(thread_id)
        async with self._handoff_locks.setdefault(key, asyncio.Lock()):
            return await self._start(key)

    async def _start(self, thread_id: str) -> dict[str, Any]:
        session = await self._get_or_create(_safe_thread(thread_id))
        async with session.io_lock:
            if session.worker:
                await session.worker.start()
            await self._observe_session(session)
            self._refresh_idle(session)
        return self.status(thread_id)

    async def _observe_session(self, session: _Session, *, reconcile: bool = False) -> None:
        if not session.worker:
            return
        if reconcile:
            # Upstream selects by ordered context pages. Resolve that index to
            # our Page identity; matching URLs cannot distinguish duplicate tabs.
            listing = _text(await session.tools["browser_tabs"].coroutine(action="list"))
            current = re.search(r"(?:^|\n)\s*-?\s*(\d+):\s*\(current\)", listing)
            if current:
                await session.worker.set_active(int(current.group(1)))
        state = await session.worker.get_state()
        if state.get("lost"):
            raise HarnessError("Chrome stopped unexpectedly. Actions were not repeated.", code="browser_session_lost", status_code=409)
        with self._status_lock:
            session.metadata = state
        if state.get("session_id"):
            if not self._marker(session.thread_id).exists():
                self._write_marker(session.thread_id)
        await self._retain_downloads(session, await session.worker.drain_downloads())

    async def _monitor(self, session: _Session) -> None:
        """Observe downloads and worker loss even while the rail is hidden."""
        try:
            while self._sessions.get(session.thread_id) is session:
                await asyncio.sleep(0.5)
                await self._observe_session(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._mark_lost(session)

    async def _retain_downloads(self, session: _Session, downloads: list[dict[str, Any]]) -> None:
        for item in downloads:
            identity = str(item["download_id"])
            if identity in session.download_ids:
                continue
            session.download_ids.add(identity)
            try:
                if item.get("error"):
                    raise RuntimeError(item["error"])
                if self.assets is None:
                    raise RuntimeError("Retained files are unavailable")
                asset = await asyncio.to_thread(self.assets.retain_browser_download,
                    session.thread_id, Path(item["path"]), filename=item["filename"],
                    source_url=item.get("url", ""), controlled_root=session.output_dir,
                    attribution=item.get("attribution") or {})
                session.downloads.append({"asset_id": asset.id, "name": asset.filename,
                    "url": self.assets._source_url(asset)})
                session.downloads = session.downloads[-50:]
            except Exception as exc:
                session.error = f"The download could not be retained: {exc}"
            finally:
                await session.worker.ack_download(identity)

    def _resolve_uploads(self, session: _Session, run: Any, references: list[str], *, manual: bool = False) -> list[str]:
        from workbench_backend.assets.service import _resolve_scoped_file
        if self.assets is None:
            raise ToolException("Conversation file access is unavailable.")
        conversation = self.assets.session_for_thread(session.thread_id)
        if conversation is None:
            raise ToolException("Browser files require an owning conversation.")
        allowed_assets = set(conversation.document_asset_ids if manual else getattr(run, "retained_asset_ids", []))
        if manual and conversation.draft:
            allowed_assets.update(getattr(conversation.draft, "attachment_ids", []))
        project = (conversation.project_path or conversation.area_project_path) if manual else getattr(run, "project_path", None)
        resolved = []
        staging = session.output_dir / "uploads"
        staging.mkdir(exist_ok=True)
        for value in references:
            if value.startswith("asset:"):
                asset_id = value[6:]
                if asset_id not in allowed_assets:
                    raise ToolException("Choose a selected conversation attachment for browser upload.")
                asset, content = self.assets._load_content(asset_id, session_id=conversation.id, project_path=project)
                target = staging / uuid.uuid4().hex / asset.filename
                target.parent.mkdir()
                target.write_bytes(content)
            else:
                candidate = Path(value)
                if not project or candidate.is_absolute() or candidate.drive or candidate.root:
                    raise ToolException("Browser uploads require a project-relative path or asset:<id> from selected files.")
                try:
                    source = _resolve_scoped_file(project, value)
                    if source.stat().st_size > 50_000_000:
                        raise ToolException("Browser upload exceeds the 50 MB limit.")
                    target = staging / uuid.uuid4().hex / source.name
                    target.parent.mkdir()
                    shutil.copyfile(source, target)
                except (OSError, ValueError) as exc:
                    raise ToolException("The selected project file is not readable.") from exc
            resolved.append(str(target.resolve()))
        return resolved

    @staticmethod
    def _validate_coordinates(session: _Session, arguments: dict[str, Any]) -> None:
        viewport = session.metadata.get("viewport", {"width": 1440, "height": 900})
        for key in ("x", "startX", "endX"):
            if key in arguments and not 0 <= float(arguments[key]) < viewport["width"]:
                raise ToolException("The horizontal coordinate is outside the actual browser viewport.")
        for key in ("y", "startY", "endY"):
            if key in arguments and not 0 <= float(arguments[key]) < viewport["height"]:
                raise ToolException("The vertical coordinate is outside the actual browser viewport.")

    async def control(self, thread_id: str, action: str, harness: Any) -> dict[str, Any]:
        key = _safe_thread(thread_id)
        async with self._handoff_locks.setdefault(key, asyncio.Lock()):
            return await self._change_control(key, action, harness)

    async def _change_control(self, key: str, action: str, harness: Any) -> dict[str, Any]:
        session = self._sessions.get(key)
        previous = self._controls.get(key, "agent")
        self._controls[key] = "taking_control"
        if session:
            session.control = "taking_control"
        drained = False
        try:
            if action == "take":
                await harness.request_browser_takeover(key)
                drained = True
                # Close/expiry/loss may have settled while existing work drained.
                session = self._sessions.get(key)
                if session:
                    async with session.io_lock:
                        await self._observe_session(session)
                        if session.worker:
                            await session.worker.reset_input()
                self._controls[key] = "user"
                if session:
                    session.control = "user"
            else:
                observation = "The browser is closed. Sign-ins were retained; the next browser action opens fresh pages."
                if session and session.metadata.get("session_id"):
                    async with session.io_lock:
                        if session.worker:
                            await session.worker.reset_input()
                        await self._observe_session(session, reconcile=True)
                        observation = present_page(await session.tools["browser_snapshot"].coroutine(), session.output_dir)
                    run = self._current_root(key) or (session.last_run if self.assets is None else None)
                    if run and self.screenshot_reader and await asyncio.to_thread(self.screenshot_reader, run):
                        try:
                            tool = self._bind_tool(run, session, session.tools["browser_take_screenshot"], observation=True)
                            observation += "\n" + _text(await tool.coroutine())
                        except Exception:
                            observation += "\nA fresh screenshot is unavailable; use the current page structure."
                # Input has remained disabled throughout refresh. Release service
                # and graph authority together, before any resumed tool can run.
                self._controls[key] = "agent"
                if session:
                    session.control = "agent"
                await harness.release_browser_takeover(key, observation)
        except BaseException as exc:
            if action == "return":
                recovery = previous
            elif getattr(exc, "code", None) == "run_cancelling":
                recovery = "agent"
            elif drained:
                recovery = "user"
            else:
                recovery = getattr(self._current_root(key), "browser_control", "agent")
            self._controls[key] = recovery
            session = self._sessions.get(key)
            if session:
                session.control = recovery
            raise
        return self.status(key)

    def _current_root(self, key: str):
        owner = self.assets.session_for_thread(key) if self.assets else None
        return self.app_store.get_run(owner.current_run_id) if self.app_store and owner and getattr(owner, "current_run_id", None) else None

    async def manual_action(self, thread_id: str, body: Any) -> dict[str, Any]:
        key = _safe_thread(thread_id)
        session = self._sessions.get(key)
        if not session or not session.worker:
            raise HarnessError("Start this chat's browser first.", code="browser_not_started", status_code=409)
        async with session.io_lock:
            if session.control != "user":
                raise HarnessError("Take control before interacting with the browser.", code="browser_control_required", status_code=409)
            payload = body.model_dump()
            action = payload["action"]
            await session.worker.validate_action(payload)
            if action["type"] in {"navigate", "new_tab"} and action.get("url") and not _allowed_url(action["url"]):
                raise HarnessError("Use an HTTP(S) address without embedded credentials.", code="browser_url_invalid", status_code=422)
            if action["type"] == "upload":
                references = ["asset:" + value for value in action.pop("asset_ids", [])] + action.pop("project_paths", [])
                action["paths"] = await asyncio.to_thread(self._resolve_uploads, session, None, references, manual=True)
            await session.worker.set_attribution({"run_id": getattr(self._current_root(key), "id", None), "tool_name": "browser_manual"})
            if action["type"] == "upload":
                await session.worker.validate_action(payload)
                await session.tools["browser_file_upload"].coroutine(paths=action["paths"])
                await session.worker.acknowledge_modal("file_chooser")
            elif action["type"] == "dialog":
                await session.worker.validate_action(payload)
                arguments = {"accept": action["accept"]}
                if action.get("prompt_text") is not None:
                    arguments["promptText"] = action["prompt_text"]
                await session.tools["browser_handle_dialog"].coroutine(**arguments)
                await session.worker.acknowledge_modal("dialog")
            else:
                await session.worker.action(payload)
            if action["type"] in {"select_tab", "new_tab", "close_tab"}:
                state = await session.worker.get_state()
                index = next((i for i, tab in enumerate(state.get("tabs", [])) if tab["page_id"] == state.get("active_page_id")), 0)
                await session.tools["browser_tabs"].coroutine(action="select", index=index)
            await self._observe_session(session)
            self._refresh_idle(session)
        return self.status(key)

    async def view_subscription(self, thread_id: str, visible: bool) -> None:
        session = self._sessions.get(_safe_thread(thread_id))
        if session and session.worker:
            session.viewers = max(0, session.viewers + (1 if visible else -1))
            await session.worker.set_streaming(session.viewers > 0)
            if not visible and session.viewers == 0 and session.control == "user":
                async with session.io_lock:
                    await session.worker.reset_input()
            self._refresh_idle(session)

    async def poll_view(self, thread_id: str, last_frame_seq: int = 0) -> dict[str, Any]:
        session = self._sessions.get(_safe_thread(thread_id))
        if not session or not session.worker:
            return {"state": self.status(thread_id)}
        try:
            result = await session.worker.poll(last_frame_seq)
            if result["state"].get("lost"):
                raise HarnessError("Chrome stopped unexpectedly.", code="browser_session_lost", status_code=409)
            session.metadata = result["state"]
            await self._retain_downloads(session, result.get("downloads", []))
            return {"state": self.status(thread_id), "frame": result.get("frame")}
        except Exception:
            await self._mark_lost(session)
            return {"state": self.status(thread_id)}

    async def _mark_lost(self, session: _Session) -> None:
        self._write_marker(session.thread_id)
        self._terminating[session.thread_id] = session.owner_task
        with self._status_lock:
            self._sessions.pop(session.thread_id, None)
        if session.idle_task:
            session.idle_task.cancel()
        if session.observer_task and session.observer_task is not asyncio.current_task():
            session.observer_task.cancel()
            await asyncio.gather(session.observer_task, return_exceptions=True)
        session.close_event.set()
        await asyncio.shield(session.owner_task)
        # Keep the marker: restart/reset must not imply a live tab survived.

    async def close_session(self, thread_id: str, *, lost: bool = False) -> None:
        key = _safe_thread(thread_id)
        async with self._handoff_locks.setdefault(key, asyncio.Lock()):
            await self._close_session(key, lost=lost)

    async def _close_session(self, thread_id: str, *, lost: bool = False) -> None:
        key = _safe_thread(thread_id)
        async with self._lock:
            with self._status_lock:
                session = self._sessions.pop(key, None)
            if session:
                self._terminating[key] = session.owner_task
                if session.observer_task:
                    session.observer_task.cancel()
                    await asyncio.gather(session.observer_task, return_exceptions=True)
                if session.idle_task and session.idle_task is not asyncio.current_task():
                    session.idle_task.cancel()
                async with session.io_lock:
                    if session.worker:
                        await self._retain_downloads(session, await session.worker.drain_downloads())
                    session.close_event.set()
                    await asyncio.shield(session.owner_task)
            terminating = self._terminating.get(key)
            if terminating:
                await asyncio.shield(terminating)
                self._terminating.pop(key, None)
            if not lost:
                self._marker(key).unlink(missing_ok=True)
                self._remove_output(key)
                if self.state_invalidator:
                    await self.state_invalidator(key, "The Chrome browser was closed. Sign-ins were retained; the next browser action opens fresh pages. Reconsider older page references and coordinates.")

    def _remove_output(self, key: str) -> None:
        root = self._output_root.resolve()
        target = (root / key).resolve()
        if target.parent != root:
            raise RuntimeError("Browser output must be a direct child of the owned capture root")
        if target.is_dir():
            shutil.rmtree(target)

    async def reset(self, thread_id: str) -> dict[str, Any]:
        key = _safe_thread(thread_id)
        async with self._handoff_locks.setdefault(key, asyncio.Lock()):
            await self._close_session(key)
            self._remove_profile(key)
            if self.state_invalidator:
                await self.state_invalidator(key, "The browser was Reset. This chat's Chrome profile and sign-ins were cleared. Older browser interactions were not repeated.")
        return self.status(thread_id)

    async def shutdown(self) -> None:
        for key in set(self._sessions) | set(self._terminating):
            await self.close_session(key)
