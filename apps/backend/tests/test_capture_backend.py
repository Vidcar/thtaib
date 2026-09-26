"""Retained screenshots stay scoped while native read_file sees image bytes."""

from __future__ import annotations

import base64
import io
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from PIL import Image

from tests.support import close_workbench_sqlite
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.assets.lifecycle import AssetLifecycleService
from workbench_backend.assets.capture_backend import CaptureBackend
from workbench_backend.assets.schemas import RetainedAssetOrigin
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore


class CaptureBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = ApplicationStore(WorkbenchPaths(self.root))
        self.assets = RetainedAssetService(self.store)
        self.run = AgentRun(
            id="run_capture", deployment_id="dep", task="test a page",
            enabled_tools=["read_file"], presented_tools=["read_file"],
            thread_id="thread_capture", source_surface="chat",
            created_at=utc_now(), updated_at=utc_now(),
        )
        self.store.put_run(self.run)
        self.store.put_conversation(ChatConversation(
            id="chat_capture", deployment_id="dep", thread_id=self.run.thread_id,
            run_ids=[self.run.id], created_at=utc_now(), updated_at=utc_now(),
        ))
        self.owned = self.root / "owned"
        self.owned.mkdir()
        image = Image.new("RGB", (18, 12), (200, 20, 20))
        output = io.BytesIO()
        image.save(output, format="PNG")
        self.content = output.getvalue()
        self.path = self.owned / "capture.png"
        self.path.write_bytes(self.content)

    def tearDown(self) -> None:
        close_workbench_sqlite(self.store)
        self.tmp.cleanup()

    def test_capture_retention_and_native_read_are_session_scoped(self) -> None:
        asset, virtual_path = self.assets.register_capture(
            self.run, self.path, source_tool_name="browser_take_screenshot",
            source_tool_call_id="call_capture", target="http://127.0.0.1:4000/",
            controlled_root=self.owned,
        )
        self.assertEqual(asset.origin, RetainedAssetOrigin.capture)
        self.assertEqual(asset.source_target, "http://127.0.0.1:4000/")
        self.assertEqual(asset.source_tool_call_id, "call_capture")
        self.assertEqual(asset.image_width, 18)
        self.assertEqual(virtual_path, f"/captures/{asset.id}.png")
        backend = CaptureBackend(self.assets, "chat_capture", image_inputs_allowed=True)
        read = backend.read(virtual_path.removeprefix("/captures"))
        self.assertEqual(base64.b64decode(read.file_data["content"]), self.content)
        self.assertEqual(len(backend.ls("/").entries), 1)
        self.assertEqual(len(backend.glob("*.png").matches), 1)
        self.assertIsNotNone(backend.write("/other.png", "bad").error)
        self.assertIsNotNone(CaptureBackend(self.assets, "another_chat", image_inputs_allowed=True).read(virtual_path.removeprefix("/captures")).error)
        self.assertIn("cannot read the screenshot", CaptureBackend(self.assets, "chat_capture").read(virtual_path.removeprefix("/captures")).error)
        self.assertIsNotNone(backend.read("/../" + asset.id + ".png").error)

    def test_capture_rejects_unowned_path(self) -> None:
        outside = self.root / "outside.png"
        outside.write_bytes(self.content)
        with self.assertRaises(HTTPException) as raised:
            self.assets.register_capture(
                self.run, outside, source_tool_name="desktop_screenshot",
                source_tool_call_id=None, target="HWND 7", controlled_root=self.owned,
            )
        self.assertEqual(raised.exception.status_code, 409)

    def test_deleting_conversation_removes_its_capture_route(self) -> None:
        asset, virtual_path = self.assets.register_capture(
            self.run, self.path, source_tool_name="browser_take_screenshot",
            source_tool_call_id="call_capture", target="http://127.0.0.1:4000/",
            controlled_root=self.owned,
        )
        self.run.status = AgentRunStatus.completed
        self.store.put_run(self.run)
        deleted = AssetLifecycleService(WorkbenchPaths(self.root), self.store).delete_conversation("chat_capture")
        self.assertIn(asset.id, deleted.affected_assets)
        self.assertIsNotNone(CaptureBackend(self.assets, "chat_capture", image_inputs_allowed=True)
            .read(virtual_path.removeprefix("/captures")).error)


if __name__ == "__main__":
    unittest.main()
