"""Project-family exclusion policy; scheduling remains in the saved Chat queue."""

import threading
from typing import Any

from workbench_backend.agents.harness_backend import roots_overlap
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live


def holds_project(run) -> bool:
    if is_run_lifecycle_live(run.status) or run.finalization_phase is not None:
        return True
    return any(item.outcome in {"running", "uncertain"} and not item.evidence.get("acknowledged_at")
               for item in run.tool_outcomes.values())


def root_runs(runs):
    # Lab parent_run_id is provenance, not a shared execution family. Only
    # actual inline child records share their parent's reservation.
    children = {activity.run_id for run in runs for activity in run.child_runs}
    return [run for run in runs if run.id not in children]


def project_blocker_locked(admissions, store, runs, project_path: str) -> dict[str, Any] | None:
    """Find an overlapping owner. The caller holds the harness lock."""

    for _token, (path, owner_thread) in admissions.items():
        if owner_thread != threading.get_ident() and roots_overlap(project_path, path):
            return {"run_id": None, "thread_id": None, "task": "Starting another task", "project_path": path, "uncertain": False}
    stored = {item.id: item for item in store.list_run_lifecycle()}
    stored.update(runs)
    for run in root_runs(list(stored.values())):
        if run.project_path and holds_project(run) and roots_overlap(project_path, run.project_path):
            return {"run_id": run.id, "thread_id": run.thread_id, "task": run.task[:160],
                    "project_path": run.project_path, "uncertain": not is_run_lifecycle_live(run.status)}
    return None
