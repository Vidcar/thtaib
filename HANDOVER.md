# Current handover

Updated 2026-10-01. **Agent-tool audit gaps N01–N05 are corrected in the working tree and awaiting merge.** Change [correct-agent-tool-audit-gaps](openspec/changes/archive/2026-10-01-correct-agent-tool-audit-gaps/resolutions.md). The closed audit remains [PR #216](https://github.com/Vidcar/thtaib/pull/216) / [PR #217](https://github.com/Vidcar/thtaib/pull/217); its [resolution report](openspec/changes/archive/2026-10-01-complete-agent-tools-audit/resolutions.md) and measured limits stay as written. Certifying acceptance passed at [`.scratch/verification/20261001T084852Z-a962e818`](.scratch/verification/20261001T084852Z-a962e818/report.json): 1,424 default tests (1 skip), 222 integration tests (3 skips), desktop build, contracts and OpenSpec. An earlier run of the same checks was invalidated because the synchronous mutation borrow landed during it (`.scratch/verification/20261001T083342Z-5f1218be`). Isolated real-model smoke passed 4 tests against the cached tiny GGUF and the installed Windows llama.cpp b11045 CPU server. The open Workbench window was not reloaded. Preserve `.vite/`, data/weights and unrelated `consolidate-product-contract`.

**The prior agent-tools audit is still merged.** Implementation `c18f85f`, report `6e43b44`. Backend delivery then passed 1,410 default/222 integration tests (1/3 skips), four real-model smoke tests; desktop build/contracts/specs and fresh review cleared. Native Chrome/WinApp and production Electron UAT passed. Fresh authenticated launch/artifact identity and restored model/profile passed. Captured saved records, persisted Chat drafts and 28 model-file identities unchanged; missing Knowledge/hidden-editor baseline is disclosed. Shutdown acknowledgement timed out; settlement verified without replay. Frozen 36-turn CPU matrix: eager/hybrid 12/12 each, deferred 6/12. Fresh skills:14/18 conditional selections; no workflow-quality claim. Those limits are unchanged by this correction.

**Models refresh remains complete, merged and running locally.** [PR #214](https://github.com/Vidcar/thtaib/pull/214), merge `740e5e4`; [delivery record](openspec/changes/archive/2026-09-30-refresh-models-workspace/design.md). Main Models/API-042 contracts are synced; every delivery task is complete.

Models retains explicit Save/Load, named setups, compact controls, rename, download recovery and capability checks. Video/audio checks remain deferred.

[Prior Models acceptance](.scratch/verification/20260930T221156Z-1f199ff5/report.json) and [final gates](.scratch/verification/20260930T223550Z-47a428b7/report.json) passed; fresh reviews cleared.

[Prior native UAT](.scratch/lab-workbench/models-refresh-20260930-224050/models-final-selection.json) passed Models journeys; allocation-helper availability remains accurately incomplete.

[Prior launch/preservation](.scratch/lab-workbench/local-delivery/models-launch.json) passed. Launch with `scripts/Launch-Workbench.ps1`; verify with `scripts/verify.py` per AGENTS.

Sidebar rings [#212](https://github.com/Vidcar/thtaib/pull/212) and Lab [#211](https://github.com/Vidcar/thtaib/pull/211) remain complete; Dave's personal Lab acceptance remains pending.
