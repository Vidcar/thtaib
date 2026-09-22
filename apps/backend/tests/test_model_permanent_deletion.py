"""Permanent model deletion crosses the real API, record and filesystem owners."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import close_workbench_sqlite, offline_workbench_client, write_tiny_gguf
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.app import create_app
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.inspection_cache import cached_inspection
from workbench_backend.inference.schemas import (
    BundleSourceKind, Deployment, DeploymentStatus, ImportJob, ImportStatus,
    LocalImportRequest, ManagementScope, ProfileWriteRequest,
)


class PermanentModelDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.app = create_app(data_root=self.root / 'product')
        self.client = offline_workbench_client(self.app)
        self.manager = self.app.state.manager
        self.primary = write_tiny_gguf(self.root / 'selected' / 'model-Q4_K_M.gguf')
        self.unrelated = self.primary.parent / 'unrelated.txt'
        self.unrelated.write_text('preserve')
        self.imported = self.manager.import_local(LocalImportRequest(source_path=str(self.primary), copy_files=False))
        self.bundle = self.manager.store.get_bundle(self.imported.bundle_id)

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.temporary.cleanup()

    def test_permanent_api_removes_files_and_model_metadata_but_retains_history(self):
        store = self.manager.store
        profile = self.manager.create_profile(ProfileWriteRequest(display_name='bound', bundle_id=self.bundle.id))
        now = utc_now()
        deployment = Deployment(id='selected-deployment', display_name='saved model', bundle_id=self.bundle.id,
            profile_id=profile.id, scope=ManagementScope.managed, status=DeploymentStatus.stopped,
            created_at=now, updated_at=now)
        store.put_deployment(deployment)
        store.put_capability_evidence({'id': 'model-proof', 'deployment_id': deployment.id, 'tested_at': now})
        keys = [f'model-verification:{self.bundle.id}', f'model-inspection:{self.bundle.id}:runtime',
                f'model-inspection:{self.bundle.id}:full', f'import_job.{self.imported.id}.copy_files']
        for key in keys:
            store.put_setting(key, 'fixture')
        stage = self.manager.paths.state / 'staging' / 'selected-import'
        stage.mkdir(parents=True)
        (stage / 'model.gguf').write_bytes(b'owned download copy')
        store.update_job_fields(self.imported.id, staging_path=str(stage))
        self.app.state.app_store.put_run(AgentRun(id='historical-run', status=AgentRunStatus.completed,
            deployment_id=deployment.id, profile_id=profile.id, task='retained history',
            enabled_tools=[], presented_tools=[], created_at=now, updated_at=now))

        preview = self.client.get(f'/v1/bundles/{self.bundle.id}/delete-preview?permanent=true')
        self.assertEqual(preview.status_code, 200, preview.text)
        plan = preview.json()
        self.assertFalse(plan['blockers'])
        self.assertEqual(plan['files'][0]['path'], str(self.primary))
        self.assertTrue(plan['files'][0]['removable'])
        self.assertTrue(all(not item['retained'] for item in plan['consumers'] if item['kind'] in {'profile', 'deployment', 'import_job'}))
        response = self.client.delete(f'/v1/bundles/{self.bundle.id}?permanent=true')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.primary.exists())
        self.assertFalse(stage.exists())
        self.assertEqual(self.unrelated.read_text(), 'preserve')
        self.assertIsNone(store.get_bundle(self.bundle.id))
        self.assertIsNone(store.get_profile(profile.id))
        self.assertIsNone(store.get_deployment(deployment.id))
        self.assertIsNone(store.get_job(self.imported.id))
        self.assertEqual(store.list_capability_evidence(deployment.id), [])
        self.assertTrue(all(store.get_setting(key) is None for key in keys))
        historical = self.app.state.app_store.get_run('historical-run')
        self.assertEqual(historical.deployment_id, deployment.id)
        self.assertEqual(historical.task, 'retained history')

    def test_shared_files_block_before_any_selected_file_or_metadata_is_removed(self):
        other = self.bundle.model_copy(update={'id': 'other-bundle', 'display_name': 'other reference'})
        self.manager.store.put_bundle(other)
        preview = self.client.get(f'/v1/bundles/{self.bundle.id}/delete-preview?permanent=true').json()
        self.assertTrue(any(item['kind'] == 'file' and 'shared_reference' in item['label'] for item in preview['blockers']))
        response = self.client.delete(f'/v1/bundles/{self.bundle.id}?permanent=true')
        self.assertEqual(response.status_code, 409)
        self.assertTrue(self.primary.exists())
        self.assertIsNotNone(self.manager.store.get_bundle(self.bundle.id))
        self.assertIsNotNone(self.manager.store.get_bundle(other.id))

    def test_active_import_using_source_files_blocks_permanent_deletion(self):
        self.manager.store.put_job(ImportJob(id='active-copy', kind=BundleSourceKind.local,
            status=ImportStatus.running, created_at=utc_now(), source_path=str(self.primary.parent)))
        response = self.client.delete(f'/v1/bundles/{self.bundle.id}?permanent=true')
        self.assertEqual(response.status_code, 409)
        self.assertTrue(self.primary.exists())
        self.manager.store.update_job_fields('active-copy', status=ImportStatus.stopped)

    def test_failed_file_removal_keeps_metadata_for_retry(self):
        original = Path.unlink
        def denied(path, *args, **kwargs):
            if path == self.primary:
                raise PermissionError('selected model is locked')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', denied):
            response = self.client.delete(f'/v1/bundles/{self.bundle.id}?permanent=true')
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['code'], 'bundle_delete_failed')
        self.assertIsNotNone(self.manager.store.get_bundle(self.bundle.id))
        self.assertTrue(self.primary.exists())

    def test_inflight_verification_does_not_recreate_deleted_model_cache(self):
        from workbench_backend.inference.hashes import sha256_file

        def delete_during_hash(path):
            self.manager.store.delete_bundle(self.bundle.id)
            return sha256_file(path)

        with patch('workbench_backend.inference.bundles.sha256_file', delete_during_hash):
            self.manager.bundles.verify_bundle(self.bundle)
        self.assertIsNone(self.manager.store.get_bundle(self.bundle.id))
        self.assertIsNone(self.manager.store.get_setting(f'model-verification:{self.bundle.id}'))

    def test_inflight_inspection_does_not_recreate_deleted_model_cache(self):
        def delete_during_read():
            self.manager.store.delete_bundle(self.bundle.id)
            return self.bundle

        cached_inspection(self.manager.store, self.bundle, 'full', type(self.bundle), delete_during_read)
        self.assertIsNone(self.manager.store.get_bundle(self.bundle.id))
        self.assertIsNone(self.manager.store.get_setting(f'model-inspection:{self.bundle.id}:full'))
