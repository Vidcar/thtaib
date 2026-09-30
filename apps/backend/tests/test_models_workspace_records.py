"""Refresh cutover preserves authored values and stable identities without default shims."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support import write_tiny_gguf
from tests.test_capability_probes import make_deployment
from workbench_backend.agents.setup_schemas import SetupConfiguration
from workbench_backend.agents.setup_service import SetupService
from workbench_backend.chat.schemas import ChatConversation, ChatQueueItem
from workbench_backend.errors import ManagerError, manager_error_handler
from workbench_backend.inference.compatibility import CompatibilityService
from workbench_backend.inference.configurations import loaded_model_identity
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.routes import router
from workbench_backend.inference.schemas import LocalImportRequest, ManagedDeploymentRequest, ModelConfigurationWriteRequest, RunProfile, HealthReport, ReconfigureDeploymentRequest
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.migrate import open_application_store


class ModelsWorkspaceRecordsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.paths = WorkbenchPaths(Path(temporary.name)).ensure()
        self.manager = ModelManager(self.paths)
        self.addCleanup(self.manager.capability_checks.close)
        self.addCleanup(self.manager.imports.close)
        self.source = write_tiny_gguf(Path(temporary.name) / "original.gguf")
        self.bundle_id = self.manager.import_local(LocalImportRequest(source_path=str(self.source))).bundle_id

    def saved(self, name="My setup", **values):
        return self.manager.save_model_configuration(self.bundle_id, ModelConfigurationWriteRequest(display_name=name, **values))

    def client(self):
        app = FastAPI()
        app.state.manager = self.manager
        app.include_router(router)
        app.add_exception_handler(ManagerError, manager_error_handler)
        return TestClient(app)

    def synthetic(self, **values):
        now = utc_now()
        return RunProfile(id=f"config_{self.bundle_id}", display_name="Default", bundle_id=self.bundle_id,
            bags=resolve_bags(), created_at=now, updated_at=now, settings_schema_version=2, **values)

    def reopen_for_migration(self):
        self.manager.store.put_setting("models-workspace-records-version", "0")
        backup = self.paths.state / "models-workspace-records-v1.backup.json"
        backup.unlink(missing_ok=True)  # isolated test metadata only
        reopened = ModelManager(self.paths)
        self.addCleanup(reopened.imports.close)
        return reopened

    def test_first_manual_save_is_preferred_and_empty_native_bags_are_legal(self):
        self.assertEqual(self.manager.list_model_configurations(self.bundle_id), [])
        saved = self.saved()
        self.assertEqual(self.manager.store.get_bundle(self.bundle_id).default_configuration_id, saved.id)
        self.assertEqual(saved.bags.startup.requested, {})
        self.assertEqual(saved.bags.per_request.requested, {})
        second = self.saved("Second")
        self.assertEqual(self.manager.store.get_bundle(self.bundle_id).default_configuration_id, saved.id)
        self.manager.delete_profile(saved.id)
        self.assertIsNone(self.manager.store.get_bundle(self.bundle_id).default_configuration_id)
        self.saved("Third")
        self.assertIsNone(self.manager.store.get_bundle(self.bundle_id).default_configuration_id)
        self.assertIsNotNone(self.manager.get_profile(second.id))

    def test_unload_and_reload_drain_automatic_reservations_without_bypassing_real_work(self):
        saved = self.saved()
        deployment = make_deployment().model_copy(update={"bundle_id": self.bundle_id, "profile_id": saved.id,
            "settings": saved.bags, "applied_startup": saved.bags.startup.applied,
            "health": HealthReport(healthy=True, endpoint="http://127.0.0.1:9", checked=utc_now())})
        self.manager.store.put_deployment(deployment)
        for operation in ("stop_deployment", "reload_deployment"):
            with self.subTest(operation=operation):
                entered, release = threading.Event(), threading.Event()
                result, errors = [], []
                def probe(manager, identifier, request, **kwargs):
                    with manager.reserve_deployment(identifier, profile_id=request.configuration_id):
                        entered.set()
                        if not release.wait(5):
                            raise RuntimeError("automatic worker fixture timed out")
                def mutate():
                    try:
                        result.append(getattr(self.manager, operation)(deployment.id))
                    except Exception as exc:
                        errors.append(exc)
                with patch("workbench_backend.inference.capability_checks.applicable_capabilities", return_value=["text_stream"]), \
                        patch("workbench_backend.inference.probes.run_capability_probe", probe), \
                        patch.object(self.manager.deployments, "stop", return_value=deployment) as stop, \
                        patch.object(self.manager.deployments, "start", return_value=deployment):
                    self.manager.capability_checks.start(deployment.id, saved.id)
                    self.assertTrue(entered.wait(5))
                    thread = threading.Thread(target=mutate)
                    thread.start()
                    try:
                        deadline = time.monotonic() + 5
                        while not self.manager.capability_checks._suspended_deployments.get(deployment.id):
                            self.assertLess(time.monotonic(), deadline)
                            time.sleep(.01)
                        stop.assert_not_called()
                        self.manager.capability_checks.start(deployment.id, saved.id)
                        self.assertEqual(len(self.manager.capability_checks._workers), 1)
                    finally:
                        release.set()
                        thread.join(5)
                        self.manager.capability_checks.stop_all()
                    self.assertFalse(thread.is_alive())
                    self.assertFalse(errors, errors)
                    self.assertEqual(result[0].id, deployment.id)
                    stop.assert_called_once()
                with self.manager.reserve_deployment(deployment.id, profile_id=saved.id):
                    with patch.object(self.manager.deployments, "stop") as stop, self.assertRaises(ManagerError) as failure:
                        getattr(self.manager, operation)(deployment.id)
                    self.assertEqual(failure.exception.code, "model_lifecycle_active")
                    stop.assert_not_called()

    def test_reconfigure_schedules_selected_setup_checks_after_mutation(self):
        saved = self.saved()
        deployment = make_deployment().model_copy(update={"bundle_id": self.bundle_id, "profile_id": saved.id,
            "settings": saved.bags, "applied_startup": saved.bags.startup.applied})
        self.manager.store.put_deployment(deployment)
        scheduled = []
        def schedule(identifier, selected):
            self.assertFalse(self.manager.lifecycle.owns_mutation("reconfigure_deployment"))
            scheduled.append((identifier, selected))
        with patch.object(self.manager.runtime, "require_executable", return_value=Path("llama-server.exe")), \
                patch("workbench_backend.inference.deployments.managed_argv"), \
                patch.object(self.manager, "_store_identical_running_launch", return_value=(deployment, deployment)), \
                patch.object(self.manager.capability_checks, "start", schedule):
            result = self.manager.reconfigure_deployment(deployment.id,
                ReconfigureDeploymentRequest(startup={}, model_configuration_id=saved.id))
        self.assertEqual(result.id, deployment.id)
        self.assertEqual(scheduled, [(deployment.id, saved.id)])

    def test_empty_and_deleted_references_never_select_another_setup(self):
        with open_application_store(self.paths) as store:
            service = SetupService(store, self.manager)
            empty = service.resolve(overrides=SetupConfiguration(bundle_id=self.bundle_id), validate=False)
            self.assertIsNone(empty.configuration.model_configuration_id)
            self.assertEqual(self.manager.store.list_profiles(), [])
            selected = self.saved()
            other = self.saved("Other")
            self.manager.delete_profile(selected.id)
            missing = service.resolve(overrides=SetupConfiguration(model_configuration_id=selected.id), validate=False)
            self.assertEqual(missing.configuration.model_configuration_id, selected.id)
            self.assertIsNone(missing.configuration.deployment_id)
            self.assertTrue(any(issue.id == selected.id for issue in service.dependencies(missing.configuration)))
            bundle_only = service.resolve(overrides=SetupConfiguration(bundle_id=self.bundle_id), validate=False)
            self.assertIsNone(bundle_only.configuration.model_configuration_id)
            self.assertEqual(self.manager.store.get_profile(other.id).id, other.id)

    def test_public_load_requires_named_saved_setup_but_internal_preparation_is_available(self):
        prepared = self.manager.create_managed(ManagedDeploymentRequest(bundle_id=self.bundle_id, auto_start=False))
        with self.client() as client, patch.object(self.manager, "start_deployment", return_value=prepared) as start:
            rejected = client.post("/v1/deployments/managed", json={"bundle_id": self.bundle_id})
            self.assertEqual((rejected.status_code, rejected.json()["code"]), (409, "configuration_required"))
            rejected = client.post(f"/v1/deployments/{prepared.id}/start")
            self.assertEqual((rejected.status_code, rejected.json()["code"]), (409, "configuration_required"))
            start.assert_not_called()
            with patch.object(self.manager, "reload_deployment") as reload, patch.object(self.manager, "reconfigure_deployment") as reconfigure:
                rejected = client.post(f"/v1/deployments/{prepared.id}/reload")
                self.assertEqual((rejected.status_code, rejected.json()["code"]), (409, "configuration_required"))
                rejected = client.post(f"/v1/deployments/{prepared.id}/reconfigure", json={"startup": {}})
                self.assertEqual((rejected.status_code, rejected.json()["code"]), (409, "configuration_required"))
                reload.assert_not_called()
                reconfigure.assert_not_called()
            saved = self.saved()
            accepted = client.post("/v1/deployments/managed", json={"bundle_id": self.bundle_id, "profile_id": saved.id})
            self.assertEqual(accepted.status_code, 200, accepted.text)
            start.assert_called_once()
            with patch.object(self.manager, "reconfigure_deployment", return_value=prepared) as reconfigure:
                accepted = client.post(f"/v1/deployments/{prepared.id}/reconfigure", json={"startup": {}, "model_configuration_id": saved.id})
                self.assertEqual(accepted.status_code, 200, accepted.text)
                reconfigure.assert_called_once()
        self.assertEqual(len(self.manager.list_model_configurations(self.bundle_id)), 1)

    def test_new_named_setup_never_reuses_anonymous_or_deleted_origin(self):
        anonymous = self.manager.create_managed(ManagedDeploymentRequest(bundle_id=self.bundle_id, auto_start=False))
        old = self.saved()
        prepared = self.manager.create_managed(ManagedDeploymentRequest(bundle_id=self.bundle_id, profile_id=old.id, auto_start=False))
        self.assertNotEqual(prepared.id, anonymous.id)
        self.manager.delete_profile(old.id)
        replacement = self.saved("Replacement")
        with open_application_store(self.paths) as store:
            resolved = SetupService(store, self.manager).resolve(
                overrides=SetupConfiguration(model_configuration_id=replacement.id), validate=False)
            self.assertIsNone(resolved.configuration.deployment_id)
        fresh = self.manager.create_managed(ManagedDeploymentRequest(bundle_id=self.bundle_id, profile_id=replacement.id, auto_start=False))
        self.assertNotIn(fresh.id, {anonymous.id, prepared.id})
        self.assertEqual(fresh.profile_id, replacement.id)
        self.assertEqual(self.manager.configuration_deployment(replacement.id).id, fresh.id)
        self.assertEqual(self.manager.get_deployment(prepared.id).profile_id, old.id)
        with self.client() as client, patch.object(self.manager, "reload_deployment", return_value=fresh) as reload:
            response = client.post(f"/v1/deployments/{fresh.id}/reload")
            self.assertEqual(response.status_code, 200, response.text)
            reload.assert_called_once_with(fresh.id)

    def test_friendly_rename_preserves_source_loading_identity_and_compatibility(self):
        saved = self.saved()
        bundle = self.manager.store.get_bundle(self.bundle_id)
        identity = loaded_model_identity(None, bundle, saved.bags)
        compatibility = CompatibilityService(self.paths)
        assessment = compatibility.assess_bundle(bundle)
        with self.client() as client:
            response = client.patch(f"/v1/bundles/{self.bundle_id}", json={"display_name": "  Friendly model  "})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["display_name"], "Friendly model")
            invalid = client.patch(f"/v1/bundles/{self.bundle_id}", json={"display_name": "  "})
            self.assertEqual((invalid.status_code, invalid.json()["code"]), (400, "bundle_name_required"))
        renamed = self.manager.store.get_bundle(self.bundle_id)
        self.assertEqual(renamed, bundle.model_copy(update={"display_name": "Friendly model"}))
        self.assertEqual(loaded_model_identity(None, renamed, saved.bags), identity)
        self.assertEqual(compatibility.assess_bundle(renamed), assessment)
        self.assertEqual(self.manager.list_model_configurations(self.bundle_id)[0].bundle_name, "Friendly model")
        self.assertEqual(self.manager.store.get_profile(saved.id).revision, saved.revision)
        self.assertTrue(self.source.is_file())

    def test_setup_menu_rename_and_copy_validate_names_and_preserve_native_values(self):
        from workbench_backend.inference.schemas import DuplicateProfileRequest
        saved = self.saved(startup={"n_gpu_layers": 3}, per_request={"temperature": .4},
            agent={"system_prompt": "Keep this instruction"})
        renamed = self.manager.rename_profile(saved.id, "  Renamed  ")
        self.assertEqual((renamed.id, renamed.display_name, renamed.revision), (saved.id, "Renamed", 2))
        self.assertEqual(renamed.bags, saved.bags)
        first = self.manager.duplicate_profile(saved.id)
        second = self.manager.duplicate_profile(saved.id)
        self.assertEqual((first.display_name, second.display_name), ("Renamed copy", "Renamed copy 2"))
        self.assertEqual(first.bags, saved.bags)
        for action in (lambda: self.manager.rename_profile(first.id, " renamed "),
                lambda: self.manager.duplicate_profile(saved.id, DuplicateProfileRequest(display_name=" "))):
            with self.assertRaises(ManagerError):
                action()
        self.assertEqual(self.manager.store.get_bundle(self.bundle_id).default_configuration_id, saved.id)

    def test_migration_removes_only_untouched_generated_setup_and_retired_product_fields(self):
        generated = self.synthetic()
        self.manager.store.put_profile(generated)
        bundle = self.manager.store.get_bundle(self.bundle_id)
        self.manager.store.put_bundle(bundle.model_copy(update={"default_configuration_id": generated.id}))
        authored = self.saved("Authored", startup={"ctx_size": 4096, "chat_template_kwargs": {"style": "compact"}},
            per_request={"stop": ["END"], "temperature": .2}, agent={"system_prompt": "Authored instructions"})
        bags = authored.bags.model_copy(deep=True)
        bags.agent = resolve_bags(agent={"system_prompt": "Authored instructions", "tools_enabled": True, "max_iterations": 7}).agent
        self.manager.store.put_profile(authored.model_copy(update={"bags": bags}))
        # Exercise raw old product fields, which the current schema no longer exposes.
        raw = json.loads(self.manager.store.bundles_path.read_text(encoding="utf-8"))
        raw[0]["huggingface_configuration"] = {"hidden_response_recipe_ids": ["old-recipe"]}
        self.manager.store.bundles_path.write_text(json.dumps(raw), encoding="utf-8")
        reopened = self.reopen_for_migration()
        self.assertIsNone(reopened.store.get_profile(generated.id))
        self.assertIsNone(reopened.store.get_bundle(self.bundle_id).default_configuration_id)
        retained = reopened.store.get_profile(authored.id)
        self.assertEqual(retained.bags.startup.requested, authored.bags.startup.requested)
        self.assertEqual(retained.bags.per_request.requested, authored.bags.per_request.requested)
        self.assertEqual(retained.bags.agent.requested, {"system_prompt": "Authored instructions"})
        self.assertNotIn("hidden_response_recipe_ids", reopened.store.bundles_path.read_text(encoding="utf-8"))
        backup = json.loads((self.paths.state / "models-workspace-records-v1.backup.json").read_text(encoding="utf-8"))
        self.assertIn(generated.id, {profile["id"] for profile in backup["profiles"]})
        self.assertEqual(backup["bundles"][0]["huggingface_configuration"]["hidden_response_recipe_ids"], ["old-recipe"])
        before = reopened.store.profiles_path.read_bytes()
        again = ModelManager(self.paths)
        self.addCleanup(again.imports.close)
        self.assertEqual(again.store.profiles_path.read_bytes(), before)

    def test_migration_preserves_edited_generated_setup_and_admitted_work(self):
        edited = self.synthetic(revision=2)
        self.manager.store.put_profile(edited)
        retained = self.reopen_for_migration()
        self.assertEqual(retained.store.get_profile(edited.id), edited)
        self.manager.store.put_profile(edited.model_copy(update={"revision": 1}))
        now = utc_now()
        queue = ChatQueueItem(id="accepted", task="Retain", frozen_config={"model_configuration_id": edited.id},
            created_at=now, updated_at=now)
        with open_application_store(self.paths) as store:
            store.put_conversation(ChatConversation(id="protected", deployment_id="accepted_load", thread_id="protected_thread",
                created_at=now, updated_at=now, queue=[queue]))
        active = self.reopen_for_migration()
        self.assertIsNotNone(active.store.get_profile(edited.id))
        with open_application_store(self.paths) as store:
            self.assertEqual(store.get_conversation("protected").queue[0].frozen_config["model_configuration_id"], edited.id)


if __name__ == "__main__":
    unittest.main()
