# Current handover

Updated 2026-10-01. **Agent-tools audit code/specs verified; final delivery active**, branch `codex/agent-tools-audit`, baseline `21136f3`. Dave authorized complete findings/upgrades resolution. [Tasks](openspec/changes/complete-agent-tools-audit/tasks.md); [report](openspec/changes/complete-agent-tools-audit/resolutions.md). Schemas/discovery/Plan/evidence, project grants, deletion, atomic edits, owned jobs, MCP resources, frozen scripts, nine skills and six templates implemented. Native Chrome/WinApp and production Electron UAT passed. Final backend delivery: 1,410 default/222 integration tests (1/3 skips), all four real-model smoke tests passed; desktop build/contracts and synced specs passed. Fresh review cleared 104 source/test/contract/spec files. Confirmed Windows admission and conversation-continuation defects are fixed. Native lifecycle controls pass; evaluator teardown corrected. All nine paired skill captures completed (12/18 conditional selections; no workflow-success claim). Next: implementation merge/local refresh with strict data preservation, stable timing/supplements, final report/archive/Git delivery. Preserve `.vite/`, all existing data/weights and unrelated `consolidate-product-contract`.

**Models refresh remains complete, merged and running locally.** [PR #214](https://github.com/Vidcar/thtaib/pull/214), merge `740e5e4`; [delivery record](openspec/changes/archive/2026-09-30-refresh-models-workspace/design.md). Main Models/API-042 contracts are synced; every delivery task is complete.

Models retains explicit Save/Load, named setups, compact controls, rename, download recovery and capability checks. Video/audio checks remain deferred.

[Prior Models acceptance](.scratch/verification/20260930T221156Z-1f199ff5/report.json) and [final gates](.scratch/verification/20260930T223550Z-47a428b7/report.json) passed; fresh reviews cleared.

[Prior native UAT](.scratch/lab-workbench/models-refresh-20260930-224050/models-final-selection.json) passed Models journeys; allocation-helper availability remains accurately incomplete.

[Prior launch/preservation](.scratch/lab-workbench/local-delivery/models-launch.json) passed. Launch with `scripts/Launch-Workbench.ps1`; verify with `scripts/verify.py` per AGENTS.

Sidebar rings [#212](https://github.com/Vidcar/thtaib/pull/212) and Lab [#211](https://github.com/Vidcar/thtaib/pull/211) remain complete; Dave's personal Lab acceptance remains pending.
