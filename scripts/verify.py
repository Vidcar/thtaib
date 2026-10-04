#!/usr/bin/env python3
"""Run existing local checks and retain bounded, revision-specific evidence.

From the repository root: uv run --project apps/backend python scripts/verify.py --help
No command in this entry point commits, rewrites source, or refreshes a running app.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
SCOPES = ("docs", "workflow", "backend", "desktop", "shared")


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    cwd: Path
    reason: str
    env: dict[str, str] = field(default_factory=dict)
    required_cases: tuple[str, ...] = ()
    minimum_tests: int = 0


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run scoped existing checks. Defaults to acceptance for all areas.",
        epilog=("Scopes are explicit and additive, not inferred from filenames. Include consumers "
                "when changing shared behavior; shared includes backend and desktop. Automatic "
                "checks never certify independent review or the running application. Evidence is "
                "written to .scratch/verification/. Later input changes invalidate that evidence."),
    )
    parser.add_argument("--scope", action="append", choices=(*SCOPES, "all"),
                        help="Repeat for affected areas; defaults to all. docs runs whitespace checks only.")
    parser.add_argument("--tier", choices=("fast", "acceptance", "delivery"), default="acceptance",
                        help="fast: feedback; acceptance: area gates; delivery: gates plus requested runtime check.")
    parser.add_argument("--test", action="append", default=[], metavar="tests.MODULE[.CASE]",
                        help="Package-qualified backend test, repeatable; fast only, requires backend scope.")
    parser.add_argument("--desktop-check", action="append", default=[], metavar="scripts/check-NAME.mjs",
                        help="Existing desktop check, repeatable; fast only, requires desktop scope.")
    parser.add_argument("--real-model", action="store_true",
                        help="delivery only: require existing tiny-model assets and run isolated real-model smoke.")
    parser.add_argument("--plan", action="store_true", help="Show selected commands without running checks or writing evidence.")
    args = parser.parse_args(argv)
    args.scopes = set(SCOPES if not args.scope or "all" in args.scope else args.scope)
    if "shared" in args.scopes:
        args.scopes.update(("backend", "desktop"))
    if (args.test or args.desktop_check) and args.tier != "fast":
        parser.error("--test and --desktop-check are fast-only; they cannot narrow acceptance or delivery")
    if args.test and "backend" not in args.scopes:
        parser.error("--test requires --scope backend (or shared/all)")
    if any(not re.fullmatch(r"tests\.[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", name) for name in args.test):
        parser.error("--test must be package-qualified, starting with tests.")
    if args.desktop_check and "desktop" not in args.scopes:
        parser.error("--desktop-check requires --scope desktop (or shared/all)")
    if any(not re.fullmatch(r"scripts/check-[A-Za-z0-9_-]+\.mjs", name) for name in args.desktop_check):
        parser.error("--desktop-check must name an existing scripts/check-NAME.mjs in apps/desktop")
    if args.real_model and args.tier != "delivery":
        parser.error("--real-model requires --tier delivery")
    return args


def select_checks(args: argparse.Namespace, root: Path = ROOT) -> list[Check]:
    backend, desktop = root / "apps/backend", root / "apps/desktop"
    checks = [
        Check("working-diff", ("git", "diff", "--check"), root, "whitespace/conflict markers in unstaged changes"),
        Check("staged-diff", ("git", "diff", "--cached", "--check"), root, "whitespace/conflict markers in staged changes"),
    ]
    if "backend" in args.scopes:
        if args.test:
            checks.append(Check("backend-focused", ("uv", "run", "python", "-m", "unittest", *args.test),
                                backend, "explicit fast feedback; package import preserves test isolation"))
        else:
            checks.append(Check("backend-default", ("uv", "run", "python", "-m", "tests.run"), backend,
                                "backend scope: default behavior, permission and integrity regressions"))
        if args.tier != "fast":
            checks.append(Check("backend-integration", ("uv", "run", "python", "-m", "tests.run", "--tier", "integration", "--durations", "10"),
                                backend, "backend acceptance: existing process and cross-service integration tier"))
    # The default backend suite already discovers these tests.
    if "workflow" in args.scopes and ("backend" not in args.scopes or args.test):
        checks.append(Check("verification-regressions", ("uv", "run", "python", "-m", "unittest", "tests.test_verify_delivery"),
                            backend, "workflow scope: selection, real subprocess failures, prerequisites and stale evidence"))
    if "desktop" in args.scopes:
        if args.tier == "fast":
            checks.append(Check("desktop-typecheck", ("pnpm", "run", "typecheck"), desktop, "desktop fast feedback"))
            checks.extend(Check(f"desktop-{Path(name).stem}", ("node", name), desktop, "explicit focused desktop regression")
                          for name in dict.fromkeys(args.desktop_check))
        else:
            checks.append(Check("desktop-build", ("pnpm", "run", "build"), desktop,
                                "desktop acceptance: established typecheck, component regressions and build"))
            checks.append(Check("desktop-ui", ("pnpm", "run", "test:ui"), desktop,
                                "desktop acceptance: actual rendered UI and isolated backend safety journeys",
                                required_cases=(
                                    "restored history and unsent draft survive reopening",
                                    "accepted lost acknowledgement and reconnect execute once",
                                    "scoped approval and Stop govern actual owned effects",
                                    "model load reload and failure remain truthful",
                                    "retained output reopens after restart and source change",
                                    "Chat rejected and uncertain original submissions preserve drafts",
                                    "Agent run rejected and uncertain original submissions preserve drafts",
                                    "Chat accepted lost response and reconnect execute once without reload",
                                    "Agent run accepted lost response and reconnect execute once without reload",
                                    "Chat navigation preserves drafts and cancellation cleans owned work",
                                    "Agent run navigation preserves drafts and cancellation cleans owned work",
                                    "uncertain native effects pause continuation across observation",
                                )))
            if args.tier == "delivery":
                checks.append(Check("desktop-electron", ("pnpm", "run", "test:electron"), desktop,
                                    "desktop delivery: actual isolated built Electron application and native bridge",
                                    required_cases=("actual Windows desktop uses isolated authenticated backend and native bridge",
                                                    "actual Windows sending recovers both screens and cleans owned commands")))
    if "shared" in args.scopes:
        checks.append(Check("shared-contracts", ("uv", "run", "python", "../../scripts/generate_shared_contracts.py", "--check"),
                            backend, "shared scope: generated contract freshness, alongside both consumer suites"))
    if args.real_model:
        checks.append(Check("real-model-smoke", ("uv", "run", "python", "-m", "unittest", "tests_integration.test_real_model_smoke"),
                            backend, "explicit delivery request: isolated real runtime plumbing, not model capability or the open desktop",
                            {"WORKBENCH_REAL_MODEL_SMOKE": "required"}, minimum_tests=4))
        if "desktop" in args.scopes:
            checks.append(Check("desktop-real-model", ("pnpm", "run", "test:electron"), desktop,
                                "explicit delivery request: actual built Windows screens and existing local model sending/recovery",
                                {"WORKBENCH_NATIVE_REAL_MODEL": "required"},
                                required_cases=("actual Windows real model sending survives lost responses and writes one file",)))
    return checks


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).stdout


def snapshot(root: Path) -> dict:
    """Conservatively hash all versioned and nonignored untracked inputs, not generated output."""
    actual_root = Path(_git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip())
    if actual_root.resolve() != root.resolve():
        raise OSError(f"Expected checkout root {root}, found {actual_root}")
    head = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    index = _git(root, "ls-files", "--stage", "-z")
    paths = sorted(set(_git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0")) - {b""})
    files = {}
    for raw in paths:
        name = raw.decode("utf-8", errors="surrogateescape")
        if name == ".scratch" or name.startswith(".scratch/"):
            continue
        path = root / name
        if path.is_symlink():
            digest = "symlink:" + hashlib.sha256(os.readlink(path).encode("utf-8")).hexdigest()
        elif not path.exists():
            digest = "deleted"
        else:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files[name] = digest
    state = {"head": head, "status": status.decode("utf-8", errors="surrogateescape"),
             "index_sha256": hashlib.sha256(index).hexdigest(), "files": files}
    state["fingerprint"] = hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()
    return state


def execute_check(check: Check, output: Path) -> dict:
    log_path = output / f"{check.name}.log"
    result = {"name": check.name, "command": list(check.command), "cwd": str(check.cwd),
              "reason": check.reason, "environment_overrides": check.env, "log": str(log_path)}
    executable = shutil.which(check.command[0])
    started = time.monotonic()
    if executable is None or not check.cwd.is_dir():
        result.update(status="unavailable", returncode=None,
                      detail=f"Missing prerequisite: {check.command[0] if executable is None else check.cwd}")
        log_path.write_text(result["detail"] + "\n", encoding="utf-8")
    else:
        result["resolved_executable"] = executable
        report_path = output / f"{check.name}-cases.json"
        child_environment = {**os.environ, **check.env}
        if check.required_cases:
            child_environment["PLAYWRIGHT_JSON_OUTPUT_NAME"] = str(report_path)
        try:
            with log_path.open("wb") as log:
                completed = subprocess.run([executable, *check.command[1:]], cwd=check.cwd,
                                           env=child_environment, stdout=log, stderr=subprocess.STDOUT)
            result.update(status="passed" if completed.returncode == 0 else "failed", returncode=completed.returncode)
            if completed.returncode == 0 and check.required_cases:
                try:
                    cases = required_playwright_results(report_path, check.required_cases)
                    result.update(case_report=str(report_path), executed_cases=cases)
                except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                    result.update(status="incomplete", detail=f"Required rendered cases not established: {exc}")
        except OSError as exc:
            result.update(status="unavailable", returncode=None, detail=str(exc))
            with log_path.open("a", encoding="utf-8") as log:
                log.write(str(exc) + "\n")
        except KeyboardInterrupt:
            result.update(status="interrupted", returncode=None, detail="Interrupted; remaining checks were not run")
    result["seconds"] = round(time.monotonic() - started, 3)
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    result["suite_skip_observations"] = [line for line in lines if re.search(r"\bskipped\b|\bSKIP\b", line)]
    if result["status"] == "passed" and check.minimum_tests:
        counts = [int(match.group(1)) for line in lines
                  if (match := re.fullmatch(r"Ran (\d+) tests? in .+", line.strip()))]
        skipped = any(re.search(r"\bskipped=\d+", line) for line in lines)
        if not counts or counts[-1] < check.minimum_tests or skipped:
            result.update(status="incomplete", detail="Required real-model cases did not all execute without skips")
        else:
            result["executed_tests"] = counts[-1]
    return result


def required_playwright_results(report_path: Path, required: tuple[str, ...]) -> list[str]:
    """An exit-zero launcher is insufficient evidence that mandatory cases ran."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    observed: dict[str, list[dict]] = {}

    def visit(suites: list[dict]) -> None:
        for suite in suites:
            for spec in suite.get("specs", []):
                cases = spec.get("tests", [])
                if not cases:
                    raise ValueError(f"discovered case has no executed tests: {spec['title']}")
                observed.setdefault(spec["title"], []).extend(cases)
            visit(suite.get("suites", []))

    visit(report["suites"])
    if report.get("errors"):
        raise ValueError("suite reported setup or teardown errors")
    for name in required:
        cases = observed.get(name, [])
        if len(cases) != 1 or cases[0].get("expectedStatus") != "passed":
            raise ValueError(f"required case missing, duplicated or disabled: {name}")
        results = cases[0].get("results", [])
        if len(results) != 1 or results[0].get("status") != "passed":
            raise ValueError(f"required case did not pass once without skips/retries: {name}")
    # Additional discovered cases must also execute successfully. Honest required
    # counts cannot conceal a skipped or failed companion case.
    for cases in observed.values():
        for case in cases:
            if case.get("expectedStatus") != "passed" or len(case.get("results", [])) != 1 \
                    or case["results"][0].get("status") != "passed":
                raise ValueError("suite contains an unexecuted, skipped, retried or failed case")
    return list(required)


