# Current handover

Last updated: 2026-09-21.

## Goal and current state

OpenSpec 1.13.1 is the sole specification/change-planning system. The eight implementation-pack changes are imported under `openspec/changes/`, in order `01-complete-model-management` through `08-complete-media-voice`. Specification loading and reconciliation are complete; feature implementation is not authorized by this import. All 112 tasks remain unchecked.

Current contracts remain unchanged in the nine `openspec/specs/` capabilities. Legacy specification trees/trackers remain retired. The original pack and README are extracted only under `.scratch/openspec-pack-import-20260921/`.

## Important decisions and constraints

- `openspec/config.yaml` owns product context; `AGENTS.md` owns workflow and local checks. Do not recreate parallel trackers.
- Preserve `%LOCALAPPDATA%\LocalAIWorkbench\` user data and models. Disposable validation belongs under `.scratch/`.
- GitHub CI remains disabled at Dave's request; applicable checks run locally.
- Preserve order 01–08. Change 05 owns saved load/media definitions and the serial baseline; 06 owns concurrency checks; 08 owns the real media round trip. Later checks do not block earlier changes.
- Imported tasks require checking existing behaviour first and implementing only gaps. Existing import/deployment, adapter, Chat/SSE/approval, knowledge/retrieval, Lab and compiler paths must be reused. Source review does not establish live acceptance.
- Proposed Lab changes deliberately permit tested-profile reuse and retire one-issue-per-trait process; current specs are not yet changed.

## Validation and use

Import validation: `openspec validate --all --strict --no-interactive` passed 17/17 (eight changes, nine capabilities), with informational long-text suggestions only. CLI show/status/apply instructions were inspected for every change: planning complete, apply ready, zero completed tasks. Requirement names reconcile without collisions or missing modification targets. No application tests or live feature checks were run for this documentation-only import.

No import blocker. A separate implementation request may start change 01 only. Do not sync or archive unimplemented deltas. Launch remains root `Launch Workbench.vbs`; application, configuration, generated skills and user data are unchanged.
