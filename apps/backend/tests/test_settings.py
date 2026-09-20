"""MOD-003 settings-bag fidelity."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import ProfileWriteRequest, RunProfile, SettingsBag, SettingsBags
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.settings import (
    DEFAULT_GPU_PROFILE,
    PER_REQUEST_KEYS,
    RETIRED_STARTUP_KEYS,
    STARTUP_ENUMS,
    STARTUP_KEYS,
    resolve_bags,
    resolve_declared_startup,
    startup_cli_args,
)
from workbench_backend.paths import WorkbenchPaths


class SettingsBagTests(unittest.TestCase):
    def test_three_bags_stay_separate(self) -> None:
        bags = resolve_bags(
            startup={"ctx_size": 4096, "weird_startup": 1},
            per_request={"temperature": 0.1, "weird_request": 2},
            agent={"tools_enabled": True, "weird_agent": 3},
        )
        self.assertEqual(bags.startup.applied["ctx_size"], 4096)
        self.assertEqual(bags.per_request.applied["temperature"], 0.1)
        self.assertTrue(bags.agent.applied["tools_enabled"])
        self.assertIn("weird_startup", bags.startup.unsupported)
        self.assertIn("weird_request", bags.per_request.unsupported)
        self.assertIn("weird_agent", bags.agent.unsupported)
        self.assertNotIn("temperature", bags.startup.applied)
        self.assertNotIn("ctx_size", bags.per_request.applied)
        self.assertNotIn("tools_enabled", bags.startup.applied)
        self.assertTrue(bags.startup.unverified)
        self.assertTrue(bags.per_request.unverified)

    def test_override_is_recorded(self) -> None:
        bags = resolve_bags(
            startup={"port": 8080},
            startup_overrides={"port": 8099},
        )
        self.assertEqual(bags.startup.applied["port"], 8099)
        self.assertEqual(bags.startup.overridden[0].key, "port")
        self.assertEqual(bags.startup.overridden[0].requested, 8080)

    def test_profile_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ModelManager(WorkbenchPaths(Path(tmp)))
            profile = manager.create_profile(
                ProfileWriteRequest(
                    display_name="uat",
                    startup={"n_gpu_layers": 0, "not_a_flag": True},
                    per_request={"top_p": 0.9},
                    agent={"max_iterations": 3},
                )
            )
            self.assertIn("not_a_flag", profile.bags.startup.unsupported)
            self.assertEqual(profile.bags.per_request.applied["top_p"], 0.9)
            loaded = manager.get_profile(profile.id)
            self.assertEqual(loaded.bags.agent.applied["max_iterations"], 3)

    def test_default_gpu_profile_does_not_override_model_context(self) -> None:
        bags = resolve_bags(startup={})
        self.assertNotIn("ctx_size", bags.startup.applied)
        self.assertEqual(bags.startup.applied["n_gpu_layers"], -1)
        self.assertEqual(bags.startup.applied["flash_attn"], "on")
        self.assertNotIn("ctx_size", DEFAULT_GPU_PROFILE)
        self.assertEqual(DEFAULT_GPU_PROFILE["n_gpu_layers"], -1)
        self.assertIn(DEFAULT_GPU_PROFILE["flash_attn"], {"on", "off", "auto"})

    def test_flash_attn_cli_is_valued_enum_never_bare(self) -> None:
        cases = (
            (True, "on"),
            (False, "off"),
            ("on", "on"),
            ("off", "off"),
            ("auto", "auto"),
            ("ON", "on"),
        )
        for requested, expected in cases:
            with self.subTest(requested=requested):
                bags = resolve_bags(startup={"flash_attn": requested})
                self.assertEqual(bags.startup.applied["flash_attn"], expected)
                args = startup_cli_args(bags.startup.applied)
                self.assertIn("--flash-attn", args)
                index = args.index("--flash-attn")
                self.assertLess(index + 1, len(args))
                self.assertEqual(args[index + 1], expected)
                self.assertNotEqual(args[index + 1], "--flash-attn")
        bare = startup_cli_args({"flash_attn": True})
        self.assertEqual(bare, ["--flash-attn", "on"])
        self.assertNotEqual(bare, ["--flash-attn"])

    def test_valued_startup_enums_audit(self) -> None:
        self.assertEqual(
            set(STARTUP_ENUMS),
            {
                "flash_attn",
                "fit",
                "cache_type_k",
                "cache_type_v",
                "load_mode",
                "embedding",
                "pooling",
                "reasoning",
                "reasoning_format",
                "reasoning_effort",
                "spec_draft_cache_type_k",
                "spec_draft_cache_type_v",
            },
        )
        self.assertEqual(STARTUP_ENUMS["flash_attn"], frozenset({"on", "off", "auto"}))
        self.assertEqual(STARTUP_ENUMS["embedding"], frozenset({"on", "off"}))
        self.assertEqual(STARTUP_ENUMS["pooling"], frozenset({"mean", "cls", "last"}))
        self.assertEqual(
            STARTUP_ENUMS["reasoning_format"],
            frozenset({"auto", "none", "deepseek", "deepseek-legacy"}),
        )
        self.assertEqual(
            STARTUP_ENUMS["reasoning_effort"],
            frozenset({"default", "minimal", "low", "medium", "high", "xhigh", "max"}),
        )
        self.assertEqual(
            STARTUP_ENUMS["load_mode"],
            frozenset({"auto", "none", "mmap", "mlock", "mmap+mlock", "dio"}),
        )
        for key in STARTUP_KEYS:
            if key in STARTUP_ENUMS:
                continue
            if key == "reasoning_preserve":
                self.assertEqual(startup_cli_args({key: True}), ["--reasoning-preserve"])
                self.assertEqual(startup_cli_args({key: False}), ["--no-reasoning-preserve"])
                continue
            args = startup_cli_args({key: "sample"})
            self.assertEqual(args, [STARTUP_KEYS[key], "sample"])
        invalid = resolve_bags(startup={"flash_attn": "maybe"})
        self.assertIn("flash_attn", invalid.startup.unsupported)
        self.assertEqual(invalid.startup.applied["flash_attn"], "on")

    def test_b11045_startup_flags_are_normalized_and_serialized(self) -> None:
        bags = resolve_bags(
            startup={
                "ctx_size": "8192",
                "threads_batch": "12",
                "cache_type_k": "Q8_0",
                "cache_type_v": "f16",
                "fit": "off",
                "reasoning": "auto",
                "reasoning_format": "deepseek-legacy",
                "reasoning_effort": "xhigh",
                "reasoning_budget": "-1",
                "reasoning_preserve": True,
                "chat_template_file": "template.jinja",
                "chat_template_kwargs": '{"enable_thinking":true}',
                "spec_type": "draft-mtp",
                "spec_draft_model": "draft.gguf",
                "spec_draft_n_max": "4",
                "spec_draft_p_min": "0.1",
                "spec_draft_threads_batch": "6",
                "spec_draft_ngl": "all",
                "spec_draft_cache_type_k": "q8_0",
                "spec_draft_cache_type_v": "q8_0",
            }
        )

        self.assertEqual(bags.startup.applied["ctx_size"], 8192)
        self.assertEqual(bags.startup.applied["threads_batch"], 12)
        self.assertEqual(bags.startup.applied["cache_type_k"], "q8_0")
        self.assertEqual(bags.startup.applied["reasoning_budget"], -1)
        self.assertTrue(bags.startup.applied["reasoning_preserve"])
        self.assertEqual(bags.startup.applied["spec_draft_p_min"], 0.1)
        self.assertEqual(bags.startup.applied["spec_draft_ngl"], "all")

        args = startup_cli_args(bags.startup.applied)
        self.assertEqual(args[args.index("--ctx-size") + 1], "8192")
        self.assertEqual(args[args.index("--threads-batch") + 1], "12")
        self.assertEqual(args[args.index("--cache-type-k") + 1], "q8_0")
        self.assertEqual(args[args.index("--fit") + 1], "off")
        self.assertEqual(args[args.index("--reasoning") + 1], "auto")
        self.assertEqual(args[args.index("--reasoning-format") + 1], "deepseek-legacy")
        self.assertEqual(args[args.index("--reasoning-effort") + 1], "xhigh")
        self.assertEqual(args[args.index("--reasoning-budget") + 1], "-1")
        self.assertIn("--reasoning-preserve", args)
        self.assertEqual(args[args.index("--chat-template-file") + 1], "template.jinja")
        self.assertEqual(args[args.index("--spec-type") + 1], "draft-mtp")
        self.assertEqual(args[args.index("--spec-draft-model") + 1], "draft.gguf")
        self.assertEqual(args[args.index("--spec-draft-n-max") + 1], "4")
        self.assertEqual(args[args.index("--spec-draft-p-min") + 1], "0.1")
        self.assertEqual(args[args.index("--spec-draft-ngl") + 1], "all")
        self.assertEqual(args[args.index("--spec-draft-type-k") + 1], "q8_0")

        for effort in ("default", "minimal", "low", "medium", "high", "xhigh", "max"):
            with self.subTest(reasoning_effort=effort):
                resolved = resolve_bags(startup={"reasoning_effort": effort})
                self.assertEqual(resolved.startup.applied["reasoning_effort"], effort)

    def test_invalid_supported_startup_values_are_not_emitted(self) -> None:
        for startup in ({"fit": "auto"}, {"port": 65536}, {"port": 0}):
            invalid = resolve_bags(startup=startup)
            self.assertEqual(invalid.startup.unsupported, list(startup))
        bags = resolve_bags(
            startup={
                "ctx_size": -1,
                "threads_batch": "many",
                "cache_type_k": "int4",
                "fit": "maybe",
                "reasoning": "perhaps",
                "reasoning_format": "qwen3",
                "reasoning_effort": "none",
                "reasoning_preserve": "sometimes",
                "spec_draft_p_min": "low",
                "spec_draft_ngl": -2,
                "chat_template_kwargs": "[]",
                "spec_type": "draft-guess",
            }
        )
        for key in (
            "ctx_size",
            "threads_batch",
            "cache_type_k",
            "fit",
            "reasoning",
            "reasoning_format",
            "reasoning_effort",
            "reasoning_preserve",
            "spec_draft_p_min",
            "spec_draft_ngl",
            "chat_template_kwargs",
            "spec_type",
        ):
            self.assertIn(key, bags.startup.unsupported)
            self.assertNotIn(key, bags.startup.applied)
        args = startup_cli_args(bags.startup.applied)
        self.assertNotIn("--ctx-size", args)
        self.assertNotIn("--threads-batch", args)
        self.assertNotIn("--cache-type-k", args)
        self.assertNotIn("--fit", args)
        self.assertNotIn("--reasoning", args)
        self.assertNotIn("--reasoning-preserve", args)

    def test_load_mode_is_valued_enum_matching_b11045(self) -> None:
        for mode in ("auto", "none", "mmap", "mlock", "mmap+mlock", "dio"):
            with self.subTest(mode=mode):
                bags = resolve_bags(startup={"load_mode": mode.upper()})
                self.assertEqual(bags.startup.applied["load_mode"], mode)
                args = startup_cli_args(bags.startup.applied)
                self.assertEqual(args[args.index("--load-mode") + 1], mode)
        self.assertNotIn("load_mode", resolve_bags(startup={}).startup.applied)
        invalid = resolve_bags(startup={"load_mode": "bogus"})
        self.assertIn("load_mode", invalid.startup.unsupported)
        self.assertNotIn("load_mode", invalid.startup.applied)
        self.assertNotIn("--load-mode", startup_cli_args(invalid.startup.applied))
        self.assertNotIn("--load-mode", startup_cli_args({"load_mode": True}))

    def test_retired_mlock_and_no_mmap_are_reported_never_emitted(self) -> None:
        self.assertEqual(set(RETIRED_STARTUP_KEYS), {"mlock", "no_mmap"})
        for key in RETIRED_STARTUP_KEYS:
            self.assertNotIn(key, STARTUP_KEYS)
        bags = resolve_bags(startup={"mlock": True, "no_mmap": True, "load_mode": "mlock"})
        self.assertIn("mlock", bags.startup.unsupported)
        self.assertIn("no_mmap", bags.startup.unsupported)
        self.assertNotIn("mlock", bags.startup.applied)
        self.assertNotIn("no_mmap", bags.startup.applied)
        notes = {note.key: note for note in bags.startup.retired}
        self.assertEqual(set(notes), {"mlock", "no_mmap"})
        self.assertTrue(notes["mlock"].requested)
        self.assertIsNone(notes["mlock"].applied)
        self.assertIn("load_mode", notes["mlock"].reason)
        self.assertIn("load_mode", notes["no_mmap"].reason)
        args = startup_cli_args(bags.startup.applied)
        self.assertNotIn("--mlock", args)
        self.assertNotIn("--no-mmap", args)
        self.assertEqual(args[args.index("--load-mode") + 1], "mlock")
        self.assertEqual(resolve_bags(startup={"ctx_size": 8}).startup.retired, [])

    def test_get_profile_reresolves_retired_startup_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ModelManager(WorkbenchPaths(Path(tmp)))
            now = utc_now()
            stale = RunProfile(
                id="profile_stale_mlock",
                display_name="pre-correction",
                bags=SettingsBags(
                    startup=SettingsBag(
                        requested={"mlock": True, "ctx_size": 4096},
                        applied={"mlock": True, "ctx_size": 4096},
                        unsupported=[],
                        retired=[],
                    )
                ),
                created_at=now,
                updated_at=now,
            )
            manager.store.put_profile(stale)
            loaded = manager.get_profile(stale.id)
            self.assertIn("mlock", loaded.bags.startup.unsupported)
            self.assertEqual([note.key for note in loaded.bags.startup.retired], ["mlock"])
            self.assertIn("load_mode", loaded.bags.startup.retired[0].reason)
            self.assertNotIn("mlock", loaded.bags.startup.applied)
            listed = manager.list_profiles()
            self.assertEqual(listed[0].bags.startup.unsupported, loaded.bags.startup.unsupported)

    def test_embedding_on_emits_bare_flag_and_pooling_is_valued(self) -> None:
        bags = resolve_bags(startup={"embedding": "on", "pooling": "mean"})
        self.assertEqual(bags.startup.applied["embedding"], "on")
        self.assertEqual(bags.startup.applied["pooling"], "mean")
        args = startup_cli_args(bags.startup.applied)
        self.assertIn("--embedding", args)
        self.assertNotEqual(args[args.index("--embedding") + 1], "on")
        self.assertEqual(args[args.index("--embedding") + 1], "--pooling")
        self.assertEqual(args[args.index("--pooling") + 1], "mean")
        off = startup_cli_args({"embedding": "off", "pooling": "cls"})
        self.assertNotIn("--embedding", off)
        self.assertEqual(off[off.index("--pooling") + 1], "cls")
        invalid = resolve_bags(startup={"embedding": "maybe", "pooling": "none"})
        self.assertIn("embedding", invalid.startup.unsupported)
        self.assertIn("pooling", invalid.startup.unsupported)
        self.assertNotIn("embedding", invalid.startup.applied)
        self.assertNotIn("pooling", invalid.startup.applied)

    def test_declared_startup_skips_managed_process_defaults(self) -> None:
        bag = resolve_declared_startup({"embedding": True, "pooling": "last"})
        self.assertEqual(bag.applied["embedding"], "on")
        self.assertEqual(bag.applied["pooling"], "last")
        self.assertNotIn("ctx_size", bag.applied)
        self.assertNotIn("n_gpu_layers", bag.applied)
        self.assertNotIn("host", bag.applied)
        self.assertNotIn("port", bag.applied)

    def test_stream_is_not_a_per_request_key(self) -> None:
        self.assertNotIn("stream", PER_REQUEST_KEYS)
        self.assertIn("stream", resolve_bags(per_request={"stream": True}).per_request.unsupported)


if __name__ == "__main__":
    unittest.main()
