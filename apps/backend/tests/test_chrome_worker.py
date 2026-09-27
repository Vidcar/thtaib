"""Pinned browser ownership and actual Chrome/MCP/rail interoperability."""

from __future__ import annotations

import asyncio
import base64
import io
import os
import tempfile
import threading
import unittest
from contextlib import AsyncExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import psutil
from fastmcp import Client
from langchain.mcp import MCPAdapter
from PIL import Image

from workbench_backend.browser.runtime import BrowserRuntime, PACKAGE_MANIFEST
from workbench_backend.browser.service import BROWSER_TOOL_NAMES, BrowserSessionService
from workbench_backend.browser.schemas import BrowserActionRequest
from workbench_backend.browser.worker_client import BrowserWorkerClient
from workbench_backend.errors import HarnessError
from workbench_backend.paths import WorkbenchPaths


class BrowserRuntimeReadinessTests(unittest.TestCase):
    def test_worker_installation_and_chrome_availability_are_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = BrowserRuntime(WorkbenchPaths(Path(temporary)))
            runtime.node.parent.mkdir(parents=True)
            runtime.node.write_bytes(b"node fixture")
            runtime.cli.parent.mkdir(parents=True)
            runtime.cli.write_bytes(b"mcp fixture")
            runtime.worker.write_bytes((PACKAGE_MANIFEST / "worker.js").read_bytes())
            runtime.tool_schemas.write_bytes((PACKAGE_MANIFEST / "tool-schemas.json").read_bytes())
            with patch.object(BrowserRuntime, "chrome", new_callable=property, fget=lambda _self: None):
                status = runtime.status()
                self.assertTrue(status["installed"])
                self.assertFalse(status["chrome_available"])
                with self.assertRaises(HarnessError) as refused:
                    runtime.require_installed()
                self.assertEqual(refused.exception.code, "browser_chrome_missing")

    def test_old_worker_requires_explicit_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = BrowserRuntime(WorkbenchPaths(Path(temporary)))
            runtime.node.parent.mkdir(parents=True)
            runtime.node.write_bytes(b"fixture")
            runtime.cli.parent.mkdir(parents=True)
            runtime.cli.write_bytes(b"fixture")
            runtime.worker.write_bytes(b"old worker")
            self.assertFalse(runtime.status()["installed"])
            self.assertEqual(runtime.status()["reason"], "browser_worker_missing")


