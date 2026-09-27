"""Accepted startup choices stay cold, isolated and frozen through dispatch."""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.app import create_app
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import (
    DeploymentStatus, HealthReport, LocalImportRequest, ManagedDeploymentRequest,
    ModelConfigurationWriteRequest, ServerProperties,
)
from tests.scripted_model import ScriptedChatModel, set_generate_hold, wait_for_generate_hold
from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run, write_tiny_gguf


class ChatModelStagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root / "data")
        self.manager = self.app.state.manager
        self.client = offline_workbench_client(self.app)
        model = write_tiny_gguf(self.root / "model.gguf", context_length=32768)
        self.bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(model))).bundle_id
        self.ready_ids = []
        self.model_runs = []
        self.responses = {}
        self.app.state.harness = HarnessService(lambda: self.manager, model_factory=self.factory,
            knowledge_provider=lambda: self.app.state.knowledge, app_store=self.app.state.app_store)
        self.ready_patch = patch.object(self.manager, "ensure_deployment_ready", side_effect=self.ready)
        self.ready_patch.start()

    def tearDown(self):
        set_generate_hold(None)
        self.ready_patch.stop()
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def profile(self, name, startup, **response):
        return self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name=name, startup=startup, per_request=response))

    def ready(self, ident):
        # This fixture exercises the real harness/admission with an observed
        # scripted endpoint; it makes no claim about native process loading.
        self.ready_ids.append(ident)
        deployment = self.manager.get_deployment(ident)
        deployment = deployment.model_copy(update={"status": DeploymentStatus.running,
            "endpoint": "http://127.0.0.1:9/v1", "health": HealthReport(
                healthy=True, endpoint="http://127.0.0.1:9/v1", checked=utc_now()),
            "server_props": ServerProperties(fetched=utc_now(), source_url="fixture",
                n_ctx=deployment.settings.startup.applied.get("ctx_size", 8192),
                chat_template_caps={"supports_system_role": True, "supports_tools": True,
                    "supports_tool_calls": True})})
        return self.manager.store.put_deployment(deployment)

    def factory(self, run, _sink):
        self.model_runs.append(run.model_copy(deep=True))
        return ScriptedChatModel(self.responses.get("child" if run.parent_run_id else run.task,
            [AIMessage(content="Fixture completed.")]))

    def test_active_model_and_paused_queue_keep_separate_frozen_startup(self):
        old = self.profile("A", {"ctx_size": 8192, "kv_offload": True})
        staged = self.profile("B", {"ctx_size": 4096, "cache_type_k": "q8_0", "kv_offload": False})
        conversation = self.post("/v1/chat/conversations", {"model_configuration_id": old.id,
            "presented_tools": []})
        hold = threading.Event()
        self.addCleanup(hold.set)
        set_generate_hold(hold)
        active = self.post(f"/v1/chat/conversations/{conversation['id']}/start",
            {"task": "Held A", "input_message_id": "active-a"})
        wait_for_generate_hold()
        active_id = active["current_run"]["deployment_id"]
        active_before = self.manager.get_deployment(active_id)
        ready_before = list(self.ready_ids)
        with patch.object(self.manager.deployments, "stop", side_effect=AssertionError("Staging must not stop A")):
            queued = self.post(f"/v1/chat/conversations/{conversation['id']}/queue", {
                "task": "Dispatch B", "input_message_id": "staged-b", "queue_after_run_id": active["current_run"]["id"],
                "model_configuration_id": staged.id})
        self.assertEqual(self.ready_ids, ready_before, "Queue must not load or inspect another running endpoint")
        self.assertEqual(self.manager.get_deployment(active_id), active_before)
        self.assertEqual(queued["queue"][0]["execution_snapshot"]["settings"]["startup"]["requested"], staged.bags.startup.requested)
        stopped = self.post(f"/v1/chat/conversations/{conversation['id']}/cancel", {})
        self.assertEqual(stopped["current_run"]["status"], "cancel_requested")
        hold.set()
        cancelled = wait_for_run(self.client, active["current_run"]["id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.app.state.chat.observe_terminal_run(self.app.state.app_store.get_run(cancelled["id"]))
        paused = self.app.state.chat.get(conversation["id"])
        self.assertEqual(paused.queue[0].status, "paused")
        self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=staged.id, display_name="B edited", startup={"ctx_size": 16384,
                "cache_type_k": "f16", "cache_type_v": "q8_0", "kv_offload": True}))
        resumed = self.post(f"/v1/chat/conversations/{conversation['id']}/queue/resume", {"resume_paused": True})
        finished = wait_for_run(self.client, resumed["current_run"]["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        frozen = self.manager.get_deployment(finished["deployment_id"])
        self.assertNotEqual(frozen.id, active_id)
        self.assertEqual(frozen.requested_startup, staged.bags.startup.requested)
        self.assertNotIn("cache_type_v", frozen.requested_startup, "Later saved keys must not leak into accepted B")
        self.assertEqual(self.manager.get_deployment(active_id).settings, active_before.settings)
        self.assertEqual(finished["effective_setup"]["bags"]["startup"]["requested"], staged.bags.startup.requested)

    def test_queued_main_and_helper_use_accepted_settings_after_both_profiles_are_saved(self):
        main = self.profile("Main", {"ctx_size": 8192, "kv_offload": True}, temperature=0.2)
        helper_profile = self.profile("Helper", {"ctx_size": 4096, "kv_offload": False}, temperature=0.4)
        helper = self.post("/v1/agent-setups", {"name": "Frozen helper", "configuration": {
            "model_configuration_id": helper_profile.id, "instructions": "Give a brief report.", "presented_tools": []}})
        conversation = self.post("/v1/chat/conversations", {"model_configuration_id": main.id,
            "presented_tools": ["echo"], "helper_agent_ids": [helper["id"]]})
        queued = self.post(f"/v1/chat/conversations/{conversation['id']}/queue", {
            "task": "Delegate frozen work", "input_message_id": "delegate-frozen"})
        self.assertEqual(self.ready_ids, [], "Queue admission stays cold for main and helper")
        self.assertEqual(queued["queue"][0]["execution_snapshot"]["helper_snapshots"][0]["settings_snapshot"]["startup"]["requested"], helper_profile.bags.startup.requested)
        for profile in (main, helper_profile):
            self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
                configuration_id=profile.id, display_name=profile.display_name, startup={"ctx_size": 16384,
                    "cache_type_v": "q8_0", "kv_offload": True}, per_request={"temperature": 0.9}))
        self.responses["Delegate frozen work"] = [AIMessage(content="", tool_calls=[{
            "name": "task", "args": {"subagent_type": helper["id"], "description": "Give a brief report."},
            "id": "frozen-delegate"}]), AIMessage(content="Received the frozen report.")]
        resumed = self.post(f"/v1/chat/conversations/{conversation['id']}/queue/resume", {})
        completed = wait_for_run(self.client, resumed["current_run"]["id"])
        self.assertEqual(completed["status"], "completed", completed.get("error"))
        child, = [run for run in self.model_runs if run.parent_run_id]
        parent, = [run for run in self.model_runs if not run.parent_run_id]
        self.assertEqual(parent.effective_setup.bags.startup.requested, main.bags.startup.requested)
        self.assertEqual(parent.effective_setup.bags.per_request.applied["temperature"], 0.2)
        self.assertEqual(child.effective_setup.bags.startup.requested, helper_profile.bags.startup.requested)
        self.assertEqual(child.effective_setup.bags.per_request.applied["temperature"], 0.4)
        self.assertEqual(self.manager.get_deployment(child.deployment_id).requested_startup, helper_profile.bags.startup.requested)
        self.assertEqual(completed["child_runs"][0]["status"], "completed")
