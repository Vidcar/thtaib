# Current handover

Updated 2026-09-30. **Models refresh is complete, merged and running locally.** [PR #214](https://github.com/Vidcar/thtaib/pull/214), merge `740e5e4`; [delivery record](openspec/changes/archive/2026-09-30-refresh-models-workspace/design.md). Main Models/API-042 contracts are synced; every delivery task is complete.

Compact Generation/Loading columns retain supported native flags once, including exact GPU layers. Models supports zero/multiple named setups, explicit Save before Load, selected card setups, Find → Choose with inline Cancel/Retry, friendly rename and persisted automatic missing checks with icon retests. Missing setups require explicit selection. Video/audio checks remain deferred; no compatibility shims.

[Shared acceptance](.scratch/verification/20260930T221156Z-1f199ff5/report.json) passed 1,328 default/220 integration backend tests, desktop build, generated contracts and specs, with existing declared skips. [Final affected desktop/spec gates](.scratch/verification/20260930T223550Z-47a428b7/report.json) passed after asynchronous selection fixes. Fresh independent backend/desktop reviews have no remaining findings.

[Isolated native UAT](.scratch/lab-workbench/models-refresh-20260930-224050/models-final-selection.json) confirms setups, real loads, persisted results across restart, manual retests, unload during checks, downloads/recovery, rename, zero row drift, themes/narrow focus and 200% scaling. Native allocation helper unavailable remains accurately incomplete. UAT stopped cleanly; original weights are unchanged.

[Local launch evidence](.scratch/lab-workbench/local-delivery/models-launch.json) verifies new backend/desktop processes, authentication, launcher compatibility and artifacts matching native UAT. [Preservation](.scratch/lab-workbench/local-delivery/models-preservation.json) confirms existing chats/projects/setups/assets and all 28 model files unchanged; only migration bookkeeping was added. Launch with `scripts/Launch-Workbench.ps1`; verify via `scripts/verify.py` per AGENTS.

Sidebar rings ([PR #212](https://github.com/Vidcar/thtaib/pull/212)) and Lab ([PR #211](https://github.com/Vidcar/thtaib/pull/211)) remain complete; Dave's personal Lab acceptance remains pending. Preserve unrelated `.vite/`, product data and unfinished `consolidate-product-contract`. No Models work remains.
