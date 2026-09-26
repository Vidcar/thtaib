"""Real owned static previews, confinement, and recoverable tool requests."""

from __future__ import annotations

import asyncio
import http.client
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from langchain_core.tools import ToolException

from workbench_backend.agents.tool_errors import recoverable_tool_error
from workbench_backend.errors import HarnessError
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.preview.routes import StaticPreviewRequest, start_static_preview
from workbench_backend.preview.service import PreviewService, _localhost_health


class StaticPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        (self.project / "pages").mkdir(parents=True)
        (self.project / "pages" / "game page.html").write_text('<script src="game.js"></script><h1>Ready</h1>')
        (self.project / "pages" / "game.js").write_text("window.ready = true;")
        (self.project / "empty").mkdir()
        self.service = PreviewService(WorkbenchPaths(self.root / "data"), idle_seconds=60)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.service.shutdown)

    def fetch(self, port, path):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.getheader("Content-type"), response.read()
        finally:
            connection.close()

    def test_exact_entry_assets_health_and_owned_reuse(self):
        info = self.service.start_static("thread_static", str(self.project), "pages/game page.html")
        self.assertEqual(info["kind"], "static")
        self.assertEqual(info["entry_path"], "pages/game page.html")
        self.assertTrue(info["url"].endswith("/pages/game%20page.html"))
        status, mime, body = self.fetch(info["port"], urlsplit(info["url"]).path)
        self.assertEqual(status, 200)
        self.assertIn("text/html", mime)
        self.assertIn(b"<h1>Ready</h1>", body)
        status, mime, body = self.fetch(info["port"], "/pages/game.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", mime)
        self.assertIn(b"window.ready", body)
        self.assertTrue(self.service.inspect("thread_static")["healthy"])
        self.assertFalse(_localhost_health(info["port"], "some-other-owner"))
        again = self.service.start_static("thread_static", str(self.project), "pages/game page.html")
        self.assertEqual(again["pid"], info["pid"])
        for path in ("/empty/", "/../private.txt", "/%2e%2e/private.txt", "/pages%5c..%5c..%5cprivate.txt"):
            self.assertEqual(self.fetch(info["port"], path)[0], 404, path)
        self.assertTrue(self.service.stop("thread_static"))
        self.assertEqual(self.service.status("thread_static")["state"], "closed")
        # Stopped means descendants have released inherited handles too, not
        # merely that the first launcher process has ended.
        (self.root / "data/logs/previews/thread_static.log").unlink()

    def test_invalid_entry_is_a_completed_tool_error_and_next_call_works(self):
        run = SimpleNamespace(thread_id="thread_static", project_path=str(self.project), work_mode="work",
                              tool_mode="live-tool", presented_tools=["start_preview"])
        start = self.service.tools_for_run(run)[0]
        async def invoke():
            failed = await start.ainvoke({"type": "tool_call", "id": "missing", "name": "start_preview", "args": {"entry_path": "missing.html"}})
            self.assertEqual(failed.status, "error")
            self.assertEqual(failed.tool_call_id, "missing")
            successful = await start.ainvoke({"type": "tool_call", "id": "corrected", "name": "start_preview", "args": {"entry_path": "pages/game page.html"}})
            self.assertEqual(successful.status, "success")
            self.assertIn("game%20page.html", successful.content)
        asyncio.run(invoke())
        for entry in ("../outside.html", "file:///page.html", "C:relative.html", "pages/game.js", "NUL.html"):
            with self.assertRaises(HarnessError):
                self.service.start_static("thread_static", str(self.project), entry)

    @unittest.skipUnless(os.name == "nt", "Windows junctions")
    def test_link_escape_rejected_at_entry_and_asset_request(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "private.html").write_text("private")
        alias = self.project / "escape"
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(outside)], capture_output=True, text=True)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.addCleanup(alias.rmdir)
        with self.assertRaises(HarnessError):
            self.service.start_static("thread_static", str(self.project), "escape/private.html")
        info = self.service.start_static("thread_static", str(self.project), "pages/game page.html")
        self.assertEqual(self.fetch(info["port"], "/escape/private.html")[0], 404)

    def test_ui_start_requires_saved_work_chat_and_selected_preview(self):
        conversation = SimpleNamespace(archived=False, project_path=str(self.project), work_mode="plan", presented_tools=["start_preview"])
        store = SimpleNamespace(conversation_id_for_thread=lambda _id: "chat", get_conversation=lambda _id: conversation)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(app_store=store, preview=self.service)))
        body = StaticPreviewRequest(entry_path="pages/game page.html")
        with self.assertRaises(HarnessError) as failure:
            start_static_preview(request, "thread_static", body)
        self.assertEqual(failure.exception.code, "preview_work_required")
        conversation.work_mode = "work"
        conversation.presented_tools = []
        with self.assertRaises(HarnessError) as failure:
            start_static_preview(request, "thread_static", body)
        self.assertEqual(failure.exception.code, "preview_not_selected")
        conversation.presented_tools = ["start_preview"]
        self.assertEqual(start_static_preview(request, "thread_static", body)["kind"], "static")

    def test_declared_mcp_failure_is_recoverable_but_unknown_effect_is_not(self):
        result = recoverable_tool_error(ToolException("Page unavailable"), name="browser_navigate", call_id="call_1")
        self.assertEqual(result.status, "error")
        self.assertEqual(result.tool_call_id, "call_1")
        self.assertIsNone(recoverable_tool_error(HarnessError("Unknown effect", code="unknown", status_code=409), name="browser_click", call_id="call_2"))
        self.assertIsNone(recoverable_tool_error(OSError("storage failure"), name="write_file", call_id="call_3"))


if __name__ == "__main__":
    unittest.main()
