from __future__ import annotations

import base64
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path

from fastapi import HTTPException

from workbench_backend.assets.schemas import (
    RetainedAssetDeletionRequest,
    RetainedAssetReuseRequest,
    RetainedUploadRequest,
)
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.app import create_app
from workbench_backend.chat.schemas import (
    ChatConversation,
    ChatDraft,
    ChatDraftUpdateRequest,
    ChatMessage,
    ChatQueueItem,
    ChatQueueItemUpdateRequest,
    ChatStartRequest,
)
from workbench_backend.chat.service import ChatService
from workbench_backend.errors import ManagerError
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore
from tests.support import close_workbench_sqlite
from tests.support import workbench_client


def b64(text: str) -> str:
    return base64.b64encode(text.encode('utf-8')).decode('ascii')


class ExplicitAssetDeletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ApplicationStore(WorkbenchPaths(Path(self.tmp.name)))
        self.assets = RetainedAssetService(self.store)

    def tearDown(self) -> None:
        close_workbench_sqlite(self.store)
        self.tmp.cleanup()

    def put_conversation(self, conversation_id: str, **updates: object) -> ChatConversation:
        now = utc_now()
        conversation = ChatConversation(
            id=conversation_id,
            deployment_id='dep',
            created_at=now,
            updated_at=now,
            **updates,
        )
        return self.store.put_conversation(conversation)

    def upload(self, session_id: str, *, filename: str = 'file.txt'):
        return self.assets.retain_upload(
            RetainedUploadRequest(
                session_id=session_id,
                filename=filename,
                content_type='text/plain',
                content_base64=b64(filename),
            )
        )

    def assert_deleted(self, asset_id: str) -> None:
        loaded = self.assets.store.get(asset_id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertIsNotNone(loaded[0].deleted_at)
        self.assertEqual(loaded[1], b'')

    def chat_service(self) -> ChatService:
        class Manager:
            paths = WorkbenchPaths(Path(self.tmp.name))

            def reserve_deployment(self, _deployment_id, *, profile_id=None):
                return nullcontext()

            def get_deployment(self, _deployment_id: str):
                raise ManagerError("missing deployment", code="deployment_missing", status_code=404)

        return ChatService(
            lambda: Manager(),
            lambda: object(),
            lambda: object(),
            app_store=self.store,
            assets_provider=lambda: self.assets,
        )

    def test_explicit_unused_upload_delete_ignores_owner_provenance(self) -> None:
        self.put_conversation('chat_unused')
        asset = self.upload('chat_unused')

        preview = self.assets.deletion_preview(RetainedAssetDeletionRequest(asset_ids=[asset.id]))

        self.assertEqual(preview.affected_asset_ids, [asset.id])
        self.assertEqual(preview.preserved_asset_ids, [])
        self.assertIn('chat_unused', preview.affected_sessions)

        deleted = self.assets.mark_deletable_assets_deleted(RetainedAssetDeletionRequest(asset_ids=[asset.id]))
        self.assertEqual(deleted.affected_asset_ids, [asset.id])
        self.assert_deleted(asset.id)

    def test_explicit_project_upload_delete_does_not_touch_project_source(self) -> None:
        project = Path(self.tmp.name) / 'project'
        project.mkdir()
        source = project / 'file.txt'
        source.write_text('project source remains', encoding='utf-8')
        self.put_conversation('chat_project', project_path=str(project))
        asset = self.upload('chat_project')

        preview = self.assets.deletion_preview(RetainedAssetDeletionRequest(asset_ids=[asset.id]))

        self.assertEqual(preview.affected_asset_ids, [asset.id])
        self.assertIn(str(project), preview.affected_projects)
        self.assets.mark_deletable_assets_deleted(RetainedAssetDeletionRequest(asset_ids=[asset.id]))
        self.assertEqual(source.read_text(encoding='utf-8'), 'project source remains')
        self.assert_deleted(asset.id)

    def test_transcript_attachment_preserves_explicit_asset_delete(self) -> None:
        self.put_conversation('chat_sent')
        asset = self.upload('chat_sent')
        conversation = self.store.get_conversation('chat_sent')
        assert conversation is not None
        conversation.transcript.append(
            ChatMessage(role='user', content='sent', attachment_ids=[asset.id], at=utc_now())
        )
        self.store.put_conversation(conversation)

        preview = self.assets.deletion_preview(RetainedAssetDeletionRequest(asset_ids=[asset.id]))

        self.assertEqual(preview.affected_asset_ids, [])
        self.assertEqual(preview.preserved_asset_ids, [asset.id])
        self.assertIn('chat_sent', preview.retained_sessions)

    def test_draft_and_queue_attachments_preserve_explicit_asset_delete(self) -> None:
        self.put_conversation('chat_refs')
        draft_asset = self.upload('chat_refs', filename='draft.txt')
        queue_asset = self.upload('chat_refs', filename='queue.txt')
        conversation = self.store.get_conversation('chat_refs')
        assert conversation is not None
        conversation.draft = ChatDraft(
            content='draft',
            attachment_ids=[draft_asset.id],
            intended_config={},
            revision=1,
            updated_at=utc_now(),
        )
        conversation.queue.append(
            ChatQueueItem(
                id='queue-item',
                task='queued',
                attachment_ids=[queue_asset.id],
                intended_config={},
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        self.store.put_conversation(conversation)

        preview = self.assets.deletion_preview(
            RetainedAssetDeletionRequest(asset_ids=[draft_asset.id, queue_asset.id])
        )

        self.assertEqual(preview.affected_asset_ids, [])
        self.assertEqual(preview.preserved_asset_ids, [draft_asset.id, queue_asset.id])
        self.assertIn('chat_refs', preview.retained_sessions)

    def test_other_session_consumer_still_preserves_explicit_asset_delete(self) -> None:
        self.put_conversation('chat_owner')
        asset = self.upload('chat_owner')
        self.assets.store.add_consumer(asset.id, kind='session', consumer_id='chat_keeper', recorded_at=utc_now())

        preview = self.assets.deletion_preview(RetainedAssetDeletionRequest(asset_ids=[asset.id]))

        self.assertEqual(preview.affected_asset_ids, [])
        self.assertEqual(preview.preserved_asset_ids, [asset.id])
        self.assertIn('chat_keeper', preview.retained_sessions)

    def test_reuse_rejects_deleted_asset_without_adding_consumer(self) -> None:
        self.put_conversation('chat_unused')
        self.put_conversation('chat_target')
        asset = self.upload('chat_unused')
        self.assets.mark_deletable_assets_deleted(RetainedAssetDeletionRequest(asset_ids=[asset.id]))

        with self.assertRaises(HTTPException) as raised:
            self.assets.current_user_content(
                RetainedAssetReuseRequest(
                    asset_ids=[asset.id],
                    session_id='chat_target',
                    allow_cross_session_reuse=True,
                )
            )

        self.assertEqual(raised.exception.status_code, 410)
        self.assertNotIn({'kind': 'session', 'id': 'chat_target'}, self.assets.store.consumers([asset.id]).get(asset.id, []))

    def test_deleted_asset_cannot_be_saved_into_stale_draft(self) -> None:
        self.put_conversation('chat_unused')
        self.put_conversation('chat_target')
        asset = self.upload('chat_unused')
        self.assets.mark_deletable_assets_deleted(RetainedAssetDeletionRequest(asset_ids=[asset.id]))

        with self.assertRaises(HTTPException) as raised:
            self.chat_service().update_draft(
                'chat_target',
                ChatDraftUpdateRequest(content='stale draft', attachment_ids=[asset.id]),
            )

        self.assertEqual(raised.exception.status_code, 410)
        self.assertIsNone(self.store.get_conversation('chat_target').draft)

    def test_foreign_asset_cannot_be_saved_into_draft(self) -> None:
        self.put_conversation('chat_owner')
        self.put_conversation('chat_target')
        asset = self.upload('chat_owner')

        with self.assertRaises(HTTPException) as raised:
            self.chat_service().update_draft(
                'chat_target',
                ChatDraftUpdateRequest(content='wrong scope', attachment_ids=[asset.id]),
            )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertIsNone(self.store.get_conversation('chat_target').draft)

    def test_deleted_asset_cannot_be_saved_into_stale_queue_item(self) -> None:
        self.put_conversation('chat_unused')
        self.put_conversation('chat_target')
        asset = self.upload('chat_unused')
        conversation = self.store.get_conversation('chat_target')
        assert conversation is not None
        conversation.queue.append(
            ChatQueueItem(
                id='queue-edit',
                task='queued',
                intended_config={},
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        self.store.put_conversation(conversation)
        self.assets.mark_deletable_assets_deleted(RetainedAssetDeletionRequest(asset_ids=[asset.id]))

        with self.assertRaises(HTTPException) as raised:
            self.chat_service().update_queue_item(
                'chat_target',
                'queue-edit',
                ChatQueueItemUpdateRequest(attachment_ids=[asset.id]),
            )

        self.assertEqual(raised.exception.status_code, 410)
        self.assertEqual(self.store.get_conversation('chat_target').queue[0].attachment_ids, [])

    def test_foreign_asset_cannot_be_saved_into_queue_item(self) -> None:
        self.put_conversation('chat_owner')
        self.put_conversation('chat_target')
        asset = self.upload('chat_owner')
        conversation = self.store.get_conversation('chat_target')
        assert conversation is not None
        conversation.queue.append(
            ChatQueueItem(
                id='queue-edit',
                task='queued',
                intended_config={},
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        self.store.put_conversation(conversation)

        with self.assertRaises(HTTPException) as raised:
            self.chat_service().update_queue_item(
                'chat_target',
                'queue-edit',
                ChatQueueItemUpdateRequest(attachment_ids=[asset.id]),
            )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(self.store.get_conversation('chat_target').queue[0].attachment_ids, [])

    def test_deleted_asset_cannot_be_enqueued_by_stale_request(self) -> None:
        self.put_conversation('chat_unused')
        self.put_conversation('chat_target')
        asset = self.upload('chat_unused')
        self.assets.mark_deletable_assets_deleted(RetainedAssetDeletionRequest(asset_ids=[asset.id]))

        with self.assertRaises(HTTPException) as raised:
            self.chat_service().enqueue(
                'chat_target',
                ChatStartRequest(task='queued stale attachment', attachment_ids=[asset.id]),
            )

        self.assertEqual(raised.exception.status_code, 410)
        self.assertEqual(self.store.get_conversation('chat_target').queue, [])

    def test_foreign_asset_cannot_be_enqueued(self) -> None:
        self.put_conversation('chat_owner')
        self.put_conversation('chat_target')
        asset = self.upload('chat_owner')

        with self.assertRaises(HTTPException) as raised:
            self.chat_service().enqueue(
                'chat_target',
                ChatStartRequest(task='queued wrong scope', attachment_ids=[asset.id]),
            )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(self.store.get_conversation('chat_target').queue, [])

    def test_public_asset_delete_rejects_owner_selectors_that_would_bypass_references(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            app = create_app(data_root=Path(root))
            try:
                client = workbench_client(app)
                now = utc_now()
                app.state.app_store.put_conversation(
                    ChatConversation(
                        id='chat_sent',
                        deployment_id='dep',
                        created_at=now,
                        updated_at=now,
                    )
                )
                asset = app.state.assets.retain_upload(
                    RetainedUploadRequest(
                        session_id='chat_sent',
                        filename='sent.txt',
                        content_type='text/plain',
                        content_base64=b64('sent'),
                    )
                )
                conversation = app.state.app_store.get_conversation('chat_sent')
                assert conversation is not None
                conversation.transcript.append(
                    ChatMessage(role='user', content='sent', attachment_ids=[asset.id], at=utc_now())
                )
                app.state.app_store.put_conversation(conversation)

                response = client.post('/v1/assets/delete', json={'session_ids': ['chat_sent']})

                self.assertEqual(response.status_code, 400, response.text)
                loaded = app.state.assets.store.get(asset.id)
                self.assertIsNotNone(loaded)
                assert loaded is not None
                self.assertIsNone(loaded[0].deleted_at)
                self.assertEqual(loaded[1], b'sent')
            finally:
                close_workbench_sqlite(app)


if __name__ == '__main__':
    unittest.main()
