"""Browser ownership, sensitive-file confinement and public typed boundaries."""
from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from langchain_core.tools import ToolException

from workbench_backend.assets.schemas import RetainedUploadRequest
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.browser.routes import router
from workbench_backend.browser.service import BrowserOwner, BrowserSessionService
from workbench_backend.chat.schemas import ChatConversation, ChatDraft
from workbench_backend.errors import WorkbenchError, workbench_error_handler
from workbench_backend.inference.ids import utc_now
from workbench_backend.local_trust import require_local_trust, WORKBENCH_LOCAL_TOKEN_HEADER
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore

class BrowserFileBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = WorkbenchPaths(self.root / "data").ensure()
        self.store = ApplicationStore(self.paths)
        self.assets = RetainedAssetService(self.store)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "allowed.txt").write_text("project file", encoding="utf-8")
        (self.root / "private.txt").write_text("private", encoding="utf-8")
        self.conversation = self.store.put_conversation(ChatConversation(id="chat_browser", deployment_id="dep",
            thread_id="thread_browser", project_path=str(self.project), created_at=utc_now(), updated_at=utc_now()))
        self.service = BrowserSessionService(self.paths, assets=self.assets, app_store=self.store)
        output = self.paths.state / "browser-captures/thread_browser"
        output.mkdir(parents=True)
        self.session = SimpleNamespace(thread_id="thread_browser", output_dir=output)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_upload_requires_confined_project_or_explicitly_selected_attachment(self):
        attachment = self.assets.retain_upload(RetainedUploadRequest(session_id=self.conversation.id,
            filename="selected.txt", content_type="text/plain", content_base64=base64.b64encode(b"attachment").decode()))
        run = SimpleNamespace(project_path=str(self.project), retained_asset_ids=[attachment.id])
        paths = self.service._resolve_uploads(self.session, run, ["allowed.txt", "asset:" + attachment.id])
        self.assertEqual([Path(path).read_bytes() for path in paths], [b"project file", b"attachment"])
        for value in ["../private.txt", str(self.root / "private.txt")]:
            with self.assertRaises((ToolException, HTTPException)):
                self.service._resolve_uploads(self.session, run, [value])
        with self.assertRaises(ToolException):
            self.service._resolve_uploads(self.session, SimpleNamespace(project_path=str(self.project), retained_asset_ids=[]), ["asset:" + attachment.id])
        self.conversation.draft = ChatDraft(attachment_ids=[attachment.id], updated_at=utc_now())
        self.store.put_conversation(self.conversation)
        self.assertEqual(Path(self.service._resolve_uploads(self.session, None, ["asset:" + attachment.id], manual=True)[0]).read_bytes(), b"attachment")

    def test_completed_download_retains_exact_binary_bytes_and_scope(self):
        raw = b"PK\x00\xff browser archive"
        source = self.session.output_dir / "completed"
        source.write_bytes(raw)
        asset = self.assets.retain_browser_download("thread_browser", source, filename="download.zip",
            source_url="https://example.test/download", controlled_root=self.session.output_dir, attribution={})
        self.assertEqual(asset.origin.value, "browser_download")
        self.assertEqual(asset.content_kind.value, "binary")
        self.assertEqual(asset.source_target, "https://example.test/download")
        content = self.assets.content(asset.id, session_id=self.conversation.id)
        self.assertEqual(base64.b64decode(content.content_base64), raw)
        with self.assertRaises(HTTPException):
            self.assets.content(asset.id, session_id="another_chat")
        with self.assertRaises(HTTPException):
            self.assets.retain_browser_download("thread_browser", self.root / "private.txt", filename="private.txt",
                source_url="https://example.test/", controlled_root=self.session.output_dir, attribution={})

class BrowserHttpBoundaries(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.add_exception_handler(WorkbenchError, workbench_error_handler)
        app.state.local_trust_token = "browser-fixture-token"
        app.middleware("http")(require_local_trust)
        self.conversation = SimpleNamespace(current_run_id=None, project_id=None, agent_setup_version_id=None,
            setup_overrides=SimpleNamespace(model_dump=lambda **_: {}), work_mode="work", presented_tools=[])
        app.state.assets = SimpleNamespace(session_for_thread=lambda ident: self.conversation if ident == "thread_browser" else None)
        app.state.setups = SimpleNamespace(resolve=lambda **_: SimpleNamespace(configuration=SimpleNamespace(presented_tools=[], work_mode="work")))
        app.state.browser = SimpleNamespace(resolve_owner=lambda ident: BrowserOwner(self.conversation if ident == "thread_browser" else None, None),
            status=lambda _, **__: {"thread_id": "thread_browser", "state": "closed",
            "worker": {"supported": True, "installed": True, "chrome_available": True}})
        app.include_router(router)
        self.client = TestClient(app)
        self.headers = {WORKBENCH_LOCAL_TOKEN_HEADER: "browser-fixture-token"}

    def tearDown(self):
        self.client.close()

    def test_authenticated_owner_and_selected_browser_required(self):
        self.assertEqual(self.client.get("/v1/browser/sessions/thread_browser").status_code, 401)
        self.assertEqual(self.client.get("/v1/browser/sessions/thread_browser", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get("/v1/browser/sessions/another_chat", headers=self.headers).status_code, 404)
        denied = self.client.post("/v1/browser/sessions/thread_browser/start", headers=self.headers)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["code"], "browser_not_selected")

    def test_public_actions_cannot_carry_worker_code_or_paths_and_reset_requires_confirmation(self):
        payload = {"session_id": "s", "page_id": "p", "revision": 1, "action": {"type": "evaluate", "code": "unrestricted"}}
        self.assertEqual(self.client.post("/v1/browser/sessions/thread_browser/actions", headers=self.headers, json=payload).status_code, 422)
        payload["action"] = {"type": "upload", "paths": ["C:/private.txt"]}
        self.assertEqual(self.client.post("/v1/browser/sessions/thread_browser/actions", headers=self.headers, json=payload).status_code, 422)
        self.assertEqual(self.client.post("/v1/browser/sessions/thread_browser/reset", headers=self.headers).status_code, 422)
