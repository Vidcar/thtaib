"""Repository discovery is metadata only; selected downloads remain upstream-owned."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from unittest import TestCase
from tempfile import TemporaryDirectory
from urllib.parse import quote

from workbench_backend.errors import ManagerError
from workbench_backend.inference.hf_fetch import HuggingFaceFetcher, describe_repository, repository_id
from workbench_backend.inference.schemas import ResponseRecipe


def info(*names):
    return SimpleNamespace(sha="a" * 40, siblings=[SimpleNamespace(rfilename=n, size=10) for n in names])


class HubSelectionTests(unittest.TestCase):
    def test_link_and_repository(self):
        self.assertEqual(repository_id("https://huggingface.co/org/model/tree/main"), "org/model")
        self.assertEqual(repository_id(" org/model "), "org/model")
        for value in ("https://evil.example/org/model", "file:///model", "org", "org/model/more"):
            with self.assertRaises(ManagerError):
                repository_id(value)

    def test_groups_shards_and_projectors_without_claiming_compatibility(self):
        result = describe_repository("org/model", info("Q4/model-00001-of-00002.gguf", "Q4/model-00002-of-00002.gguf", "Q8/model-00001-of-00002.gguf", "mmproj-a.gguf", "mmproj-b.gguf", "README.md", "config.json", "weights.safetensors"))
        self.assertEqual(len(result.variants), 2)
        self.assertTrue(result.variants[0].complete)
        self.assertEqual(result.variants[0].size_bytes, 20)
        self.assertFalse(result.variants[1].complete)
        self.assertEqual(len(result.projectors), 2)
        self.assertEqual(result.guidance_files, ["README.md", "config.json"])

    def test_mtp_and_imatrix_files_are_auxiliary_and_not_primary_weights(self):
        listing = describe_repository("org/model", info(
            "Q4/model-Q4_K_M-00001-of-00002.gguf", "Q4/model-Q4_K_M-00002-of-00002.gguf",
            "MTP/mtp-model-Q4_0.gguf", "imatrix_unsloth.gguf", "BF16/model-BF16.gguf",
        ))
        self.assertEqual(len(listing.variants), 2)
        sharded = next(variant for variant in listing.variants if variant.name.startswith("Q4/"))
        self.assertEqual(sharded.size_bytes, 20)
        self.assertTrue(sharded.complete)
        self.assertEqual([variant.name for variant in listing.auxiliary_ggufs], ["MTP/mtp-model-Q4_0.gguf", "imatrix_unsloth.gguf"])
        with tempfile.TemporaryDirectory() as tmp, patch.object(HuggingFaceFetcher, "inspect", return_value=listing), patch("workbench_backend.inference.hf_fetch.snapshot_download") as download:
            for patterns in (["MTP/mtp-model-Q4_0.gguf"], ["imatrix_unsloth.gguf"], ["Q4/*.gguf", "MTP/*.gguf"]):
                with self.assertRaisesRegex(ManagerError, "auxiliary"):
                    HuggingFaceFetcher().download(repo_id="org/model", revision="main", dest=Path(tmp), allow_patterns=patterns)
            download.assert_not_called()

    def test_missing_immutable_revision_is_rejected(self):
        with self.assertRaises(ManagerError):
            describe_repository("org/model", SimpleNamespace(sha="main", siblings=[]))

    def test_unsafe_paths_rejected(self):
        for name in ("../model.gguf", "/model.gguf", "C:/model.gguf", "dir\\model.gguf"):
            with self.assertRaises(ManagerError):
                describe_repository("org/model", info(name))

    def test_ambiguous_or_incomplete_selection_never_downloads_weights(self):
        listing = describe_repository("org/model", info("q4.gguf", "q8.gguf", "mmproj-a.gguf", "mmproj-b.gguf"))
        with tempfile.TemporaryDirectory() as tmp, patch.object(HuggingFaceFetcher, "inspect", return_value=listing), patch("workbench_backend.inference.hf_fetch.snapshot_download") as download:
            for patterns in (None, ["*.gguf"], ["q4.gguf", "mmproj*.gguf"], []):
                with self.assertRaises(ManagerError):
                    HuggingFaceFetcher().download(repo_id="org/model", revision="main", dest=Path(tmp), allow_patterns=patterns)
            download.assert_not_called()
        listing = describe_repository("org/model", info("q4-00001-of-00002.gguf", "q4-00002-of-00002.gguf"))
        with tempfile.TemporaryDirectory() as tmp, patch.object(HuggingFaceFetcher, "inspect", return_value=listing), patch("workbench_backend.inference.hf_fetch.snapshot_download") as download:
            with self.assertRaises(ManagerError):
                HuggingFaceFetcher().download(repo_id="org/model", revision="main", dest=Path(tmp), allow_patterns=["q4-00001-of-00002.gguf"])
            download.assert_not_called()

    def test_selected_files_download_at_resolved_revision(self):
        listing = describe_repository("org/model", info("q4.gguf", "q8.gguf", "README.md"))
        with tempfile.TemporaryDirectory() as tmp, patch.object(HuggingFaceFetcher, "inspect", return_value=listing), patch("workbench_backend.inference.hf_fetch.snapshot_download") as download:
            result = HuggingFaceFetcher().download(repo_id="org/model", revision="main", dest=Path(tmp), allow_patterns=["q4.gguf", "README.md"])
        self.assertEqual(download.call_args.kwargs["revision"], "a" * 40)
        self.assertEqual(download.call_args.kwargs["allow_patterns"], ["README.md", "q4.gguf"])
        self.assertEqual(result.resolved_revision, "a" * 40)
        self.assertEqual(result.local_dir, Path(tmp) / ("a" * 40))

    def test_case_insensitive_selected_path_collision_never_downloads(self):
        listing = describe_repository("org/model", info("q4.gguf", "Q4.GGUF"))
        with tempfile.TemporaryDirectory() as tmp, patch.object(HuggingFaceFetcher, "inspect", return_value=listing), patch("workbench_backend.inference.hf_fetch.snapshot_download") as download:
            with self.assertRaises(ManagerError):
                HuggingFaceFetcher().download(repo_id="org/model", revision="main", dest=Path(tmp), allow_patterns=None)
            download.assert_not_called()

    def test_metadata_access_failure_is_actionable(self):
        from huggingface_hub.errors import GatedRepoError
        import httpx
        with patch("workbench_backend.inference.hf_fetch.HfApi") as api:
            api.return_value.model_info.side_effect = GatedRepoError("denied", response=httpx.Response(403, request=httpx.Request("GET", "https://huggingface.co/org/model")))
            with self.assertRaisesRegex(ManagerError, "gated"):
                HuggingFaceFetcher().inspect(repo_id="org/model")

    def test_search_returns_simple_repository_results(self):
        with patch("workbench_backend.inference.hf_fetch.HfApi") as api:
            api.return_value.list_models.return_value = [
                SimpleNamespace(modelId="org/a", downloads=10, likes=2),
                SimpleNamespace(id="org/b", downloads=None, likes=0),
            ]

            results = HuggingFaceFetcher().search("tiny llama", limit=2)

        self.assertEqual([item.repo_id for item in results], ["org/a", "org/b"])
        self.assertEqual(results[0].downloads, 10)
        api.return_value.list_models.assert_called_once()

    def test_empty_search_is_rejected_before_network(self):
        with patch("workbench_backend.inference.hf_fetch.HfApi") as api:
            with self.assertRaises(ManagerError):
                HuggingFaceFetcher().search("   ")
            api.assert_not_called()


REPO = "DavidAU/Qwen3.8-27B-TURBO-Fable-Cold-Fusion-735-882-Heretic-Uncensored-NEO-CODER-MAX-MTP-GGUF"
REVISION = "c02caef111a8acf987947f35e1e288aa5450e184"
STANDARD = "Qwen3.8-27B-TurboFCFusion-735-882-Here-Uncen-NEO-CODER-MAX-IQ4_XS.gguf"
LOW = "Qwen3.8-27B-TurboFCFusion-735-882-Here-Uncen-NEO-CODER-MAX-LOW-MTP-IQ4_XS.gguf"
CARD = """# Demo
<B>Qwen Model Settings (suggested):</B>
- Thinking mode for general tasks: temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, repetition_penalty=1.0
- Thinking mode for precise coding: temperature=0.6, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, repetition_penalty=1.0
- Instruct (or non-thinking) mode: temperature=0.7, top_p=0.80, top_k=20, min_p=0.0, presence_penalty=1.5, repetition_penalty=1.0
"""


def _info():
    return SimpleNamespace(sha=REVISION, card_data=None,
        siblings=[SimpleNamespace(rfilename=name, size=100, lfs=None)
            for name in (STANDARD, LOW, "README.md")])


class HuggingFaceSelectionTests(TestCase):
    def test_low_mtp_file_link_retains_exact_pinned_variant_hint(self):
        url = f"https://huggingface.co/{REPO}?show_file_info={quote(LOW)}"
        with patch("workbench_backend.inference.hf_fetch.HfApi") as api:
            api.return_value.model_info.return_value = _info()
            listing = HuggingFaceFetcher().inspect(repo_id=url)
        self.assertEqual(listing.repo_id, REPO)
        self.assertEqual(listing.resolved_revision, REVISION)
        self.assertEqual(listing.file_hint, LOW)
        self.assertTrue(any(LOW in variant.files and variant.complete for variant in listing.variants))
        self.assertFalse(any("Linked file" in warning for warning in listing.warnings))

    def test_unavailable_linked_file_is_visible_and_not_silently_substituted(self):
        unavailable = "model-LOW-MTP-IQ4_XS.gguf"
        url = f"https://huggingface.co/{REPO}?show_file_info={unavailable}"
        with patch("workbench_backend.inference.hf_fetch.HfApi") as api:
            api.return_value.model_info.return_value = _info()
            listing = HuggingFaceFetcher().inspect(repo_id=url)
        self.assertEqual(listing.file_hint, unavailable)
        self.assertTrue(any(unavailable in warning and "not an available" in warning
            for warning in listing.warnings))

    def test_unsafe_file_hint_is_rejected_before_remote_lookup(self):
        url = f"https://huggingface.co/{REPO}?show_file_info=..%2F..%2Fsecret.gguf"
        with patch("workbench_backend.inference.hf_fetch.HfApi") as api:
            with self.assertRaises(ManagerError) as raised:
                HuggingFaceFetcher().inspect(repo_id=url)
            api.assert_not_called()
        self.assertEqual(raised.exception.code, "hf_file_hint")

    def test_inspect_returns_typed_recipes_from_pinned_readme(self):
        scratch = Path(__file__).resolve().parents[3] / ".scratch"
        scratch.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=scratch) as tmp:
            card = Path(tmp) / "README.md"
            card.write_text(CARD, encoding="utf-8")
            with patch("workbench_backend.inference.hf_fetch.HfApi") as api, patch(
                "workbench_backend.inference.hf_fetch.hf_hub_download", return_value=str(card)) as fetch:
                api.return_value.model_info.return_value = _info()
                listing = HuggingFaceFetcher().inspect(repo_id=REPO, include_recipes=True)
        fetch.assert_called_once_with(repo_id=REPO, filename="README.md", revision=REVISION)
        self.assertEqual([item.name for item in listing.response_recipes],
            ["General thinking", "Precise coding", "Non-thinking"])
        self.assertTrue(all(isinstance(item, ResponseRecipe) for item in listing.response_recipes))
        self.assertEqual(listing.response_recipes[2].per_request["presence_penalty"], 1.5)
        self.assertEqual(listing.response_recipes[2].reasoning, "off")
        self.assertTrue(all(item.source_revision == REVISION for item in listing.response_recipes))
