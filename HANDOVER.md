# Current handover

Updated 2026-09-30. **Models refresh implemented and verified**, delivery active on `codex/refresh-models-workspace`; [tasks](openspec/changes/refresh-models-workspace/tasks.md), [mock](.scratch/models-design-20260930/HANDOVER.md).

Compact Models retains native flags once, exact GPU layers, zero/multiple named setups, explicit Save before Load, Find → Choose with Cancel/Retry, friendly rename, and persisted automatic missing checks with icon retests. Video/audio checks are deferred. No implicit setups or compatibility shims; authored settings, history and weights remain protected. Main Models/API-042 contracts are synced.

[Shared acceptance](.scratch/verification/20260930T221156Z-1f199ff5/report.json) passed 1,328 default/220 integration backend tests, desktop build, generated contracts and specs, with existing declared skips. [Final desktop/spec acceptance](.scratch/verification/20260930T223550Z-47a428b7/report.json) passed after asynchronous selection fixes. Fresh independent backend/desktop reviews have no remaining findings.

[Native UAT](.scratch/lab-workbench/models-refresh-20260930-224050/models-final-selection.json) uses isolated data and original weights read only. It confirms empty/named/multiple setups, explicit missing-reference recovery, real loads, persisted checks across restart, retests, unload during checks, downloads/recovery, rename, zero row drift, themes/narrow keyboard focus and 200% scaling. Final native artifacts match the build. Native allocation helper unavailable is correctly reported incomplete.

Next: merge implementation, refresh the established local app, verify build/process/auth and [preservation snapshot](.scratch/lab-workbench/local-delivery/models-before.json), then close delivery and archive. Product deployment is still unchanged. Launch with `scripts/Launch-Workbench.ps1`; use `scripts/verify.py` per AGENTS.

Sidebar rings ([PR #212](https://github.com/Vidcar/thtaib/pull/212)) and Lab ([PR #211](https://github.com/Vidcar/thtaib/pull/211)) remain complete. Dave's personal Lab acceptance remains pending. Preserve unrelated `.vite/` and unfinished `consolidate-product-contract`.
