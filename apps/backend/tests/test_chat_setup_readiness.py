"""Canonical Chat setup ownership and live capability admission."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage
from workbench_backend.app import create_app
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.setup_service import SetupService
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

    def test_project_cannot_save_execution_setup_and_agent_does_not_switch_main_model(self):
        rejected = self.client.post("/v1/projects", json={"path": str(self.folder),
            "defaults": {"deployment_id": self.second.id, "approval_mode": "full_access"}})
        self.assertEqual(rejected.status_code, 400, rejected.text)
        project = self.client.post("/v1/projects", json={"path": str(self.folder)}).json()
        agent = self.client.post("/v1/agent-setups", json={"name": "Coder",
            "configuration": {"deployment_id": self.second.id, "instructions": "Write clear code."}}).json()
        chat_response = self.client.post("/v1/chat/conversations", json={
            "project_id": project["id"], "deployment_id": self.first.id,
            "agent_setup_version_id": agent["current_version_id"]})
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
            "agent_setup_version_id": alternate["current_version_id"]})
        self.assertEqual(candidate.status_code, 200, candidate.text)
        self.assertEqual(candidate.json()["selection"]["configuration"]["deployment_id"], self.first.id)
        self.assertEqual(self.client.get(f"/v1/chat/conversations/{chat['id']}").json()["deployment_id"], self.first.id)

    def test_window_grant_is_reported_before_dispatch_and_shell_defaults_off(self):
        presented, *_ = resolve_presented_tools(None, project_bound=True)
        self.assertIn("read_file", presented)
        self.assertNotIn("execute", presented)
        chat = self.client.post("/v1/chat/conversations", json={
            "deployment_id": self.first.id, "desktop_access": "all",
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
