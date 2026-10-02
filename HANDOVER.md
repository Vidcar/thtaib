# Current handover

Updated 2026-10-03. **Build, Qwen end-user testing and confirmed fixes are in progress** on `codex/verify-qwen-real-journeys`, based on main `fdea336` (PR 238). Dave authorized fixes and treats existing chats/work as disposable tests. Preserve weights/runtimes. No previously running Workbench process was interrupted.

Baseline desktop acceptance passed. Corrected service/window now run through the established launcher: live Qwen smoke passes and native Models shows RAM unavailable. Qwen is DavidAU 27B IQ4_XS, deployment `deploy_2fd62adb067a`. Natural journeys/evidence live in ignored `.scratch/qwen-journeys/`. Website follow-up is browser-testing its favourites repair; research is rechecking an unsupported contrast claim. Independent game QA covers controls; remaining game checks are underway.

Plan/report: [correct-reviewed-runtime-boundaries](openspec/changes/correct-reviewed-runtime-boundaries/verification.md). Nine baseline/application findings cover compaction rewind, Queue acknowledgements, host confirmation, managed-job recovery, preview stop/deletion races, helper discovery, smoke identity and RAM. Focused regressions pass. Chat/model fresh review is clear; permission owner/reviewer are checking atomic late-helper publication/restart. Root owns docs, live processes and delivery.

Completed changes `align-reviewed-behavior` and `selected-tools-index` are merged but not archived or synced to main specs. Their deltas remain relevant; `consolidate-product-contract` owns unfinished Workflows/media.

The broad run passed 1,455 default/202 integration tests, desktop build, contract and spec checks, but correctly reported stale inputs as fixes landed (`20261002T230522Z-1bf1c1b1`). Next: settle review, repeat affected acceptance on a stable tree, finish Qwen/browser outcomes, then commit/PR/merge, restart final service/build, verify identity/launcher and refresh this note. Current loaded service precedes the final atomic-publication hardening.
