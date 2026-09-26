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
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable
from urllib.parse import urlsplit

from langchain_core.tools import BaseTool, ToolException

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
    "browser_navigate": " Returns the page address, title, and the headings and links to cite.",
    "browser_snapshot": " Use this to read and cite what the page says.",
    "browser_find": " Use this to locate one element on a large page.",
    "browser_take_screenshot": " Use this to look at the page and show the person. Read headlines from the page structure, not from the picture.",
}


def _safe_thread(thread_id: str | None) -> str:
    if not thread_id or not _THREAD_ID.fullmatch(thread_id):
        raise HarnessError("This browser requires a saved conversation.", code="browser_thread_required", status_code=409)
    return sanitize_thread_id(thread_id)


def _allowed_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password


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
    ):
        self.paths = paths
        self.runtime = runtime or BrowserRuntime(paths)
        self.capture_publisher = capture_publisher
        self.app_store = app_store
        self.adapter_factory = adapter_factory
        self.screenshot_reader = screenshot_reader
        self.idle_seconds = idle_seconds
        self._sessions: dict[str, _Session] = {}
        self._lock = asyncio.Lock()
        self._status_lock = threading.RLock()
        self._state_root = paths.state / "browser-sessions"
        self._output_root = paths.state / "browser-captures"

    def status(self, thread_id: str) -> dict[str, Any]:
        key = _safe_thread(thread_id)
        with self._status_lock:
            active = key in self._sessions
        marker = self._marker(key)
        return {
            "thread_id": key,
            "state": "active" if active else ("lost" if marker.exists() else "closed"),
            "worker": self.runtime.status(),
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
                self._write_marker(key)
                with self._status_lock:
                    self._sessions[key] = session
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
                else:
                    from fastmcp import Client
                    from fastmcp.client.transports import StdioTransport
                    from fastmcp.client.elicitation import ElicitResult
                    from langchain.mcp import MCPAdapter

                    async def decline(*_args, **_kwargs):
                        return ElicitResult(action="decline")

                    transport = StdioTransport(
                        str(node),
                        args=[str(cli), "--browser", "msedge", "--isolated", "--no-webmcp",
                              "--image-responses", "omit", "--output-dir", str(output)],
                        env={}, keep_alive=False,
                    )
                    adapter = await stack.enter_async_context(MCPAdapter(Client(
                        transport, timeout=60, init_timeout=30, elicitation_handler=decline,
                    )))
                discovered = await adapter.list_tools()
                tools = {tool.name: tool for tool in discovered if tool.name in BROWSER_TOOL_NAMES}
                if len(tools) != len(set(tools)) or not {"browser_navigate", "browser_snapshot", "browser_take_screenshot"} <= tools.keys():
                    raise HarnessError("The pinned browser worker has an unexpected tool set.", code="browser_worker_schema_changed", status_code=409)
                ready.set_result(_Session(key, tools, output, asyncio.current_task(), close_event))
                await close_event.wait()
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

    def _bind_tool(self, run, session: _Session, original: BaseTool) -> BaseTool:
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
            effect = None
            effects = None
            async with session.io_lock:
                self._refresh_idle(session)
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
                        readable = self.screenshot_reader(run)
                    except Exception:
                        readable = False
                message = f"Screenshot captured from {target}.\n{page}\nSaved screenshot: {virtual_path}"
                if readable is False:
                    message = f"{message}\n{CANNOT_READ_IMAGE}"
                return text_result(message)

        return original.model_copy(update={
            "args_schema": _without_filename(original),
            "coroutine": invoke,
            "description": f"Isolated test browser: {original.description}{_TOOL_GUIDANCE.get(name, '')}",
            "metadata": {**(original.metadata or {}), "browser_worker": True, "browser_read_only": name in BROWSER_READ_TOOLS},
        })

    @staticmethod
    def _observed_url(result: Any) -> str | None:
        content = _text(result)
        match = re.search(r"(?:Page URL:|URL:)\s*(https?://[^\s]+)", content)
        return match.group(1).rstrip("),]") if match else None

    async def _mark_lost(self, session: _Session) -> None:
        with self._status_lock:
            self._sessions.pop(session.thread_id, None)
        if session.idle_task:
            session.idle_task.cancel()
        session.close_event.set()
        await asyncio.shield(session.owner_task)
        # Keep the marker: restart/reset must not imply a live tab survived.

    async def close_session(self, thread_id: str, *, lost: bool = False) -> None:
        key = _safe_thread(thread_id)
        async with self._lock:
            with self._status_lock:
                session = self._sessions.pop(key, None)
            if session:
                if session.idle_task and session.idle_task is not asyncio.current_task():
                    session.idle_task.cancel()
                async with session.io_lock:
                    session.close_event.set()
                    await asyncio.shield(session.owner_task)
            if not lost:
                self._marker(key).unlink(missing_ok=True)
                self._remove_output(key)

    def _remove_output(self, key: str) -> None:
        root = self._output_root.resolve()
        target = (root / key).resolve()
        if target.parent != root:
            raise RuntimeError("Browser output must be a direct child of the owned capture root")
        if target.is_dir():
            shutil.rmtree(target)

    async def reset(self, thread_id: str) -> dict[str, Any]:
        await self.close_session(thread_id)
        return self.status(thread_id)

    async def shutdown(self) -> None:
        for key in list(self._sessions):
            await self.close_session(key, lost=True)
