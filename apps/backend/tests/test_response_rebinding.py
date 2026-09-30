"""Explicit response configuration switches preserve a verified loaded model."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.support import write_tiny_gguf
from workbench_backend.agents.effective_setup import resolve_effective_setup
from workbench_backend.agents.setup_schemas import SetupConfiguration
from workbench_backend.agents.setup_service import SetupService
from workbench_backend.chat.schemas import ChatConversation, ChatQueueItem
from workbench_backend.errors import ManagerError
from workbench_backend.inference.schemas import (DeploymentStatus, HealthReport, LocalImportRequest, ManagedDeploymentRequest,
    ModelConfigurationWriteRequest, ProcessIdentity, ReconfigureDeploymentRequest, ResponseRecipeOrigin,
    ServerProperties)
from workbench_backend.knowledge.schemas import KnowledgeRefs
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.migrate import open_application_store


class ResponseRebindingTests(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.paths = WorkbenchPaths(Path(fixture.name)).ensure()
        self.manager = ModelManager(self.paths)
        self.addCleanup(self.manager.capability_checks.close)
        self.addCleanup(self.manager.imports.close)
        source_file = write_tiny_gguf(Path(fixture.name) / "model.gguf")
        self.bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(source_file))).bundle_id
        initial = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(display_name="Initial setup"))
        self.startup = {"ctx_size": 16384, "n_gpu_layers": "all", "reasoning_preserve": True}
        source = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=initial.id, display_name="Thinking", startup=self.startup,
            per_request={"temperature": 1.0, "top_p": 0.95, "reasoning_effort": "xhigh"}))
        self.source = self.manager.store.put_profile(source.model_copy(update={"recipe_origin": ResponseRecipeOrigin(
            recipe_id="thinking-fixture", name="Thinking", source_repo_id="fixture/model",
            source_revision="pinned", card_sha256="a" * 64, section="Sampling")}))
        created = self.manager.create_managed(ManagedDeploymentRequest(
            bundle_id=self.bundle_id, profile_id=source.id, auto_start=False))
        self.loaded = self.manager.store.put_deployment(created.model_copy(update={
            "status": DeploymentStatus.running, "pid": 42,
            "process_identity": ProcessIdentity(pid=42, create_time=1, executable="fixture"),
            "health": HealthReport(healthy=True, endpoint="fixture", checked="now"),
            "server_props": ServerProperties(fetched="now", source_url="fixture", n_ctx=16384),
        }))
        self.balanced = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="Balanced", startup=self.startup, make_default=True,
            per_request={**source.bags.per_request.requested, "reasoning_effort": "medium",
                         "reasoning_budget_tokens": 2048, "max_tokens": 8192}))

    def request(self, **updates):
        values = {"startup": dict(self.startup), "replace_startup": True,
                  "model_configuration_id": self.balanced.id,
                  "expected_configuration_revision": self.balanced.revision,
                  "expected_updated_at": self.loaded.updated_at}
        return ReconfigureDeploymentRequest(**{**values, **updates})

    def guards(self, *, ownership="match", healthy=None):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(self.manager.runtime, "require_executable", return_value=Path("llama-server")))
        classify = stack.enter_context(patch.object(self.manager.deployments.processes, "classify", return_value=ownership))
        health = stack.enter_context(patch.object(self.manager.deployments, "health", return_value=healthy or self.loaded))
        stop = stack.enter_context(patch.object(self.manager.deployments, "stop", side_effect=RuntimeError("reload path")))
        start = stack.enter_context(patch.object(self.manager.deployments, "start"))
        return classify, health, stop, start

    def test_balanced_binding_preserves_process_startup_recipe_and_next_request(self):
        _, health, stop, start = self.guards()
        result = self.manager.reconfigure_deployment(self.loaded.id, self.request())
        health.assert_called_once_with(self.loaded.id)
        stop.assert_not_called()
        start.assert_not_called()
        for field in ("id", "bundle_id", "pid", "process_identity", "endpoint", "requested_startup",
                      "applied_startup", "startup_overrides", "server_props", "loaded_chat_template_origin"):
            self.assertEqual(getattr(result, field), getattr(self.loaded, field), field)
        self.assertEqual(result.settings.startup, self.loaded.settings.startup)
        self.assertEqual(result.profile_id, self.source.id)
        self.assertEqual(result.configuration_revision, self.source.revision)
        self.assertEqual(result.profile_snapshot, self.source.bags)
        self.assertEqual(result.settings.per_request, self.loaded.settings.per_request)
        self.assertEqual(self.manager.store.get_profile(self.source.id).model_dump(exclude={"bundle_name"}),
                         self.source.model_dump(exclude={"bundle_name"}))
        self.assertIsNone(self.manager.get_profile(self.balanced.id).recipe_origin)
        self.assertEqual(self.manager.get_bundle(self.bundle_id).default_configuration_id, self.balanced.id)
        with open_application_store(self.paths) as store:
            # Selecting the default alone must find the rebound loaded instance.
            selected = SetupService(store, self.manager).resolve(overrides=SetupConfiguration(bundle_id=self.bundle_id))
        self.assertEqual(selected.configuration.deployment_id, self.loaded.id)
        self.assertFalse(any(f.requires_reload for f in selected.effective_values.values()))
        effective = resolve_effective_setup(deployment=result, profile=self.manager.get_profile(self.balanced.id),
            knowledge_refs=KnowledgeRefs(), knowledge_versions=[], surface_system_prompt=None,
            default_system_prompt="Fixture instructions")
        self.assertEqual(effective.bags.per_request.applied["reasoning_budget_tokens"], 2048)
        self.assertEqual(effective.bags.per_request.applied["max_tokens"], 8192)
        self.assertEqual(effective.bags.per_request.applied["temperature"], 1.0)

    def test_automatic_port_uses_existing_identity_rule_and_keeps_actual_port(self):
        applied = {**self.loaded.applied_startup, "port": 51819}
        self.loaded = self.manager.store.put_deployment(self.loaded.model_copy(update={
            "applied_startup": applied, "settings": self.loaded.settings.model_copy(update={
                "startup": self.loaded.settings.startup.model_copy(update={"applied": applied})})}))
        _, _, stop, _ = self.guards()
        result = self.manager.reconfigure_deployment(self.loaded.id, self.request())
        self.assertEqual(result.applied_startup["port"], 51819)
        self.assertNotIn("port", result.requested_startup)
        stop.assert_not_called()

    def test_busy_and_revision_guards_still_precede_response_binding(self):
        _, health, stop, _ = self.guards()
        for status in ("queued", "dispatching", "paused"):
            with self.subTest(status=status):
                with open_application_store(self.paths) as store:
                    store.put_conversation(ChatConversation(id="chat", deployment_id=self.loaded.id,
                        created_at="now", updated_at="now", queue=[ChatQueueItem(
                            id="queued", task="later", status=status, created_at="now", updated_at="now")]))
                with self.assertRaises(ManagerError) as caught:
                    self.manager.reconfigure_deployment(self.loaded.id, self.request())
                self.assertEqual(caught.exception.code, "deployment_active")
        with open_application_store(self.paths) as store:
            chat = store.get_conversation("chat")
            store.put_conversation(chat.model_copy(update={"queue": []}))
        for request, code in ((self.request(expected_configuration_revision=0), "configuration_revision_conflict"),
                              (self.request(expected_updated_at="stale"), "deployment_revision_conflict")):
            with self.assertRaises(ManagerError) as caught:
                self.manager.reconfigure_deployment(self.loaded.id, request)
            self.assertEqual(caught.exception.code, code)
        health.assert_not_called()
        stop.assert_not_called()
        self.assertEqual(self.manager.get_deployment(self.loaded.id).profile_id, self.source.id)

    def test_unproven_process_does_not_take_response_only_path(self):
        _, health, stop, _ = self.guards(ownership="unproven")
        with self.assertRaisesRegex(RuntimeError, "reload path"):
            self.manager.reconfigure_deployment(self.loaded.id, self.request())
        health.assert_not_called()
        stop.assert_called_once_with(self.loaded.id)
        self.assertEqual(self.manager.get_deployment(self.loaded.id).profile_id, self.source.id)

    def test_fresh_unhealthy_observation_does_not_take_response_only_path(self):
        unhealthy = self.loaded.model_copy(update={"status": DeploymentStatus.unhealthy,
            "health": HealthReport(healthy=False, endpoint="fixture", checked="later")})
        _, health, stop, _ = self.guards(healthy=unhealthy)
        with self.assertRaisesRegex(RuntimeError, "reload path"):
            self.manager.reconfigure_deployment(self.loaded.id, self.request())
        health.assert_called_once()
        stop.assert_called_once()
        self.assertEqual(self.manager.get_deployment(self.loaded.id).profile_id, self.source.id)

    def test_different_startup_keeps_existing_stop_and_start(self):
        _, health, stop, start = self.guards()
        stop.side_effect = None
        stop.return_value = self.loaded.model_copy(update={"status": DeploymentStatus.stopped,
            "pid": None, "process_identity": None})
        def restarted(ident):
            pending = self.manager.store.get_deployment(ident)
            return pending.model_copy(update={"status": DeploymentStatus.running, "pid": 43,
                "process_identity": ProcessIdentity(pid=43, create_time=2, executable="fixture"),
                "health": self.loaded.health})
        start.side_effect = restarted
        result = self.manager.reconfigure_deployment(self.loaded.id,
            self.request(startup={**self.startup, "ctx_size": 32768}))
        stop.assert_called_once_with(self.loaded.id)
        start.assert_called_once_with(self.loaded.id)
        health.assert_not_called()
        self.assertEqual(result.applied_startup["ctx_size"], 32768)
        self.assertEqual(result.pid, 43)


if __name__ == "__main__":
    unittest.main()
