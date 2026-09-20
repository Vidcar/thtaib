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

    def test_default_gpu_profile_uses_large_ctx_and_full_offload(self) -> None:
        bags = resolve_bags(startup={})
        self.assertGreaterEqual(bags.startup.applied["ctx_size"], 65536)
        self.assertEqual(bags.startup.applied["n_gpu_layers"], -1)
        self.assertEqual(bags.startup.applied["flash_attn"], "on")
        self.assertEqual(DEFAULT_GPU_PROFILE["ctx_size"], 65536)
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
        self.assertEqual(set(STARTUP_ENUMS), {"flash_attn", "load_mode", "embedding", "pooling"})
        self.assertEqual(STARTUP_ENUMS["flash_attn"], frozenset({"on", "off", "auto"}))
        self.assertEqual(STARTUP_ENUMS["embedding"], frozenset({"on", "off"}))
        self.assertEqual(STARTUP_ENUMS["pooling"], frozenset({"mean", "cls", "last"}))
        self.assertEqual(
            STARTUP_ENUMS["load_mode"],
            frozenset({"auto", "none", "mmap", "mlock", "mmap+mlock", "dio"}),
        )
        for key in STARTUP_KEYS:
            if key in STARTUP_ENUMS:
                continue
            args = startup_cli_args({key: "sample"})
            self.assertEqual(args, [STARTUP_KEYS[key], "sample"])
        invalid = resolve_bags(startup={"flash_attn": "maybe"})
        self.assertIn("flash_attn", invalid.startup.unsupported)
        self.assertEqual(invalid.startup.applied["flash_attn"], "on")

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
