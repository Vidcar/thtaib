"""Retained evidence survives bounded previews, long lines and owner changes."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from langchain_core.tools import ToolException, StructuredTool
from pydantic import ValidationError

from workbench_backend.agents.owned_shell import OwnedLocalShellBackend
from workbench_backend.agents.tool_results import OwnedToolResults, bounded_preview, MAX_READ_SERIALIZED_BYTES
from workbench_backend.browser.service import present_page, browser_arguments_schema, redact_browser_evidence, redact_browser_source, _inline_snapshot_files, BrowserSessionService, _Session
from workbench_backend.connections.public_web import read_web_page, search_web
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.preview.service import PreviewService, PreviewStartInput


class ToolEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = WorkbenchPaths(Path(self.temp.name) / "data").ensure()
        self.run = SimpleNamespace(id="run_evidence", thread_id="thread_evidence", parent_run_id=None)
        self.results = OwnedToolResults(self.paths, self.run)

    def test_long_single_line_unicode_search_and_character_continuation(self):
        text = "α😀" * 25_000 + " late-failure-needle " + "終" * 10_000
        retained = self.results.retain(text, source={"tool": "execute", "exit_code": 7})
        found = self.results.read(retained["path"], query="late-failure-needle")
        self.assertEqual(found["match_count"], 1)
        self.assertIn("late-failure-needle", found["matches"][0]["content"])
        first = self.results.read(retained["path"], char_count=12_000)
        self.assertEqual(first["content"], text[:first["end_char"]])
        self.assertLessEqual(len(json.dumps(first, ensure_ascii=False).encode("utf-8")), MAX_READ_SERIALIZED_BYTES)
        second = self.results.read(retained["path"], start_char=first["next_start_char"], char_count=50)
        self.assertEqual(second["content"], text[first["end_char"]:first["end_char"] + 50])
        self.assertEqual(retained["retained_utf8_bytes"], len(text.encode("utf-8")))

    def test_scope_helper_hash_and_path_boundary(self):
        handle = self.results.retain("owned", source={"tool": "snapshot"})
        for other in [SimpleNamespace(id="other", thread_id="other", parent_run_id=None),
                      SimpleNamespace(id="child", thread_id=self.run.thread_id, parent_run_id=self.run.id)]:
            with self.assertRaises(ToolException):
                OwnedToolResults(self.paths, other).read(handle["path"])
        for path in ["/large_tool_results/owned/../../private.txt", "/project/private.txt", handle["path"].replace("owned/", "owned\\")]:
            with self.assertRaises(ToolException):
                self.results.read(path)
        (self.results.root / Path(handle["path"]).name).write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ToolException, "changed"):
            self.results.read(handle["path"])

    def test_retention_limit_reports_coverage_and_keeps_late_failure(self):
        text = "start " + "x" * 10_000 + " late failure"
        handle = self.results.retain(text, source={"tool": "execute"}, limit=1024)
        self.assertFalse(handle["complete"])
        self.assertLessEqual(handle["retained_utf8_bytes"], 1024)
        self.assertIn("late failure", self.results.read(handle["path"])["content"])
        self.assertGreater(handle["acquired_utf8_bytes"], handle["retained_utf8_bytes"])
        self.assertLessEqual(len(bounded_preview("😀" * 1000, 100, tail=True).encode("utf-8")), 100)

    def test_native_nonwindows_acquisition_is_retained_before_its_preview(self):
        project = Path(self.temp.name) / "project"
        project.mkdir()
        backend = OwnedLocalShellBackend(root_dir=str(project), virtual_mode=True, max_output_bytes=12_000,
            result_retainer=self.results.retain)
        output = "early-context " + "😀" * 20_000 + " late-error"
        with patch("workbench_backend.agents.owned_shell.sys.platform", "linux"), patch("subprocess.run", return_value=subprocess.CompletedProcess("fixture", 7, output, "")):
            result = backend.execute("fixture")
        self.assertEqual(result.exit_code, 7)
        self.assertTrue(result.truncated)
        self.assertLessEqual(len(result.output.encode("utf-8")), 12_000)
        handle = json.loads(result.output.split("Retained result: ", 1)[1])
        self.assertTrue(handle["complete"])
        self.assertEqual(self.results.read(handle["path"], query="late-error")["match_count"], 1)
        self.assertEqual(self.results.read(handle["path"], query="early-context")["match_count"], 1)
        self.assertEqual(backend._max_output_bytes, 12_000)

    def test_large_browser_paragraph_survives_without_navigation(self):
        page = "Page URL: https://example.test/doc\nPage Title: Document\n- paragraph: " + "x" * 40_000 + " unique-table-fact"
        output = Path(self.temp.name) / "captures"
        output.mkdir()
        preview = present_page(page, output, result_retainer=self.results.retain, source={"tool": "browser_snapshot", "page_id": "page_1"})
        self.assertNotIn("unique-table-fact", preview)
        metadata = json.loads(preview.split("Retained result: ", 1)[1])
        found = self.results.read(metadata["path"], query="unique-table-fact")
        self.assertEqual(found["result"]["source"]["page_id"], "page_1")
        self.assertEqual(found["result"]["source"]["url"], "https://example.test/doc")
        self.assertEqual(found["match_count"], 1)

    def test_browser_schema_bounds_and_secret_redaction(self):
        wait = browser_arguments_schema("browser_wait_for", {"properties": {"time": {"type": "number"}, "filename": {"type": "string"}}, "required": ["filename"]})
        self.assertEqual(wait["properties"]["time"]["maximum"], 30)
        self.assertNotIn("filename", wait["properties"])
        clean = redact_browser_evidence('Authorization: Bearer private\nCookie: session=secret\n{"password":"private", "access_token":"private", "message":"useful error"}\nhttps://example.test/api?api_key=private&ok=yes')
        self.assertNotIn("private", clean)
        self.assertNotIn("session=secret", clean)
        self.assertIn("useful error", clean)
        self.assertIn("ok=yes", clean)
        apostrophe = redact_browser_evidence("{'password': 'private', 'message': \"don't retry\"}\nclient_secret=private&ok=yes")
        self.assertNotIn("private", apostrophe)
        self.assertIn("don't retry", apostrophe)
        source = redact_browser_source({"url": "https://example.test/api?token=private&ok=yes", "dialog": {"text": "Bearer private"}})
        self.assertNotIn("private", json.dumps(source))

    def test_binary_network_body_is_explicit_and_raw_file_is_removed(self):
        output = Path(self.temp.name) / "captures"
        output.mkdir()
        body = output / "response-123.png"
        body.write_bytes(b"\x89PNG\x00private")
        rendered = _inline_snapshot_files("### Result\nresponse-123.png\n", output, cleanup=True)
        self.assertIn("Binary response body", rendered)
        self.assertIn("text extraction is unavailable", rendered)
        self.assertNotIn("private", rendered)
        self.assertFalse(body.exists())

    @unittest.skipUnless(os.name == "nt", "Windows owned shell")
    def test_native_shell_retains_late_nonzero_error_and_earlier_context(self):
        script = Path(self.temp.name) / "long_output.py"
        script.write_text("import sys\nprint('earlier-context ' + 'x'*20000)\nprint('late-error',file=sys.stderr)\nsys.exit(7)\n", encoding="utf-8")
        backend = OwnedLocalShellBackend(root_dir=Path(self.temp.name), inherit_env=True,
            max_output_bytes=1024, result_retainer=self.results.retain)
        import sys
        result = backend.execute(f'"{sys._base_executable}" "{script}"', timeout=10)
        self.assertEqual(result.exit_code, 7)
        self.assertTrue(result.truncated)
        self.assertIn("late-error", result.output)
        metadata = json.loads(result.output.split("Retained result: ", 1)[1].split("\n\nExit code:", 1)[0])
        self.assertEqual(self.results.read(metadata["path"], query="earlier-context")["match_count"], 1)
        self.assertEqual(self.results.read(metadata["path"], query="late-error")["match_count"], 1)

    def test_preview_log_has_current_launch_identity_and_older_continuation(self):
        service = PreviewService(self.paths)
        self.addCleanup(service.shutdown)
        service._log_root.mkdir(parents=True, exist_ok=True)
        log = service._log_root / (self.run.thread_id + ".log")
        log.write_text("Workbench preview launch " + "a" * 32 + "\nold-error " + "x" * 15000 + "\nlatest", encoding="utf-8")
        info = service.inspect(self.run.thread_id, run=self.run)
        self.assertNotIn("old-error", info["recent_log"])
        self.assertEqual(info["launch_id"], "a" * 32)
        self.assertEqual(info["retained_log"]["source"]["launch_id"], info["launch_id"])
        self.assertEqual(self.results.read(info["retained_log"]["path"], query="old-error")["match_count"], 1)

    def test_preview_input_exclusivity_and_bounds_are_executable(self):
        for args in [{}, {"entry_path": "x.html", "port": 1024}, {"command": ["python"]},
                     {"command": ["python"], "port": 1000}, {"command": ["python", "bad\x00arg"], "port": 1024}]:
            with self.assertRaises(ValidationError):
                PreviewStartInput(**args)
        self.assertEqual(PreviewStartInput(entry_path="index.html").entry_path, "index.html")
        self.assertIn("oneOf", PreviewStartInput.model_json_schema())


class PublicPageRetentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_page_after_old_clipping_boundary_is_retrievable(self):
        with tempfile.TemporaryDirectory() as temp:
            results = OwnedToolResults(WorkbenchPaths(Path(temp)), SimpleNamespace(id="run", thread_id="thread", parent_run_id=None))
            class Response:
                status = 200
                content_type = "text/plain"
                charset = "utf-8"
                headers = {}
                @property
                def content(self): return self
                async def iter_chunked(self, _size):
                    yield ("x" * 50000 + " retained-public-fact").encode()
                async def __aenter__(self): return self
                async def __aexit__(self, *args): pass
            class Session:
                def __init__(self, **kwargs): self.connector = kwargs["connector"]
                async def __aenter__(self): return self
                async def __aexit__(self, *args): await self.connector.close()
                def get(self, *args, **kwargs): return Response()
            with patch("workbench_backend.connections.public_web.aiohttp.ClientSession", Session):
                page = await read_web_page("https://example.test/doc", result_retainer=results.retain)
            self.assertTrue(page["truncated"])
            self.assertNotIn("retained-public-fact", page["content"])
            self.assertEqual(results.read(page["retained_result"]["path"], query="retained-public-fact")["match_count"], 1)

    async def test_empty_public_search_is_a_normal_empty_result(self):
        with patch("workbench_backend.connections.public_web.DDGS") as provider:
            provider.return_value.text.return_value = []
            result = await search_web("unique no-match")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["query"], "unique no-match")


class BrowserFreshObservationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = WorkbenchPaths(Path(self.temp.name)).ensure()
        self.service = BrowserSessionService(self.paths)
        self.run = SimpleNamespace(id="run", thread_id="thread", parent_run_id=None)
        self.session = _Session("thread", {}, self.paths.root, None, asyncio.Event(),
            worker=SimpleNamespace(set_attribution=AsyncMock()),
            metadata={"session_id":"session", "active_page_id":"page", "revision":1,
                      "viewport":{"width":800,"height":600}, "dialog":None})
        self.service._sessions["thread"] = self.session
        self.service._observe_session = AsyncMock()
        self.called = []

    def bound(self, name, error=None):
        async def operation(**arguments):
            self.called.append(name)
            if error:
                raise ToolException(error)
            return "observed result"
        native = StructuredTool(name=name, description="Native fixture", args_schema={"type":"object", "properties":{}}, coroutine=operation)
        return self.service._bind_tool(self.run, self.session, native).coroutine

    async def test_dialog_change_stale_network_and_ungrounded_coordinates_are_not_dispatched(self):
        self.session.last_model_epoch = self.service._epoch(self.session)
        self.session.metadata["dialog"] = {"type":"confirm", "message":"New dialog"}
        with self.assertRaisesRegex(ToolException, "changed after"):
            await self.bound("browser_click")()
        self.session.last_model_epoch = self.service._epoch(self.session)
        with self.assertRaisesRegex(ToolException, "List current network"):
            await self.bound("browser_network_request")(index=1)
        with self.assertRaisesRegex(ToolException, "fresh viewport screenshot"):
            await self.bound("browser_mouse_click_xy")(x=20,y=20)
        self.assertEqual(self.called, [])
        self.session.network_observation = ("session", "page", 1)
        result = await self.bound("browser_network_request")(index=1)
        self.assertIn("Retained result", result)
        self.assertEqual(self.called, ["browser_network_request"])

    async def test_partial_form_failure_is_explicit_and_is_never_replayed(self):
        self.session.last_model_epoch = self.service._epoch(self.session)
        with self.assertRaisesRegex(ToolException, "may have changed earlier fields"):
            await self.bound("browser_fill_form", error="Second field missing")(fields=[])
        self.assertEqual(self.called, ["browser_fill_form"])
        self.assertTrue(self.service._observe_session.called)
