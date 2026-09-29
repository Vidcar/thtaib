"""Every role prepares its accepted model plan and retains its runtime binding."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage

from tests import test_agent_capabilities as helper_fixture
from tests.scripted_model import ScriptedChatModel
from tests.support import wait_for_run, write_tiny_gguf
from workbench_backend.agents.effective_setup import resolve_effective_setup
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.helpers import freeze_settings, prepare_frozen_model
from workbench_backend.agents.setup_schemas import SetupConfiguration
from workbench_backend.errors import HarnessError
from workbench_backend.inference.configurations import loaded_model_identity
from workbench_backend.inference.schemas import (
    Deployment, LocalImportRequest, ModelConfigurationWriteRequest, ServerProperties,
)
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.knowledge.schemas import KnowledgeRefs
from workbench_backend.paths import WorkbenchPaths


class FrozenModelControlsTests(unittest.TestCase):
    def test_acceptance_keeps_unlimited_on_a_non_thinking_model(self):
        bags = resolve_bags(per_request={"temperature": .21})
        dep = Deployment(id="connected", display_name="Connected", scope="connected", status="running",
            endpoint="http://127.0.0.1:9/v1", created_at="now", updated_at="now", settings=bags,
            server_props=ServerProperties(fetched="now", source_url="fixture", n_ctx=8192,
                chat_template="{{ messages }}", chat_template_caps={"supports_thinking": False}))
        manager = SimpleNamespace(get_deployment=lambda _: dep)
        accepted = type(bags).model_validate(freeze_settings(manager, SetupConfiguration(deployment_id=dep.id)))
        self.assertEqual(accepted.per_request.applied["max_tokens"], -1)
        self.assertNotIn("reasoning", accepted.per_request.applied)
        self.assertEqual(accepted.per_request.applied["temperature"], .21)

    def test_cold_selected_template_keeps_unlimited_and_selected_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ModelManager(WorkbenchPaths(Path(directory)).ensure())
            bundle_id = manager.import_local(LocalImportRequest(
                source_path=str(write_tiny_gguf(Path(directory) / "model.gguf")))).bundle_id
            template = Path(directory) / "custom.jinja"
            template.write_text("{% if enable_thinking|default(false) %}think{% endif %}{{ messages }}", encoding="utf-8")
            profile = manager.save_model_configuration(bundle_id, ModelConfigurationWriteRequest(
                display_name="Selected template", startup={"chat_template_file": str(template)}, per_request={"temperature": .21}))
            accepted = type(profile.bags).model_validate(freeze_settings(manager,
                SetupConfiguration(bundle_id=bundle_id, profile_id=profile.id, model_configuration_id=profile.id)))
            self.assertEqual(accepted.per_request.applied["max_tokens"], -1)
            self.assertEqual(accepted.per_request.applied["reasoning"], "off")
            self.assertEqual(accepted.startup.requested["chat_template_file"], str(template))

    def test_acceptance_routes_historical_request_aliases_without_loading_or_sampling_changes(self):
        bags = resolve_bags(startup={"ctx_size": 8192}, per_request={"temperature": .21, "reasoning": "on"})
        profile = SimpleNamespace(bags=bags, recipe_origin=None, bundle_id=None)
        manager = SimpleNamespace(get_profile=lambda _: profile)
        configuration = SetupConfiguration(profile_id="selected", startup_overrides={
            "reasoning_preserve": False, "reasoning_budget": 123,
            "chat_template_kwargs": '{"enable_thinking":false,"tool_style":"compact"}'})
        accepted = type(bags).model_validate(freeze_settings(manager, configuration))
        self.assertEqual(accepted.per_request.applied["temperature"], .21)
        self.assertEqual(accepted.per_request.applied["reasoning"], "off")
        self.assertIs(accepted.per_request.applied["reasoning_preserve"], False)
        self.assertEqual(accepted.per_request.applied["reasoning_budget_tokens"], 123)
        self.assertEqual(accepted.startup.requested, {"ctx_size": 8192, "chat_template_kwargs": '{"tool_style":"compact"}'})
        self.assertEqual(accepted.per_request.applied["max_tokens"], -1)
        configuration.per_request_overrides = {"reasoning": "on"}
        explicit = type(bags).model_validate(freeze_settings(manager, configuration))
        self.assertEqual(explicit.per_request.applied["reasoning"], "on")

    def test_resolved_accepted_setup_retains_loading_identity_and_exact_output(self):
        bags = resolve_bags(per_request={"temperature": .21, "reasoning": "off"})
        bags.accepted_loading_identity = "accepted-plan"
        dep = Deployment(id="child", display_name="Child", scope="managed", status="running",
            endpoint="http://127.0.0.1:9/v1", loaded_model_identity="accepted-plan",
            created_at="now", updated_at="now", settings=bags,
            server_props=ServerProperties(fetched="now", source_url="fixture", n_ctx=8192))
        effective = resolve_effective_setup(deployment=dep, profile=None, knowledge_refs=KnowledgeRefs(),
            knowledge_versions=[], surface_system_prompt=None, default_system_prompt="Respond")
        reopened = type(effective).model_validate(effective.model_dump(mode="json"))
        self.assertEqual(reopened.bags.accepted_loading_identity, "accepted-plan")
        self.assertEqual(reopened.bags.per_request.applied["max_tokens"], -1)
        self.assertEqual(reopened.bags.per_request.applied, bags.per_request.applied)

    def test_resumed_provider_rejects_changed_plan_before_loading_or_creating_client(self):
        bags = resolve_bags()
        bags.accepted_loading_identity = "accepted-plan"
        dep = Deployment(id="child", display_name="Changed child", scope="managed", status="stopped",
            loaded_model_identity="changed-plan", created_at="now", updated_at="now")
        manager = SimpleNamespace(get_deployment=lambda _: dep, ensure_deployment_ready=Mock())
        owner = SimpleNamespace(manager=manager)
        run = SimpleNamespace(deployment_id=dep.id, effective_setup=SimpleNamespace(bags=bags))
        with self.assertRaises(HarnessError) as caught:
            HarnessService._deployment_model(owner, run, [])
        self.assertEqual(caught.exception.code, "accepted_model_identity_changed")
        manager.ensure_deployment_ready.assert_not_called()

    def test_frozen_preparation_reuses_weights_while_saved_response_revision_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ModelManager(WorkbenchPaths(Path(directory)).ensure())
            bundle_id = manager.import_local(LocalImportRequest(
                source_path=str(write_tiny_gguf(Path(directory) / "model.gguf")))).bundle_id
            profile = manager.save_model_configuration(bundle_id, ModelConfigurationWriteRequest(
                display_name="Selected", startup={"ctx_size": 8192}, per_request={"temperature": .21}))
            accepted = profile.bags.model_copy(deep=True)
            accepted.accepted_loading_identity = loaded_model_identity(None, manager.store.get_bundle(bundle_id), accepted)
            configuration = SetupConfiguration(bundle_id=bundle_id, model_configuration_id=profile.id, profile_id=profile.id)
            with patch.object(manager.deployments, "start") as start:
                first = prepare_frozen_model(manager, configuration, accepted)
                manager.save_model_configuration(bundle_id, ModelConfigurationWriteRequest(
                    configuration_id=profile.id, display_name=profile.display_name, startup={"ctx_size": 8192},
                    per_request={"temperature": .91}))
                second = prepare_frozen_model(manager, configuration, accepted)
                self.assertEqual(first.deployment_id, second.deployment_id)
                self.assertEqual(accepted.per_request.applied["temperature"], .21)
                self.assertEqual(manager.get_deployment(first.deployment_id).status.value, "stopped")
                start.assert_not_called()


class DirectHelperPreparationTests(unittest.TestCase):
    setUp = helper_fixture.AgentCapabilitiesTests.setUp
    tearDown = helper_fixture.AgentCapabilitiesTests.tearDown
    post = helper_fixture.AgentCapabilitiesTests.post
    setup = helper_fixture.AgentCapabilitiesTests.setup
    harness = helper_fixture.AgentCapabilitiesTests.harness
    start = helper_fixture.AgentCapabilitiesTests.start

    def test_late_known_helper_capacity_never_changes_accepted_unlimited_output(self):
        manager = self.app.state.manager
        helper = self.setup(presented_tools=[])
        main = ScriptedChatModel([helper_fixture.call("task", {
            "subagent_type": helper["id"], "description": "Report"}, "delegate"), AIMessage(content="Parent done")])
        recorded = []
        helper_models = []

        def model_for_role(run, sink):
            if not run.parent_run_id:
                return main
            self.assertEqual(run.effective_setup.bags.per_request.applied["max_tokens"], -1)
            manager.store.put_deployment(self.deployment.model_copy(update={"server_props": ServerProperties(
                fetched="now", source_url="fixture", n_ctx=8192, model_alias="late-helper-fixture")}))
            owner = self.app.state.harness

            def provider(_deployment, *, per_request, **_kwargs):
                parent = owner.store.get_execution_run(run.parent_run_id)
                role = type(run.effective_setup.bags).model_validate(parent.helper_snapshots[0].settings_snapshot)
                child = owner.store.get_execution_run(run.id)
                recorded.append((per_request.applied["max_tokens"], role.per_request.applied["max_tokens"],
                    child.effective_setup.bags.per_request.applied["max_tokens"]))
                return ScriptedChatModel([AIMessage(content="Unused provider")])

            with patch("workbench_backend.agents.harness.chat_model_for_deployment", provider):
                HarnessService._deployment_model(owner, run, sink)
            # This test uses a scripted graph model; close the uncalled provider
            # client without asking that scripted model to own adapter cleanup.
            owner._model_clients.pop(run.id).close()
            owner._adapter_models.pop(run.id)
            model = ScriptedChatModel([AIMessage(content="Helper done")])
            helper_models.append(model)
            return model

        self.harness(model_for_role)
        finished = wait_for_run(self.client, self.start(presented_tools=["echo"], helper_agent_ids=[helper["id"]])["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        provider, parent, child = recorded[0]
        self.assertEqual(provider, parent)
        self.assertEqual(provider, child)
        self.assertEqual(provider, -1)
        self.assertEqual(helper_models[0].profile["max_input_tokens"], 8192,
            "Binding must use newly observed helper capacity, not unknown admission capacity")

    def test_helper_role_and_lab_capture_keep_accepted_output_when_capacity_changes(self):
        manager = self.app.state.manager
        initial = self.deployment.model_copy(update={"server_props": ServerProperties(
            fetched="now", source_url="fixture", n_ctx=8192)})
        manager.store.put_deployment(initial)
        helper = self.setup(presented_tools=[])
        main = ScriptedChatModel([
            helper_fixture.call("task", {"subagent_type": helper["id"], "description": "First call"}, "delegate-one"),
            helper_fixture.call("task", {"subagent_type": helper["id"], "description": "Second call"}, "delegate-two"),
            AIMessage(content="Parent done"),
        ])
        bindings = []
        parent_snapshots = []

        def model_for_role(run, _sink):
            if not run.parent_run_id:
                return main
            binding = run.effective_setup.bags.per_request.applied["max_tokens"]
            bindings.append(binding)
            parent = self.app.state.harness.store.get_execution_run(run.parent_run_id)
            parent_snapshots.append(type(run.effective_setup.bags).model_validate(parent.helper_snapshots[0].settings_snapshot))
            manager.store.put_deployment(initial.model_copy(update={"server_props": initial.server_props.model_copy(update={"n_ctx": 16384})}))
            return ScriptedChatModel([AIMessage(content="Helper done")])

        self.harness(model_for_role)
        workspace = self.post("/v1/lab/workspaces", {"display_name": "Helper binding", "files": {"note.txt": "Fixture"}})
        finished = wait_for_run(self.client, self.start(workspace_id=workspace["id"], presented_tools=["echo"], helper_agent_ids=[helper["id"]])["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertEqual(len(bindings), 2)
        self.assertEqual(bindings[0], bindings[1])
        self.assertEqual(bindings[0], -1)
        self.assertTrue(all(bag.per_request.applied["max_tokens"] == bindings[0] for bag in parent_snapshots),
            "the accepted exact output setting must remain durable for repeated helper calls")
        case = self.post("/v1/lab/cases/capture", {"workspace_id": workspace["id"], "run_id": finished["id"]})
        captured = type(parent_snapshots[0]).model_validate(case["helper_snapshots"][0]["settings_snapshot"])
        self.assertEqual(captured.per_request.applied["max_tokens"], bindings[0])

    def test_direct_execution_prepares_a_cold_helper_setup_without_loading_at_save(self):
        manager = self.app.state.manager
        bundle_id = manager.import_local(LocalImportRequest(
            source_path=str(write_tiny_gguf(self.folder / "helper.gguf")))).bundle_id
        profile = manager.list_model_configurations(bundle_id)[0]
        helper = self.setup(model_configuration_id=profile.id, presented_tools=[])
        self.assertEqual(manager.store.list_deployments(), [self.deployment])
        main = ScriptedChatModel([helper_fixture.call("task", {
            "subagent_type": helper["id"], "description": "Report"}, "delegate"), AIMessage(content="Parent done")])
        admitted = []

        def model_for_role(run, _sink):
            if run.parent_run_id:
                admitted.append(run.model_copy(deep=True))
                return ScriptedChatModel([AIMessage(content="Helper done")])
            return main

        self.harness(model_for_role)
        ready = manager.ensure_deployment_ready

        def ready_without_native(deployment_id):
            dep = manager.get_deployment(deployment_id)
            if dep.scope.value != "managed":
                return ready(deployment_id)
            return dep.model_copy(update={"endpoint": "http://127.0.0.1:9/v1"})

        with patch.object(manager, "ensure_deployment_ready", ready_without_native), patch.object(manager.deployments, "start") as native_start:
            finished = wait_for_run(self.client, self.start(presented_tools=["echo"], helper_agent_ids=[helper["id"]])["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        child, = admitted
        prepared = manager.get_deployment(child.deployment_id)
        self.assertEqual(prepared.bundle_id, bundle_id)
        self.assertEqual(child.profile_id, profile.id)
        self.assertEqual(prepared.status.value, "stopped")
        native_start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
