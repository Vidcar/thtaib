# Current handover

Updated 2026-09-29. `startup-catalogue` implementation and validation are complete on `codex/startup-catalogue` (base `3cd3fee`); PR/merge is the remaining delivery step. Archived record: [tasks](openspec/changes/archive/2026-09-29-startup-catalogue/tasks.md).

Each sidebar list now owns readiness/error for its current selection. Failures remain visible and retry at 1/2/4/8 seconds, capped at eight, until success or disposal. Empty copy needs a successful response. Selection/unmount cancels timers; late results cannot overwrite replacements. Chat refresh bypasses obsolete shared requests. Lightweight reads, saved transcripts, token maintenance and passive no-model-start paths remain intact.

Passed: 68 focused backend tests; mounted fake-clock regression and original-source negative control; backend acceptance (1,253 default tests, one symlink skip; 213 integration tests, three Chrome-worker prerequisite skips); desktop build/OpenSpec acceptance; fresh-context independent review. Acceptance exposed two test preconditions, repaired without weakening assertions: close Vite before fake timers, and wait for bound memory-selection ownership. Cold-cache repeats and an isolated generation-guard violation verified those corrections.

Built Windows validation used isolated `.scratch/startup-catalogue/native/` data/profile and the actual built main/preload/renderer: cold launch, 38 failed reads per list, independent recovery, automatic transcript recovery before reload, and restoration in another process. Hashes/processes/screenshots were verified; no model start was attempted; test processes were cleaned up. Evidence: `.scratch/verification/20260929T214434Z-a6df2590/` (desktop/spec), `20260929T212722Z-57b6e978/` (passing backend gates), and native reports.

Limits: the separate Chat startup warning can linger after catalogue/transcript recovery. Native fixture has no configured model; launcher/current product window were not restarted. New local artifacts are ready for the next normal launch. Broader stabilisation remains unfinished.

PR #207's workflow remains unchanged; GitHub CI stays disabled. `lab-workbench`, `consolidate-product-contract`, weights, protected chats and unrelated work are unchanged.
