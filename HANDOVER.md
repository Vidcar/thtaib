# Current handover

Last updated: 2026-09-21.

Packet 03 is in progress on `codex/packet-03-shared-chat`; Dave authorized all 25 tasks, discovered fixes, validation and delivery. This is an implementation checkpoint, not completed delivery. Do not archive, merge or claim completion. Contract/tasks: `openspec/changes/03-complete-shared-chat`; prerequisites archived (PRs #116/#117). GitHub CI stays disabled.

Implemented foundations: durable scoped sessions/drafts/queues, SDK shell, scoped grants/typed questions, retained assets, standalone Library/recovery/attachment components, branches, backups, tray/attention and coordinated restart/Quit. Schema v2 preserves history; regeneration uses framework checkpoint state with tools disabled. Advanced components still need shell integration.

Latest evidence: backend default 472 passed; integration 149 passed; full desktop build passed with stopped-model wording and delayed ownership-lookup repairs. Contracts fresh; OpenSpec 15/15; diff check clean. Reproduced/fixed fixture popup, stale SDK answer authority, output-file correlation/later-write attribution, orphan consumer retention, unused asset deletion and stale/deleted/wrong-scope attachment writes. Exact-input Stop uses a shared harness cancellation Event plus durable tombstones, with admission/publication/restart races covered. Renderer confirms new queued runs against saved ownership and guards delayed lookups against replacing newer turns.

Real Windows: full/half-screen composer/sidebar corrected; Models loads promptly. Qwen continuation across reopen/restart, streamed Stop partial output, and loading-time Stop verified. Latest loading Stop had zero model requests/tool calls and only cancellation events. Disposable everyday Chat and its four runs/checkpoint were deleted after validation. Evidence under `.scratch/packet03-windows-review/`.

Machine: everyday backend healthy on8000, Workbench open, deploy_6d08aca4f54a Ready at64k, idle. Weights preserved. Launcher finished; its tool session34713 may retain inherited backend handles. Isolated backend/model stopped.

Next: obtain early layout acceptance or explicit deferral. Neither UX checkpoint is accepted/deferred; the arrangement question remains pending. Do not accumulate advanced controls until resolved. Then finish advanced UI/live journeys, final checks, Git/PR/merge and rebuilt delivery.
