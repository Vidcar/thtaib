# Current handover

Updated 2026-10-03. **Review, fixes and verification complete.** Delivery is [PR 239](https://github.com/Vidcar/thtaib/pull/239), branch `codex/verify-qwen-real-journeys`, based on `fdea336`; source `c7bade3`/`cd64bcb`, final regressions `deff4b2`. Dave authorized fixes and confirmed chats/work are disposable tests. Weights/runtimes remain intact; no previously running Workbench process was interrupted.

Ten supported application defects are fixed: P1 compaction Edit/Retry input loss; P2 Queue duplicates, command/custom-preview first-use bypass, uncertain job recovery, preview stop/deletion ownership and admission race, helper discovery, smoke alias and shared-context exhaustion; P3 router RAM attribution. Fresh independent reviews are clear. [Ranked findings and evidence](openspec/changes/correct-reviewed-runtime-boundaries/verification.md) includes the MOD-007 managed default of one native slot, retaining explicit Auto/positive counts and historical facts.

Final backend acceptance passed 1,477 default tests (one skip)/202 integration (three skips): `.scratch/verification/20261003T003931Z-997a6e75/report.json`. Desktop/spec/docs passed `20261003T002909Z-0e5e2e2b`; contracts match. Later changes are tests/docs only. Use `uv run --project apps/backend python scripts/verify.py --tier acceptance --scope <affected-area>`.

The rebuilt desktop is running from final source: backend PID 24892, Electron 16776, Qwen child 23608. Launcher/authenticated API/process/bundle checks passed. Original preferred General thinking profile is restored; observed context 76,800, one slot, MTP. Models shows Ready and truthful RAM unavailable. Launch with `scripts/Launch-Workbench.ps1`.

Real Qwen game and repaired website each passed ten independent browser checks. Research used online/local helpers and completed, but still made a factual error; browser helper runs looped. These P2 model-quality limits remain, with no supported replay/context-loss application cause. Sixteen created test chats were removed; ignored sample/evidence files remain under `.scratch/qwen-journeys/`.

Completed `align-reviewed-behavior` and `selected-tools-index` remain merged but unarchived/unsynced; `consolidate-product-contract` owns unfinished Workflows/media. No additional work is required for this review task.
