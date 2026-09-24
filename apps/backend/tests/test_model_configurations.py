"""Unified configurations retain snapshots and gate actual lifecycle changes."""
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workbench_backend.agents.setup_schemas import SetupConfiguration
from workbench_backend.agents.setup_service import SetupService
from workbench_backend.chat.schemas import ChatConversation, ChatQueueItem
from workbench_backend.errors import HarnessError, ManagerError
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
        # This record predates named configurations, unlike an explicit Save as
        # variant action whose chosen identity must remain in the selector.
        duplicate = self.manager.store.put_profile(original.model_copy(update={
            "id": "legacy_duplicate", "display_name": "Old duplicate", "configuration_origin": "legacy"}))
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

    def test_explicit_equal_named_variants_keep_identity_after_listing_and_restart(self):
        original = self.manager.list_model_configurations(self.bundle_id)[0]
        variant = self.manager.save_model_configuration(self.bundle_id,
            ModelConfigurationWriteRequest(display_name="My experiment"))
        self.assertEqual(variant.bags, original.bags)
        self.assertEqual(variant.configuration_origin, "named")
        for _ in range(2):
            self.assertEqual({p.id for p in self.manager.list_model_configurations(self.bundle_id)}, {original.id, variant.id})
            self.assertEqual(self.manager.canonical_configuration(variant.id).id, variant.id)
        self.manager.set_default_configuration(self.bundle_id, variant.id)
        reopened = ModelManager(self.paths)
        self.addCleanup(reopened.imports.close)
        self.assertEqual({p.id for p in reopened.list_profiles()}, {original.id, variant.id})
        self.assertEqual(reopened.get_bundle(self.bundle_id).default_configuration_id, variant.id)
        changed = reopened.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=variant.id, display_name="My experiment", per_request={"temperature": 0.5}))
        self.assertEqual(changed.id, variant.id)
        self.assertEqual(reopened.get_profile(original.id).bags, original.bags)

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

    def test_named_variants_share_healthy_startup_but_keep_selected_response_settings(self):
        from workbench_backend.agents.effective_setup import resolve_effective_setup
        from workbench_backend.inference.schemas import DeploymentStatus, HealthReport, ProcessIdentity
        from workbench_backend.knowledge.schemas import KnowledgeRefs

        loaded_profile = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="Loaded variant", startup={"ctx_size": 8192}, per_request={"temperature": 0.2}))
        deployment = self.manager.create_managed(ManagedDeploymentRequest(
            bundle_id=self.bundle_id, profile_id=loaded_profile.id, auto_start=False))
        self.manager.store.put_deployment(deployment.model_copy(update={
            "status": DeploymentStatus.running,
            "process_identity": ProcessIdentity(pid=42, create_time=1, executable="fixture"),
            "health": HealthReport(healthy=True, endpoint="fixture", checked="now"),
        }))
        selected = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="Response variant", startup={"ctx_size": 8192}, per_request={"temperature": 0.8}))
        selected = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=selected.id, expected_revision=selected.revision,
            display_name="Response variant", startup={"ctx_size": 8192}, per_request={"temperature": 0.9}))

        with open_application_store(self.paths) as store:
            resolved = SetupService(store, self.manager).resolve(
                overrides=SetupConfiguration(model_configuration_id=selected.id), prepare_model=True)
        self.assertEqual(resolved.configuration.deployment_id, deployment.id)
        self.assertEqual(resolved.configuration.profile_id, selected.id)
        self.assertFalse(any(fact.requires_reload for fact in resolved.effective_values.values()))
        self.assertEqual(len(self.manager.list_deployments()), 1)

        execution = resolve_effective_setup(
            deployment=self.manager.get_deployment(deployment.id), profile=self.manager.get_profile(selected.id),
            knowledge_refs=KnowledgeRefs(), knowledge_versions=[], surface_system_prompt=None,
            default_system_prompt="Fixture system prompt")
        self.assertEqual(execution.bags.per_request.applied["temperature"], 0.9)
        self.assertEqual(self.manager.get_deployment(deployment.id).settings.per_request.applied["temperature"], 0.2)

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

    def test_named_configuration_replaces_inherited_stopped_deployment(self):
        old = self.deployment(ctx_size=8192)
        selected = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="Larger variant", startup={"ctx_size": 16384}))
        with open_application_store(self.paths) as store:
            store.put_setup_defaults(SetupConfiguration(deployment_id=old.id))
            resolved = SetupService(store, self.manager).resolve(
                overrides=SetupConfiguration(model_configuration_id=selected.id), prepare_model=True)
        replacement = self.manager.get_deployment(resolved.configuration.deployment_id)
        self.assertNotEqual(replacement.id, old.id)
        self.assertEqual(replacement.profile_id, selected.id)
        self.assertEqual(replacement.status.value, "stopped")
        self.assertEqual(replacement.requested_startup["ctx_size"], 16384)
        self.assertEqual(self.manager.get_deployment(old.id).requested_startup["ctx_size"], 8192)
        self.assertFalse(any(fact.requires_reload for fact in resolved.effective_values.values()))

    def test_named_configuration_without_existing_deployment_prepares_its_recipe(self):
        selected = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="Larger variant", startup={"ctx_size": 16384}))
        with open_application_store(self.paths) as store:
            resolved = SetupService(store, self.manager).resolve(
                overrides=SetupConfiguration(model_configuration_id=selected.id), prepare_model=True)
        deployment = self.manager.get_deployment(resolved.configuration.deployment_id)
        self.assertEqual(deployment.profile_id, selected.id)
        self.assertEqual(deployment.requested_startup["ctx_size"], 16384)
        self.assertFalse(any(fact.requires_reload for fact in resolved.effective_values.values()))

    def test_edited_named_configuration_does_not_reuse_stale_stopped_recipe(self):
        selected = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="Variant", startup={"ctx_size": 8192}))
        previous = self.manager.create_managed(ManagedDeploymentRequest(
            bundle_id=self.bundle_id, profile_id=selected.id, auto_start=False))
        selected = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=selected.id, display_name="Variant", startup={"ctx_size": 16384},
            expected_revision=selected.revision))
        with open_application_store(self.paths) as store:
            resolved = SetupService(store, self.manager).resolve(
                overrides=SetupConfiguration(model_configuration_id=selected.id), prepare_model=True)
        replacement = self.manager.get_deployment(resolved.configuration.deployment_id)
        self.assertNotEqual(replacement.id, previous.id)
        self.assertEqual(replacement.requested_startup["ctx_size"], 16384)
        self.assertEqual(self.manager.get_deployment(previous.id).requested_startup["ctx_size"], 8192)
        self.assertFalse(any(fact.requires_reload for fact in resolved.effective_values.values()))

    def test_explicit_stopped_deployment_keeps_mismatch_until_applied(self):
        old = self.deployment(ctx_size=8192)
        selected = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="Larger variant", startup={"ctx_size": 16384}))
        with open_application_store(self.paths) as store:
            service = SetupService(store, self.manager)
            preview = service.resolve(overrides=SetupConfiguration(
                deployment_id=old.id, model_configuration_id=selected.id))
            self.assertEqual(preview.configuration.deployment_id, old.id)
            self.assertTrue(preview.effective_values["startup.ctx_size"].requires_reload)
            with self.assertRaises(HarnessError) as error:
                service.resolve(overrides=SetupConfiguration(
                    deployment_id=old.id, model_configuration_id=selected.id), prepare_model=True)
        self.assertEqual(error.exception.code, "model_reload_required")
        self.assertEqual(self.manager.get_deployment(old.id).requested_startup["ctx_size"], 8192)

    def test_parent_permission_and_sampler_value_remain_available_under_override(self):
        with open_application_store(self.paths) as store:
            store.put_setup_defaults(SetupConfiguration(approval_mode="full_access", per_request_overrides={"temperature":0.3}))
            service = SetupService(store, self.manager)
            resolved = service.resolve(overrides=SetupConfiguration(approval_mode="ask", per_request_overrides={"temperature":0.7}))
            self.assertEqual(resolved.effective_values["approval_mode"].inherited_value, "full_access")
            self.assertEqual(resolved.effective_values["per_request.temperature"].inherited_value, 0.3)
            self.assertEqual(resolved.effective_values["per_request.temperature"].requested_override, 0.7)

    def test_legacy_loaded_model_has_save_target_without_replacing_its_snapshot(self):
        from workbench_backend.inference.schemas import DeploymentStatus, HealthReport, ProcessIdentity
        deployment = self.deployment(ctx_size=8192)
        default = self.manager.list_model_configurations(self.bundle_id)[0]
        deployment = self.manager.store.put_deployment(deployment.model_copy(update={
            "status": DeploymentStatus.running,
            "health": HealthReport(healthy=True, endpoint="fixture", checked="now"),
            "process_identity": ProcessIdentity(pid=42, create_time=1, executable="fixture")}))
        other = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="Larger default", startup={"ctx_size": 16384}, make_default=True))
        with open_application_store(self.paths) as store:
            service = SetupService(store, self.manager)
            for overrides in (None, SetupConfiguration(deployment_id=deployment.id)):
                preview = service.resolve(overrides=overrides)
                self.assertIsNone(preview.configuration.model_configuration_id)
                self.assertIsNone(preview.configuration.profile_id)
                self.assertEqual(preview.configuration.deployment_id, deployment.id)
                self.assertEqual(preview.effective_values["model_configuration_target"].value, default.id)
                self.assertEqual(preview.effective_values["model_selection"].source, "Loaded model")
                self.assertEqual(preview.effective_values["loaded_model"].value, deployment.id)
                self.assertEqual(preview.effective_values["startup.ctx_size"].value, 8192)
                self.assertFalse(preview.effective_values["startup.ctx_size"].requires_reload)
            self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
                configuration_id=default.id, display_name=default.display_name, startup={"ctx_size": 32768}))
            # With no exact saved recipe left, Save targets the current model
            # default; merely previewing still cannot apply that different recipe.
            preview = service.resolve(overrides=SetupConfiguration(deployment_id=deployment.id))
            self.assertEqual(preview.effective_values["model_configuration_target"].value, other.id)
            self.assertEqual(preview.effective_values["startup.ctx_size"].value, 8192)
            self.assertFalse(preview.effective_values["startup.ctx_size"].requires_reload)
            self.assertEqual(self.manager.get_deployment(deployment.id).requested_startup, deployment.requested_startup)
            # A removed historical save destination cannot make an otherwise
            # usable loaded snapshot unavailable merely for display metadata.
            historical = self.manager.store.put_profile(default.model_copy(update={
                "id": "historical_profile", "merged_into_configuration_id": "removed_configuration"}))
            self.manager.store.put_deployment(deployment.model_copy(update={"profile_id": historical.id}))
            preview = service.resolve(overrides=SetupConfiguration(deployment_id=deployment.id))
            self.assertEqual(preview.effective_values["model_configuration_target"].value, other.id)
            self.assertEqual(preview.effective_values["startup.ctx_size"].value, 8192)

    def test_connected_choice_has_truthful_source_but_no_owned_save_target(self):
        from workbench_backend.inference.schemas import ConnectedDeploymentRequest
        deployment = self.manager.attach_connected(ConnectedDeploymentRequest(
            display_name="External model", endpoint="http://127.0.0.1:9/v1"))
        with open_application_store(self.paths) as store:
            store.put_setup_defaults(SetupConfiguration(deployment_id=deployment.id))
            preview = SetupService(store, self.manager).resolve()
        self.assertEqual(preview.effective_values["model_selection"].source, "Application defaults")
        self.assertEqual(preview.effective_values["model_selection"].value, "External model")
        self.assertFalse(preview.effective_values["model_configuration_target"].supported)
        self.assertIsNone(preview.effective_values["model_configuration_target"].value)
        self.assertIn("external server", preview.effective_values["model_configuration_target"].unavailable_reason)

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