class _BrowserFixture(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/download":
            body = b"Downloaded through the owned Chrome context."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Disposition", 'attachment; filename="browser-result.txt"')
        else:
            body = ("""<!doctype html><title>Owned browser fixture</title>
<style>body{margin:0}input,button,a{position:absolute;left:20px;height:30px}
#name{top:20px}#popup{top:70px}#dialog{top:110px}#upload{top:150px}
#download{top:200px}#drag{position:absolute;top:250px;left:20px;width:40px;height:40px;background:red;touch-action:none}
#drop{position:absolute;top:250px;left:200px;width:100px;height:80px;background:green}
#width{position:absolute;top:350px}#value{position:absolute;top:390px}#cookie{position:absolute;top:430px}
@media(max-width:500px){body{background:#ddeeff}}</style>
<input id="name" aria-label="Name"><button id="popup" onclick="window.open('/page')">Popup</button>
<button id="dialog" onclick="alert('Inside rail')">Dialog</button><input id="upload" type="file" aria-label="Upload">
<a id="download" href="/download">Download</a><div id="drag">Drag</div><div id="drop">Drop target</div>
<p id="width"></p><p id="value"></p><p id="cookie">Cookie: COOKIE_TEXT</p>
<script>function width(){document.querySelector('#width').textContent='Viewport: '+innerWidth+' x '+innerHeight}width();addEventListener('resize',width);
document.querySelector('#name').addEventListener('input',e=>document.querySelector('#value').textContent='Name: '+e.target.value);
document.querySelector('#upload').addEventListener('change',e=>document.querySelector('#value').textContent='Upload: '+e.target.files[0].name);
let dragging=false;document.querySelector('#drag').onpointerdown=()=>dragging=true;
document.querySelector('#drop').onpointerup=()=>{if(dragging)document.querySelector('#value').textContent='Dragged successfully';dragging=false};</script>""").replace("COOKIE_TEXT", self.headers.get("Cookie", "none")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            if self.path == "/set-cookie":
                self.send_header("Set-Cookie", "chat_signin=retained; Max-Age=3600; Path=/; SameSite=Lax")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


class ChromeIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        product = Path(os.environ.get("LOCALAPPDATA", "")) / "LocalAIWorkbench"
        self.runtime = BrowserRuntime(WorkbenchPaths(product))
        if not self.runtime.node.is_file() or self.runtime.chrome is None or not (PACKAGE_MANIFEST / "node_modules/@playwright/mcp").is_dir():
            self.skipTest("Actual Chrome and the explicitly installed pinned development worker are required.")
        scratch = Path(__file__).resolve().parents[3] / ".scratch"
        self.temp = tempfile.TemporaryDirectory(prefix="chrome-worker-", dir=scratch)
        self.root = Path(self.temp.name)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _BrowserFixture)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.stack = AsyncExitStack()
        self.workers = []

    async def asyncTearDown(self):
        if not hasattr(self, "stack"):
            return
        for worker in self.workers:
            await worker.close()
        await self.stack.aclose()
        await asyncio.to_thread(self.server.shutdown)
        self.server.server_close()
        self.server_thread.join(timeout=3)
        self.temp.cleanup()

    async def worker(self, profile="chat-a"):
        worker = BrowserWorkerClient(self.runtime.node, PACKAGE_MANIFEST / "worker.js", self.root / profile, self.root / f"output-{len(self.workers)}", chrome_path=self.runtime.chrome)
        self.workers.append(worker)
        await worker.transport.connect()
        await worker.connect()
        self.assertIsNone((await worker.get_state())["session_id"])
        self.assertFalse(any(child.name().lower() == "chrome.exe" for child in psutil.Process(worker.pid).children(recursive=True)))
        adapter = await self.stack.enter_async_context(MCPAdapter(Client(worker.transport, timeout=35, init_timeout=15)))
        await worker.connect()
        discovered = await adapter.list_tools()
        tools = {item.name: item for item in discovered}
        return worker, tools

    async def until(self, callback, predicate, seconds=8):
        deadline = asyncio.get_running_loop().time() + seconds
        while asyncio.get_running_loop().time() < deadline:
            value = await callback()
            if predicate(value):
                return value
            await asyncio.sleep(.025)
        self.fail("The owned Chrome observation did not reach the expected state.")

    async def act(self, worker, action):
        state = await worker.get_state()
        return await worker.action({"session_id": state["session_id"], "page_id": state["active_page_id"], "revision": state["revision"], "action": action})

    async def test_actual_context_frames_manual_input_tabs_files_and_cleanup(self):
        worker, tools = await self.worker()
        await tools["browser_navigate"].coroutine(url=self.url + "/page")
        state = await worker.get_state()
        self.assertEqual(state["viewport"], {"width": 1440, "height": 900})
        self.assertEqual(len(state["tabs"]), 1)
        await worker.set_streaming(True)
        frame = (await self.until(worker.poll, lambda value: bool(value.get("frame"))))["frame"]
        with Image.open(io.BytesIO(base64.b64decode(frame["data"]))) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertLessEqual(image.width, 1280)
        await self.act(worker, {"type": "pointer", "event": "click", "x": 70, "y": 30})
        await self.act(worker, {"type": "text", "text": "same Chrome page"})
        snapshot = str(await tools["browser_snapshot"].coroutine())
        self.assertIn("same Chrome page", snapshot)
        stale = await worker.get_state()
        await self.act(worker, {"type": "resize", "width": 390, "height": 844})
        snapshot = str(await tools["browser_snapshot"].coroutine())
        self.assertIn("Viewport: 390 x 844", snapshot)
        with self.assertRaises(HarnessError) as refused:
            await worker.action({"session_id": stale["session_id"], "page_id": stale["active_page_id"], "revision": stale["revision"], "action": {"type": "text", "text": "obsolete"}})
        self.assertEqual(refused.exception.code, "browser_stale_action")
        frame = (await self.until(worker.poll, lambda value: value.get("frame", {}).get("viewport", {}).get("width") == 390))["frame"]
        self.assertEqual(frame["viewport"], {"width": 390, "height": 844})
        await self.act(worker, {"type": "pointer", "event": "down", "x": 35, "y": 265})
        await self.act(worker, {"type": "pointer", "event": "move", "x": 220, "y": 265})
        await self.act(worker, {"type": "pointer", "event": "up", "x": 220, "y": 265})
        self.assertIn("Dragged successfully", str(await tools["browser_snapshot"].coroutine()))
        await self.act(worker, {"type": "pointer", "event": "click", "x": 50, "y": 80})
        state = await self.until(worker.get_state, lambda value: len(value["tabs"]) == 2)
        self.assertEqual(state["tabs"][0]["url"], state["tabs"][1]["url"])
        self.assertNotEqual(state["tabs"][0]["page_id"], state["tabs"][1]["page_id"])
        await worker.set_active(0)
        await tools["browser_tabs"].coroutine(action="select", index=0)
        await self.act(worker, {"type": "pointer", "event": "click", "x": 50, "y": 120})
        state = await self.until(worker.get_state, lambda value: bool(value["dialog"]))
        self.assertEqual(state["dialog"]["message"], "Inside rail")
        await tools["browser_handle_dialog"].coroutine(accept=True)
        await worker.acknowledge_modal("dialog")
        self.assertIsNone((await worker.get_state())["dialog"])
        await self.act(worker, {"type": "pointer", "event": "click", "x": 70, "y": 160})
        await self.until(worker.get_state, lambda value: bool(value["file_chooser"]))
        upload = worker.output_dir / "upload.txt"
        upload.write_text("Scoped browser upload", encoding="utf8")
        await tools["browser_file_upload"].coroutine(paths=[str(upload)])
        await worker.acknowledge_modal("file_chooser")
        self.assertIn("Upload: upload.txt", str(await tools["browser_snapshot"].coroutine()))
        await self.act(worker, {"type": "pointer", "event": "click", "x": 50, "y": 210})
        completed = await self.until(worker.drain_downloads, lambda value: bool(value))
        self.assertEqual(Path(completed[0]["path"]).read_bytes(), b"Downloaded through the owned Chrome context.")
        await worker.ack_download(completed[0]["download_id"])
        self.assertFalse(Path(completed[0]["path"]).exists())
        owned_pids = [worker.pid, *[child.pid for child in psutil.Process(worker.pid).children(recursive=True)]]
        await worker.set_streaming(False)
        self.assertNotIn("frame", await worker.poll())
        await worker.close()
        self.assertFalse(any(psutil.pid_exists(pid) for pid in owned_pids), owned_pids)

    async def test_profiles_retain_signin_on_relaunch_and_isolate_chats(self):
        worker, tools = await self.worker()
        await tools["browser_navigate"].coroutine(url=self.url + "/set-cookie")
        await tools["browser_navigate"].coroutine(url=self.url + "/page")
        self.assertIn("chat_signin=retained", str(await tools["browser_snapshot"].coroutine()))
        await worker.close()
        reopened, reopened_tools = await self.worker()
        state = await reopened.start()
        self.assertEqual(state["tabs"][0]["url"], "about:blank")
        await reopened_tools["browser_navigate"].coroutine(url=self.url + "/page")
        self.assertIn("chat_signin=retained", str(await reopened_tools["browser_snapshot"].coroutine()))
        isolated, isolated_tools = await self.worker("chat-b")
        await isolated_tools["browser_navigate"].coroutine(url=self.url + "/page")
        self.assertNotIn("chat_signin=retained", str(await isolated_tools["browser_snapshot"].coroutine()))

    async def test_browser_service_uses_same_mcp_page_and_closes_without_scope_leaks(self):
        paths = WorkbenchPaths(self.root / "service").ensure()
        runtime = self.runtime

        class SourceRuntime:
            def require_installed(self):
                return runtime.node, PACKAGE_MANIFEST / "worker.js"
            def status(self):
                return {**runtime.status(), "installed": True}
            def read_tool_schemas(self):
                import json
                return json.loads((PACKAGE_MANIFEST / "tool-schemas.json").read_text(encoding="utf8"))["tools"]

        project = self.root / "permitted-project"
        project.mkdir()
        (project / "upload.txt").write_text("Project-scoped browser upload", encoding="utf8")
        retained = []
        class FixtureAssets:
            def session_for_thread(self, _thread):
                return SimpleNamespace(id="fixture-session", project_path=str(project), area_project_path=None, document_asset_ids=[], draft=None)
            def retain_browser_download(self, _thread, path, **options):
                retained.append(path.read_bytes())
                return SimpleNamespace(id="fixture-download", filename=options["filename"])
            def _source_url(self, _asset):
                return "/assets/fixture-download/content"

        service = BrowserSessionService(paths, runtime=SourceRuntime(), assets=FixtureAssets())
        run = SimpleNamespace(id="browser-run", thread_id="browser-thread", work_mode="work", tool_mode="live-tool", presented_tools=list(BROWSER_TOOL_NAMES))
        try:
            async with service.open_tools(run) as available:
                tools = {item.name: item for item in available}
                self.assertEqual(service.status(run.thread_id)["state"], "closed")
                self.assertFalse((paths.state / "browser-profiles" / run.thread_id).exists())
                await tools["browser_navigate"].coroutine(url=self.url + "/page")
                state = service.status(run.thread_id)
                self.assertEqual(state["tabs"][0]["url"], self.url + "/page")
                await tools["browser_resize"].coroutine(width=768, height=1024)
                self.assertEqual(service.status(run.thread_id)["viewport"], {"width": 768, "height": 1024})
                await tools["browser_resize"].coroutine(width=1440, height=900)
                session = service._sessions[run.thread_id]
                session.control = "user"
                await self.act(session.worker, {"type": "pointer", "event": "click", "x": 70, "y": 30})
                await self.act(session.worker, {"type": "text", "text": "service shares page"})
                session.control = "agent"
                self.assertIn("service shares page", str(await tools["browser_snapshot"].coroutine()))
                session.control = "user"
                async def manual(action):
                    await service._observe_session(session)
                    current = service.status(run.thread_id)
                    return await service.manual_action(run.thread_id, BrowserActionRequest.model_validate({
                        "session_id": current["session_id"], "page_id": current["active_page_id"], "revision": current["revision"], "action": action,
                    }))
                shown = await manual({"type": "pointer", "event": "click", "x": 50, "y": 120})
                self.assertEqual(shown["dialog"]["message"], "Inside rail")
                await manual({"type": "dialog", "accept": True})
                await manual({"type": "pointer", "event": "click", "x": 70, "y": 160})
                await manual({"type": "upload", "project_paths": ["upload.txt"]})
                session.control = "agent"
                self.assertIn("upload.txt", str(await tools["browser_snapshot"].coroutine()))
                session.control = "user"
                await manual({"type": "pointer", "event": "click", "x": 50, "y": 210})
                await self.until(lambda: service.poll_view(run.thread_id), lambda _value: bool(retained))
                self.assertEqual(retained[0], b"Downloaded through the owned Chrome context.")
                await service.view_subscription(run.thread_id, True)
                observed = await self.until(lambda: service.poll_view(run.thread_id), lambda value: bool(value.get("frame")))
                self.assertEqual(observed["frame"]["session_id"], state["session_id"])
                await service.view_subscription(run.thread_id, False)
            await service.close_session(run.thread_id)
            self.assertEqual(service.status(run.thread_id)["state"], "closed")
            profile = paths.state / "browser-profiles" / run.thread_id
            self.assertTrue(profile.is_dir())
            await service.start(run.thread_id)
            reset_worker = service._sessions[run.thread_id].worker
            reset_pids = [reset_worker.pid, *[child.pid for child in psutil.Process(reset_worker.pid).children(recursive=True)]]
            await service.reset(run.thread_id)
            self.assertFalse(profile.exists())
            self.assertFalse(any(psutil.pid_exists(pid) for pid in reset_pids), reset_pids)
            await service.start(run.thread_id)
            await service.delete_chat(run.thread_id)
            self.assertFalse(profile.exists())
        finally:
            await service.shutdown()
