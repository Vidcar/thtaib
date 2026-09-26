"""Owned browser and preview worker boundaries without touching user data."""

from __future__ import annotations

import asyncio
import io
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.tools import ToolException, tool
from PIL import Image
import psutil

from workbench_backend.agents.execution_policy import CURRENT_TOOL_CALL
from workbench_backend.browser.runtime import BrowserRuntime, MCP_VERSION, NODE_SHA256, PACKAGE_MANIFEST
from workbench_backend.browser.service import BrowserSessionService, present_page
from workbench_backend.inference.image_validation import CANNOT_READ_IMAGE
from workbench_backend.errors import HarnessError
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.preview.service import PreviewService


class _FakeRuntime:
    def require_installed(self):
        return Path("node.exe"), Path("cli.js")

    def status(self):
        return {"installed": True}


class BrowserWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.paths = WorkbenchPaths(Path(self.temp.name))
        self.starts = 0
        self.closes = 0
        self.published = []

        @asynccontextmanager
        async def factory(_node, _cli, output):
            self.starts += 1
            page_url = None

            @tool("browser_navigate")
            async def navigate(url: str) -> str:
                """Navigate to a web page."""
                nonlocal page_url
                page_url = url
                return f"Page URL: {url}\n"

            @tool("browser_snapshot")
            async def snapshot(filename: str | None = None) -> str:
                """Read an accessible page snapshot."""
                return f"Page URL: {page_url}\nheading: Example" if page_url else "heading: Example"

            @tool("browser_click")
            async def click(target: str) -> str:
                """Click a control."""
                nonlocal page_url
                page_url = target if target.startswith("http") else None
                return "Clicked"

            @tool("browser_take_screenshot")
            async def screenshot(filename: str | None = None) -> str:
                """Capture page image."""
                image = Image.new("RGB", (8, 8), "red")
                image.save(output / f"capture-{self.starts}.png")
                return "Saved page image"

            class Adapter:
                async def list_tools(self):
                    return [navigate, snapshot, click, screenshot]

            try:
                yield Adapter()
            finally:
                self.closes += 1

        def publish(run, path, **kwargs):
            self.published.append((run.id, path, kwargs))
            return object(), "/captures/asset_red.png"

        self.service = BrowserSessionService(self.paths, capture_publisher=publish, runtime=_FakeRuntime(), adapter_factory=factory, idle_seconds=120)
        self.run = SimpleNamespace(id="run_1", thread_id="thread_1", work_mode="work", tool_mode="live-tool", presented_tools=["browser_navigate", "browser_snapshot", "browser_click", "browser_take_screenshot"])

    async def asyncTearDown(self):
        await self.service.shutdown()
        self.temp.cleanup()

    async def test_session_survives_turns_and_marks_restart_lost(self):
        async with self.service.open_tools(self.run) as tools:
            by_name = {item.name: item for item in tools}
            self.assertNotIn("filename", by_name["browser_snapshot"].args_schema["properties"])
            await by_name["browser_navigate"].coroutine(url="http://127.0.0.1:8080/")
            token = CURRENT_TOOL_CALL.set("call_capture_1")
            try:
                capture = await by_name["browser_take_screenshot"].coroutine()
            finally:
                CURRENT_TOOL_CALL.reset(token)
            self.assertIn("/captures/asset_red.png", capture)
            self.assertIn("heading: Example", capture)
            self.assertNotIn("read_file", capture)
            self.assertEqual(self.published[0][2]["target"], "http://127.0.0.1:8080/")
            self.assertEqual(self.published[0][2]["source_tool_call_id"], "call_capture_1")
            await by_name["browser_click"].coroutine(target="http://127.0.0.1:8080/after-click")
            await by_name["browser_take_screenshot"].coroutine()
            self.assertEqual(self.published[-1][2]["target"], "http://127.0.0.1:8080/after-click")
            await by_name["browser_click"].coroutine(target="unknown")
            await by_name["browser_take_screenshot"].coroutine()
            self.assertEqual(self.published[-1][2]["target"], "browser page (URL unavailable)")
            self.service.screenshot_reader = lambda _run: False
            denied = await by_name["browser_take_screenshot"].coroutine()
            self.assertIn(CANNOT_READ_IMAGE, denied)
            self.assertNotIn("probe", denied)
            self.service.screenshot_reader = lambda _run: True
            allowed = await by_name["browser_take_screenshot"].coroutine()
            self.assertNotIn(CANNOT_READ_IMAGE, allowed)
            def broken_publisher(*_args, **_kwargs):
                raise RuntimeError("fixture storage failure")
            self.service.capture_publisher = broken_publisher
            with self.assertRaises(ToolException):
                await by_name["browser_take_screenshot"].coroutine()
            self.assertEqual(list(self.paths.state.joinpath("browser-captures", "thread_1").iterdir()), [])
            with self.assertRaises(ToolException):
                await by_name["browser_snapshot"].coroutine(filename="../../private.txt")
            with self.assertRaises(ToolException):
                await by_name["browser_navigate"].coroutine(url="file:///C:/private.txt")
        async with self.service.open_tools(self.run):
            self.assertEqual(self.starts, 1)
        self.assertEqual(self.service.status("thread_1")["state"], "active")
        await self.service.shutdown()
        self.assertEqual(self.service.status("thread_1")["state"], "lost")
        with self.assertRaises(HarnessError):
            async with self.service.open_tools(self.run):
                pass
        await self.service.reset("thread_1")
        self.assertEqual(self.service.status("thread_1")["state"], "closed")


