"""Import setup intent survives installed-weight preparation failures and retry."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests import test_recipe_workflow as recipe_fixtures
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import ImportJob


class ImportSetupChoicesTests(unittest.TestCase):
    setUp = recipe_fixtures.RecipeWorkflowTests.setUp
    tearDown = recipe_fixtures.RecipeWorkflowTests.tearDown

    def job(self, **values):
        return ImportJob(id="initial_choices", kind="huggingface", status="running", created_at=utc_now(),
            updated_at=utc_now(), initial_startup={"ctx_size": 4096}, **values)

    def test_inline_recipe_and_custom_response_create_one_independent_setup(self):
        job = self.job(initial_recipe_id=self.recipes[2]["id"], initial_per_request={"temperature": .41, "max_tokens": 512})
        self.manager.store.put_job(job)
        self.assertIsNone(self.manager.imports._create_job_recipes(job, self.bundle))
        saved = self.manager.store.get_profile(self.manager.store.get_bundle(self.bundle.id).default_configuration_id)
        self.assertEqual(saved.bags.startup.requested, {"ctx_size": 4096})
        self.assertEqual(saved.bags.per_request.requested["temperature"], .41)
        self.assertEqual(saved.bags.per_request.requested["reasoning"], "off")
        self.assertEqual(saved.bags.per_request.requested["max_tokens"], 512)
        self.assertEqual(saved.recipe_origin.recipe_id, self.recipes[2]["id"])
        self.assertEqual(len(self.manager.list_model_configurations(self.bundle.id)), 2)
        self.assertEqual(self.manager.store.get_profile(self.base.id).bags.per_request.requested["temperature"], .2)
        # A retry respects deliberate edits to the already-created setup.
        saved.bags.per_request.requested["temperature"] = .33
        self.manager.store.put_profile(saved)
        retry = job.model_copy(update={"id": "retried", "retry_of": job.id})
        self.assertIsNone(self.manager.imports._create_job_recipes(retry, self.bundle))
        self.assertEqual(self.manager.store.get_profile(saved.id).bags.per_request.requested["temperature"], .33)

    def test_preparation_failure_retains_weight_and_retry_candidate(self):
        job = self.job(initial_recipe_id=self.recipes[0]["id"])
        self.manager.store.put_job(job)
        with patch("workbench_backend.inference.recipe_configurations.validate_response_recipe", side_effect=ValueError("template unavailable")):
            error = self.manager.imports._create_job_recipes(job, self.bundle)
        self.assertEqual(error, "template unavailable")
        self.assertTrue(self.weight.is_file())
        self.assertEqual(self.manager.store.get_bundle(self.bundle.id).default_configuration_id, self.base.id)
        self.assertIsNone(self.manager.imports._create_job_recipes(job, self.bundle))
        self.assertTrue(self.weight.is_file())

    def test_response_only_initial_choice_is_saved_without_loading(self):
        job = self.job(initial_per_request={"max_tokens": 391, "top_p": .71})
        job.initial_startup = {}
        self.assertIsNone(self.manager.imports._create_job_recipes(job, self.bundle))
        saved = self.manager.store.get_profile(self.manager.store.get_bundle(self.bundle.id).default_configuration_id)
        self.assertEqual(saved.bags.per_request.applied["max_tokens"], 391)
        self.assertEqual(saved.bags.per_request.applied["top_p"], .71)
        self.assertEqual(self.manager.store.list_deployments(), [])


if __name__ == "__main__":
    unittest.main()
