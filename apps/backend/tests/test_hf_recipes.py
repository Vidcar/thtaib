"""Model-card recommendations are selectable guidance, not request defaults."""

import hashlib
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from support import write_tiny_gguf
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.hf_configuration import (_generation_defaults,
    configuration_from_download, response_recipes_from_bundle_card)
from workbench_backend.inference.hf_fetch import HuggingFaceDownload
from workbench_backend.inference.hf_recipes import parse_model_card_recipes
from workbench_backend.inference.schemas import BundleFile, BundleSource, BundleSourceKind, FileRole, ModelBundle


REPO = "DavidAU/Qwen3.8-27B-TURBO-Fable-Cold-Fusion-735-882-Heretic-Uncensored-NEO-CODER-MAX-MTP-GGUF"
REVISION = "c02caef111a8acf987947f35e1e288aa5450e184"
CARD = """# Model card
<B>Qwen Model Settings (suggested):</B>

- Thinking mode for general tasks: temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, repetition_penalty=1.0
- Thinking mode for precise coding tasks (e.g. WebDev): temperature=0.6, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, repetition_penalty=1.0
- Instruct (or non-thinking) mode: temperature=0.7, top_p=0.80, top_k=20, min_p=0.0, presence_penalty=1.5, repetition_penalty=1.0
- Context window min from 8k to 16k.

<B>Other details</B>
> We recommend using the following sets of sampling parameters for generation:
> - Thinking Mode: `temperature=1.0`, `top_p=0.95`, `top_k=20`, `min_p=0.0`, `presence_penalty=0.0`, `repetition_penalty=1.0`
"""


def _parse(card: str):
    return parse_model_card_recipes(card, repo_id=REPO, revision=REVISION,
        sha256=hashlib.sha256(card.encode("utf-8")).hexdigest())


