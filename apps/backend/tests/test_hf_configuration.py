"""Pinned publisher configuration must survive import and reach managed inference."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import json

from support import write_tiny_gguf
from workbench_backend.inference.adapter import _extra_body
from workbench_backend.inference.deployments import _verified_loaded_template, managed_argv
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.hf_configuration import _generation_defaults, configuration_from_download
from workbench_backend.inference.hf_fetch import HuggingFaceDownload, HuggingFaceFetcher, HubSource, describe_repository
from workbench_backend.inference.schemas import (BundleFile, BundleSource, BundleSourceKind, Deployment,
    DeploymentStatus, FileRole, GgufRuntimeMetadata, ManagementScope, ModelBundle, ServerProperties)
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.agents.effective_setup import _resolve_per_request
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.schemas import HuggingFaceConfiguration
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.errors import ManagerError


def _info(sha: str, *names: str, base_model: str | None = None):
    return SimpleNamespace(sha=sha, siblings=[SimpleNamespace(rfilename=name, size=100) for name in names],
        card_data={"base_model": base_model} if base_model else None)


class HuggingFaceConfigurationTests(TestCase):
    def test_download_keeps_publisher_files_under_pinned_namespace(self):
        listing = describe_repository("converter/demo", _info("a" * 40, "model.gguf", ".src_sha"))
        listing.source = HubSource(repo_id="publisher/demo", resolved_revision="b" * 40,
            verified=True, guidance_files=["chat_template.jinja", "generation_config.json"])
        source_info = _info("b" * 40, "chat_template.jinja", "generation_config.json")
        with TemporaryDirectory() as tmp, patch.object(HuggingFaceFetcher, "inspect", return_value=listing), patch(
            "workbench_backend.inference.hf_fetch.HfApi") as api, patch(
            "workbench_backend.inference.hf_fetch.snapshot_download") as snapshot:
            api.return_value.model_info.return_value = source_info
            result = HuggingFaceFetcher().download(repo_id="converter/demo", revision="main",
                dest=Path(tmp), allow_patterns=["model.gguf", ".src_sha"])
        self.assertEqual(snapshot.call_count, 2)
        self.assertEqual(snapshot.call_args.kwargs["revision"], "b" * 40)
        self.assertEqual(result.source_repo_id, "publisher/demo")
        self.assertIn(".workbench-publisher/chat_template.jinja", result.expected_sizes)

    def test_reserved_publisher_namespace_blocks_repository_collision(self):
        listing = describe_repository("converter/demo", _info("a" * 40, "model.gguf",
            ".workbench-publisher/generation_config.json"))
        with TemporaryDirectory() as tmp, patch.object(HuggingFaceFetcher, "inspect", return_value=listing), patch(
            "workbench_backend.inference.hf_fetch.snapshot_download") as snapshot:
            with self.assertRaisesRegex(ManagerError, "reserved configuration path"):
                HuggingFaceFetcher().download(repo_id="converter/demo", revision="main",
                    dest=Path(tmp), allow_patterns=["model.gguf"])
            snapshot.assert_not_called()

    def test_verified_source_requires_declared_base_model_and_primary_commit(self):
        gguf = describe_repository("ggml-org/demo-GGUF", _info("a" * 40, "q4.gguf", ".src_sha"))
        conversion = _info("a" * 40, "q4.gguf", ".src_sha", base_model="publisher/demo")
        source = _info("b" * 40, "chat_template.jinja", "generation_config.json")
        with TemporaryDirectory() as tmp:
            marker = Path(tmp) / ".src_sha"
            marker.write_text("PRIMARY=" + "b" * 40, encoding="utf-8")
            with patch("workbench_backend.inference.hf_fetch.hf_hub_download", return_value=str(marker)), patch(
                "workbench_backend.inference.hf_fetch.HfApi") as api:
                api.return_value.model_info.return_value = source
                verified = HuggingFaceFetcher()._verified_source(gguf, conversion)
                self.assertTrue(verified and verified.verified)
                self.assertEqual(verified.resolved_revision, "b" * 40)
                marker.write_text("PRIMARY=" + "c" * 40, encoding="utf-8")
                mismatched = HuggingFaceFetcher()._verified_source(gguf, conversion)
                self.assertFalse(mismatched and mismatched.verified)
                marker.write_text("PRIMARY=" + "b" * 40, encoding="utf-8")
                api.return_value.model_info.side_effect = OSError("publisher unavailable")
                inaccessible = HuggingFaceFetcher()._verified_source(gguf, conversion)
                self.assertFalse(inaccessible and inaccessible.verified)
        self.assertIsNone(HuggingFaceFetcher()._verified_source(gguf, _info("a" * 40, "q4.gguf")))
        ambiguous = _info("a" * 40, "q4.gguf", ".src_sha")
        ambiguous.card_data = {"base_model": ["publisher/demo", "another/demo"]}
        self.assertIsNone(HuggingFaceFetcher()._verified_source(gguf, ambiguous))

    def test_source_only_candidates_require_exact_declared_base_model(self):
        entries = [SimpleNamespace(modelId="converter/right", card_data={"base_model": "publisher/demo"}, downloads=1, likes=0),
            SimpleNamespace(modelId="converter/derivative", card_data={"base_model": "other/demo"}, downloads=2, likes=0)]
        with patch("workbench_backend.inference.hf_fetch.HfApi") as api:
            api.return_value.list_models.return_value = entries
            candidates = HuggingFaceFetcher()._gguf_candidates("publisher/demo")
        self.assertEqual([item.repo_id for item in candidates], ["converter/right"])

    def test_generation_settings_and_unsupported_values_are_distinct(self):
        defaults, unsupported = _generation_defaults({"do_sample": True, "temperature": 1.0,
            "top_k": 20, "top_p": 0.95, "eos_token_id": [1, 2], "mystery": 5})
        self.assertEqual(defaults, {"temperature": 1.0, "top_k": 20, "top_p": 0.95})
        self.assertIn("eos_token_id", unsupported)
        self.assertIn("mystery", unsupported)
        self.assertEqual(_generation_defaults({"do_sample": False, "top_k": 64})[0], {"temperature": 0.0})
        bounded, _ = _generation_defaults({"max_new_tokens": 128, "stop_strings": ["<|done|>"]})
        self.assertEqual(bounded["max_tokens"], 128)
        self.assertEqual(bounded["stop"], ["<|done|>"])

    def test_publisher_file_hash_mismatch_blocks_install(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / ".workbench-publisher" / "generation_config.json"
            file.parent.mkdir()
            file.write_text('{"top_k":20}', encoding="utf-8")
            manager = ModelManager(WorkbenchPaths(root / "app"))
            with self.assertRaisesRegex(ManagerError, "hash did not match"):
                manager.bundles._verify_expected_hashes([file], root,
                    {".workbench-publisher/generation_config.json": "0" * 64})

    def test_bundle_template_conflict_defaults_to_gguf_and_request_defaults_reach_adapter(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            weights = write_tiny_gguf(root / "model.gguf")
            source = root / ".workbench-publisher"
            source.mkdir()
            (source / "chat_template.jinja").write_text("publisher {{ messages }}", encoding="utf-8")
            (source / "generation_config.json").write_text(json.dumps({"do_sample": True,
                "temperature": 1.0, "top_k": 64, "top_p": 0.95, "suppress_tokens": [17]}), encoding="utf-8")
            (source / "tokenizer.json").write_text("{}", encoding="utf-8")
            files = [BundleFile(role=FileRole.primary_weights if path == weights else FileRole.companion,
                name=path.relative_to(root).as_posix(), path=str(path), sha256=sha256_file(path),
                size_bytes=path.stat().st_size) for path in [weights, *source.iterdir()]]
            bundle = ModelBundle(id="bundle", display_name="Demo", source=BundleSource(kind=BundleSourceKind.huggingface,
                repo_id="converter/demo", resolved_revision="a" * 40), files=files,
                primary_path=str(weights), created_at="2026-09-24T00:00:00Z")
            download = HuggingFaceDownload(repo_id="converter/demo", requested_revision="main",
                resolved_revision="a" * 40, local_dir=root, source_repo_id="publisher/demo",
                source_revision="b" * 40)
            with patch("workbench_backend.inference.hf_configuration.read_gguf_runtime_metadata",
                return_value=GgufRuntimeMetadata(chat_template="embedded {{ messages }}")), patch(
                "workbench_backend.inference.hf_configuration._token_ids_match", return_value=True):
                config = configuration_from_download(bundle, download)
            self.assertEqual(config.template_origin, "gguf")
            self.assertTrue(config.template_differs)
            self.assertEqual(config.generation_defaults["top_k"], 64)
            self.assertEqual(config.generation_defaults["logit_bias"], [[17, False]])
            deployment = Deployment(id="deployment", display_name="demo", scope=ManagementScope.managed,
                status=DeploymentStatus.stopped, bundle_id=bundle.id, publisher_request_defaults=config.generation_defaults,
                created_at="2026-09-24T00:00:00Z", updated_at="2026-09-24T00:00:00Z")
            inherited = _resolve_per_request(None, deployment, None)
            self.assertEqual(inherited.applied["top_k"], 64)
            self.assertEqual(_extra_body(inherited)["logit_bias"], [[17, False]])
            overridden = _resolve_per_request(None, deployment, {"top_k": 5})
            self.assertEqual(overridden.applied["top_k"], 5)
            self.assertEqual(overridden.applied["top_p"], 0.95)
            self.assertEqual(resolve_bags(per_request_defaults=config.generation_defaults).per_request.applied["top_k"], 64)
            chosen = bundle.model_copy(update={"huggingface_configuration": config.model_copy(update={
                "template_origin": "publisher", "template_file": str(source / "chat_template.jinja")})})
            argv = managed_argv("llama-server", chosen, {})
            self.assertEqual(argv[argv.index("--chat-template-file") + 1], str(source / "chat_template.jinja"))
            props = ServerProperties(fetched="2026-09-24T00:00:00Z", source_url="http://127.0.0.1/props",
                chat_template="publisher {{ messages }}")
            self.assertEqual(_verified_loaded_template(chosen, {}, props), "publisher")
            with self.assertRaisesRegex(ManagerError, "did not report"):
                _verified_loaded_template(chosen, {}, props.model_copy(update={"chat_template": "embedded {{ messages }}"}))
            with self.assertRaisesRegex(ManagerError, "did not report"):
                _verified_loaded_template(chosen, {}, None)
            (source / "chat_template.jinja").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(Exception, "missing or changed"):
                managed_argv("llama-server", chosen, {})

    def test_publisher_template_choice_persists_only_after_runtime_probe(self):
        with TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp))
            manager = ModelManager(paths)
            weight = write_tiny_gguf(paths.models / "model.gguf")
            publisher = paths.models / ".workbench-publisher" / "chat_template.jinja"
            publisher.parent.mkdir(parents=True)
            publisher.write_text("{{ messages }}", encoding="utf-8")
            bundle = ModelBundle(id="bundle", display_name="Demo", source=BundleSource(
                kind=BundleSourceKind.huggingface, repo_id="converter/demo", resolved_revision="a" * 40),
                files=[BundleFile(role=FileRole.primary_weights if path == weight else FileRole.companion,
                    name=path.relative_to(paths.models).as_posix(), path=str(path), sha256=sha256_file(path),
                    size_bytes=path.stat().st_size) for path in (weight, publisher)],
                primary_path=str(weight), created_at="2026-09-24T00:00:00Z",
                huggingface_configuration=HuggingFaceConfiguration(source_repo_id="publisher/demo",
                    source_revision="b" * 40, source_verified=True, template_origin="gguf",
                    template_differs=True, generation_defaults={"top_k": 20},
                    unsupported={"chat_template.jinja": "Conflicting template was not selected."}))
            manager.store.put_bundle(bundle)
            with patch.object(manager, "_probe_chat_template", side_effect=ManagerError(
                "Template failed runtime check", code="template_incompatible", status_code=409)):
                with self.assertRaisesRegex(ManagerError, "Template failed runtime check"):
                    manager.select_bundle_chat_template(bundle.id, "publisher")
            self.assertEqual(manager.store.get_bundle(bundle.id).huggingface_configuration.template_origin, "gguf")
            with patch.object(manager, "_probe_chat_template") as probe:
                manager.select_bundle_chat_template(bundle.id, "publisher")
                probe.assert_called_once_with(bundle, publisher)
            reopened = ModelManager(paths).store.get_bundle(bundle.id)
            self.assertEqual(reopened.huggingface_configuration.template_origin, "publisher")
            self.assertEqual(reopened.huggingface_configuration.template_file, str(publisher))
            self.assertEqual(reopened.huggingface_configuration.generation_defaults["top_k"], 20)
            self.assertNotIn("chat_template.jinja", reopened.huggingface_configuration.unsupported)
