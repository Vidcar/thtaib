"""The verification wrapper must fail visibly when its real child checks fail."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


_SPEC = importlib.util.spec_from_file_location("thtaib_verify", Path(__file__).resolve().parents[3] / "scripts/verify.py")
assert _SPEC is not None and _SPEC.loader is not None
verify = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = verify
_SPEC.loader.exec_module(verify)


class VerificationSelectionTests(unittest.TestCase):
    def checks(self, *argv: str) -> dict:
        return {item.name: item for item in verify.select_checks(verify.arguments(list(argv)))}

    def test_default_and_shared_acceptance_include_both_consumers(self) -> None:
        required = {"backend-default", "backend-integration", "desktop-build", "desktop-ui", "shared-contracts"}
        self.assertEqual(set(self.checks()), {"working-diff", "staged-diff", *required})
        self.assertTrue(required <= self.checks("--scope", "shared").keys())
        self.assertEqual(self.checks("--scope", "shared")["shared-contracts"].cwd, verify.ROOT / "apps/backend")

    def test_default_plan_does_not_require_external_executables(self) -> None:
        result = subprocess.run(
            [sys.executable, str(verify.ROOT / "scripts/verify.py"), "--plan"],
            capture_output=True, text=True, env={**os.environ, "PATH": ""}, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("scopes: backend, desktop, docs, shared, workflow", result.stdout)
        planned = {line.strip().split(": ", 1)[0] for line in result.stdout.splitlines()
                   if line.startswith("  ") and not line.startswith("    ")}
        self.assertEqual(planned, {"working-diff", "staged-diff", "backend-default",
                                   "backend-integration", "desktop-build", "desktop-ui", "shared-contracts"})
        self.assertIn("nothing executed", result.stdout)

    def test_removed_scope_is_rejected_even_alongside_all(self) -> None:
        for argv in (["--scope", "spec"], ["--scope", "all", "--scope", "spec"]):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as raised:
                    verify.arguments(argv)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("invalid choice", error.getvalue())

    def test_workflow_and_trivial_docs_do_not_require_product_builds(self) -> None:
        self.assertEqual(set(self.checks("--scope", "docs")), {"working-diff", "staged-diff"})
        self.assertEqual(set(self.checks("--scope", "workflow")), {"working-diff", "staged-diff", "verification-regressions"})

    def test_explicit_scopes_are_additive_and_fast_allows_focused_feedback(self) -> None:
        checks = self.checks("--tier", "fast", "--scope", "backend", "--scope", "workflow", "--test", "tests.test_verify_delivery")
        self.assertEqual(set(checks), {"working-diff", "staged-diff", "backend-focused", "verification-regressions"})
        self.assertEqual(checks["backend-focused"].command[-1], "tests.test_verify_delivery")
        desktop = self.checks("--tier", "fast", "--scope", "desktop", "--desktop-check", "scripts/check-model-settings.mjs")
        self.assertEqual(set(desktop), {"working-diff", "staged-diff", "desktop-typecheck", "desktop-check-model-settings"})

    def test_focus_cannot_silently_narrow_acceptance_or_escape_selected_scope(self) -> None:
        cases = [
            ["--test", "tests.test_verify_delivery"],
            ["--tier", "delivery", "--desktop-check", "scripts/check-model-settings.mjs"],
            ["--tier", "fast", "--scope", "docs", "--test", "tests.test_verify_delivery"],
            ["--tier", "fast", "--test", "test_verify_delivery"],
            ["--tier", "fast", "--desktop-check", "../outside.mjs"],
            ["--real-model"],
        ]
        for argv in cases:
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    verify.arguments(argv)
                self.assertNotEqual(raised.exception.code, 0)

    def test_delivery_smoke_requires_assets_and_is_only_explicit(self) -> None:
        self.assertNotIn("real-model-smoke", self.checks("--tier", "delivery"))
        smoke = self.checks("--tier", "delivery", "--real-model")["real-model-smoke"]
        self.assertEqual(smoke.env, {"WORKBENCH_REAL_MODEL_SMOKE": "required"})
        self.assertEqual(smoke.command[-1], "tests_integration.test_real_model_smoke")
        self.assertEqual(smoke.minimum_tests, 4)
        ui = self.checks("--scope", "desktop")["desktop-ui"]
        self.assertEqual(len(ui.required_cases), 5)
        self.assertNotIn("desktop-electron", self.checks("--scope", "desktop"))
        native = self.checks("--tier", "delivery", "--scope", "desktop")["desktop-electron"]
        self.assertEqual(len(native.required_cases), 1)

    def test_plan_has_no_execution_or_evidence(self) -> None:
        with redirect_stdout(io.StringIO()) as output, patch.object(
            verify, "run_checks", side_effect=AssertionError("plan mode must not execute checks or write evidence")
        ) as execute:
            self.assertEqual(verify.main(["--scope", "docs", "--plan"]), 0)
        execute.assert_not_called()
        self.assertIn("nothing executed", output.getvalue())


class VerificationExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        # tests.__init__ keeps every fixture under the repository's .scratch/.
        self.tmp = tempfile.TemporaryDirectory(prefix="verify-fixture-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init", "-q")
        (self.root / ".gitignore").write_text(".scratch/\n", encoding="utf-8")
        (self.root / "input.txt").write_text("original\n", encoding="utf-8")
        self.git("add", ".")
        self.git("-c", "user.name=Verification fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        self.args = verify.arguments(["--scope", "docs"])

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def run_check(self, body: str | None = None, *, command: tuple | None = None, cwd: Path | None = None,
                  required_cases: tuple[str, ...] = (), minimum_tests: int = 0) -> tuple[int, dict]:
        check = verify.Check("fixture", command or (sys.executable, "-c", body), cwd or self.root, "isolated regression fixture",
                             required_cases=required_cases, minimum_tests=minimum_tests)
        with redirect_stdout(io.StringIO()):
            code, path = verify.run_checks(self.root, [check], self.args)
        return code, json.loads(path.read_text(encoding="utf-8"))

    def test_real_child_success_records_exact_revision_command_and_boundaries(self) -> None:
        code, report = self.run_check("print('fixture passed')")
        self.assertEqual(code, 0)
        self.assertTrue(report["inputs_current"])
        self.assertEqual(report["before"]["head"], self.git("rev-parse", "HEAD").stdout.decode().strip())
        self.assertEqual(report["checks"][0]["command"], [sys.executable, "-c", "print('fixture passed')"])
        self.assertEqual(report["checks"][0]["cwd"], str(self.root))
        self.assertIn("not certified", report["independent_review"])
        self.assertIn("not validated", report["running_application"])
        self.assertIn("fixture passed", Path(report["checks"][0]["log"]).read_text())

    def test_false_green_text_cannot_hide_deliberate_failure(self) -> None:
        code, report = self.run_check("print('All checks passed'); raise SystemExit(7)")
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["checks"][0]["status"], "failed")
        self.assertEqual(report["checks"][0]["returncode"], 7)
        self.assertFalse(report["automatic_checks_passed"])

    def test_missing_command_and_working_directory_are_mandatory_failures(self) -> None:
        for kwargs in ({"command": ("thtaib-guaranteed-missing-verifier-7f2519",)},
                       {"body": "pass", "cwd": self.root / "missing"}):
            with self.subTest(kwargs=kwargs):
                code, report = self.run_check(**kwargs)
                self.assertEqual(code, 1)
                self.assertEqual(report["checks"][0]["status"], "unavailable")
                self.assertFalse(report["automatic_checks_passed"])

    def test_worktree_edit_during_passing_check_invalidates_result(self) -> None:
        code, report = self.run_check("from pathlib import Path; Path('input.txt').write_text('changed')")
        self.assertEqual(code, 1)
        self.assertEqual(report["checks"][0]["status"], "passed")
        self.assertTrue(report["automatic_checks_passed"])
        self.assertFalse(report["inputs_current"])

    def test_untracked_content_changes_are_detected_even_when_status_is_identical(self) -> None:
        target = self.root / "new.txt"
        target.write_text("first", encoding="utf-8")
        before = verify.snapshot(self.root)
        target.write_text("other", encoding="utf-8")
        after = verify.snapshot(self.root)
        self.assertEqual(before["status"], after["status"])
        self.assertNotEqual(before["fingerprint"], after["fingerprint"])
        self.assertNotEqual(before["files"]["new.txt"], after["files"]["new.txt"])

    def test_suite_declared_skip_is_recorded_without_claiming_it_ran(self) -> None:
        code, report = self.run_check("print('OK (skipped=1)')")
        self.assertEqual(code, 0)
        self.assertEqual(report["checks"][0]["suite_skip_observations"], ["OK (skipped=1)"])

    def test_required_rendered_case_cannot_pass_without_a_report(self) -> None:
        code, report = self.run_check("print('5 passed')", required_cases=("required journey",))
        self.assertEqual(code, 1)
        self.assertEqual(report["checks"][0]["status"], "incomplete")

    def test_required_rendered_result_proves_cases_executed(self) -> None:
        payload = {"suites": [{"specs": [{"title": "required journey", "tests": [
            {"expectedStatus": "passed", "results": [{"status": "passed"}]}]}]}]}
        body = ("import os; from pathlib import Path; "
                f"Path(os.environ['PLAYWRIGHT_JSON_OUTPUT_NAME']).write_text({json.dumps(payload)!r})")
        code, report = self.run_check(body, required_cases=("required journey",))
        self.assertEqual(code, 0)
        self.assertEqual(report["checks"][0]["executed_cases"], ["required journey"])

    def test_false_green_rendered_reports_fail_even_with_exit_zero(self) -> None:
        valid_case = {"expectedStatus": "passed", "results": [{"status": "passed"}]}
        payloads = [
            {"suites": [None]},
            {"suites": [{"specs": [None]}]},
            {"suites": []},
            {"suites": [{"specs": [{"title": "different journey", "tests": [valid_case]}]}]},
            {"suites": [{"specs": [{"title": "required journey", "tests": []}]}]},
            {"suites": [{"specs": [{"title": "required journey", "tests": [valid_case, valid_case]}]}]},
            {"suites": [{"specs": [{"title": "required journey", "tests": [
                {"expectedStatus": "skipped", "results": [{"status": "skipped"}]}]}]}]},
            {"suites": [{"specs": [{"title": "required journey", "tests": [
                {"expectedStatus": "passed", "results": []}]}]}]},
            {"suites": [{"specs": [{"title": "required journey", "tests": [
                {"expectedStatus": "passed", "results": [{"status": "failed"}, {"status": "passed"}]}]}]}]},
            {"errors": [{"message": "teardown failed"}], "suites": [{"specs": [
                {"title": "required journey", "tests": [valid_case]}]}]},
            {"suites": [{"specs": [
                {"title": "required journey", "tests": [valid_case]},
                {"title": "extra skipped journey", "tests": [{"expectedStatus": "skipped", "results": [{"status": "skipped"}]}]},
            ]}]},
            {"suites": [{"specs": [
                {"title": "required journey", "tests": [valid_case]},
                {"title": "extra unexecuted journey", "tests": []},
            ]}]},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                body = ("import os; from pathlib import Path; "
                        f"Path(os.environ['PLAYWRIGHT_JSON_OUTPUT_NAME']).write_text({json.dumps(payload)!r}); print('5 passed')")
                code, report = self.run_check(body, required_cases=("required journey",))
                self.assertEqual(code, 1)
                self.assertEqual(report["checks"][0]["status"], "incomplete")

    def test_required_real_model_cases_cannot_be_skipped_empty_or_under_count(self) -> None:
        for summary in ("OK", "Ran 0 tests in 0.1s\nOK", "Ran 1 test in 0.1s\nOK",
                        "Ran 4 tests in 0.1s\nOK (skipped=1)"):
            with self.subTest(summary=summary):
                code, report = self.run_check(f"print({summary!r})", minimum_tests=4)
                self.assertEqual(code, 1)
                self.assertEqual(report["checks"][0]["status"], "incomplete")
        code, report = self.run_check("print('Ran 4 tests in 0.1s\\nOK')", minimum_tests=4)
        self.assertEqual(code, 0)
        self.assertEqual(report["checks"][0]["executed_tests"], 4)

    def test_unversioned_directory_cannot_produce_acceptance(self) -> None:
        # The repository-root check must also reject accidental inheritance from a parent checkout.
        with tempfile.TemporaryDirectory(prefix="verify-no-git-") as location, redirect_stdout(io.StringIO()):
            code, _ = verify.run_checks(Path(location), [], self.args)
        self.assertEqual(code, 1)

    def test_redirected_scratch_cannot_write_evidence_before_rejection(self) -> None:
        outside = self.root / "outside-evidence"
        outside.mkdir()
        marker = outside / "preserved.txt"
        marker.write_text("preserved", encoding="utf-8")
        link = self.root / ".scratch"
        if os.name == "nt":
            subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
                           check=True, capture_output=True)
            self.addCleanup(link.rmdir)
        else:
            link.symlink_to(outside, target_is_directory=True)
            self.addCleanup(link.unlink)
        with self.assertRaisesRegex(OSError, "must not redirect"):
            verify.run_checks(self.root, [], self.args)
        self.assertEqual(list(outside.iterdir()), [marker])
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserved")
        with patch.object(verify, "ROOT", self.root), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(verify.main(["--scope", "docs"]), 1)


if __name__ == "__main__":
    unittest.main()
