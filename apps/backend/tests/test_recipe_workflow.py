"""Pinned card choices survive imports and become independent model configurations."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from gguf import GGUFWriter

from workbench_backend.errors import ManagerError
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.hf_recipes import parse_model_card_recipes
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.import_jobs import ImportJobRunner
from workbench_backend.inference.schemas import (
    BundleFile, BundleSource, BundleSourceKind, Deployment, DeploymentStatus,
    FileRole, HuggingFaceConfiguration, HuggingFaceImportRequest, ImportJob,
    ImportStatus, ManagementScope,
    ModelBundle, RunProfile,
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

    def test_create_all_recipes_with_default_is_idempotent_and_copies_launch_settings(self) -> None:
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
        self.assertTrue(all(item.bags.startup.requested == self.base.bags.startup.requested
            and item.bags.per_request.requested["max_tokens"] == 128 for item in first.configurations))
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
        self.assertEqual(restarted.store.get_profile(first.configurations[0].id).bags.startup.requested["ctx_size"], 8192)
        self.assertEqual(restarted.store.get_profile(first.configurations[0].id).bags.per_request.requested["max_tokens"], 128)

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