def run_checks(root: Path, checks: list[Check], args: argparse.Namespace) -> tuple[int, Path]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    scratch = root.resolve() / ".scratch"
    if scratch.resolve() != scratch:
        raise OSError("Checkout scratch evidence directory must not redirect outside its expected path")
    output = scratch / "verification" / run_id
    if scratch not in output.resolve().parents:
        raise OSError("Verification evidence must remain beneath checkout root scratch")
    output.mkdir(parents=True)
    report = {"tier": args.tier, "scopes": sorted(args.scopes), "started_utc": datetime.now(timezone.utc).isoformat(),
              "checks": [], "independent_review": "not certified by this command",
              "running_application": "not validated by this command",
              "real_model": "requested" if args.real_model else "not run: not requested",
              "unselected_scopes": sorted(set(SCOPES) - args.scopes),
              "evidence_boundary": "All tracked and nonignored untracked contents, index and HEAD; ignored build output and external runtime state are not fingerprinted."}
    try:
        report["before"] = snapshot(root)
        print(f"Revision: {report['before']['head']}\nInput fingerprint: {report['before']['fingerprint']}", flush=True)
        for check in checks:
            print(f"Running {check.name}: {check.reason}", flush=True)
            result = execute_check(check, output)
            report["checks"].append(result)
            print(f"  {result['status']} ({result['seconds']}s); log: {result['log']}", flush=True)
            for line in result["suite_skip_observations"]:
                print(f"  suite-declared skip observation: {line}", flush=True)
            if result["status"] == "interrupted":
                break
        report["after"] = snapshot(root)
        report["inputs_current"] = report["before"]["fingerprint"] == report["after"]["fingerprint"]
        report["automatic_checks_passed"] = len(report["checks"]) == len(checks) and all(item["status"] == "passed" for item in report["checks"])
        code = 0 if report["inputs_current"] and report["automatic_checks_passed"] else 1
        report["status"] = "passed" if code == 0 else "incomplete"
        if not report["inputs_current"]:
            report["detail"] = "Inputs changed during verification; results do not certify the current tree. Recheck affected work."
            print(report["detail"], flush=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        code = 1
        report.update(status="incomplete", detail=f"Cannot establish current revision/input evidence: {exc}")
        print(report["detail"], flush=True)
    completed_names = {item["name"] for item in report["checks"]}
    report["not_run"] = [{"name": check.name, "command": list(check.command), "cwd": str(check.cwd),
                          "reason": "verification could not finish"} for check in checks if check.name not in completed_names]
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Automatic {args.tier} checks: {report['status']}. Report: {report_path}", flush=True)
    print("Independent review and the running application are not certified. Suite-declared skips remain visible in logs.", flush=True)
    return code, report_path


def main(argv: list[str] | None = None) -> int:
    args = arguments(argv)
    checks = select_checks(args)
    print(f"Tier: {args.tier}; scopes: {', '.join(sorted(args.scopes))}")
    for check in checks:
        print(f"  {check.name}: {check.reason}\n    cwd: {check.cwd}\n    argv: {json.dumps(check.command)}")
        if check.env:
            print(f"    env overrides: {json.dumps(check.env)}")
    if args.plan:
        print("Plan only: nothing executed; no acceptance, review, live or build evidence produced.")
        return 0
    try:
        return run_checks(ROOT, checks, args)[0]
    except OSError as exc:
        print(f"Cannot create safe checkout evidence: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