class PageObservationTests(unittest.TestCase):
    def test_snapshot_file_is_inlined_and_bounded_to_citable_lines(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            snapshot = folder / "page.yml"
            snapshot.write_text("\n".join(
                ["- heading \"City news\" [level=1]"]
                + [f"- link \"Result {index}\" [ref=e{index}]" for index in range(800)]
            ), encoding="utf-8")
            observed = present_page(
                f"Page URL: https://news.example/uk\nPage Title: UK news\n- [Snapshot]({snapshot})",
                folder,
            )
            self.assertIn("heading \"City news\"", observed)
            self.assertIn("link \"Result 0\"", observed)
            self.assertNotIn(str(snapshot), observed)
            self.assertIn("browser_find", observed)
            self.assertLess(len(observed), 13_000)

    def test_consent_dialog_is_named_and_not_accepted(self):
        text = "\n".join([
            "Page URL: https://www.bbc.co.uk/news/uk",
            "Page Title: UK news",
            "- heading \"Cookies on the BBC website\" [active] [level=2]",
            "- button \"Reject additional cookies\" [ref=e4]",
            "- heading \"Man City ruling\" [level=3]",
        ])
        observed = present_page(text, Path("."))
        self.assertIn("consent dialog is open", observed)
        self.assertIn("was not clicked", observed)
        self.assertIn("Man City ruling", observed)
        self.assertIn("Reject additional cookies", observed)

    def test_blocked_browser_is_not_described_as_results(self):
        observed = present_page("Page URL: https://www.google.com/sorry/index\nPage Title: unusual traffic", Path("."))
        self.assertIn("refused the automated browser", observed)
        self.assertIn("not a search-result page", observed)


class BrowserRuntimeTests(unittest.TestCase):
    def test_redirect_result_uses_observed_destination(self):
        result = ([{"type": "text", "text": "### Page\n- Page URL: http://127.0.0.1:54321/final\n### Snapshot"}], None)
        self.assertEqual(BrowserSessionService._observed_url(result), "http://127.0.0.1:54321/final")

    def test_pinned_manifest_and_missing_runtime(self):
        lock = json.loads((PACKAGE_MANIFEST / "package-lock.json").read_text(encoding="utf-8"))
        package = lock["packages"]["node_modules/@playwright/mcp"]
        self.assertEqual(package["version"], MCP_VERSION)
        self.assertTrue(package["integrity"].startswith("sha512-"))
        self.assertEqual(len(NODE_SHA256), 64)
        with tempfile.TemporaryDirectory() as root:
            runtime = BrowserRuntime(WorkbenchPaths(Path(root)))
            with self.assertRaises(HarnessError) as failure:
                runtime.require_installed()
            self.assertEqual(failure.exception.code, "browser_worker_missing")

    def test_node_archive_digest_is_checked(self):
        with tempfile.TemporaryDirectory() as root, patch("urllib.request.urlopen", return_value=io.BytesIO(b"wrong archive")):
            with self.assertRaises(HarnessError) as failure:
                BrowserRuntime._download_node(Path(root) / "node.zip")
            self.assertEqual(failure.exception.code, "browser_node_hash_failed")


class PreviewWorkerTests(unittest.TestCase):
    @staticmethod
    def _port() -> int:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    def test_owned_server_starts_and_stops(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            (project / "index.html").write_text("preview ready", encoding="utf-8")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            service = PreviewService(WorkbenchPaths(Path(root) / "data"), idle_seconds=60)
            command = [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"]
            try:
                result = service.start("thread_preview", str(project), command, port)
                self.assertEqual(result["state"], "active")
                self.assertEqual(service.status("thread_preview")["state"], "active")
                inspection = service.inspect("thread_preview")
                self.assertTrue(inspection["healthy"])
                self.assertIn("GET /", inspection["recent_log"])
                self.assertLessEqual(len(inspection["recent_log"]), 4_000)
                self.assertEqual(service.start("thread_preview", str(project), command, port)["state"], "active")
            finally:
                self.assertTrue(service.stop("thread_preview"))
                service.shutdown()
            self.assertEqual(service.status("thread_preview")["state"], "closed")

    def test_projectless_run_has_no_preview_tools(self):
        with tempfile.TemporaryDirectory() as root:
            service = PreviewService(WorkbenchPaths(Path(root)))
            run = SimpleNamespace(project_path=None, work_mode="work", tool_mode="live-tool", presented_tools=list(("start_preview", "stop_preview")))
            self.assertEqual(service.tools_for_run(run), [])

    def test_restart_reports_lost_preview_without_replaying_launch(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            (project / "index.html").write_text("preview ready", encoding="utf-8")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            paths = WorkbenchPaths(Path(root) / "data")
            owner = PreviewService(paths, idle_seconds=60)
            recovered = PreviewService(paths, idle_seconds=60)
            command = [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"]
            try:
                owner.start("thread_preview", str(project), command, port)
                self.assertEqual(recovered.status("thread_preview")["state"], "lost")
                with self.assertRaises(HarnessError) as raised:
                    recovered.start("thread_preview", str(project), command, port)
                self.assertEqual(raised.exception.code, "preview_session_lost")
            finally:
                self.assertTrue(owner.stop("thread_preview"))
                owner.shutdown()
            self.assertEqual(recovered.reset_lost("thread_preview")["state"], "closed")

    @unittest.skipUnless(sys.platform == "win32", "Windows Job Object ownership")
    def test_launcher_exit_ends_its_child_server(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            port = self._port()
            pid_file = project / "child.pid"
            script = (
                "import subprocess,sys,pathlib; "
                "child=subprocess.Popen([sys.executable,'-m','http.server',sys.argv[1],"
                "'--bind','127.0.0.1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
                "pathlib.Path(sys.argv[2]).write_text(str(child.pid))"
            )
            service = PreviewService(WorkbenchPaths(Path(root) / "data"), idle_seconds=60)
            try:
                try:
                    service.start("thread_preview", str(project),
                        [sys.executable, "-c", script, str(port), str(pid_file)], port)
                except HarnessError as exc:
                    self.assertIn(exc.code, {"preview_exited", "preview_not_ready"})
                deadline = time.monotonic() + 5
                while not pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(pid_file.exists())
                child_pid = int(pid_file.read_text())
                # A launcher that exits before a later turn must not leave its
                # child server alive, even if the first health probe raced it.
                service.status("thread_preview")
                service.stop("thread_preview")
                deadline = time.monotonic() + 5
                while psutil.pid_exists(child_pid) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(psutil.pid_exists(child_pid))
            finally:
                service.shutdown()

    def test_failed_start_exposes_bounded_log_tail(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            service = PreviewService(WorkbenchPaths(Path(root) / "data"), idle_seconds=60)
            with self.assertRaises(HarnessError):
                service.start("thread_preview", str(project),
                    [sys.executable, "-c", "print('preview-failure-sentinel',flush=True)"], self._port())
            inspection = service.inspect("thread_preview")
            self.assertEqual(inspection["state"], "closed")
            self.assertIn("preview-failure-sentinel", inspection["recent_log"])
            self.assertLessEqual(len(inspection["recent_log"]), 4_000)
            run = SimpleNamespace(thread_id="thread_preview", project_path=str(project),
                work_mode="work", tool_mode="live-tool", presented_tools=["preview_status"])
            status_tool = service.tools_for_run(run)[0]
            agent_view = json.loads(asyncio.run(status_tool.coroutine()))
            self.assertIn("preview-failure-sentinel", agent_view["recent_log"])

    def test_idle_expiry_stops_owned_server(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            port = self._port()
            service = PreviewService(WorkbenchPaths(Path(root) / "data"), idle_seconds=1)
            try:
                service.start("thread_preview", str(project),
                    [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], port)
                deadline = time.monotonic() + 5
                while service.status("thread_preview")["state"] != "closed" and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertEqual(service.status("thread_preview")["state"], "closed")
                with socket.socket() as probe:
                    self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0)
            finally:
                service.shutdown()


class PreviewCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_launch_cleans_up_after_thread_finishes(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            port = PreviewWorkerTests._port()
            service = PreviewService(WorkbenchPaths(Path(root) / "data"), idle_seconds=60)
            original_start = service.start
            entered = threading.Event()
            release = threading.Event()

            def delayed_start(*args):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Test launch was not released")
                return original_start(*args)

            run = SimpleNamespace(thread_id="thread_preview", project_path=str(project),
                work_mode="work", tool_mode="live-tool", presented_tools=["start_preview"])
            try:
                with patch.object(service, "start", side_effect=delayed_start):
                    start_tool = service.tools_for_run(run)[0]
                    action = asyncio.create_task(start_tool.coroutine(
                        command=[sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                        port=port))
                    self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                    action.cancel()
                    release.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await action
                self.assertEqual(service.status("thread_preview")["state"], "closed")
                with socket.socket() as probe:
                    self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0)
            finally:
                release.set()
                service.shutdown()
