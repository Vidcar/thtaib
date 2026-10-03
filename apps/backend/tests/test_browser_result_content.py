"""Pinned MCP content stays separate from artifacts in browser model evidence."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from langchain.mcp.tools import _convert_call_tool_result
from langchain_core.tools import StructuredTool, ToolException
from mcp.types import ImageContent, TextContent

from workbench_backend.agents.tool_results import OwnedToolResults
from workbench_backend.browser.service import BrowserSessionService, _Session, _text
from workbench_backend.paths import WorkbenchPaths


def adapted(text, *, artifact=None, is_error=False, images=()):
    return _convert_call_tool_result(SimpleNamespace(content=[TextContent(type="text", text=text), *images],
        structured_content=artifact, is_error=is_error))


class BrowserResultContentTests(unittest.TestCase):
    def test_pinned_adapter_absent_or_nonempty_artifact_is_not_model_text(self):
        for artifact in (None, {"same_result": "native browser text", "artifact_only_field": "private fixture marker"}):
            with self.subTest(artifact_present=artifact is not None):
                result = adapted("native browser text", artifact=artifact)
                self.assertEqual(_text(result), "native browser text")
                self.assertEqual(result[1], {"structured_content": artifact} if artifact is not None else None)

    def test_literal_native_none_text_and_legacy_content_are_preserved(self):
        self.assertEqual(_text(adapted("None\nThis is native page text.")), "None\nThis is native page text.")
        self.assertEqual(_text("plain response"), "plain response")
        self.assertEqual(_text([{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]), "first\nsecond")
        self.assertEqual(_text(SimpleNamespace(content=[{"type": "text", "text": "native object"}])), "native object")

    def test_ordinary_two_item_text_tuples_keep_both_items(self):
        self.assertEqual(_text(("first visible paragraph", "second visible paragraph")), "first visible paragraph\nsecond visible paragraph")
        self.assertEqual(_text(({"type": "text", "text": "first"}, {"type": "text", "text": "second"})), "first\nsecond")

    def test_native_image_blocks_are_separate_from_text_and_artifact_metadata(self):
        result = adapted("screenshot text", artifact={"artifact_only_field": "private fixture marker"},
            images=[ImageContent(type="image", data="aXNvbGF0ZWQtaW1hZ2U=", mimeType="image/png")])
        self.assertEqual(_text(result), _text(result[0]))
        self.assertEqual(_text(result).strip(), "screenshot text")
        self.assertEqual(result[0][1]["type"], "image")
        self.assertEqual(result[0][1]["base64"], "aXNvbGF0ZWQtaW1hZ2U=")
        self.assertNotIn("private fixture marker", _text(result))



class BrowserBoundResultContentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.paths = WorkbenchPaths(Path(self.temp.name)).ensure()
        self.service = BrowserSessionService(self.paths)
        self.run = SimpleNamespace(id="result-run", thread_id="result-thread", parent_run_id=None)
        self.session = _Session(self.run.thread_id, {}, self.paths.root, None, asyncio.Event())
        self.service._sessions[self.run.thread_id] = self.session

    async def asyncTearDown(self):
        if self.session.idle_task:
            self.session.idle_task.cancel()
            await asyncio.gather(self.session.idle_task, return_exceptions=True)
        self.service._sessions.clear()
        self.temp.cleanup()

    def bound(self, name, text, *, artifact=None, is_error=False):
        async def native(**arguments):
            return adapted(text, artifact=artifact, is_error=is_error)

        original = StructuredTool(name=name, description="Pinned adapter fixture",
            args_schema={"type": "object", "properties": {"url": {"type": "string"}}},
            coroutine=native, response_format="content_and_artifact")
        return self.service._bind_tool(self.run, self.session, original)

    async def test_browser_wrappers_and_retained_readers_receive_only_native_content(self):
        text = "Page URL: https://example.test/page\nPage Title: Fixture\n- paragraph: None\nNative current-page evidence."
        for artifact in (None, {"artifact_only_field": "private fixture marker", "same_result": text}):
            for name in ("browser_navigate", "browser_snapshot", "browser_console_messages", "browser_network_requests", "browser_network_request", "browser_click"):
                with self.subTest(name=name, artifact_present=artifact is not None):
                    tool = self.bound(name, text, artifact=artifact)
                    message = await tool.ainvoke({"type": "tool_call", "id": "fixture", "name": name,
                        "args": {"url": "https://example.test/page"} if name == "browser_navigate" else {}})
                    self.assertEqual(message.status, "success")
                    self.assertIsNone(message.artifact)
                    self.assertIn("- paragraph: None", message.content)
                    self.assertNotIn("\nNone", message.content)
                    self.assertNotIn("private fixture marker", message.content)
                    self.assertEqual(message.content.count("Native current-page evidence."), 1)
                    if name != "browser_click":
                        metadata = json.loads(message.content.split("Retained result: ", 1)[1])
                        retained = OwnedToolResults(self.paths, self.run).read(metadata["path"])
                        self.assertEqual(retained["content"], text)
                        self.assertEqual(retained["result"]["source"]["tool"], name)
                    if name == "browser_navigate":
                        self.assertEqual(self.session.last_url, "https://example.test/page")

    async def test_native_execution_error_remains_an_error_without_lost_session(self):
        tool = self.bound("browser_click", "Native missing target. None is literal error detail.",
            artifact={"artifact_only_field": "private fixture marker"}, is_error=True)
        message = await tool.ainvoke({"type": "tool_call", "id": "fixture", "name": tool.name, "args": {}})
        self.assertEqual(message.status, "error")
        self.assertEqual(message.content, "Native missing target. None is literal error detail.")
        self.assertIs(self.service._sessions[self.run.thread_id], self.session)
        self.assertFalse(self.service._marker(self.run.thread_id).exists())

    async def test_screenshot_fallback_retains_image_without_stringifying_image_blocks(self):
        saved = self.paths.root / "retained-image.bin"
        published = []
        def publish(_run, path, **options):
            saved.write_bytes(path.read_bytes())
            published.append(options)
            return SimpleNamespace(id="capture-fixture"), "/captures/current.png"
        self.service.capture_publisher = publish
        async def unavailable_snapshot():
            raise ToolException("Native snapshot is unavailable.")
        self.session.tools["browser_snapshot"] = StructuredTool(name="browser_snapshot", description="Native snapshot fixture",
            args_schema={"type": "object", "properties": {}}, coroutine=unavailable_snapshot)
        async def screenshot():
            (self.paths.root / "controlled.png").write_bytes(b"isolated-image-bytes")
            return adapted("Page URL: https://example.test/canvas\nNative screenshot evidence.",
                artifact={"artifact_only_field": "private fixture marker"},
                images=[ImageContent(type="image", data="aXNvbGF0ZWQtaW1hZ2U=", mimeType="image/png")])
        original = StructuredTool(name="browser_take_screenshot", description="Native screenshot fixture",
            args_schema={"type": "object", "properties": {}}, coroutine=screenshot, response_format="content_and_artifact")
        tool = self.service._bind_tool(self.run, self.session, original)
        message = await tool.ainvoke({"type": "tool_call", "id": "fixture", "name": tool.name, "args": {}})
        self.assertEqual(message.status, "success")
        self.assertIn("Saved screenshot: /captures/current.png", message.content)
        self.assertIn("Native screenshot evidence.", message.content)
        self.assertNotIn("private fixture marker", message.content)
        self.assertNotIn("aXNvbGF0ZWQtaW1hZ2U=", message.content)
        self.assertEqual(saved.read_bytes(), b"isolated-image-bytes")
        self.assertFalse((self.paths.root / "controlled.png").exists())
        self.assertEqual(published[0]["source_tool_name"], "browser_take_screenshot")
        self.assertEqual(published[0]["target"], "https://example.test/canvas")


if __name__ == "__main__":
    unittest.main()
