"""Canonical Chat setup ownership and live capability admission."""

import tempfile
import base64
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage
from workbench_backend.app import create_app
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.setup_service import SetupService
from workbench_backend.assets.schemas import RetainedUploadRequest
from workbench_backend.agents.tools import resolve_presented_tools
from workbench_backend.desktop_automation.service import DesktopAccessScope
from workbench_backend.errors import ManagerError
from workbench_backend.inference.schemas import ConnectedDeploymentRequest, ProfileWriteRequest, ServerProperties
from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client
from tests.test_chat import wait_for_chat


class ChatSetupReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = self.root / "project"
        self.folder.mkdir()
        self.app = create_app(data_root=self.root / "data")
        self.client = offline_workbench_client(self.app)
        self.first = self.app.state.manager.attach_connected(ConnectedDeploymentRequest(
            display_name="First", endpoint="http://127.0.0.1:9/v1"))
        self.second = self.app.state.manager.attach_connected(ConnectedDeploymentRequest(
            display_name="Second", endpoint="http://127.0.0.1:10/v1"))

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def test_nullable_setup_preview_keeps_explicit_clears_without_loading_or_saving(self):
        profile = self.app.state.manager.create_profile(ProfileWriteRequest(display_name="Optional profile"))
        agent = self.client.post("/v1/agent-setups", json={"name": "Assistant",
            "configuration": {"instructions": "Answer carefully."}}).json()
        created = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.first.id, "profile_id": profile.id,
            "embedding_deployment_id": self.second.id,
            "agent_setup_version_id": agent["current_version_id"]})
        self.assertEqual(created.status_code, 200, created.text)
        chat = created.json()
        url = f"/v1/chat/conversations/{chat['id']}/readiness"
        original_resolve = SetupService.resolve
        resolution_count = 0

        def counted_resolve(service, **kwargs):
            nonlocal resolution_count
            resolution_count += 1
            return original_resolve(service, **kwargs)

        with patch.object(self.app.state.manager, "ensure_deployment_ready",
            side_effect=AssertionError("a preview must not load a model")), \
            patch.object(SetupService, "resolve", counted_resolve):
            preview = self.client.post(url, json={"overrides": {
                "bundle_id": None,
                "inherit_deployment_settings": None,
                "profile_id": None,
                "embedding_deployment_id": None,
            }})
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["status"], "ready")
        self.assertEqual(resolution_count, 1)
        self.assertIsNone(preview.json()["selection"]["configuration"]["profile_id"])
        self.assertIsNone(preview.json()["selection"]["configuration"]["embedding_deployment_id"])
        explicit_false = self.client.post(url, json={"overrides": {
            "inherit_deployment_settings": False}})
        self.assertEqual(explicit_false.status_code, 200, explicit_false.text)
        self.assertFalse(explicit_false.json()["selection"]["configuration"]["inherit_deployment_settings"])
        saved = self.client.get(f"/v1/chat/conversations/{chat['id']}").json()
        self.assertEqual(saved["profile_id"], profile.id)
        self.assertEqual(saved["embedding_deployment_id"], self.second.id)
        self.assertEqual(saved["setup_cleared_fields"], [])
        self.assertEqual(saved["transcript"], [])

    def test_unsupported_non_null_setup_preview_returns_structured_client_error(self):
        chat = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.first.id}).json()
        url = f"/v1/chat/conversations/{chat['id']}/readiness"
        rejected = self.client.post(url, json={"overrides": {
            "bundle_id": "bundle_other", "requires_project": False}})
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertEqual(rejected.json()["code"], "readiness_override_unsupported")
        self.assertEqual(rejected.json()["fields"], ["bundle_id", "requires_project"])
        self.assertEqual(self.client.get(f"/v1/chat/conversations/{chat['id']}").json()["transcript"], [])

    def test_project_context_only_and_inherited_or_fixed_main_agent_preview_stays_cold(self):
        rejected = self.client.post("/v1/projects", json={"path": str(self.folder),
            "defaults": {"deployment_id": self.second.id, "approval_mode": "full_access"}})
        self.assertEqual(rejected.status_code, 400, rejected.text)
        project = self.client.post("/v1/projects", json={"path": str(self.folder)}).json()
        agent = self.client.post("/v1/agent-setups", json={"name": "Coder",
            "configuration": {"instructions": "Write clear code."}}).json()
        chat_response = self.client.post("/v1/chat/conversations", json={
            "project_id": project["id"], "deployment_id": self.first.id,
            "agent_setup_id": agent["id"]})
        self.assertEqual(chat_response.status_code, 200, chat_response.text)
        chat = chat_response.json()
        self.assertEqual(chat["deployment_id"], self.first.id)
        before = [item.model_dump(mode="json") for item in self.app.state.manager.store.list_deployments()]
        with patch.object(self.app.state.manager, "ensure_deployment_ready",
            side_effect=AssertionError("readiness must not warm a model")), \
            patch.object(self.app.state.manager, "list_model_configurations",
                side_effect=AssertionError("readiness must not create model configurations")), \
            patch("workbench_backend.agents.effective_setup.effective_setting_values",
                side_effect=AssertionError("readiness must not inspect or cache model metadata")):
            preview = self.client.post(f"/v1/chat/conversations/{chat['id']}/readiness", json={})
        self.assertEqual(before, [item.model_dump(mode="json") for item in self.app.state.manager.store.list_deployments()])
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["selection"]["configuration"]["deployment_id"], self.first.id)
        alternate = self.client.post("/v1/agent-setups", json={"name": "Other",
            "configuration": {"deployment_id": self.second.id}}).json()
        candidate = self.client.post(f"/v1/chat/conversations/{chat['id']}/readiness", json={
            "agent_setup_id": alternate["id"]})
        self.assertEqual(candidate.status_code, 200, candidate.text)
        self.assertEqual(candidate.json()["selection"]["configuration"]["deployment_id"], self.second.id)
        self.assertEqual(self.client.get(f"/v1/chat/conversations/{chat['id']}").json()["deployment_id"], self.first.id)
        fixed = self.client.post('/v1/chat/conversations', json={'deployment_id': self.first.id, 'agent_setup_id': alternate['id']})
        self.assertEqual(fixed.status_code, 200, fixed.text)
        self.assertEqual(fixed.json()['deployment_id'], self.second.id)
        self.assertEqual(fixed.json()['transcript'], [])

    def test_readiness_resolves_latest_saved_agent_and_knowledge_by_record_identity(self):
        memory = self.client.post('/v1/knowledge/entries', json={'scope': 'user', 'kind': 'memory', 'content': 'Original memory'}).json()
        policy = {'reference_loading': {memory['id']: 'always'}}
        agent = self.client.post('/v1/agent-setups', json={'name': 'Selected', 'configuration': {'memory_entry_ids': [memory['id']], 'presented_tools': [], 'input_policy': policy}}).json()
        chat = self.client.post('/v1/chat/conversations', json={'deployment_id': self.first.id, 'agent_setup_id': agent['id']}).json()
        updated = self.client.patch(f'/v1/agent-setups/{agent["id"]}', json={'name': 'Latest', 'base_version': agent['current_version_id'], 'configuration': {'instructions': 'Saved instructions', 'memory_entry_ids': [memory['id']], 'presented_tools': [], 'input_policy': policy}}).json()
        changed_memory = self.client.post(f'/v1/knowledge/entries/{memory["id"]}/edit', json={'content': 'Latest memory', 'base_version': memory['current_version_id']}).json()
        preview = self.client.post(f'/v1/chat/conversations/{chat["id"]}/readiness', json={})
        self.assertEqual(preview.status_code, 200, preview.text)
        selection = preview.json()['selection']
        self.assertEqual(selection['agent_setup_version_id'], updated['current_version_id'])
        self.assertEqual(selection['configuration']['memory_version_refs'], [changed_memory['current_version_id']])
        self.assertEqual(selection['configuration']['presented_tools'], [])
        self.assertEqual(self.client.get(f'/v1/chat/conversations/{chat["id"]}').json()['transcript'], [])

    def test_window_grant_is_reported_before_dispatch_and_shell_defaults_off(self):
        presented, *_ = resolve_presented_tools(None, project_bound=True)
        self.assertIn("read_file", presented)
        self.assertNotIn("execute", presented)
        chat = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.first.id, "desktop_access": "all",
            "input_policy": {"pinned_tools": ["desktop_list_windows"]},
            "presented_tools": ["desktop_list_windows"]}).json()
        url = f"/v1/chat/conversations/{chat['id']}/readiness"
        missing = self.client.post(url, json={})
        self.assertEqual(missing.status_code, 200, missing.text)
        self.assertEqual(missing.json()["status"], "needs_action")
        self.assertEqual(missing.json()["issues"][0]["code"], "desktop_grant_required")
        self.assertFalse(missing.json()["can_send"])
        denied = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": "Inspect the window"})
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(denied.json()["code"], "desktop_grant_required")
        self.assertEqual(self.client.get(f"/v1/chat/conversations/{chat['id']}").json()["transcript"], [])
        with patch.object(self.app.state.harness.desktop_automation, "scope_for_thread",
            return_value=(DesktopAccessScope.all, None)):
            granted = self.client.post(url, json={})
        self.assertEqual(granted.status_code, 200, granted.text)
        self.assertTrue(granted.json()["can_send"])

    def test_browser_worker_and_lost_session_block_readiness_and_send_before_saving_message(self):
        chat = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.first.id,
            "presented_tools": ["browser_snapshot", "browser_take_screenshot"],
            "input_policy": {"tool_loading": "always"},
        }).json()
        readiness_url = f"/v1/chat/conversations/{chat['id']}/readiness"
        send_url = f"/v1/chat/conversations/{chat['id']}/start"
        missing = self.client.post(readiness_url, json={})
        self.assertEqual(missing.status_code, 200, missing.text)
        self.assertEqual(missing.json()["status"], "needs_action")
        self.assertFalse(missing.json()["can_send"])
        self.assertEqual(missing.json()["issues"][0]["code"], "browser_worker_missing")
        self.assertEqual(missing.json()["issues"][0]["action"], "Install browser worker")
        denied = self.client.post(send_url, json={"task": "Inspect the page"})
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(denied.json()["code"], "browser_worker_missing")
        self.assertEqual(self.client.get(f"/v1/chat/conversations/{chat['id']}").json()["transcript"], [])

        browser = self.app.state.browser
        with patch.object(browser.runtime, "require_installed", return_value=(self.root / "node", self.root / "cli")):
            available = self.client.post(readiness_url, json={})
            self.assertEqual(available.status_code, 200, available.text)
            self.assertTrue(available.json()["can_send"])
            with patch.object(browser, "status", return_value={"state": "lost"}):
                lost = self.client.post(readiness_url, json={})
                self.assertEqual(lost.status_code, 200, lost.text)
                self.assertEqual(lost.json()["status"], "needs_action")
                self.assertEqual(lost.json()["issues"][0]["code"], "browser_session_lost")
                self.assertEqual(lost.json()["issues"][0]["action"], "Reset browser")
                denied = self.client.post(send_url, json={"task": "Inspect the page"})
                self.assertEqual(denied.status_code, 409, denied.text)
                self.assertEqual(denied.json()["code"], "browser_session_lost")
        self.assertEqual(self.client.get(f"/v1/chat/conversations/{chat['id']}").json()["transcript"], [])

    def test_browser_tool_override_is_checked_for_the_intended_next_turn(self):
        chat = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.first.id, "presented_tools": [],
        }).json()
        chosen_tools = ["browser_snapshot"]
        preview = self.client.post(f"/v1/chat/conversations/{chat['id']}/readiness", json={
            "overrides": {"presented_tools": chosen_tools, "input_policy": {"pinned_tools": chosen_tools}},
        })
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["issues"][0]["code"], "browser_worker_missing")
        rejected = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={
            "task": "Inspect the page", "presented_tools": chosen_tools,
            "input_policy": {"pinned_tools": chosen_tools},
        })
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["code"], "browser_worker_missing")
        saved = self.client.get(f"/v1/chat/conversations/{chat['id']}").json()
        self.assertEqual(saved["transcript"], [])
        self.assertEqual(saved["presented_tools"], [])

    def test_optional_capabilities_do_not_block_cold_preview_and_full_inspection_is_explicit(self):
        chat = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.first.id, "instructions": "Keep this exact authored text.",
            "presented_tools": ["browser_snapshot", "desktop_list_windows"],
        }).json()
        self.assertIn("id", chat)
        with patch.object(self.app.state.browser.runtime, "require_installed", side_effect=AssertionError("optional setup was eagerly checked")), \
            patch.object(self.app.state.harness.desktop_automation, "snapshot_grant", side_effect=AssertionError("optional windows setup was eagerly checked")), \
            patch.object(self.app.state.manager, "ensure_deployment_ready", side_effect=AssertionError("inspection loaded a model")):
            preview = self.client.post(f"/v1/chat/conversations/{chat['id']}/readiness", json={})
            full = self.client.post(f"/v1/chat/conversations/{chat['id']}/readiness", json={"include_input_content": True})
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertTrue(preview.json()["can_send"])
        self.assertEqual(preview.json()["input_preview"]["policy"]["tool_loading"], "when_needed")
        self.assertTrue(all(row["content"] is None for row in preview.json()["input_preview"]["sources"]))
        sources = {row["id"]: row for row in full.json()["input_preview"]["sources"]}
        self.assertEqual(sources["conversation_instructions"]["content"], "Keep this exact authored text.")
        self.assertEqual(sources["tool:browser_snapshot"]["mode"], "when_needed")
        self.assertFalse(full.json()["input_preview"]["prepared"])
        self.assertEqual(self.client.get(f"/v1/chat/conversations/{chat['id']}").json()["transcript"], [])

    def test_tools_off_reference_has_explicit_choices_without_silently_enabling_reading(self):
        memory = self.client.post('/v1/knowledge/entries', json={
            'scope': 'user', 'kind': 'memory', 'content': 'Selected frozen reference'}).json()
        chat = self.client.post('/v1/chat/conversations', json={
            'deployment_id': self.first.id, 'presented_tools': []}).json()
        url = f"/v1/chat/conversations/{chat['id']}/readiness"
        blocked = self.client.post(url, json={'overrides': {'memory_entry_ids': [memory['id']]}})
        self.assertFalse(blocked.json()['can_send'])
        self.assertEqual(blocked.json()['issues'][0]['code'], 'deferred_reference_tools_off')
        self.assertEqual(blocked.json()['issues'][0]['action'], 'Include now, Remove, or Enable reading')
        included = self.client.post(url, json={'overrides': {'memory_entry_ids': [memory['id']],
            'input_policy': {'reference_loading': {memory['id']: 'always'}}}})
        self.assertTrue(included.json()['can_send'], included.text)
        self.assertEqual(included.json()['selection']['configuration']['presented_tools'], [])
        self.assertEqual(self.client.get(f"/v1/chat/conversations/{chat['id']}").json()['memory_version_refs'], [])

    def test_selected_context_readiness_matches_send_and_skips_exclusions(self):
        chat = self.client.post('/v1/chat/conversations', json={'deployment_id': self.first.id}).json()
        url = f"/v1/chat/conversations/{chat['id']}/readiness"
        missing_project = self.client.post(url, json={'project_file_refs': ['notes.txt']}).json()
        self.assertFalse(missing_project['can_send'])
        self.assertEqual(missing_project['issues'][0]['code'], 'project_context_required')
        omitted_path = self.client.post(url, json={'project_file_refs': ['notes.txt'], 'overrides': {
            'input_policy': {'excluded_sources': ['project_file:notes.txt']}}}).json()
        self.assertTrue(omitted_path['can_send'], omitted_path)
        asset = self.app.state.chat.assets.retain_upload(RetainedUploadRequest(session_id=chat['id'],
            filename='selected.md', content_type='text/markdown',
            content_base64=base64.b64encode(b'Original selected content').decode('ascii')))
        with patch.object(self.app.state.chat.assets, '_load_content',
            side_effect=AssertionError('Cold readiness must not load attachment bytes')):
            active = self.client.post(url, json={'attachment_ids': [asset.id]}).json()
        self.assertTrue(active['can_send'], active)
        self.app.state.chat.assets.store.put(asset.model_copy(update={'deleted_at': 'now'}), b'Original selected content')
        deleted = self.client.post(url, json={'attachment_ids': [asset.id]}).json()
        self.assertFalse(deleted['can_send'])
        self.assertEqual(deleted['issues'][0]['code'], 'retained_asset_unavailable')
        omitted = self.client.post(url, json={'attachment_ids': [asset.id], 'overrides': {
            'input_policy': {'excluded_sources': [f'attachment:{asset.id}']}}}).json()
        self.assertTrue(omitted['can_send'], omitted)

    def test_always_skill_missing_requirements_blocks_before_send_and_keeps_controls(self):
        skill = self.client.post('/v1/knowledge/entries', json={'scope': 'user', 'kind': 'skill',
            'content': '---\nname: echo-check\ndescription: Verify a value.\nrequired-tools: [echo]\n---\nUse echo.\n'}).json()
        self.assertIn('id', skill, skill)
        chat = self.client.post('/v1/chat/conversations', json={
            'deployment_id': self.first.id, 'presented_tools': []}).json()
        choices = {'skill_entry_ids': [skill['id']],
            'input_policy': {'reference_loading': {skill['id']: 'always'}}}
        with patch.object(self.app.state.manager, 'ensure_deployment_ready',
                side_effect=AssertionError('Missing requirements must block before model loading')):
            readiness = self.client.post(f"/v1/chat/conversations/{chat['id']}/readiness",
                json={'overrides': choices})
            self.assertEqual(readiness.status_code, 200, readiness.text)
            blocked = readiness.json()
            self.assertEqual(blocked['status'], 'needs_action')
            self.assertFalse(blocked['can_send'])
            self.assertEqual(blocked['issues'][0]['code'], 'skill_selection_required')
            self.assertEqual(blocked['issues'][0]['action'], 'Update selected tools, connections or project')
            source = next(row for row in blocked['input_preview']['sources'] if row['id'] == f"skill:{skill['id']}")
            self.assertEqual(source['required_tools'], ['echo'])
            rejected = self.client.post(f"/v1/chat/conversations/{chat['id']}/start",
                json={'task': 'Run the check', **choices})
            self.assertEqual(rejected.status_code, 409, rejected.text)
            self.assertEqual(rejected.json()['code'], 'skill_selection_required')
        saved = self.client.get(f"/v1/chat/conversations/{chat['id']}").json()
        self.assertEqual(saved['transcript'], [])
        self.assertEqual(saved['run_ids'], [])
        self.assertEqual(saved['presented_tools'], [])
        removed = self.client.post(f"/v1/chat/conversations/{chat['id']}/readiness",
            json={'overrides': {**choices, 'input_policy': {'reference_loading': {skill['id']: 'off'}}}})
        self.assertTrue(removed.json()['can_send'], removed.text)

    def test_project_file_readiness_validates_path_and_selected_reader_cold(self):
        (self.folder / 'notes.txt').write_text('Read on demand', encoding='utf-8')
        project = self.client.post('/v1/projects', json={'path': str(self.folder)}).json()
        chat = self.client.post('/v1/chat/conversations', json={
            'deployment_id': self.first.id, 'project_id': project['id'], 'presented_tools': ['read_file']}).json()
        url = f"/v1/chat/conversations/{chat['id']}/readiness"
        with patch.object(SetupService, 'read_project_file', side_effect=AssertionError('No file bodies in cold readiness')):
            ready = self.client.post(url, json={'project_file_refs': ['notes.txt']}).json()
        self.assertTrue(ready['can_send'], ready)
        missing = self.client.post(url, json={'project_file_refs': ['missing.txt']}).json()
        self.assertEqual(missing['issues'][0]['code'], 'project_file_missing')
        denied = self.client.post(url, json={'project_file_refs': ['notes.txt'], 'overrides': {
            'input_policy': {'excluded_sources': ['tool:read_file']}}}).json()
        self.assertEqual(denied['issues'][0]['code'], 'context_file_tool_required')

    def test_known_history_incompatibility_rejects_send_before_saving_message(self):
        self.app.state.harness = HarnessService(
            lambda: self.app.state.manager, app_store=self.app.state.app_store,
            knowledge_provider=lambda: self.app.state.knowledge,
            model_factory=lambda *_: ScriptedChatModel([AIMessage(content="First reply")]),
        )
        chat = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.first.id, "presented_tools": []}).json()
        first = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": "First"})
        self.assertEqual(first.status_code, 200, first.text)
        completed = wait_for_chat(self.client, chat["id"])
        self.assertEqual(completed["current_run"]["status"], "completed")
        deployment = self.app.state.manager.get_deployment(self.first.id)
        self.app.state.manager.store.put_deployment(deployment.model_copy(update={
            "server_props": ServerProperties(fetched="now", source_url="http://fixture/props",
                chat_template_caps={"supports_system_role": False})
        }))
        preview = self.client.post(f"/v1/chat/conversations/{chat['id']}/readiness", json={})
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["status"], "incompatible")
        before = completed["transcript"]
        rejected = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": "Second"})
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["code"], "context_system_unsupported")
        self.assertEqual(self.client.get(f"/v1/chat/conversations/{chat['id']}").json()["transcript"], before)

    def test_unavailable_helper_is_reported_before_saving_message(self):
        helper = self.client.post("/v1/agent-setups", json={"name": "Other model",
            "configuration": {"deployment_id": self.second.id}}).json()
        chat = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.first.id, "helper_agent_ids": [helper["id"]],
            "presented_tools": ["echo"]}).json()
        self.app.state.manager.store.delete_deployment(self.second.id)
        preview = self.client.post(f"/v1/chat/conversations/{chat['id']}/readiness", json={})
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["status"], "incompatible")
        self.assertEqual(preview.json()["issues"][0]["code"], "helper_unavailable")
        rejected = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={"task": "Delegate"})
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(self.client.get(f"/v1/chat/conversations/{chat['id']}").json()["transcript"], [])

    def test_failed_model_load_restores_previous_chat_selection_and_preserves_retry_identity(self):
        chat = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.first.id, "presented_tools": []}).json()
        with patch.object(self.app.state.manager, "ensure_deployment_ready",
            side_effect=ManagerError("Unable to load model", code="model_load_failed", status_code=409)):
            rejected = self.client.post(f"/v1/chat/conversations/{chat['id']}/start", json={
                "task": "Use the other model", "deployment_id": self.second.id})
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["code"], "model_load_failed")
        saved = self.client.get(f"/v1/chat/conversations/{chat['id']}").json()
        self.assertEqual(saved["deployment_id"], self.first.id)
        self.assertEqual([message["content"] for message in saved["transcript"]], ["Use the other model"])
        self.assertIsNone(saved["transcript"][0]["run_id"])
        self.assertEqual(saved["run_ids"], [])


if __name__ == "__main__":
    unittest.main()
