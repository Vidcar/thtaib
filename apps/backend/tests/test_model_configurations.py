"""Unified configurations retain snapshots and gate actual lifecycle changes."""
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench_backend.agents.setup_schemas import SetupConfiguration
from workbench_backend.agents.setup_service import SetupService
from workbench_backend.chat.schemas import ChatConversation, ChatQueueItem
from workbench_backend.errors import ManagerError
from workbench_backend.inference.schemas import (LocalImportRequest, ManagedDeploymentRequest,
    ModelConfigurationWriteRequest, ReconfigureDeploymentRequest)
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.migrate import open_application_store
from support import write_tiny_gguf


class ModelConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = WorkbenchPaths(Path(self.tmp.name)).ensure()
        self.manager = ModelManager(self.paths)
        file = write_tiny_gguf(Path(self.tmp.name) / "model.gguf")
        self.bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(file))).bundle_id

    def deployment(self, **startup):
        return self.manager.create_managed(ManagedDeploymentRequest(bundle_id=self.bundle_id, startup=startup, auto_start=False))

    def test_migration_and_repeated_loading_are_idempotent(self):
        first = self.deployment(ctx_size=8192)
        self.assertEqual(first.id, self.deployment(ctx_size=8192).id)
        profiles = self.manager.list_model_configurations(self.bundle_id)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(self.manager.list_model_configurations(self.bundle_id), profiles)
        self.assertEqual(self.manager.store.get_bundle(self.bundle_id).default_configuration_id, profiles[0].id)
        self.assertEqual(self.manager.get_deployment(first.id).settings, first.settings)

    def test_configuration_save_revision_and_default_are_explicit(self):
        original = self.manager.list_model_configurations(self.bundle_id)[0]
        variant = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(display_name="Long", startup={"ctx_size":8192}))
        self.assertEqual(self.manager.store.get_bundle(self.bundle_id).default_configuration_id, original.id)
        updated = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(display_name="Long", configuration_id=variant.id, expected_revision=1, make_default=True, startup={"ctx_size":16384}))
        self.assertEqual(updated.revision, 2)
        with self.assertRaises(ManagerError) as caught:
            self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(display_name="stale", configuration_id=variant.id, expected_revision=1))
        self.assertEqual(caught.exception.code, "configuration_revision_conflict")
        self.assertEqual(self.manager.store.get_bundle(self.bundle_id).default_configuration_id, variant.id)

    def test_equivalent_configurations_share_chooser_entry_and_live_model_name(self):
        original = self.manager.list_model_configurations(self.bundle_id)[0]
        duplicate = self.manager.save_model_configuration(self.bundle_id,
            ModelConfigurationWriteRequest(display_name="Old duplicate"))
        self.assertEqual([p.id for p in self.manager.list_model_configurations(self.bundle_id)], [original.id])
        self.assertEqual([p.id for p in self.manager.list_profiles()], [original.id])
        self.assertEqual(self.manager.list_profiles()[0].equivalent_configuration_ids, [duplicate.id])
        with open_application_store(self.paths) as store:
            resolved = SetupService(store, self.manager).resolve(overrides=SetupConfiguration(model_configuration_id=duplicate.id))
            self.assertEqual(resolved.configuration.model_configuration_id, original.id)
            self.assertEqual(resolved.configuration.profile_id, original.id)
        self.assertEqual(self.manager.get_profile(duplicate.id).id, duplicate.id)
        bundle = self.manager.store.get_bundle(self.bundle_id)
        self.manager.store.put_bundle(bundle.model_copy(update={"display_name": "Renamed model"}))
        self.assertEqual(self.manager.get_profile(original.id).bundle_name, "Renamed model")
        self.assertEqual(self.manager.list_model_configurations(self.bundle_id)[0].bundle_name, "Renamed model")
        self.assertNotIn('"bundle_name"', self.manager.store.profiles_path.read_text())
        self.manager.set_default_configuration(self.bundle_id, duplicate.id)
        self.assertEqual([p.id for p in self.manager.list_model_configurations(self.bundle_id)], [original.id])
        self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=original.id, display_name="Default", startup={"ctx_size": 8192}))
        self.assertEqual([p.id for p in self.manager.list_model_configurations(self.bundle_id)], [original.id])
        self.assertEqual(self.manager.canonical_configuration(duplicate.id).bags.startup.requested["ctx_size"], 8192)
        self.assertEqual(self.manager.get_profile(duplicate.id).bags.startup.requested, {})

    def test_configuration_names_are_unique_and_legacy_instructions_are_not_lost(self):
        from workbench_backend.inference.schemas import ProfileWriteRequest
        legacy = self.manager.create_profile(ProfileWriteRequest(display_name="Legacy", bundle_id=self.bundle_id,
            agent={"system_prompt": "Retain the authored instructions."}))
        saved = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=legacy.id, display_name="Legacy", per_request={"temperature": 0.5}))
        self.assertEqual(saved.bags.agent.requested, legacy.bags.agent.requested)
        for name, code in ((" ", "configuration_name_required"), (" legacy ", "configuration_name_conflict")):
            with self.subTest(name=name), self.assertRaises(ManagerError) as error:
                self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(display_name=name))
            self.assertEqual(error.exception.code, code)
        with self.assertRaises(ManagerError) as error:
            self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
                display_name="New", agent={"system_prompt": "Wrong owner"}))
        self.assertEqual(error.exception.code, "configuration_agent_instructions")

    def test_fixed_port_collision_is_rejected_before_process_creation(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            deployment = self.deployment(port=port)
            with patch.object(self.manager.deployments.processes, "start") as start:
                with self.assertRaises(ManagerError) as caught:
                    self.manager.start_deployment(deployment.id)
            self.assertEqual(caught.exception.code, "managed_port_conflict")
            start.assert_not_called()
            self.assertEqual(self.manager.get_deployment(deployment.id).status.value, "stopped")

    def test_auto_port_is_checked_at_launch(self):
        deployment = self.deployment()
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            from workbench_backend.inference.deployments import _first_free_port
            self.assertNotEqual(_first_free_port("127.0.0.1", port), port)
        self.assertNotIn("port", deployment.requested_startup)

    def test_queued_and_paused_messages_block_reconfigure_before_stop(self):
        deployment = self.deployment(ctx_size=8192)
        for status in ("queued", "dispatching", "paused"):
            with open_application_store(self.paths) as store:
                store.put_conversation(ChatConversation(id="chat",deployment_id=deployment.id,archived=status == "paused",created_at="now",updated_at="now",
                    queue=[ChatQueueItem(id="queued",task="later",status=status,created_at="now",updated_at="now")]))
            with patch.object(self.manager.deployments, "stop") as stop:
                with self.assertRaises(ManagerError) as caught:
                    self.manager.reconfigure_deployment(deployment.id, ReconfigureDeploymentRequest(startup={"ctx_size":16384}))
            self.assertEqual(caught.exception.code, "deployment_active")
            stop.assert_not_called()

    def test_application_editor_replaces_its_layer_and_known_provenance_is_reported(self):
        with open_application_store(self.paths) as store:
            store.put_setup_defaults(SetupConfiguration(approval_mode="full_access"))
            service = SetupService(store, self.manager)
            app = service.resolve(overrides=SetupConfiguration(), editing_layer="application")
            self.assertEqual(app.effective_values["approval_mode"].value, "ask")
            agent = service.resolve(overrides=SetupConfiguration(), editing_layer="agent")
            self.assertEqual(agent.effective_values["approval_mode"].value, "full_access")
            self.assertTrue(agent.effective_values["approval_mode"].inherited)

    def test_canonical_configuration_prepares_only_at_execution(self):
        configuration = self.manager.list_model_configurations(self.bundle_id)[0]
        with open_application_store(self.paths) as store:
            service = SetupService(store, self.manager)
            preview = service.resolve(overrides=SetupConfiguration(model_configuration_id=configuration.id))
            self.assertIsNone(preview.configuration.deployment_id)
            self.assertEqual(self.manager.list_deployments(), [])
            prepared = service.resolve(overrides=SetupConfiguration(model_configuration_id=configuration.id), prepare_model=True)
            self.assertIsNotNone(prepared.configuration.deployment_id)
            self.assertEqual(self.manager.get_deployment(prepared.configuration.deployment_id).status.value, "stopped")

    def test_historical_context_shrink_is_rejected_before_stop(self):
        deployment = self.deployment(ctx_size=8192)
        with open_application_store(self.paths) as store:
            store.put_conversation(ChatConversation(id="chat", deployment_id=deployment.id, created_at="now", updated_at="now", run_ids=["retained-run"]))
        with patch.object(self.manager.runtime, "require_executable", return_value=Path("llama-server")), patch.object(self.manager.deployments, "stop") as stop:
            with self.assertRaises(ManagerError) as caught:
                self.manager.reconfigure_deployment(deployment.id, ReconfigureDeploymentRequest(startup={"ctx_size":4096}, conversation_id="chat"))
        self.assertEqual(caught.exception.code, "context_history_requires_new_chat")
        self.assertEqual(caught.exception.details["applied_context"], 8192)
        stop.assert_not_called()

    def test_explicit_null_response_override_really_omits_profile_value(self):
        from workbench_backend.agents.effective_setup import _resolve_per_request
        deployment = self.deployment()
        profile = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(display_name="Warm",per_request={"temperature":0.7}))
        bag = _resolve_per_request(profile, deployment, {"temperature":None})
        self.assertNotIn("temperature", bag.applied)

    def test_healthy_matching_configuration_wins_over_recent_failed_duplicate(self):
        from workbench_backend.inference.schemas import DeploymentStatus, HealthReport, ProcessIdentity
        deployment = self.deployment(ctx_size=8192)
        config = self.manager.list_model_configurations(self.bundle_id)[0]
        healthy = deployment.model_copy(update={"status":DeploymentStatus.running,"process_identity":ProcessIdentity(pid=42,create_time=1,executable="fixture"),
            "health":HealthReport(healthy=True,endpoint="fixture",checked="now"),"updated_at":"2020"})
        self.manager.store.put_deployment(healthy)
        self.manager.store.put_deployment(deployment.model_copy(update={"id":"duplicate","status":DeploymentStatus.failed,"updated_at":"2030"}))
        self.assertEqual(self.manager.configuration_deployment(config.id).id, healthy.id)

    def test_model_selection_uses_default_and_preserves_explicit_loaded_target(self):
        first = self.deployment(ctx_size=8192)
        second = self.deployment(ctx_size=16384)
        configurations = self.manager.list_model_configurations(self.bundle_id)
        default = self.manager.store.get_bundle(self.bundle_id).default_configuration_id
        with open_application_store(self.paths) as store:
            service = SetupService(store, self.manager)
            model = service.resolve(overrides=SetupConfiguration(bundle_id=self.bundle_id))
            self.assertEqual(model.configuration.model_configuration_id, default)
            selected = next(p for p in configurations if p.bags.startup.requested.get("ctx_size") == 16384)
            preview = service.resolve(overrides=SetupConfiguration(deployment_id=first.id, model_configuration_id=selected.id))
            self.assertEqual(preview.configuration.deployment_id, first.id)
            self.assertTrue(preview.effective_values["startup.ctx_size"].requires_reload)
            self.assertEqual(self.manager.get_deployment(second.id).requested_startup["ctx_size"], 16384)

    def test_parent_permission_and_sampler_value_remain_available_under_override(self):
        with open_application_store(self.paths) as store:
            store.put_setup_defaults(SetupConfiguration(approval_mode="full_access", per_request_overrides={"temperature":0.3}))
            service = SetupService(store, self.manager)
            resolved = service.resolve(overrides=SetupConfiguration(approval_mode="ask", per_request_overrides={"temperature":0.7}))
            self.assertEqual(resolved.effective_values["approval_mode"].inherited_value, "full_access")
            self.assertEqual(resolved.effective_values["per_request.temperature"].inherited_value, 0.3)
            self.assertEqual(resolved.effective_values["per_request.temperature"].requested_override, 0.7)

    def test_explicit_other_model_overrides_inherited_selector_but_same_model_keeps_variant(self):
        from workbench_backend.inference.schemas import ConnectedDeploymentRequest
        first = self.deployment(ctx_size=8192)
        profile = self.manager.list_model_configurations(self.bundle_id)[0]
        same_model = self.deployment(ctx_size=16384)
        connected = self.manager.attach_connected(ConnectedDeploymentRequest(
            display_name="Explicit other", endpoint="http://127.0.0.1:9/v1"))
        other_file = write_tiny_gguf(Path(self.tmp.name) / "other.gguf", name="Other model")
        other_bundle = self.manager.import_local(LocalImportRequest(source_path=str(other_file))).bundle_id
        with open_application_store(self.paths) as store:
            store.put_setup_defaults(SetupConfiguration(model_configuration_id=profile.id))
            service = SetupService(store, self.manager)
            explicit = service.resolve(overrides=SetupConfiguration(deployment_id=connected.id))
            self.assertEqual(explicit.configuration.deployment_id, connected.id)
            self.assertIsNone(explicit.configuration.model_configuration_id)
            self.assertIsNone(explicit.configuration.profile_id)
            self.assertIsNone(explicit.configuration.bundle_id)
            same = service.resolve(overrides=SetupConfiguration(deployment_id=same_model.id))
            self.assertEqual(same.configuration.deployment_id, same_model.id)
            self.assertEqual(same.configuration.model_configuration_id, profile.id)
            self.assertTrue(same.effective_values["startup.ctx_size"].requires_reload)
            other = service.resolve(overrides=SetupConfiguration(bundle_id=other_bundle))
            self.assertEqual(other.configuration.bundle_id, other_bundle)
            self.assertNotEqual(other.configuration.model_configuration_id, profile.id)
            self.assertNotEqual(other.configuration.deployment_id, first.id)
