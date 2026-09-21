"""Tiered backend unittest runner.

The default tier is the fast product-behaviour suite. Process-heavy
Windows/runtime checks stay available as an explicit integration tier so CI can
run them when their inputs changed without slowing every backend job.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unittest
from collections.abc import Iterable


INTEGRATION_TEST_IDS = {
    "tests.test_runtime.RuntimePinTests.test_pin_while_running_is_rejected_without_half_pin",
    "tests.test_runtime.RuntimePinTests.test_pin_while_running_stop_first_then_pins",
    "tests.test_event_stream.InteractionStreamTests.test_live_loopback_stream_resume_does_not_duplicate_snapshot_values",
}
# Cross-service harness/replay flows, subprocesses and actual HTTP servers.
# Default keeps Models/Chat regressions and pure permission/integrity rules.
INTEGRATION_PREFIXES = (
    "tests.test_desktop_lifecycle.",
    "tests.test_deployments.",
    "tests.test_adapter.",
    "tests.test_process_ownership.ProcessOwnershipTests.",
    "tests.test_process_logs.ManagedStartLogTests.",
    "tests.test_host_shell.HostShellHarnessTests.",
    "tests.test_effective_setup.EffectiveSetupLiveAdapterTests.",
    "tests.test_effective_setup.AdapterResolvedBagTests.",
    "tests.test_memory_skills.MemorySkillsHarnessTests.",
    "tests.test_harness.HarnessApiTests.",
    "tests.test_lab.LabApiTests.",
    "tests.test_recorded_tools.RecordedToolHarnessTests.",
    "tests.test_recorded_tools.RecordedToolLabTests.",
    "tests.test_retrieval.RetrievalHarnessTests.",
    "tests.test_knowledge.KnowledgeLabHarnessTests.",
)


def iter_cases(suite: unittest.TestSuite) -> Iterable[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_cases(item)
        else:
            yield item


def tier_for(test_id: str) -> str:
    if test_id in INTEGRATION_TEST_IDS or test_id.startswith(INTEGRATION_PREFIXES):
        return "integration"
    return "default"


def load_suite(tier: str) -> unittest.TestSuite:
    discovered = discover_all()
    selected = unittest.TestSuite()
    for case in iter_cases(discovered):
        case_tier = tier_for(case.id())
        if tier == "all" or case_tier == tier:
            selected.addTest(case)
    if selected.countTestCases() == 0:
        raise RuntimeError(f"{tier} tier is empty")
    return selected


def discover_all() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    discovered = loader.discover("tests", pattern="test_*.py", top_level_dir=".")
    if loader.errors:
        raise RuntimeError("\n".join(loader.errors))
    ids = {case.id() for case in iter_cases(discovered)}
    missing = sorted(INTEGRATION_TEST_IDS - ids)
    missing.extend(prefix for prefix in INTEGRATION_PREFIXES if not any(key.startswith(prefix) for key in ids))
    if missing:
        raise RuntimeError("integration tier references missing tests: " + ", ".join(missing))
    return discovered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run backend unittest tiers.")
    parser.add_argument(
        "--tier",
        choices=("default", "integration", "all"),
        default="default",
        help="Suite tier to run.",
    )
    parser.add_argument("-v", "--verbosity", type=int, default=1)
    parser.add_argument("--durations", type=int, default=None)
    args = parser.parse_args(argv)

    from tests import _close_test_session

    try:
        suite = load_suite(args.tier)
        print(f"backend test tier: {args.tier} ({suite.countTestCases()} tests)", flush=True)
        result = unittest.TextTestRunner(verbosity=args.verbosity, durations=args.durations).run(suite)
        return 0 if result.wasSuccessful() else 1
    finally:
        # Make cleanup failures fail the command, rather than only log at exit.
        _close_test_session()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
