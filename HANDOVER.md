# Current handover

Last updated: 2026-09-21.

## Goal and current state

OpenSpec 1.13.1 is the repository's sole product-specification and change-planning system. Current contracts live under `openspec/specs/`; proposals and active work live under `openspec/changes/`. Start planning with `$openspec-propose` and begin implementation only in a later request with `$openspec-apply-change`.

The legacy `specs/` and `docs/` trees, standalone product-vision document, catalogue/evidence/templates/ADR trackers, delivery map, custom spec checker and checker tests were removed after current behavioral contracts were migrated into nine OpenSpec capability specs. Their history remains recoverable in Git.

## Important decisions and constraints

- `openspec/config.yaml` carries concise product and integration context.
- `AGENTS.md` owns engineering workflow and exact local validation commands; do not recreate a parallel documentation or tracking system.
- Shared-contract repository discovery uses the backend and desktop package manifests, not a documentation file.
- Preserve `%LOCALAPPDATA%\LocalAIWorkbench\` user data and models. Disposable validation belongs under `.scratch/`.
- GitHub CI remains disabled at Dave's request; applicable checks run locally.

## Validation and use

Validation passed: OpenSpec 9/9 capabilities; 233 default and 109 integration backend tests; shared-contract freshness; whitespace/error checks. OpenSpec emitted informational long-requirement suggestions only. Repeat with `openspec validate --all` from the repository root when specs change.

Launch the product with root `Launch Workbench.vbs`. No application behavior or user data was intentionally changed by the documentation migration.
