# Current handover

Updated 2026-09-30. Lab implementation, agent-driven real-model Windows QA/UAT and local delivery are complete. [PR #211](https://github.com/Vidcar/thtaib/pull/211) merged as `65f4e8e`; this checkout is on `main`. The normal application is open at Lab. All 17 tasks are checked; contracts are synced and the change archived: [delivery record](openspec/changes/archive/2026-09-30-lab-workbench/design.md), [tasks](openspec/changes/archive/2026-09-30-lab-workbench/tasks.md).

Performance, Memory and editable Echo/Clock Challenges are usable with durable results, scoped Stop/leave, partial-result recovery and temporary extra-model cleanup. Independent backend, desktop, verification-guard and closeout reviews are clear.

Real-model evidence: `.scratch/lab-workbench/candidate-20260930-022406/qa-summary.json` and `phase1.json`–`phase5.json`. Built Electron/backend with installed Qwen3.5 4B/CUDA b11045 passed exact 256/512/1024 output, four requests, two native slots, all 15 needle/depth outcomes, challenge positive/negative/edit checks, failure/recovery, restart/deletion, keyboard, long content, 57 cards and native 200% scaling/full/half windows. Disposable records/extras were removed; normal Quit exited cleanly.

Checks: backend default 1,288 and integration 220 tests passed (optional skips one/three) in `.scratch/verification/20260930T011917Z-286027f7/`; unchanged backend inputs preserve that evidence despite the overall changing-tree report. Final desktop/spec acceptance passed in `20260930T014517Z-94d2c1b3`; contracts and strict validation passed. Later handover edits require only docs checks.

Normal launcher, authenticated compatibility, product-root/process identity and native Lab/model catalogue passed; built artifact hashes match UAT. `.scratch/lab-workbench/local-delivery/` records launch and unchanged saved data/weights.

Dave approved the layout; his separate personal acceptance of the built UX remains pending. No technical delivery blocker remains. Preserve unrelated `.vite/`, product data and weights. `consolidate-product-contract` remains separate and unfinished.
