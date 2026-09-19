"""MOD-003 settings-bag fidelity."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workbench_backend.inference.schemas import ProfileWriteRequest
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.settings import (
    DEFAULT_GPU_PROFILE,
    STARTUP_ENUMS,
    STARTUP_FLAG_KEYS,
    STARTUP_KEYS,
    resolve_bags,
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
        self.assertEqual(bare[bare.index("--flash-attn") + 1], "on")
        self.assertNotIn(["--flash-attn"], [bare[i : i + 1] for i in range(len(bare))])

    def test_valued_startup_enums_audit(self) -> None:
        self.assertEqual(set(STARTUP_ENUMS), {"flash_attn"})
        self.assertEqual(STARTUP_ENUMS["flash_attn"], frozenset({"on", "off", "auto"}))
        self.assertEqual(STARTUP_FLAG_KEYS, frozenset({"mlock", "no_mmap"}))
        for key in STARTUP_KEYS:
            if key in STARTUP_ENUMS:
                continue
            if key in STARTUP_FLAG_KEYS:
                args = startup_cli_args({key: True})
                self.assertEqual(args, [STARTUP_KEYS[key]])
                continue
            args = startup_cli_args({key: "sample"})
            self.assertEqual(args, [STARTUP_KEYS[key], "sample"])
        invalid = resolve_bags(startup={"flash_attn": "maybe"})
        self.assertIn("flash_attn", invalid.startup.unsupported)
        self.assertEqual(invalid.startup.applied["flash_attn"], "on")
        args = startup_cli_args({"mlock": True, "no_mmap": True, "flash_attn": "on"})
        self.assertEqual(args.count("--flash-attn"), 1)
        self.assertEqual(args[args.index("--flash-attn") + 1], "on")
        self.assertIn("--mlock", args)
        self.assertIn("--no-mmap", args)


if __name__ == "__main__":
    unittest.main()
