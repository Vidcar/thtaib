"""Tool observation markers follow their owning run during deletion."""

import base64
import tempfile
import unittest
from pathlib import Path

from workbench_backend.assets.schemas import RetainedAssetDeletionRequest, RetainedUploadRequest
from workbench_backend.assets.lifecycle import AssetLifecycleService
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore
from tests.support import close_workbench_sqlite


class AssetConsumerDeletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ApplicationStore(WorkbenchPaths(Path(self.tmp.name)))
        self.assets = RetainedAssetService(self.store)
        self.store.put_conversation(ChatConversation(
            id="chat_owner", deployment_id="dep", created_at=utc_now(), updated_at=utc_now(),
        ))
        self.asset = self.assets.retain_upload(RetainedUploadRequest(
            session_id="chat_owner", filename="kept.txt", content_type="text/plain",
            content_base64=base64.b64encode(b"retained bytes").decode(),
        ))
        for kind, identity in (("run", "run_owner"), ("tool_call", "run_owner:call_1")):
            self.assets.store.add_consumer(self.asset.id, kind=kind, consumer_id=identity, recorded_at=utc_now())

    def tearDown(self):
        close_workbench_sqlite(self.store)
        self.tmp.cleanup()

    def test_tool_marker_does_not_retain_deleted_run_bytes(self):
        request = RetainedAssetDeletionRequest(session_ids=["chat_owner"], run_ids=["run_owner"])
        preview = self.assets.deletion_preview(request)
        self.assertEqual(preview.affected_asset_ids, [self.asset.id])
        result = self.assets.mark_deletable_assets_deleted(request)
        self.assertEqual(result.preserved_asset_ids, [])
        self.assertEqual(self.assets.store.get(self.asset.id)[1], b"")
        self.assertEqual(self.assets.store.consumers([self.asset.id]), {})

    def test_surviving_consumer_preserves_bytes_but_not_deleted_run_marker(self):
        self.assets.store.add_consumer(self.asset.id, kind="case", consumer_id="case_survivor", recorded_at=utc_now())
        result = self.assets.mark_deletable_assets_deleted(RetainedAssetDeletionRequest(
            session_ids=["chat_owner"], run_ids=["run_owner"],
        ))
        self.assertEqual(result.preserved_asset_ids, [self.asset.id])
        self.assertEqual(self.assets.store.get(self.asset.id)[1], b"retained bytes")
        self.assertEqual(self.assets.store.consumers([self.asset.id]), {
            self.asset.id: [{"kind": "case", "id": "case_survivor"}],
        })

    def test_conversation_delete_removes_only_its_cancellation_records(self):
        self.store.request_chat_submission_cancel("chat_owner", "input_stopped")
        self.store.request_chat_submission_cancel("chat_other", "input_other")
        AssetLifecycleService(WorkbenchPaths(Path(self.tmp.name)), self.store).delete_conversation("chat_owner")
        self.assertFalse(self.store.chat_submission_cancel_requested("chat_owner", "input_stopped"))
        self.assertTrue(self.store.chat_submission_cancel_requested("chat_other", "input_other"))
