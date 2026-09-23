"""llama-bench engine measurement. Never invent scores."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.process import argv_for_host
from workbench_backend.inference.schemas import Deployment
from workbench_backend.inference.service import ModelManager
from workbench_backend.lab.schemas import EngineMeasurement
from workbench_backend.paths import WorkbenchPaths

BENCH_NAMES = ("llama-bench.exe", "llama-bench")


def find_llama_bench(server_executable: Path, *, install_dir: str | None = None) -> Path | None:
    search_roots = [server_executable.parent]
    if install_dir:
        search_roots.append(Path(install_dir))
    seen: set[Path] = set()
    for root in search_roots:
        resolved = root.resolve()
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        for name in BENCH_NAMES:
            candidate = resolved / name
            if candidate.is_file():
                return candidate
        for name in BENCH_NAMES:
            matches = sorted(resolved.rglob(name))
            if matches:
                return matches[0]
    return None


def parse_llama_bench_output(text: str) -> dict[str, str] | None:
    scores: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "t/s" in stripped.lower() and "test" in stripped.lower():
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        test_name = cells[-2] if len(cells) >= 2 else ""
        rate = cells[-1]
        if not test_name or not re.search(r"\d", rate):
            continue
        if test_name.lower() in {"test", "model"}:
            continue
        scores[test_name] = rate
    return scores or None


def measure_engine(
    manager: ModelManager,
    *,
    deployment: Deployment | None,
    paths: WorkbenchPaths,
) -> EngineMeasurement:
    created = utc_now()
    measurement_id = new_id("eng")
    try:
        executable = manager.runtime.require_executable()
    except Exception as exc:  # noqa: BLE001 - report unavailable, do not invent scores
        return EngineMeasurement(
            id=measurement_id,
            available=False,
            success=False,
            reason=f"Managed runtime is not ready for llama-bench ({exc}).",
            scores=None,
            deployment_id=deployment.id if deployment else None,
            created_at=created,
        )

    manifest = manager.runtime.current()
    install_dir = manifest.install_dir if manifest else None
    bench = find_llama_bench(executable, install_dir=install_dir)
    if bench is None:
        return EngineMeasurement(
            id=measurement_id,
            available=False,
            success=False,
            reason="llama-bench is not present in the managed runtime.",
            scores=None,
            deployment_id=deployment.id if deployment else None,
            runtime_executable=str(executable),
            created_at=created,
        )

    model_path: Path | None = None
    if deployment and deployment.bundle_id:
        bundle = manager.store.get_bundle(deployment.bundle_id)
        if bundle and bundle.primary_path:
            candidate = Path(bundle.primary_path)
            if candidate.is_file():
                model_path = candidate
    if model_path is None:
        return EngineMeasurement(
            id=measurement_id,
            available=True,
            success=False,
            reason=(
                "llama-bench is present but no local GGUF is available. "
                "Connected endpoints without a managed bundle cannot be benched. "
                "No score was fabricated."
            ),
            scores=None,
            command=[str(bench)],
            deployment_id=deployment.id if deployment else None,
            runtime_executable=str(executable),
            created_at=created,
        )

    command = argv_for_host([str(bench), "-m", str(model_path), "-p", "16", "-n", "8"])
    try:
        completed = subprocess.run(  # noqa: S603 - argv is managed runtime + recorded model path
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
            cwd=str(paths.runtimes),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return EngineMeasurement(
            id=measurement_id,
            available=True,
            success=False,
            reason=f"llama-bench failed to run: {exc}",
            scores=None,
            command=command,
            deployment_id=deployment.id if deployment else None,
            runtime_executable=str(executable),
            created_at=created,
        )

    raw = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    scores = parse_llama_bench_output(raw) if completed.returncode == 0 else None
    if completed.returncode != 0:
        return EngineMeasurement(
            id=measurement_id,
            available=True,
            success=False,
            reason=f"llama-bench exited {completed.returncode}",
            scores=None,
            raw_output=raw or None,
            command=command,
            deployment_id=deployment.id if deployment else None,
            runtime_executable=str(executable),
            created_at=created,
        )
    return EngineMeasurement(
        id=measurement_id,
        available=True,
        success=True,
        reason=None if scores else "llama-bench ran; output was not parsed into scores.",
        scores=scores,
        raw_output=raw or None,
        command=command,
        deployment_id=deployment.id if deployment else None,
        runtime_executable=str(executable),
        created_at=created,
    )
