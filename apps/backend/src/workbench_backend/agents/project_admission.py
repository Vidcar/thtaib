"""Project-family exclusion policy; scheduling remains in the saved Chat queue."""

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
