"""Saved Models setup must reach the composed Chat prompt and settings."""
import tempfile
from contextlib import ExitStack
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage
from workbench_backend.app import create_app
from workbench_backend.agents.harness import HarnessService
from workbench_backend.inference.schemas import LocalImportRequest, ManagedDeploymentRequest, ProfileWriteRequest
from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client, write_tiny_gguf
from tests.test_chat import wait_for_chat


class SavedSetupChatTests(unittest.TestCase):
    def test_desktop_sparse_profile_payload_reports_edits_and_preserves_resets(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as cleanup:
            app = create_app(data_root=Path(directory))
            cleanup.callback(close_workbench_sqlite, app)
            manager = app.state.manager
            model = Path(directory) / 'fixture.gguf'
            write_tiny_gguf(model)
            bundle = manager.import_local(LocalImportRequest(source_path=str(model), copy_files=False))
            profile = manager.create_profile(ProfileWriteRequest(display_name='Preset', startup={'ctx_size': 4096}))
            # The production desktop serializer is exercised by check-model-settings.mjs:
            # selecting its untouched preset submits profile identity + an empty map.
            saved = manager.create_managed(ManagedDeploymentRequest(bundle_id=bundle.bundle_id, profile_id=profile.id, startup={}, auto_start=False))
            cleared = manager.create_managed(ManagedDeploymentRequest(bundle_id=bundle.bundle_id, profile_id=profile.id, startup={'ctx_size': None}, auto_start=False))
            self.assertNotIn('ctx_size', cleared.requested_startup)
            self.assertEqual(cleared.startup_overrides, {'ctx_size': None})
            manager.update_profile(profile.id, ProfileWriteRequest(display_name='Preset', startup={'ctx_size': 8192}))
            self.assertTrue(manager.deployment_profile_changes(saved.id).has_pending_startup_changes)
            self.assertFalse(manager.deployment_profile_changes(cleared.id).has_pending_startup_changes)
            self.assertEqual(manager.get_deployment(saved.id).requested_startup['ctx_size'], 4096)

    def test_saved_setup_inherits_all_bags_and_explicit_none_opts_out(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as cleanup:
            app = create_app(data_root=Path(directory))
            cleanup.callback(close_workbench_sqlite, app)
            manager = app.state.manager
            model = Path(directory) / 'fixture.gguf'
            write_tiny_gguf(model)
            bundle = manager.import_local(LocalImportRequest(source_path=str(model), copy_files=False))
            profile = manager.create_profile(ProfileWriteRequest(
                display_name='Saved instructions', startup={'ctx_size': 4096},
                per_request={'temperature': 0.17}, agent={'system_prompt': 'SAVED-SETUP-INSTRUCTION-UNIQUE'},
            ))
            deployment = manager.create_managed(ManagedDeploymentRequest(
                bundle_id=bundle.bundle_id, profile_id=profile.id, auto_start=False,
            ))
            manager.update_profile(profile.id, ProfileWriteRequest(
                display_name='Edited preset', startup={'ctx_size': 8192},
                per_request={'temperature': 0.91}, agent={'system_prompt': 'EDITED-PRESET-INSTRUCTION'},
            ))
            app.state.harness = HarnessService(
                lambda: manager, model_factory=lambda *_: ScriptedChatModel([AIMessage(content='done')]),
                knowledge_provider=lambda: app.state.knowledge, app_store=app.state.app_store,
            )
            client = offline_workbench_client(app)
            try:
                with patch.object(manager, 'ensure_deployment_ready', return_value=deployment):
                    for choice in ('saved', 'none', 'edited'):
                        payload = {'deployment_id': deployment.id}
                        if choice == 'none':
                            payload.update(profile_id=None, inherit_deployment_settings=False)
                        elif choice == 'edited':
                            payload.update(profile_id=profile.id)
                        response = client.post('/v1/chat/conversations', json=payload)
                        self.assertEqual(response.status_code, 200, response.text)
                        conversation = response.json()
                        result = client.post(f'/v1/chat/conversations/{conversation["id"]}/start', json={'task': 'Reply briefly.'})
                        self.assertEqual(result.status_code, 200, result.text)
                        run = wait_for_chat(client, conversation['id'])['current_run']
                        setup = run['effective_setup']
                        if choice == 'saved':
                            self.assertIn('SAVED-SETUP-INSTRUCTION-UNIQUE', setup['system_prompt'])
                            self.assertEqual(setup['selected_profile_id'], profile.id)
                            self.assertEqual(setup['bags']['per_request']['applied']['temperature'], 0.17)
                            self.assertEqual(setup['bags']['agent']['applied']['system_prompt'], 'SAVED-SETUP-INSTRUCTION-UNIQUE')
                        elif choice == 'edited':
                            self.assertIn('EDITED-PRESET-INSTRUCTION', setup['system_prompt'])
                            self.assertEqual(setup['bags']['per_request']['applied']['temperature'], 0.91)
                        else:
                            self.assertNotIn('SAVED-SETUP-INSTRUCTION-UNIQUE', setup['system_prompt'])
                            self.assertIsNone(setup['selected_profile_id'])
                            self.assertNotIn('temperature', setup['bags']['per_request']['requested'])
                            self.assertEqual(setup['bags']['agent']['requested'], {})
            finally:
                close_workbench_sqlite(app, client)
