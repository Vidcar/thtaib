"""Pinned card choices survive imports and become independent model configurations."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gguf import GGUFWriter

from workbench_backend.errors import ManagerError, manager_error_handler
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.hf_recipes import parse_model_card_recipes
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.import_jobs import ImportJobRunner
from workbench_backend.inference.routes import router
from workbench_backend.inference.schemas import (
    BundleFile, BundleSource, BundleSourceKind, Deployment, DeploymentStatus,
    FileRole, HuggingFaceConfiguration, HuggingFaceImportRequest, ImportJob,
    ImportStatus, ManagementScope,
    ModelBundle, ModelConfigurationWriteRequest, RunProfile,
)
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.inference.store import RecordStore
from workbench_backend.paths import WorkbenchPaths


REPO = "converter/demo-GGUF"
REVISION = "a" * 40
CARD = """# Demo
## Recommended sampling settings
- Thinking mode for general tasks: temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, repetition_penalty=1.0
- Thinking mode for precise coding: temperature=0.6, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, repetition_penalty=1.0
- Instruct (or non-thinking) mode: temperature=0.7, top_p=0.80, top_k=20, min_p=0.0, presence_penalty=1.5, repetition_penalty=1.0
"""
NEUTRAL_CARD = """# Demo
## Recommended Inference Settings
- **Temperature**: `0.6`
- **Top-P**: `0.95`
- **Flash Attention**: Enable `-fa` in llama.cpp.
"""


def _weight(path: Path, *, template: str | None = None) -> Path:
    writer = GGUFWriter(str(path), "qwen35")
    writer.add_name("recipe fixture")
    if template is not None:
        writer.add_chat_template(template)
    writer.add_tensor("token_embd.weight", np.zeros((2, 2), dtype=np.float32))
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
    return path


class RecipeWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = Path(__file__).resolve().parents[3] / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.paths = WorkbenchPaths(Path(self.tmp.name) / "app").ensure()
        self.manager = ModelManager(self.paths)
        self.weight = _weight(Path(self.tmp.name) / "model.gguf",
            template="{% if enable_thinking is undefined or enable_thinking is true %}think{% endif %}")
        self.card = Path(self.tmp.name) / "README.md"
        self.card.write_text(CARD, encoding="utf-8")
        self.digest = sha256_file(self.card)
        self.recipes = parse_model_card_recipes(CARD, repo_id=REPO, revision=REVISION, sha256=self.digest)
        self.base = RunProfile(id="config_base", display_name="Default", bundle_id="bundle",
            settings_schema_version=2,
            bags=resolve_bags(
                startup={"ctx_size": 8192, "n_gpu_layers": 8},
                per_request={"max_tokens": 128, "temperature": 0.2}),
            created_at=utc_now(), updated_at=utc_now())
        self.bundle = ModelBundle(id="bundle", display_name="Demo", source=BundleSource(
            kind=BundleSourceKind.huggingface, repo_id=REPO, resolved_revision=REVISION),
            files=[BundleFile(role=FileRole.primary_weights, name="model.gguf", path=str(self.weight),
                sha256=sha256_file(self.weight), size_bytes=self.weight.stat().st_size),
                BundleFile(role=FileRole.companion, name="README.md", path=str(self.card),
                    sha256=self.digest, size_bytes=self.card.stat().st_size)],
            primary_path=str(self.weight), created_at=utc_now(),
            default_configuration_id=self.base.id,
            huggingface_configuration=HuggingFaceConfiguration(response_recipes=self.recipes))
        self.manager.store.put_bundle(self.bundle)
        self.manager.store.put_profile(self.base)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_mode_neutral_recipe_uses_native_baseline_without_cloning_other_setup(self) -> None:
        plain = _weight(Path(self.tmp.name) / "plain.gguf", template="{{ messages }}")
        neutral = parse_model_card_recipes(NEUTRAL_CARD, repo_id=REPO,
            revision=REVISION, sha256=hashlib.sha256(NEUTRAL_CARD.encode()).hexdigest())
        self.assertEqual(len(neutral), 1)
        self.assertEqual(neutral[0]["reasoning"], "preserve")
        base = self.base.model_copy(update={"bags": resolve_bags(
            startup={"ctx_size": 8192, "n_gpu_layers": 8},
            per_request={"reasoning": "off", "max_tokens": 128,
                "temperature": 0.2, "repeat_penalty": 1.1})})
        self.manager.store.put_profile(base)
        bundle = self.bundle.model_copy(update={"primary_path": str(plain), "files": [
            self.bundle.files[0].model_copy(update={"name": "plain.gguf", "path": str(plain),
                "sha256": sha256_file(plain), "size_bytes": plain.stat().st_size}), self.bundle.files[1]],
            "huggingface_configuration": HuggingFaceConfiguration(response_recipes=neutral)})
        self.manager.store.put_bundle(bundle)
        self.assertEqual([item.id for item in self.manager.list_model_configurations(bundle.id)], [base.id])

        result = self.manager.create_response_recipe_configurations(bundle.id,
            [neutral[0]["id"]], neutral[0]["id"])
        created = result.configurations[0]
        self.assertEqual(created.bags.startup.requested, {})
        self.assertEqual(created.bags.per_request.requested, {"temperature": 0.6, "top_p": 0.95})
        self.assertEqual(result.bundle.default_configuration_id, created.id)
        self.assertEqual(self.manager.store.get_profile(base.id), base)

        restarted = ModelManager(self.paths)
        again = restarted.create_response_recipe_configurations(bundle.id,
            [neutral[0]["id"]], neutral[0]["id"])
        self.assertEqual(again.configurations[0].id, created.id)
        self.assertEqual(len(restarted.list_model_configurations(bundle.id)), 2)

    def test_mode_neutral_recipe_does_not_add_thinking_when_default_inherits_it(self) -> None:
        neutral = parse_model_card_recipes(NEUTRAL_CARD, repo_id=REPO,
            revision=REVISION, sha256=hashlib.sha256(NEUTRAL_CARD.encode()).hexdigest())
        bundle = self.bundle.model_copy(update={"huggingface_configuration":
            HuggingFaceConfiguration(response_recipes=neutral)})
        self.manager.store.put_bundle(bundle)
        result = self.manager.create_response_recipe_configurations(bundle.id, [neutral[0]["id"]])
        self.assertNotIn("reasoning", result.configurations[0].bags.per_request.requested)
        self.assertEqual(result.bundle.default_configuration_id, self.base.id)

    def test_create_all_recipes_is_idempotent_and_does_not_clone_launch_settings(self) -> None:
        collision = self.base.model_copy(update={"id": "config_named",
            "display_name": "General thinking"})
        self.manager.store.put_profile(collision)
        deployment = Deployment(id="deployment", display_name="Prior", bundle_id=self.bundle.id,
            scope=ManagementScope.managed, status=DeploymentStatus.stopped,
            created_at=utc_now(), updated_at=utc_now())
        self.manager.store.put_deployment(deployment)
        saved_deployment = self.manager.store.get_deployment(deployment.id)
        ids = [recipe["id"] for recipe in self.recipes]

        first = self.manager.create_response_recipe_configurations(self.bundle.id, ids, ids[0])
        self.assertEqual(len(first.configurations), 3)
        self.assertEqual(first.bundle.default_configuration_id, first.configurations[0].id)
        self.assertEqual(first.configurations[0].display_name, "General thinking (model card)")
        self.assertEqual([item.bags.per_request.requested["reasoning"] for item in first.configurations],
            ["on", "on", "off"])
        self.assertEqual([item.bags.per_request.requested["temperature"] for item in first.configurations],
            [1.0, 0.6, 0.7])
        self.assertEqual(first.configurations[2].bags.per_request.requested["presence_penalty"], 1.5)
        self.assertEqual(first.configurations[2].bags.per_request.requested["min_p"], 0.0)
        self.assertTrue(all(item.bags.startup.requested == {}
            and "max_tokens" not in item.bags.per_request.requested for item in first.configurations))
        self.assertEqual(self.manager.store.get_deployment(deployment.id), saved_deployment)

        restarted = ModelManager(self.paths)
        second = restarted.create_response_recipe_configurations(self.bundle.id, ids, ids[0])
        self.assertEqual([item.id for item in second.configurations], [item.id for item in first.configurations])
        self.assertEqual(len(restarted.list_model_configurations(self.bundle.id)), 5)
        edited = second.configurations[1].model_copy(update={"bags": resolve_bags(
            startup={"ctx_size": 8192}, per_request={"temperature": 0.42, "reasoning": "on"})})
        restarted.store.put_profile(edited)
        retried = restarted.create_response_recipe_configurations(self.bundle.id, ids, ids[0])
        self.assertEqual(retried.configurations[1].id, edited.id)
        self.assertEqual(retried.configurations[1].bags.per_request.requested["temperature"], 0.42)
        changed_base = self.base.model_copy(update={"bags": resolve_bags(
            startup={"ctx_size": 4096}, per_request={"max_tokens": 64})})
        restarted.store.put_profile(changed_base)
        self.assertEqual(restarted.store.get_profile(first.configurations[0].id).bags.startup.requested, {})
        self.assertNotIn("max_tokens", restarted.store.get_profile(first.configurations[0].id).bags.per_request.requested)

    def test_missing_thinking_toggle_rejects_all_creations(self) -> None:
        plain = _weight(Path(self.tmp.name) / "plain.gguf", template="{{ messages }}")
        changed = self.bundle.model_copy(update={"primary_path": str(plain), "files": [
            self.bundle.files[0].model_copy(update={"name": "plain.gguf", "path": str(plain),
                "sha256": sha256_file(plain), "size_bytes": plain.stat().st_size}), self.bundle.files[1]]})
        self.manager.store.put_bundle(changed)
        with self.assertRaises(ManagerError) as raised:
            self.manager.create_response_recipe_configurations(changed.id,
                [item["id"] for item in self.recipes], self.recipes[0]["id"])
        self.assertEqual(raised.exception.code, "recipe_thinking_unsupported")
        self.assertEqual([item.id for item in self.manager.list_model_configurations(changed.id)], [self.base.id])
        self.assertEqual(self.manager.store.get_bundle(changed.id).default_configuration_id, self.base.id)

    def test_import_recipe_is_independent_and_retry_preserves_its_edits(self) -> None:
        recipe_id = self.recipes[0]["id"]
        prior = self.manager.create_response_recipe_configurations(self.bundle.id, [recipe_id]).configurations[0]
        job = ImportJob(id="job_initial", kind=BundleSourceKind.huggingface,
            status=ImportStatus.running, created_at=utc_now(), updated_at=utc_now(),
            recipe_ids=[recipe_id],
            default_recipe_id=recipe_id)
        self.assertIsNone(self.manager.imports._create_job_recipes(job, self.bundle))
        current = self.manager.store.get_bundle(self.bundle.id)
        imported = self.manager.store.get_profile(current.default_configuration_id)
        self.assertNotEqual(imported.id, prior.id)
        self.assertEqual(imported.bags.startup.requested, {})
        edited = imported.model_copy(update={"bags": resolve_bags(
            startup={"ctx_size": 2048, "kv_offload": False}, per_request={"temperature": 0.42})})
        self.manager.store.put_profile(edited)
        retry = job.model_copy(update={"id": "job_retry", "retry_of": job.id})
        self.manager.store.put_job(job)
        self.manager.store.put_job(retry)
        self.assertIsNone(self.manager.imports._create_job_recipes(retry, current))
        retry_again = retry.model_copy(update={"id": "job_retry_again", "retry_of": retry.id})
        self.assertIsNone(self.manager.imports._create_job_recipes(retry_again, current))
        self.assertEqual(self.manager.store.get_bundle(self.bundle.id).default_configuration_id, imported.id)
        self.assertEqual(self.manager.store.get_profile(imported.id).bags, edited.bags)
        self.assertEqual(self.manager.store.get_profile(prior.id).bags.startup.requested, {})

    def test_thinking_token_only_in_template_comment_is_not_a_toggle(self) -> None:
        commented = _weight(Path(self.tmp.name) / "commented.gguf",
            template="{# enable_thinking #}{{ messages }}")
        changed = self.bundle.model_copy(update={"primary_path": str(commented), "files": [
            self.bundle.files[0].model_copy(update={"name": "commented.gguf", "path": str(commented),
                "sha256": sha256_file(commented), "size_bytes": commented.stat().st_size}), self.bundle.files[1]]})
        self.manager.store.put_bundle(changed)
        with self.assertRaises(ManagerError) as raised:
            self.manager.create_response_recipe_configurations(changed.id, [self.recipes[2]["id"]])
        self.assertEqual(raised.exception.code, "recipe_thinking_unsupported")

    def test_creation_without_default_keeps_existing_default_and_stale_ids_write_nothing(self) -> None:
        ids = [item["id"] for item in self.recipes]
        with self.assertRaises(ManagerError) as raised:
            self.manager.create_response_recipe_configurations(self.bundle.id, [ids[0], "old-card-id"])
        self.assertEqual(raised.exception.code, "recipe_stale")
        self.assertEqual([item.id for item in self.manager.list_model_configurations(self.bundle.id)], [self.base.id])
        result = self.manager.create_response_recipe_configurations(self.bundle.id, ids)
        self.assertEqual(len(result.configurations), 3)
        self.assertEqual(result.bundle.default_configuration_id, self.base.id)

    def test_adding_card_setup_does_not_replace_an_intentionally_empty_preference(self) -> None:
        other = self.manager.store.put_profile(self.base.model_copy(update={"id": "other_setup", "display_name": "Other"}))
        self.manager.delete_profile(self.base.id)
        result = self.manager.create_response_recipe_configurations(self.bundle.id, [self.recipes[0]["id"]])
        self.assertIsNone(result.bundle.default_configuration_id)
        self.assertIsNotNone(self.manager.store.get_profile(other.id))

    def test_local_metadata_refresh_preserves_weights_profiles_and_deployment(self) -> None:
        initial = self.bundle.model_copy(update={"huggingface_configuration": HuggingFaceConfiguration()})
        self.manager.store.put_bundle(initial)
        deployment = Deployment(id="deployment", display_name="Prior", bundle_id=self.bundle.id,
            scope=ManagementScope.managed, status=DeploymentStatus.stopped,
            created_at=utc_now(), updated_at=utc_now())
        self.manager.store.put_deployment(deployment)
        saved_deployment = self.manager.store.get_deployment(deployment.id)
        before_weight = sha256_file(self.weight)
        with patch.object(self.manager.bundles.hf, "read_pinned_card") as remote:
            refreshed = self.manager.refresh_response_recipes(self.bundle.id)
        remote.assert_not_called()
        self.assertEqual(len(refreshed.huggingface_configuration.response_recipes), 3)
        self.assertIsNotNone(refreshed.huggingface_configuration.metadata_refreshed_at)
        self.assertEqual(refreshed.default_configuration_id, self.base.id)
        self.assertEqual(self.manager.store.get_profile(self.base.id), self.base)
        self.assertEqual(self.manager.store.get_deployment(deployment.id), saved_deployment)
        self.assertEqual(sha256_file(self.weight), before_weight)

    def test_remote_metadata_refresh_uses_pinned_revision_without_weight_download(self) -> None:
        missing = self.bundle.model_copy(update={"files": self.bundle.files[:1],
            "huggingface_configuration": HuggingFaceConfiguration()})
        self.manager.store.put_bundle(missing)
        listing = SimpleNamespace(resolved_revision=REVISION, guidance_files=["README.md"])
        with patch.object(self.manager.bundles.hf, "inspect", return_value=listing) as inspect, patch.object(self.manager.bundles.hf, "read_pinned_card",
            return_value=(CARD, self.digest)) as remote, patch.object(
            self.manager.bundles.hf, "download", side_effect=AssertionError("weights downloaded")):
            refreshed = self.manager.refresh_response_recipes(missing.id)
        inspect.assert_called_once_with(repo_id=REPO, revision=REVISION)
        remote.assert_called_once_with(REPO, REVISION, filename="README.md", expected_sha256=None)
        self.assertEqual(len(refreshed.huggingface_configuration.response_recipes), 3)
        self.assertEqual(refreshed.files, missing.files)

    def test_remote_refresh_preserves_lowercase_card_filename(self) -> None:
        missing = self.bundle.model_copy(update={"files": self.bundle.files[:1],
            "huggingface_configuration": HuggingFaceConfiguration()})
        self.manager.store.put_bundle(missing)
        listing = SimpleNamespace(resolved_revision=REVISION,
            guidance_files=["notes.txt", "readme.md"])
        with patch.object(self.manager.bundles.hf, "inspect", return_value=listing), patch.object(
            self.manager.bundles.hf, "read_pinned_card", return_value=(CARD, self.digest)) as remote, patch.object(
            self.manager.bundles.hf, "download", side_effect=AssertionError("weights downloaded")):
            refreshed = self.manager.refresh_response_recipes(missing.id)
        remote.assert_called_once_with(REPO, REVISION, filename="readme.md", expected_sha256=None)
        self.assertEqual(len(refreshed.huggingface_configuration.response_recipes), 3)
        self.assertEqual(refreshed.files, missing.files)

    def test_corrupt_local_card_fetches_only_recorded_pinned_card(self) -> None:
        self.card.write_text("corrupted", encoding="utf-8")
        with patch.object(self.manager.bundles.hf, "read_pinned_card",
            return_value=(CARD, self.digest)) as remote, patch.object(
            self.manager.bundles.hf, "download", side_effect=AssertionError("weights downloaded")):
            refreshed = self.manager.refresh_response_recipes(self.bundle.id)
        remote.assert_called_once_with(REPO, REVISION, filename="README.md", expected_sha256=self.digest)
        self.assertEqual(len(refreshed.huggingface_configuration.response_recipes), 3)
        self.assertIn("README.md", refreshed.huggingface_configuration.unsupported)

    def test_refresh_never_parses_bytes_changed_after_a_separate_checksum(self) -> None:
        from workbench_backend.inference import service
        original_hash = service.sha256_file
        def mutate_after_hash(path):
            digest = original_hash(path)
            if Path(path) == self.card:
                self.card.write_text(CARD.replace("temperature=1.0", "temperature=0.4"), encoding="utf-8")
            return digest
        with patch.object(service, "sha256_file", side_effect=mutate_after_hash), patch.object(
            self.manager.bundles.hf, "read_pinned_card", return_value=(CARD, self.digest)):
            refreshed = self.manager.refresh_response_recipes(self.bundle.id)
        general = next(item for item in refreshed.huggingface_configuration.response_recipes
            if item.name == "General thinking")
        self.assertEqual(general.per_request["temperature"], 1.0)


    def test_card_refresh_without_setups_does_not_recreate_records_and_visibility_is_retired(self) -> None:
        self.manager.delete_profile(self.base.id)
        app = FastAPI()
        app.state.manager = self.manager
        app.include_router(router)
        app.add_exception_handler(ManagerError, manager_error_handler)
        with TestClient(app) as client:
            response = client.post(f"/v1/bundles/{self.bundle.id}/response-recipes/refresh")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn("hidden_response_recipe_ids", response.json()["huggingface_configuration"])
            self.assertEqual(client.put(f"/v1/bundles/{self.bundle.id}/response-recipes/{self.recipes[0]['id']}/visibility",
                json={"visible": False}).status_code, 404)
        self.assertEqual(self.manager.list_model_configurations(self.bundle.id), [])
        self.assertIsNone(self.manager.store.get_bundle(self.bundle.id).default_configuration_id)

    def test_card_refresh_preserves_concurrent_friendly_name_and_current_metadata(self) -> None:
        from workbench_backend.inference.hf_configuration import read_bundle_model_card
        reading, release = Event(), Event()

        def read(bundle, hf):
            reading.set()
            if not release.wait(5):
                raise RuntimeError("Refresh test worker was not released")
            return read_bundle_model_card(bundle, hf)

        with ThreadPoolExecutor(max_workers=1) as pool, patch(
            "workbench_backend.inference.hf_configuration.read_bundle_model_card", side_effect=read):
            pending = pool.submit(self.manager.refresh_response_recipes, self.bundle.id)
            try:
                self.assertTrue(reading.wait(5))
                current = self.manager.rename_bundle(self.bundle.id, "Renamed while reading")
                config = current.huggingface_configuration.model_copy(update={
                    "generation_defaults": {"temperature": .81}, "source_note": "Changed while reading"})
                current = self.manager.store.put_bundle(current.model_copy(update={"huggingface_configuration": config}))
            finally:
                release.set()
            refreshed = pending.result(timeout=5)
        self.assertEqual(refreshed.display_name, current.display_name)
        self.assertEqual(refreshed.huggingface_configuration.generation_defaults, {"temperature": .81})
        self.assertEqual(refreshed.huggingface_configuration.source_note, "Changed while reading")
        self.assertEqual(self.manager.store.get_profile(self.base.id), self.base)

    def test_card_refresh_rejects_source_change_or_deletion_during_read(self) -> None:
        from workbench_backend.inference.hf_configuration import read_bundle_model_card
        for deleted in (False, True):
            with self.subTest(deleted=deleted):
                self.manager.store.put_bundle(self.bundle)
                changed = self.bundle.model_copy(update={"source": self.bundle.source.model_copy(update={"resolved_revision": "b" * 40})})

                def read(bundle, hf):
                    result = read_bundle_model_card(bundle, hf)
                    if deleted:
                        self.manager.store.delete_bundle(bundle.id)
                    else:
                        self.manager.store.put_bundle(changed)
                    return result

                with patch("workbench_backend.inference.hf_configuration.read_bundle_model_card", side_effect=read), self.assertRaises(ManagerError) as raised:
                    self.manager.refresh_response_recipes(self.bundle.id)
                self.assertEqual((raised.exception.code, raised.exception.status_code), ("recipe_source_changed", 409))
                self.assertEqual(self.manager.store.get_bundle(self.bundle.id), None if deleted else changed)

    def test_selected_recipe_ids_and_default_survive_durable_retry(self) -> None:
        inspect = SimpleNamespace(repo_id=REPO, resolved_revision=REVISION,
            file_sizes={"model.gguf": 100, "README.md": len(CARD)},
            response_recipes=self.bundle.huggingface_configuration.response_recipes)
        selected = [item.id for item in self.bundle.huggingface_configuration.response_recipes]
        with patch.object(self.manager.bundles.hf, "inspect", return_value=inspect), patch.object(
            self.manager.imports, "_launch", side_effect=lambda job, _request: job):
            job = self.manager.imports.start_huggingface(HuggingFaceImportRequest(
                repo_id=REPO, revision="main", allow_patterns=["model.gguf"],
                recipe_ids=selected, default_recipe_id=selected[0]))
        durable = RecordStore(self.paths).get_job(job.id)
        self.assertEqual(durable.recipe_ids, selected)
        self.assertEqual(durable.default_recipe_id, selected[0])
        self.assertEqual(durable.resolved_revision, REVISION)
        self.assertIn("README.md", durable.allow_patterns)
        failed = durable.model_copy(update={"status": ImportStatus.failed})
        self.manager.store.put_job(failed)
        captured = []
        def retry(request, *, retry_of=None):
            captured.append((request, retry_of))
            return failed
        restarted = ImportJobRunner(self.paths, RecordStore(self.paths), self.manager.bundles)
        with patch.object(restarted, "start_huggingface", side_effect=retry):
            restarted.retry_job(job.id)
        self.assertEqual(captured[0][0].recipe_ids, selected)
        self.assertEqual(captured[0][0].default_recipe_id, selected[0])
        self.assertEqual(captured[0][0].revision, REVISION)
        self.assertEqual(captured[0][1], job.id)

    def test_installed_weights_complete_when_recipe_creation_needs_attention(self) -> None:
        plain = _weight(Path(self.tmp.name) / "plain.gguf", template="{{ messages }}")
        bundle = self.bundle.model_copy(update={"primary_path": str(plain), "files": [
            self.bundle.files[0].model_copy(update={"name": "plain.gguf", "path": str(plain),
                "sha256": sha256_file(plain), "size_bytes": plain.stat().st_size}), self.bundle.files[1]]})
        self.manager.store.put_bundle(bundle)
        selected = [item["id"] for item in self.recipes]
        job = ImportJob(id="import_recipes", kind=BundleSourceKind.huggingface,
            status=ImportStatus.running, created_at=utc_now(), updated_at=utc_now(),
            repo_id=REPO, resolved_revision=REVISION, recipe_ids=selected,
            default_recipe_id=selected[0],
            staging_path=str(self.paths.state / "staging" / "recipe-fixture"))
        self.manager.store.put_job(job)

        def fake_launch(args, **_kwargs):
            request = json.loads(Path(args[-1]).read_text(encoding="utf-8"))
            Path(request["output"]).write_text(json.dumps({"repo_id": REPO,
                "requested_revision": REVISION, "resolved_revision": REVISION,
                "local_dir": str(Path(self.tmp.name)), "expected_sizes": {},
                "expected_sha256": {}}), encoding="utf-8")
            return SimpleNamespace(pid=os.getpid(), returncode=0, poll=lambda: 0)

        with patch("workbench_backend.inference.import_jobs.subprocess.Popen", side_effect=fake_launch), patch.object(
            self.manager.bundles, "record_huggingface_download", return_value=bundle):
            complete = self.manager.imports._run_huggingface_subprocess(job,
                HuggingFaceImportRequest(repo_id=REPO, revision=REVISION,
                    allow_patterns=["plain.gguf", "README.md"], recipe_ids=selected,
                    default_recipe_id=selected[0]))
        self.assertEqual(complete.status, ImportStatus.complete)
        self.assertEqual(complete.bundle_id, bundle.id)
        self.assertIsNone(complete.error)
        self.assertIn("thinking", complete.configuration_error or "")
        self.assertEqual(self.manager.store.get_bundle(bundle.id).default_configuration_id, self.base.id)
        self.assertEqual([item.id for item in self.manager.list_model_configurations(bundle.id)], [self.base.id])

    def test_unexpected_recipe_save_error_does_not_fail_installed_weights(self) -> None:
        selected = [item["id"] for item in self.recipes]
        job = ImportJob(id="import_recipe_fault", kind=BundleSourceKind.huggingface,
            status=ImportStatus.running, created_at=utc_now(), updated_at=utc_now(),
            repo_id=REPO, resolved_revision=REVISION, recipe_ids=selected,
            default_recipe_id=selected[0],
            staging_path=str(self.paths.state / "staging" / "recipe-fault"))
        self.manager.store.put_job(job)

        def fake_launch(args, **_kwargs):
            request = json.loads(Path(args[-1]).read_text(encoding="utf-8"))
            Path(request["output"]).write_text(json.dumps({"repo_id": REPO,
                "requested_revision": REVISION, "resolved_revision": REVISION,
                "local_dir": str(Path(self.tmp.name)), "expected_sizes": {},
                "expected_sha256": {}}), encoding="utf-8")
            return SimpleNamespace(pid=os.getpid(), returncode=0, poll=lambda: 0)

        with patch("workbench_backend.inference.import_jobs.subprocess.Popen", side_effect=fake_launch), patch.object(
            self.manager.bundles, "record_huggingface_download", return_value=self.bundle), patch(
            "workbench_backend.inference.recipe_configurations.create_recipe_configurations",
            side_effect=RuntimeError("injected configuration failure")), patch(
            "workbench_backend.inference.import_jobs.logging.getLogger"):
            complete = self.manager.imports._run_huggingface_subprocess(job,
                HuggingFaceImportRequest(repo_id=REPO, revision=REVISION,
                    allow_patterns=["model.gguf", "README.md"], recipe_ids=selected,
                    default_recipe_id=selected[0]))
        self.assertEqual(complete.status, ImportStatus.complete)
        self.assertEqual(complete.bundle_id, self.bundle.id)
        self.assertIsNone(complete.error)
        self.assertIn("response configurations could not be saved", complete.configuration_error or "")
        self.assertIsNotNone(self.manager.store.get_bundle(self.bundle.id))

    def test_restart_finishes_selected_recipes_for_installed_bundle(self) -> None:
        selected = [item["id"] for item in self.recipes]
        job = ImportJob(id="import_recover", kind=BundleSourceKind.huggingface,
            status=ImportStatus.running, created_at=utc_now(), updated_at=utc_now(),
            worker_id="previous-process", bundle_id=self.bundle.id,
            repo_id=REPO, resolved_revision=REVISION, recipe_ids=selected,
            default_recipe_id=selected[0])
        self.manager.store.put_job(job)
        with patch.object(self.manager.imports, "_terminate_transfer"):
            recovered = self.manager.imports.reconcile_on_startup()
        self.assertEqual(recovered[0].status, ImportStatus.complete)
        self.assertIsNone(recovered[0].configuration_error)
        created = self.manager.list_model_configurations(self.bundle.id)
        self.assertEqual(len(created), 4)
        default = self.manager.store.get_bundle(self.bundle.id).default_configuration_id
        self.assertEqual(self.manager.store.get_profile(default).recipe_origin.recipe_id, selected[0])


if __name__ == "__main__":
    unittest.main()
