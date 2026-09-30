"""Zero setups are legal while deletion preserves active-use and history guards."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests import test_recipe_workflow as recipe_tests
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.chat.schemas import ChatConversation, ChatQueueItem
from workbench_backend.errors import ManagerError, manager_error_handler
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.routes import router
from workbench_backend.inference.schemas import Deployment, DeploymentStatus, ManagementScope
from workbench_backend.state.migrate import open_application_store


class ModelSetupDeletionTests(unittest.TestCase):
    setUp = recipe_tests.RecipeWorkflowTests.setUp

    def tearDown(self):
        if getattr(self, "reopened", None) is not None:
            self.reopened.imports.close()
        recipe_tests.RecipeWorkflowTests.tearDown(self)

    def extra(self):
        return self.manager.store.put_profile(self.base.model_copy(update={
            "id": "config_extra", "display_name": "Extra"}))

    def deployment(self, profile_id, status=DeploymentStatus.stopped, **fields):
        now = utc_now()
        return self.manager.store.put_deployment(Deployment(id="deletion_deployment",
            display_name="Selected model load", bundle_id=self.bundle.id, profile_id=profile_id,
            scope=ManagementScope.managed, status=status, created_at=now, updated_at=now, **fields))

    def test_preferred_last_setup_can_be_deleted_without_recreation(self):
        app = FastAPI()
        app.state.manager = self.manager
        app.include_router(router)
        app.add_exception_handler(ManagerError, manager_error_handler)
        with TestClient(app) as client:
            preview = client.get(f"/v1/profiles/{self.base.id}/delete-preview")
            self.assertEqual(preview.status_code, 200)
            self.assertEqual(preview.json()["blockers"], [])
            deletion = client.delete(f"/v1/profiles/{self.base.id}")
            self.assertEqual(deletion.status_code, 200)
        self.assertIsNone(self.manager.store.get_bundle(self.bundle.id).default_configuration_id)
        self.assertEqual(self.manager.list_model_configurations(self.bundle.id), [])
        self.assertEqual(self.manager.list_bundles()[0].default_configuration_id, None)
        reopened = type(self.manager)(self.paths)
        self.reopened = reopened
        self.assertEqual(reopened.list_model_configurations(self.bundle.id), [])
        self.assertTrue(self.weight.is_file())

    def test_replacement_default_allows_deletion_and_retains_historical_consumers(self):
        alternative = self.extra()
        preview = self.manager.profile_delete_preview(self.base.id)
        self.assertEqual(preview.blockers, [])
        self.manager.set_default_configuration(self.bundle.id, alternative.id)
        now = utc_now()
        run = AgentRun(id="historical_run", profile_id=self.base.id, deployment_id="old_load",
            status="completed", task="Retained history", enabled_tools=[], presented_tools=[],
            created_at=now, updated_at=now)
        chat = ChatConversation(id="historical_chat", profile_id=self.base.id, deployment_id="old_load",
            created_at=now, updated_at=now)
        with open_application_store(self.paths) as store:
            store.put_run(run)
            store.put_conversation(chat)
        preview = self.manager.profile_delete_preview(self.base.id)
        self.assertEqual(preview.blockers, [])
        self.assertEqual({item.kind for item in preview.consumers}, {"agent_run", "chat"})
        self.manager.delete_profile(self.base.id)
        self.assertEqual(self.manager.store.list_profiles(), [alternative])
        self.assertEqual(self.manager.store.get_bundle(self.bundle.id).default_configuration_id, alternative.id)
        with open_application_store(self.paths) as store:
            self.assertEqual(store.get_run(run.id).profile_id, self.base.id)
            self.assertEqual(store.get_conversation(chat.id).profile_id, self.base.id)
        self.assertTrue(self.weight.is_file())

    def test_last_setup_can_be_deleted_if_its_preferred_pointer_is_missing(self):
        initial = self.bundle.model_copy(update={"default_configuration_id": None})
        self.manager.store.put_bundle(initial)
        preview = self.manager.profile_delete_preview(self.base.id)
        self.assertEqual(preview.blockers, [])
        self.manager.delete_profile(self.base.id)
        self.assertEqual(self.manager.store.get_bundle(self.bundle.id), initial)
        self.assertEqual(self.manager.store.list_profiles(), [])

    def test_deleting_preferred_with_other_setups_clears_pointer_without_substitution(self):
        alternative = self.extra()
        self.manager.delete_profile(self.base.id)
        self.assertEqual(self.manager.store.list_profiles(), [alternative])
        self.assertIsNone(self.manager.store.get_bundle(self.bundle.id).default_configuration_id)
        self.manager.list_bundles()
        self.manager.list_model_configurations(self.bundle.id)
        self.assertIsNone(self.manager.store.get_bundle(self.bundle.id).default_configuration_id)

    def test_active_or_unreaped_model_load_blocks_preview_and_deletion(self):
        alternative = self.extra()
        for status, fields in (
            (DeploymentStatus.starting, {}), (DeploymentStatus.running, {}),
            (DeploymentStatus.unhealthy, {}), (DeploymentStatus.failed, {"pid": 12345}),
        ):
            with self.subTest(status=status):
                deployment = self.deployment(alternative.id, status, **fields)
                preview = self.manager.profile_delete_preview(alternative.id)
                self.assertTrue(any(item.kind == "deployment" and item.id == deployment.id and item.live
                    for item in preview.blockers))
                with self.assertRaises(ManagerError) as raised:
                    self.manager.delete_profile(alternative.id)
                self.assertEqual((raised.exception.code, raised.exception.status_code), ("profile_delete_blocked", 409))
                self.assertEqual(self.manager.store.get_profile(alternative.id), alternative)
                self.assertEqual(self.manager.store.get_deployment(deployment.id), deployment)

    def test_active_runs_and_queued_inputs_block_preview_and_deletion(self):
        alternative = self.extra()
        now = utc_now()
        run = AgentRun(id="active_run", profile_id=alternative.id, deployment_id="accepted_load",
            status="running", task="Accepted work", enabled_tools=[], presented_tools=[],
            created_at=now, updated_at=now)
        queued = ChatQueueItem(id="accepted_input", task="Queued work", created_at=now, updated_at=now,
            frozen_config={"model_configuration_id": alternative.id})
        chat = ChatConversation(id="queued_chat", profile_id=self.base.id, deployment_id="other_load",
            queue=[queued], created_at=now, updated_at=now)
        with open_application_store(self.paths) as store:
            store.put_run(run)
            store.put_conversation(chat)
        preview = self.manager.profile_delete_preview(alternative.id)
        self.assertEqual({item.kind for item in preview.blockers}, {"agent_run", "chat_queue"})
        with self.assertRaises(ManagerError) as raised:
            self.manager.delete_profile(alternative.id)
        self.assertEqual((raised.exception.code, raised.exception.status_code), ("profile_delete_blocked", 409))
        self.assertEqual(self.manager.store.get_profile(alternative.id), alternative)
        with open_application_store(self.paths) as store:
            self.assertEqual(store.get_run(run.id).status, "running")
            self.assertEqual(store.get_conversation(chat.id).queue, [queued])

    def test_admitted_work_reservation_still_blocks_deletion(self):
        alternative = self.extra()
        deployment = self.deployment(alternative.id)
        with self.manager.lifecycle.reserve(deployment, profile_id=alternative.id), self.assertRaises(ManagerError) as raised:
            self.manager.delete_profile(alternative.id)
        self.assertEqual((raised.exception.code, raised.exception.status_code), ("model_lifecycle_active", 409))
        self.assertEqual(self.manager.store.get_profile(alternative.id), alternative)

    def test_default_promotion_cannot_race_a_validated_deletion(self):
        alternative = self.extra()
        deleting = Event()
        promotion_started = Event()
        promotion_finished = Event()
        release = Event()
        original_delete = self.manager.store.delete_profile

        def delete(profile_id):
            deleting.set()
            if not release.wait(5):
                raise RuntimeError("Deletion test worker was not released")
            return original_delete(profile_id)

        def promote():
            promotion_started.set()
            try:
                return self.manager.set_default_configuration(self.bundle.id, alternative.id)
            finally:
                promotion_finished.set()

        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(self.manager.store, "delete_profile", side_effect=delete):
            removal = pool.submit(self.manager.delete_profile, alternative.id)
            try:
                self.assertTrue(deleting.wait(5))
                promotion = pool.submit(promote)
                self.assertTrue(promotion_started.wait(5))
                self.assertFalse(promotion_finished.wait(0.1), "Default pointer changed before deletion released its lock")
            finally:
                release.set()
            removal.result(timeout=5)
            with self.assertRaises(ManagerError) as raised:
                promotion.result(timeout=5)
            self.assertEqual(raised.exception.code, "profile_missing")
        self.assertEqual(self.manager.store.get_bundle(self.bundle.id).default_configuration_id, self.base.id)
        self.assertEqual(self.manager.store.list_profiles(), [self.base])


if __name__ == "__main__":
    unittest.main()
