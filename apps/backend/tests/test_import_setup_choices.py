"""Only checked card recipes create named setups; preview tuning is not imported."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from pydantic import ValidationError

from tests import test_recipe_workflow as recipe_fixtures
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import HuggingFaceImportRequest, ImportJob, LocalImportRequest


class ImportSetupChoicesTests(unittest.TestCase):
    setUp = recipe_fixtures.RecipeWorkflowTests.setUp

    def tearDown(self):
        if getattr(self, "reopened", None) is not None:
            self.reopened.imports.close()
        recipe_fixtures.RecipeWorkflowTests.tearDown(self)

    def job(self, **values):
        return ImportJob(id="card_choices", kind="huggingface", status="running", created_at=utc_now(),
            updated_at=utc_now(), **values)

    def clear_setups(self):
        self.manager.delete_profile(self.base.id)

    def test_zero_selected_recipes_stays_empty_after_reads_and_restart(self):
        self.clear_setups()
        self.assertIsNone(self.manager.imports._create_job_recipes(self.job(), self.bundle))
        self.assertEqual(self.manager.list_model_configurations(self.bundle.id), [])
        self.manager.list_bundles()
        reopened = type(self.manager)(self.paths)
        self.reopened = reopened
        self.assertEqual(reopened.list_model_configurations(self.bundle.id), [])
        self.assertIsNone(reopened.store.get_bundle(self.bundle.id).default_configuration_id)
        self.assertTrue(self.weight.is_file())

    def test_checked_recipes_only_use_card_order_and_native_loading_defaults(self):
        self.clear_setups()
        selected = [self.recipes[2]["id"], self.recipes[0]["id"]]
        job = self.job(recipe_ids=selected)
        self.manager.store.put_job(job)
        self.assertIsNone(self.manager.imports._create_job_recipes(job, self.bundle))
        profiles = self.manager.list_model_configurations(self.bundle.id)
        self.assertEqual({profile.recipe_origin.recipe_id for profile in profiles}, set(selected))
        self.assertTrue(all(profile.bags.startup.requested == {} for profile in profiles))
        self.assertFalse(any(profile.display_name in {"Default", "Import settings"} for profile in profiles))
        preferred = self.manager.store.get_profile(self.manager.store.get_bundle(self.bundle.id).default_configuration_id)
        self.assertEqual(preferred.recipe_origin.recipe_id, self.recipes[0]["id"])
        preferred.bags.per_request.requested["temperature"] = .33
        self.manager.store.put_profile(preferred)
        retry = job.model_copy(update={"id": "retried", "retry_of": job.id})
        self.assertIsNone(self.manager.imports._create_job_recipes(retry, self.bundle))
        self.assertEqual(len(self.manager.list_model_configurations(self.bundle.id)), 2)
        self.assertEqual(self.manager.store.get_profile(preferred.id).bags.per_request.requested["temperature"], .33)

    def test_preparation_failure_retains_weights_and_creates_no_fake_setup(self):
        self.clear_setups()
        job = self.job(recipe_ids=[self.recipes[0]["id"]])
        self.manager.store.put_job(job)
        with patch("workbench_backend.inference.recipe_configurations.validate_response_recipe", side_effect=ValueError("template unavailable")):
            error = self.manager.imports._create_job_recipes(job, self.bundle)
        self.assertEqual(error, "template unavailable")
        self.assertEqual(self.manager.list_model_configurations(self.bundle.id), [])
        self.assertIsNone(self.manager.store.get_bundle(self.bundle.id).default_configuration_id)
        self.assertTrue(self.weight.is_file())
        self.assertIsNone(self.manager.imports._create_job_recipes(job, self.bundle))
        self.assertEqual(len(self.manager.list_model_configurations(self.bundle.id)), 1)

    def test_retired_import_tuning_is_rejected_instead_of_creating_hidden_overrides(self):
        for schema, values in ((LocalImportRequest, {"source_path": str(self.weight)}),
                (HuggingFaceImportRequest, {"repo_id": "publisher/model"})):
            for field, value in (("initial_startup", {"ctx_size": 4096}),
                    ("initial_per_request", {"temperature": .2}), ("initial_recipe_id", "old")):
                with self.subTest(schema=schema, field=field), self.assertRaises(ValidationError):
                    schema(**values, **{field: value})


if __name__ == "__main__":
    unittest.main()
