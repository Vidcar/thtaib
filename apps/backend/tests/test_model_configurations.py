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
from tests.support import write_tiny_gguf


class ModelConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = WorkbenchPaths(Path(self.tmp.name)).ensure()
        self.manager = ModelManager(self.paths)
        file = write_tiny_gguf(Path(self.tmp.name) / "model.gguf")
        self.bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(file))).bundle_id
        self.assertEqual(self.manager.list_model_configurations(self.bundle_id), [])
        self.initial = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(display_name="Saved setup"))

    def deployment(self, **startup):
        return self.manager.create_managed(ManagedDeploymentRequest(bundle_id=self.bundle_id, startup=startup, auto_start=False))

    def test_named_setup_and_repeated_deployment_lookup_are_idempotent(self):
        first = self.deployment(ctx_size=8192)
        self.assertEqual(first.id, self.deployment(ctx_size=8192).id)
        profiles = self.manager.list_model_configurations(self.bundle_id)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(self.manager.list_model_configurations(self.bundle_id), profiles)
        self.assertEqual(self.manager.store.get_bundle(self.bundle_id).default_configuration_id, profiles[0].id)
        self.assertEqual(self.manager.get_deployment(first.id).settings, first.settings)

    def test_named_empty_setup_preserves_publisher_and_template_defaults(self):
        import numpy as np
        from gguf import GGUFWriter
        from workbench_backend.inference.schemas import HuggingFaceConfiguration
        source = Path(self.tmp.name) / "thinking.gguf"
        writer = GGUFWriter(str(source), "llama")
        writer.add_chat_template("{% set level = reasoning_effort|default('xhigh') %}{% if reasoning_effort in ['medium', 'xhigh'] %}{{ level }}{% endif %}{% if enable_thinking %}think{% endif %}")
        writer.add_tensor("token_embd.weight", np.zeros((2, 2), dtype=np.float32))
        writer.write_header_to_file()
        writer.write_kv_data_to_file()
        writer.write_tensors_to_file()
        writer.close()
        bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(source))).bundle_id
        bundle = self.manager.store.get_bundle(bundle_id)
        self.manager.store.put_bundle(bundle.model_copy(update={"huggingface_configuration":
            HuggingFaceConfiguration(generation_defaults={"reasoning_effort": "xhigh", "reasoning": "off", "temperature": 0.6})}))
        self.assertEqual(self.manager.list_model_configurations(bundle_id), [])
        profile = self.manager.save_model_configuration(bundle_id, ModelConfigurationWriteRequest(display_name="Native setup"))
        self.assertEqual(profile.display_name, "Native setup")
        self.assertEqual(profile.bags.per_request.requested, {})
        self.assertEqual(profile.bags.per_request.applied["reasoning_effort"], "xhigh")
        self.assertEqual(profile.bags.per_request.applied["temperature"], 0.6)
        options = self.manager.get_bundle_configuration_options(bundle_id)
        self.assertEqual(options.response_presets, [])
        self.assertEqual(options.per_request_defaults["reasoning_effort"].default_value, "xhigh")
        self.assertIn("medium", [item.value for item in options.per_request_defaults["reasoning_effort"].options])
        # A previously authored configuration remains the user's choice.
        saved = self.manager.save_model_configuration(bundle_id, ModelConfigurationWriteRequest(
            configuration_id=profile.id, display_name="Deep choice", per_request={"reasoning_effort": "xhigh"}))
        self.assertEqual(self.manager.list_model_configurations(bundle_id)[0].bags.per_request.requested, saved.bags.per_request.requested)

    def test_empty_named_setup_does_not_invent_thinking_or_response_limits(self):
        profile = self.manager.list_model_configurations(self.bundle_id)[0]
        self.assertEqual(profile.bags.per_request.requested, {})
        self.assertEqual(profile.bags.per_request.applied["max_tokens"], -1)
        self.assertNotIn("reasoning", profile.bags.per_request.applied)
        self.assertNotIn("ctx_size", profile.bags.startup.applied)

    def test_context_baseline_reset_and_native_auto_are_distinct(self):
        profile = self.manager.list_model_configurations(self.bundle_id)[0]
        automatic = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=profile.id, display_name=profile.display_name, startup={"ctx_size": "auto"}))
        self.assertIn("ctx_size", automatic.bags.startup.requested)
        self.assertEqual(automatic.bags.startup.requested["ctx_size"], "auto")
        self.assertNotIn("ctx_size", automatic.bags.startup.applied)
        deployment = self.manager.create_managed(ManagedDeploymentRequest(bundle_id=self.bundle_id,
            profile_id=profile.id, auto_start=False))
        self.assertNotIn("ctx_size", deployment.applied_startup)
        options = self.manager.get_bundle_configuration_options(self.bundle_id, configuration_id=profile.id)
        self.assertIsNone(options.context_size.applied)
        self.assertIsNone(options.context_size.default_value)
        reset = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=profile.id, display_name=profile.display_name, startup={}))
        self.assertNotIn("ctx_size", reset.bags.startup.applied)

    def test_native_baseline_uses_matching_card_facts_without_creating_a_setup(self):
        import numpy as np
        from gguf import GGUFWriter
        from workbench_backend.inference.schemas import HuggingFaceConfiguration, ResponseRecipe
        source = Path(self.tmp.name) / "card-thinking.gguf"
        writer = GGUFWriter(str(source), "qwen35")
        writer.add_context_length(262144)
        writer.add_chat_template("""
            {% set resolved_reasoning_effort = reasoning_effort|default('xhigh') %}
            {% if resolved_reasoning_effort not in ('low', 'medium', 'xhigh') %}{{ raise_exception('Invalid') }}{% endif %}
            {% if enable_thinking is undefined or enable_thinking is true %}think{% endif %}
            {% if preserve_thinking is undefined or preserve_thinking is true %}history{% endif %}
        """)
        writer.add_tensor("token_embd.weight", np.zeros((2, 2), dtype=np.float32))
        writer.write_header_to_file(); writer.write_kv_data_to_file(); writer.write_tensors_to_file(); writer.close()
        bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(source))).bundle_id
        bundle = self.manager.store.get_bundle(bundle_id)
        common = dict(section="Sampling", source_repo_id="publisher/model", source_revision="a" * 40, card_sha256="b" * 64)
        samplers = dict(temperature=1.0, top_p=0.95, top_k=20, min_p=0, presence_penalty=0, repeat_penalty=1)
        recipes = [ResponseRecipe(id="thinking", name="Thinking", reasoning="on", per_request={**samplers, "max_tokens": 65000}, **common),
                   ResponseRecipe(id="non-thinking", name="Non-thinking", reasoning="off",
                                  per_request={**samplers, "temperature": 0.7}, **common)]
        self.manager.store.put_bundle(bundle.model_copy(update={"huggingface_configuration":
            HuggingFaceConfiguration(generation_defaults={"temperature": 0.6, "max_tokens": 128}, response_recipes=recipes)}))
        self.assertEqual(self.manager.list_model_configurations(bundle_id), [])
        self.manager.save_model_configuration(bundle_id, ModelConfigurationWriteRequest(display_name="Native setup"))
        profiles = self.manager.list_model_configurations(bundle_id)
        self.assertEqual(len(profiles), 1)
        profile = profiles[0]
        self.assertEqual(profile.bags.per_request.requested, {})
        self.assertEqual(profile.bags.per_request.applied["temperature"], .6)
        self.assertEqual(profile.bags.per_request.applied["top_k"], 40)
        self.assertEqual(profile.bags.per_request.applied["min_p"], .05)
        self.assertEqual(profile.bags.per_request.applied["frequency_penalty"], 0)
        self.assertEqual(profile.bags.per_request.applied["max_tokens"], -1)
        self.assertEqual(profile.bags.per_request.applied["reasoning_effort"], "xhigh")
        self.assertEqual(profile.bags.per_request.applied["reasoning"], "on")
        self.assertIs(profile.bags.per_request.applied["reasoning_preserve"], True)
        changed = self.manager.save_model_configuration(bundle_id, ModelConfigurationWriteRequest(
            configuration_id=profile.id, display_name=profile.display_name, per_request={"reasoning": "off"}))
        self.assertEqual(changed.bags.per_request.applied["temperature"], .6)
        self.assertEqual(changed.bags.per_request.applied["min_p"], .05)
        deployment = self.manager.create_managed(ManagedDeploymentRequest(bundle_id=bundle_id, profile_id=profile.id, auto_start=False))
        self.assertEqual(deployment.settings.per_request.applied["temperature"], .6)
        self.assertEqual(deployment.settings.per_request.applied["max_tokens"], -1)

    def test_suggested_context_and_gpu_bounds_do_not_block_native_choices(self):
        saved = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="Native limits", startup={"ctx_size": 1048576, "n_gpu_layers": 999}))
        self.assertEqual(saved.bags.startup.applied["ctx_size"], 1048576)
        self.assertEqual(saved.bags.startup.applied["n_gpu_layers"], 999)

    def test_loading_identity_uses_native_parallel_auto_result(self):
        from workbench_backend.inference.configurations import loading_startup_settings
        from workbench_backend.inference.settings import resolve_bags
        automatic = resolve_bags(startup={"parallel": -1, "kv_unified": False})
        explicit = resolve_bags(startup={"parallel": 4, "kv_unified": True})
        divided = resolve_bags(startup={"parallel": 4, "kv_unified": False})
        self.assertIs(automatic.startup.applied["kv_unified"], False)
        self.assertEqual(loading_startup_settings(automatic), loading_startup_settings(explicit))
        self.assertNotEqual(loading_startup_settings(automatic), loading_startup_settings(divided))

    def test_frozen_historical_auto_identity_stays_distinct_from_new_default(self):
        from workbench_backend.inference.configurations import loaded_model_identity, loading_startup_settings
        from workbench_backend.inference.schemas import SettingsBag, SettingsBags
        from workbench_backend.inference.settings import resolve_bags
        historical = SettingsBags(startup=SettingsBag(requested={}, applied={"host": "127.0.0.1", "port": 8080}))
        explicit_auto = resolve_bags(startup={"parallel": -1})
        current_default = resolve_bags()
        self.assertEqual(loading_startup_settings(historical), loading_startup_settings(explicit_auto))
        self.assertEqual(loading_startup_settings(historical)["parallel"], 4)
        self.assertEqual(loading_startup_settings(current_default)["parallel"], 1)
        bundle = self.manager.get_bundle(self.bundle_id)
        self.assertEqual(loaded_model_identity(None, bundle, historical), loaded_model_identity(None, bundle, explicit_auto))
        self.assertNotEqual(loaded_model_identity(None, bundle, historical), loaded_model_identity(None, bundle, current_default))

    def test_effective_shared_context_default_follows_selected_parallel_policy(self):
        from workbench_backend.agents.effective_setup import effective_setting_values
        from workbench_backend.inference.configurations import loading_startup_settings
        for startup, expected in (({}, False), ({"parallel": -1}, True), ({"parallel": 2}, False)):
            with self.subTest(startup=startup):
                profile = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
                    display_name=f"Parallel policy {startup.get('parallel', 'default')}", startup=startup))
                configuration = SetupConfiguration(profile_id=profile.id, bundle_id=self.bundle_id)
                facts = effective_setting_values(self.manager, configuration, {})
                shared = facts["startup.kv_unified"]
                self.assertIs(shared.value, expected)
                self.assertIs(shared.default_value, expected)
                self.assertTrue(shared.known)
                self.assertEqual(shared.source, "pinned_runtime_default")
                self.assertIs(loading_startup_settings(profile.bags)["kv_unified"], expected)
                self.assertNotIn("kv_unified", profile.bags.startup.requested)
                switched = configuration.model_copy(update={"startup_overrides": {"parallel": -1 if expected is False else 2}})
                self.assertIs(effective_setting_values(self.manager, switched, {})["startup.kv_unified"].value, not expected)
        reset = SetupConfiguration(profile_id=profile.id, bundle_id=self.bundle_id, startup_overrides={"parallel": None})
        self.assertFalse(effective_setting_values(self.manager, reset, {})["startup.kv_unified"].value)

    def test_inherited_historical_loading_facts_do_not_become_new_defaults(self):
        from workbench_backend.agents.effective_setup import effective_setting_values
        from workbench_backend.inference.schemas import SettingsBag
        deployment = self.deployment()
        historical_startup = {key: value for key, value in deployment.applied_startup.items() if key != "parallel"}
        historical_bags = deployment.settings.model_copy(update={"startup": SettingsBag(requested={}, applied=historical_startup)})
        frozen = self.manager.store.put_deployment(deployment.model_copy(update={
            "settings": historical_bags, "applied_startup": historical_startup}))
        configuration = SetupConfiguration(deployment_id=deployment.id, bundle_id=self.bundle_id)
        facts = effective_setting_values(self.manager, configuration, {})
        self.assertEqual(facts["startup.parallel"].value, 4)
        self.assertEqual(facts["startup.parallel"].source, "Loaded model")
        self.assertEqual(facts["startup.parallel"].default_value, 1)
        self.assertEqual(facts["startup.parallel"].default_source, "workbench_default")
        self.assertIs(facts["startup.kv_unified"].value, True)
        self.assertTrue(facts["startup.kv_unified"].known)
        self.assertIs(facts["startup.kv_unified"].default_value, True)
        self.assertEqual(self.manager.store.get_deployment(deployment.id), frozen)

    def test_connected_effective_facts_do_not_claim_managed_slot_default(self):
        from workbench_backend.agents.effective_setup import effective_setting_values
        from workbench_backend.inference.schemas import ManagementScope, SettingsBags
        connected = self.deployment().model_copy(update={
            "id": "external-model", "scope": ManagementScope.connected, "bundle_id": None,
            "profile_id": None, "settings": SettingsBags(), "applied_startup": {}})
        self.manager.store.put_deployment(connected)
        facts = effective_setting_values(self.manager, SetupConfiguration(deployment_id=connected.id), {})
        self.assertEqual(facts["startup.parallel"].default_value, -1)
        self.assertEqual(facts["startup.parallel"].default_source, "pinned_runtime_default")
        self.assertNotEqual(facts["startup.parallel"].source, "workbench_default")

    def test_prepare_and_save_during_active_work_do_not_change_the_resident_record(self):
        current = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="Current", startup={"ctx_size": 8192}, per_request={"temperature": 0.2}))
        resident = self.manager.create_managed(ManagedDeploymentRequest(
            bundle_id=self.bundle_id, profile_id=current.id, auto_start=False))
        frozen = self.manager.get_deployment(resident.id)
        with self.manager.reserve_deployment(resident.id, profile_id=current.id), patch.object(self.manager.deployments, "start") as start:
            response_only = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
                display_name="Response", startup={"ctx_size": 8192}, per_request={"temperature": 0.9}))
            same = self.manager.create_managed(ManagedDeploymentRequest(
                bundle_id=self.bundle_id, profile_id=response_only.id, auto_start=False))
            future = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
                display_name="Future", startup={"ctx_size": 16384}))
            prepared = self.manager.create_managed(ManagedDeploymentRequest(
                bundle_id=self.bundle_id, profile_id=future.id, auto_start=False))
        self.assertEqual(same.id, resident.id)
        self.assertNotEqual(prepared.id, resident.id)
        self.assertEqual(prepared.status.value, "stopped")
        self.assertEqual(self.manager.get_deployment(resident.id), frozen)
        start.assert_not_called()

    def test_reading_saved_configuration_does_not_insert_loading_overrides(self):
        saved = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="CPU", startup={"ctx_size": 8192, "n_gpu_layers": 0}, per_request={"max_tokens": 0}))
        before = self.manager.store.get_profile(saved.id)
        resolved = self.manager.get_profile(saved.id)
        self.manager.list_model_configurations(self.bundle_id)
        self.assertEqual(self.manager.store.get_profile(saved.id), before)
        self.assertEqual(resolved.id, saved.id)
        self.assertEqual(resolved.revision, saved.revision)
        self.assertEqual(resolved.bags.startup.requested, {"ctx_size": 8192, "n_gpu_layers": 0})
        self.assertNotIn("kv_offload", resolved.bags.startup.applied)
        self.assertNotIn("op_offload", resolved.bags.startup.applied)
        self.assertNotIn("mmproj_use_gpu", resolved.bags.startup.applied)
        self.assertNotIn("spec_draft_ngl", resolved.bags.startup.applied)
        self.assertEqual(resolved.bags.per_request.applied["max_tokens"], 0)

    def test_loaded_identity_includes_primary_content_and_non_response_template_kwargs(self):
        from workbench_backend.inference.configurations import loaded_model_identity
        from workbench_backend.inference.settings import resolve_bags
        bundle = self.manager.get_bundle(self.bundle_id)
        first = resolve_bags(startup={"chat_template_kwargs": '{"tool_style":"compact","enable_thinking":true}'})
        response_change = resolve_bags(startup={"chat_template_kwargs": '{"tool_style":"compact","enable_thinking":false}'},
                                      per_request={"temperature": 0.9})
        loading_change = resolve_bags(startup={"chat_template_kwargs": '{"tool_style":"expanded"}'})
        identity = loaded_model_identity(None, bundle, first)
        self.assertEqual(identity, loaded_model_identity(None, bundle, response_change))
        self.assertNotEqual(identity, loaded_model_identity(None, bundle, loading_change))
        changed = bundle.model_copy(update={"files": [bundle.files[0].model_copy(update={"sha256": "changed"}), *bundle.files[1:]]})
        self.assertNotEqual(identity, loaded_model_identity(None, changed, first))

    def test_prepared_identity_cannot_silently_load_changed_artifacts(self):
        deployment = self.deployment(ctx_size=8192)
        bundle = self.manager.store.get_bundle(self.bundle_id)
        changed = bundle.model_copy(update={"files": [bundle.files[0].model_copy(update={"sha256": "replaced"}), *bundle.files[1:]]})
        self.manager.store.put_bundle(changed)
        with patch.object(self.manager.deployments, "start") as start, self.assertRaises(ManagerError) as caught:
            self.manager.ensure_deployment_ready(deployment.id)
        self.assertEqual(caught.exception.code, "loaded_model_identity_changed")
        start.assert_not_called()

    def test_compatible_child_does_not_bypass_invalid_requested_startup(self):
        deployment = self.deployment()
        with patch.object(self.manager.deployments, "start") as start, self.assertRaises(ManagerError) as caught:
            self.manager.create_managed(ManagedDeploymentRequest(bundle_id=self.bundle_id,
                startup={"ctx_size": -1}, auto_start=False))
        self.assertEqual(caught.exception.code, "managed_startup_invalid")
        self.assertEqual(len(self.manager.store.list_deployments()), 1)
        self.assertEqual(self.manager.get_deployment(deployment.id), deployment)
        start.assert_not_called()

    def test_invalid_known_values_fail_save_without_replacing_the_saved_revision(self):
        original = self.manager.list_model_configurations(self.bundle_id)[0]
        for response in ({"temperature": float("nan")}, {"top_p": 1.1}, {"max_tokens": 1.5}, {"reasoning_budget_tokens": -2}):
            with self.subTest(response=response), self.assertRaises(ManagerError) as caught:
                self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
                    configuration_id=original.id, display_name=original.display_name,
                    expected_revision=original.revision, per_request=response))
            self.assertEqual(caught.exception.code, "configuration_values_invalid")
        self.assertEqual(self.manager.get_profile(original.id).revision, original.revision)

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

    def test_equal_named_configurations_keep_separate_editable_identities(self):
        original = self.manager.list_model_configurations(self.bundle_id)[0]
        duplicate = self.manager.store.put_profile(original.model_copy(update={
            "id": "second_configuration", "display_name": "Another choice"}))
        self.assertEqual({p.id for p in self.manager.list_model_configurations(self.bundle_id)}, {original.id, duplicate.id})
        with open_application_store(self.paths) as store:
            resolved = SetupService(store, self.manager).resolve(overrides=SetupConfiguration(model_configuration_id=duplicate.id))
            self.assertEqual(resolved.configuration.model_configuration_id, duplicate.id)
            self.assertEqual(resolved.configuration.profile_id, duplicate.id)
        self.assertEqual(self.manager.get_profile(duplicate.id).id, duplicate.id)
        bundle = self.manager.store.get_bundle(self.bundle_id)
        self.manager.store.put_bundle(bundle.model_copy(update={"display_name": "Renamed model"}))
        self.assertEqual(self.manager.get_profile(original.id).bundle_name, "Renamed model")
        self.assertEqual(self.manager.list_model_configurations(self.bundle_id)[0].bundle_name, "Renamed model")
        self.assertNotIn('"bundle_name"', self.manager.store.profiles_path.read_text())
        self.manager.set_default_configuration(self.bundle_id, duplicate.id)
        self.assertEqual({p.id for p in self.manager.list_model_configurations(self.bundle_id)}, {original.id, duplicate.id})
        self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=original.id, display_name="Default", startup={"ctx_size": 8192}))
        self.assertEqual({p.id for p in self.manager.list_model_configurations(self.bundle_id)}, {original.id, duplicate.id})
        self.assertEqual(self.manager.canonical_configuration(original.id).bags.startup.requested["ctx_size"], 8192)
        self.assertEqual(self.manager.get_profile(duplicate.id).bags.startup.requested, {})

    def test_explicit_equal_named_variants_keep_identity_after_listing_and_restart(self):
        original = self.manager.list_model_configurations(self.bundle_id)[0]
        variant = self.manager.save_model_configuration(self.bundle_id,
            ModelConfigurationWriteRequest(display_name="My experiment", per_request=dict(original.bags.per_request.requested)))
        self.assertEqual(variant.bags, original.bags)
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

    def test_configuration_deployment_uses_loading_identity_and_preserves_setup_identity(self):
        original = self.manager.list_model_configurations(self.bundle_id)[0]
        variant = self.manager.save_model_configuration(self.bundle_id,
            ModelConfigurationWriteRequest(display_name="Same launch settings"))
        first = self.manager.create_managed(ManagedDeploymentRequest(
            bundle_id=self.bundle_id, profile_id=original.id, auto_start=False))
        self.assertEqual(self.manager.configuration_deployment(original.id).id, first.id)
        self.assertEqual(self.manager.configuration_deployment(variant.id).id, first.id)

        second = self.manager.create_managed(ManagedDeploymentRequest(
            bundle_id=self.bundle_id, profile_id=variant.id, auto_start=False))
        self.assertEqual(second.id, first.id)
        self.assertEqual(self.manager.configuration_deployment(variant.id).id, second.id)

        self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=variant.id, expected_revision=variant.revision,
            display_name=variant.display_name, per_request={"temperature": 0.55}))
        self.assertEqual(self.manager.configuration_deployment(variant.id).id, first.id)
        self.assertEqual(self.manager.get_deployment(first.id).profile_id, original.id)

    def test_configuration_names_are_unique_and_optional_model_instructions_are_explicit(self):
        from workbench_backend.inference.schemas import ProfileWriteRequest
        legacy = self.manager.create_profile(ProfileWriteRequest(display_name="Legacy", bundle_id=self.bundle_id,
            agent={"system_prompt": "Retain the authored instructions."}))
        saved = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=legacy.id, display_name="Legacy", per_request={"temperature": 0.5}))
        self.assertEqual(saved.bags.agent.applied["system_prompt"], "Retain the authored instructions.")
        for name, code in ((" ", "configuration_name_required"), (" legacy ", "configuration_name_conflict")):
            with self.subTest(name=name), self.assertRaises(ManagerError) as error:
                self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(display_name=name))
            self.assertEqual(error.exception.code, code)
        with self.assertRaises(ManagerError) as error:
            self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
                display_name="New", agent={"tools_enabled": True}))
        self.assertEqual(error.exception.code, "configuration_agent_instructions")

    def test_model_instruction_edit_reset_and_omission_preserve_other_saved_values(self):
        saved = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="Authored guidance", startup={"ctx_size": 8192},
            per_request={"temperature": 0.4}, agent={"system_prompt": "Answer in plain language."}))
        self.assertEqual(saved.bags.agent.applied["system_prompt"], "Answer in plain language.")
        updated = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=saved.id, expected_revision=saved.revision, display_name=saved.display_name,
            startup=saved.bags.startup.requested, per_request=saved.bags.per_request.requested,
            agent={"system_prompt": "Use short examples."}))
        self.assertEqual(updated.bags.agent.applied["system_prompt"], "Use short examples.")
        reset = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            configuration_id=saved.id, expected_revision=updated.revision, display_name=saved.display_name,
            startup=updated.bags.startup.requested, per_request=updated.bags.per_request.requested, agent={}))
        self.assertEqual(reset.bags.agent.requested, {})
        self.assertEqual(reset.bags.startup.requested["ctx_size"], 8192)
        self.assertEqual(reset.bags.per_request.requested["temperature"], 0.4)

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

    def test_historical_context_shrink_needs_compatibility_owner_before_stop(self):
        deployment = self.deployment(ctx_size=8192)
        with open_application_store(self.paths) as store:
            store.put_conversation(ChatConversation(id="chat", deployment_id=deployment.id, created_at="now", updated_at="now", run_ids=["retained-run"]))
        with patch.object(self.manager.runtime, "require_executable", return_value=Path("llama-server")), patch.object(self.manager.deployments, "stop") as stop:
            with self.assertRaises(ManagerError) as caught:
                self.manager.reconfigure_deployment(deployment.id, ReconfigureDeploymentRequest(startup={"ctx_size":4096}, conversation_id="chat"))
        self.assertEqual(caught.exception.code, "context_compatibility_unavailable")
        stop.assert_not_called()

    def test_context_shrink_consults_existing_compatibility_owner(self):
        deployment = self.deployment(ctx_size=8192)
        with open_application_store(self.paths) as store:
            store.put_conversation(ChatConversation(id="chat", deployment_id=deployment.id, created_at="now", updated_at="now", run_ids=["retained-run"]))
        from unittest.mock import Mock
        validator = Mock(side_effect=ManagerError("Retained images are incompatible", code="retained_incompatible", status_code=409))
        self.manager.validate_chat_reconfiguration = validator
        with patch.object(self.manager.runtime, "require_executable", return_value=Path("llama-server")), patch.object(self.manager.deployments, "stop") as stop:
            with self.assertRaises(ManagerError) as caught:
                self.manager.reconfigure_deployment(deployment.id, ReconfigureDeploymentRequest(startup={"ctx_size":4096}, conversation_id="chat"))
        validator.assert_called_once_with("chat", deployment.id, {"ctx_size":4096}, deployment.profile_id)
        self.assertEqual(caught.exception.code, "retained_incompatible")
        stop.assert_not_called()

    def test_explicit_null_response_override_really_omits_profile_value(self):
        from workbench_backend.agents.effective_setup import _resolve_per_request
        deployment = self.deployment()
        profile = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(display_name="Warm",per_request={"temperature":0.7}))
        bag = _resolve_per_request(profile, deployment, {"temperature":None})
        self.assertNotIn("temperature", bag.applied)

    def test_healthy_matching_configuration_wins_over_recent_failed_duplicate(self):
        from workbench_backend.inference.schemas import DeploymentStatus, HealthReport, ProcessIdentity
        config = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="8k", startup={"ctx_size": 8192}))
        deployment = self.manager.create_managed(ManagedDeploymentRequest(
            bundle_id=self.bundle_id, profile_id=config.id, auto_start=False))
        healthy = deployment.model_copy(update={"status":DeploymentStatus.running,"process_identity":ProcessIdentity(pid=42,create_time=1,executable="fixture"),
            "health":HealthReport(healthy=True,endpoint="fixture",checked="now"),"updated_at":"2020"})
        self.manager.store.put_deployment(healthy)
        self.manager.store.put_deployment(deployment.model_copy(update={"id":"duplicate","status":DeploymentStatus.failed,"updated_at":"2030"}))
        self.assertEqual(self.manager.configuration_deployment(config.id).id, healthy.id)

    def test_named_variants_share_one_deployment_and_keep_separate_response_settings(self):
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
            deployment=self.manager.get_deployment(resolved.configuration.deployment_id),
            profile=self.manager.get_profile(selected.id),
            knowledge_refs=KnowledgeRefs(), knowledge_versions=[], surface_system_prompt=None,
            default_system_prompt="Fixture system prompt")
        self.assertEqual(execution.bags.per_request.applied["temperature"], 0.9)
        self.assertEqual(self.manager.get_deployment(deployment.id).settings.per_request.applied["temperature"], 0.2)

    def test_model_selection_uses_default_and_never_binds_another_variant(self):
        first = self.deployment(ctx_size=8192)
        selected = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="16k", startup={"ctx_size": 16384}))
        second = self.manager.create_managed(ManagedDeploymentRequest(
            bundle_id=self.bundle_id, profile_id=selected.id, auto_start=False))
        default = self.manager.store.get_bundle(self.bundle_id).default_configuration_id
        with open_application_store(self.paths) as store:
            service = SetupService(store, self.manager)
            model = service.resolve(overrides=SetupConfiguration(bundle_id=self.bundle_id))
            self.assertEqual(model.configuration.model_configuration_id, default)
            preview = service.resolve(overrides=SetupConfiguration(deployment_id=first.id, model_configuration_id=selected.id))
            self.assertEqual(preview.configuration.deployment_id, second.id)
            applied = service.resolve(overrides=SetupConfiguration(
                deployment_id=first.id, model_configuration_id=selected.id), prepare_model=True)
            exact = self.manager.get_deployment(applied.configuration.deployment_id)
            self.assertEqual(applied.configuration.profile_id, selected.id)
            self.assertEqual(exact.requested_startup["ctx_size"], 16384)
            self.assertEqual(exact.id, second.id)
            self.assertEqual(self.manager.get_deployment(first.id).requested_startup["ctx_size"], 8192)
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

    def test_explicit_stopped_deployment_is_replaced_by_exact_variant(self):
        old = self.deployment(ctx_size=8192)
        selected = self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(
            display_name="Larger variant", startup={"ctx_size": 16384}))
        with open_application_store(self.paths) as store:
            service = SetupService(store, self.manager)
            preview = service.resolve(overrides=SetupConfiguration(
                deployment_id=old.id, model_configuration_id=selected.id))
            self.assertIsNone(preview.configuration.deployment_id)
            applied = service.resolve(overrides=SetupConfiguration(
                deployment_id=old.id, model_configuration_id=selected.id), prepare_model=True)
        replacement = self.manager.get_deployment(applied.configuration.deployment_id)
        self.assertNotEqual(replacement.id, old.id)
        self.assertEqual(replacement.profile_id, selected.id)
        self.assertEqual(replacement.requested_startup["ctx_size"], 16384)
        self.assertEqual(self.manager.get_deployment(old.id).requested_startup["ctx_size"], 8192)

    def test_app_seeds_access_but_not_sampler_values(self):
        with open_application_store(self.paths) as store:
            store.put_setup_defaults(SetupConfiguration(approval_mode="full_access", per_request_overrides={"temperature":0.3}))
            service = SetupService(store, self.manager)
            resolved = service.resolve(overrides=SetupConfiguration(approval_mode="ask", per_request_overrides={"temperature":0.7}))
            self.assertEqual(resolved.effective_values["approval_mode"].inherited_value, "full_access")
            self.assertEqual(resolved.effective_values["per_request.temperature"].inherited_value, 0.8)
            self.assertEqual(resolved.effective_values["per_request.temperature"].requested_override, 0.7)

    def test_loaded_model_is_not_an_implicit_chat_selection(self):
        from workbench_backend.inference.schemas import DeploymentStatus, HealthReport, ProcessIdentity
        deployment = self.deployment(ctx_size=8192)
        deployment = self.manager.store.put_deployment(deployment.model_copy(update={
            "status": DeploymentStatus.running,
            "health": HealthReport(healthy=True, endpoint="fixture", checked="now"),
            "process_identity": ProcessIdentity(pid=42, create_time=1, executable="fixture")}))
        with open_application_store(self.paths) as store:
            service = SetupService(store, self.manager)
            empty = service.resolve()
            self.assertIsNone(empty.configuration.deployment_id)
            self.assertNotIn("model_selection", empty.effective_values)
            chosen = service.resolve(overrides=SetupConfiguration(deployment_id=deployment.id))
            self.assertEqual(chosen.configuration.deployment_id, deployment.id)
            self.assertIsNone(chosen.configuration.model_configuration_id)
            self.assertEqual(chosen.effective_values["loaded_model"].value, deployment.id)
            self.assertEqual(chosen.effective_values["startup.ctx_size"].value, 8192)

    def test_connected_choice_has_truthful_source_but_no_owned_save_target(self):
        from workbench_backend.inference.schemas import ConnectedDeploymentRequest
        deployment = self.manager.attach_connected(ConnectedDeploymentRequest(
            display_name="External model", endpoint="http://127.0.0.1:9/v1"))
        with open_application_store(self.paths) as store:
            store.put_setup_defaults(SetupConfiguration(deployment_id=deployment.id))
            service = SetupService(store, self.manager)
            self.assertIsNone(service.resolve().configuration.deployment_id)
            preview = service.resolve(overrides=SetupConfiguration(deployment_id=deployment.id))
        self.assertEqual(preview.effective_values["model_selection"].source, "Selected model")
        self.assertEqual(preview.effective_values["model_selection"].value, "External model")
        self.assertFalse(preview.effective_values["model_configuration_target"].supported)
        self.assertIsNone(preview.effective_values["model_configuration_target"].value)
        self.assertIn("external server", preview.effective_values["model_configuration_target"].unavailable_reason)

    def test_explicit_model_choice_does_not_inherit_app_model_configuration(self):
        from workbench_backend.inference.schemas import ConnectedDeploymentRequest
        self.deployment(ctx_size=8192)
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
            self.assertIsNone(same.configuration.model_configuration_id)
            self.assertFalse(same.effective_values["startup.ctx_size"].requires_reload)
            other = service.resolve(overrides=SetupConfiguration(bundle_id=other_bundle),
                                    validate=False, read_only=True)
            self.assertEqual(other.configuration.bundle_id, other_bundle)
            self.assertIsNone(other.configuration.model_configuration_id)
            self.assertIsNone(other.configuration.deployment_id)
