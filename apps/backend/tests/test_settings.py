"""MOD-003 settings-bag fidelity."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workbench_backend.inference.schemas import ProfileWriteRequest
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.settings import resolve_bags
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


if __name__ == "__main__":
    unittest.main()