class ModelCardRecipeTests(TestCase):
    def test_explicit_section_yields_three_distinct_recipes_not_copied_guidance(self):
        recipes = _parse(CARD)
        self.assertEqual([recipe["name"] for recipe in recipes],
            ["General thinking", "Precise coding", "Non-thinking"])
        self.assertEqual([recipe["reasoning"] for recipe in recipes], ["on", "on", "off"])
        self.assertEqual([recipe["per_request"]["temperature"] for recipe in recipes], [1, 0.6, 0.7])
        self.assertEqual([recipe["per_request"]["presence_penalty"] for recipe in recipes], [0, 0, 1.5])
        self.assertTrue(all(recipe["per_request"]["min_p"] == 0 for recipe in recipes))
        self.assertTrue(all(recipe["per_request"]["repeat_penalty"] == 1 for recipe in recipes))
        self.assertTrue(all(recipe["source_repo_id"] == REPO and recipe["source_revision"] == REVISION
            and recipe["section"] == "Qwen Model Settings (suggested)" for recipe in recipes))
        self.assertTrue(all(REVISION[:12] in recipe["id"] and recipe["card_sha256"][:12] in recipe["id"]
            for recipe in recipes))

    def test_duplicate_matches_dedupe_and_conflicting_label_is_not_selectable(self):
        original = CARD.split("\n\n<B>Other details", 1)[0]
        duplicate = original + "\n- Thinking mode for general tasks: temperature=1.0, top_p=0.95\n"
        # The second line is a conflicting partial recipe, so the general
        # candidate is rejected while other distinct candidates remain.
        self.assertEqual([item["name"] for item in _parse(duplicate)], ["Precise coding", "Non-thinking"])
        exact = original + "\n" + original.splitlines()[3] + "\n"
        self.assertEqual(len(_parse(exact)), 3)
        second_section = original + "\n\n## Recommended sampling settings\n" + original.splitlines()[3] + "\n"
        self.assertEqual(len(_parse(second_section)), 3)
        conflict = second_section + "- Thinking mode for precise coding tasks: temperature=0.3, top_p=0.95\n"
        self.assertEqual([item["name"] for item in _parse(conflict)], ["General thinking", "Non-thinking"])
        unsupported = original + "\n- Thinking mode for general tasks: temperature=1.0, top_p=0.95, unsupported_sampler=4\n"
        self.assertEqual([item["name"] for item in _parse(unsupported)], ["Precise coding", "Non-thinking"])

    def test_invalid_and_ambiguous_values_are_not_offered(self):
        bad = """## Recommended sampling settings
- Thinking mode: temperature=nan, top_p=0.9
- Instruct mode: temperature=0.7, top_p=0.8, presence_penalty=9
- Thinking mode for general tasks: temperature=1.0, top_p=0.95, top_p=0.8
- Thinking mode for precise coding: temperature=0.6, top_p=0.95, unsupported_sampler=4
"""
        self.assertEqual(_parse(bad), [])
        self.assertEqual(_parse("- Thinking mode: temperature=1, top_p=.95"), [])

    def test_best_practices_numbered_sampling_section_yields_only_its_recipes(self):
        card = """## Best Practices

To achieve optimal performance, we recommend the following settings:

1. **Sampling Parameters**: We suggest using the following sets of sampling parameters:

    - Thinking Mode: `temperature=1.0`, `top_p=0.95`, `top_k=20`, `min_p=0.0`, `presence_penalty=0.0`, `repetition_penalty=1.0`
    - Instruct (or non-thinking) mode: `temperature=0.7`, `top_p=0.80`, `top_k=20`, `min_p=0.0`, `presence_penalty=1.5`, `repetition_penalty=1.0`

2. **Adequate Output Length**: Use enough space for a complete answer.
    - Thinking Mode: temperature=0.2, top_p=0.5
"""
        recipes = _parse(card)
        self.assertEqual([item["name"] for item in recipes], ["Thinking", "Non-thinking"])
        self.assertEqual([item["section"] for item in recipes], ["Sampling Parameters"] * 2)
        self.assertEqual([item["per_request"]["temperature"] for item in recipes], [1.0, 0.7])
        self.assertEqual([item["per_request"]["presence_penalty"] for item in recipes], [0.0, 1.5])
        self.assertEqual(_parse(card.replace("We suggest", "Examples of")), [])
        self.assertEqual(_parse(card.replace("## Best Practices", "## Other details")), [])

    def test_json_sampling_validation_accepts_zero_and_penalties(self):
        defaults, unsupported = _generation_defaults({"temperature": 0, "top_k": 0,
            "min_p": 0, "presence_penalty": 1.5, "frequency_penalty": -0.5,
            "repetition_penalty": 1.0})
        self.assertEqual(defaults, {"temperature": 0, "top_k": 0, "min_p": 0,
            "presence_penalty": 1.5, "frequency_penalty": -0.5, "repeat_penalty": 1.0})
        self.assertEqual(unsupported, {})
        invalid, notes = _generation_defaults({"top_k": True, "top_p": 0,
            "min_p": math.nan, "presence_penalty": 2.5, "frequency_penalty": math.inf})
        self.assertEqual(invalid, {})
        self.assertEqual(set(notes), {"top_k", "top_p", "min_p", "presence_penalty", "frequency_penalty"})
        self.assertIn("top_k", _generation_defaults({"top_k": 10 ** 1000})[1])
        greedy, _ = _generation_defaults({"do_sample": False, "top_k": 20,
            "presence_penalty": 1.5, "repetition_penalty": 1.1})
        self.assertEqual(greedy, {"temperature": 0.0, "presence_penalty": 1.5,
            "repeat_penalty": 1.1})

    def test_installed_card_hash_is_verified_and_never_becomes_generation_defaults(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            weight = write_tiny_gguf(root / "model.gguf")
            card = root / "README.md"
            card.write_text(CARD, encoding="utf-8")
            files = [BundleFile(role=FileRole.primary_weights if item == weight else FileRole.companion,
                name=item.name, path=str(item), sha256=sha256_file(item), size_bytes=item.stat().st_size)
                for item in (weight, card)]
            bundle = ModelBundle(id="bundle", display_name="Demo", source=BundleSource(
                kind=BundleSourceKind.huggingface, repo_id=REPO, resolved_revision=REVISION),
                files=files, primary_path=str(weight), created_at="2026-09-24T00:00:00Z")
            download = HuggingFaceDownload(repo_id=REPO, requested_revision="main",
                resolved_revision=REVISION, local_dir=root)
            self.assertEqual(len(response_recipes_from_bundle_card(bundle)[0]), 3)
            with patch("workbench_backend.inference.hf_configuration.read_gguf_runtime_metadata", return_value=None):
                config = configuration_from_download(bundle, download)
                self.assertEqual(len(config.response_recipes), 3)
                self.assertEqual(config.generation_defaults, {})
                card.write_text(CARD + "tampered", encoding="utf-8")
                changed = configuration_from_download(bundle, download)
                self.assertEqual(changed.response_recipes, [])
                self.assertIn("hash", changed.unsupported["README.md"])
                self.assertEqual(response_recipes_from_bundle_card(bundle)[0], [])
