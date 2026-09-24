# Tasks

## 1. Finalization and project capture

- [x] 1.1 Persist one settled outcome and saving phase before project capture; verify concurrent finalization, Stop, cancellation, failure and restart tests.
- [x] 1.2 Prune excluded trees, honor explicit empty Lab allowlists, stage and verify capture, then publish atomically; verify symlink, changing-file, failed-capture and exact branch-restore tests.
- [x] 1.3 Show saving and disable Stop in Chat and Agent run; verify desktop component checks and run contract freshness.

## 2. Generation and interaction delivery

- [x] 2.1 Replace per-token observation waits with a bounded latest-sample publisher and terminal sample merge; verify blocked and failing publisher tests.
- [x] 2.2 Keep ordered native event persistence and classify essential failures as `interaction_persistence_failed`; verify a persistence-failure regression.
- [x] 2.3 Add scalar interaction metadata and migration, one binding per batch, and off-loop SSE reads; verify migration, streaming and cursor tests.
- [x] 2.4 Seed partial replay once and update incrementally; verify late-join and long-conversation checks.
- [x] 2.5 Link checkpoints in 64-item pages to a saved pre-run or previous boundary; verify bounded history and restart tests.

## 3. Subscription replay

- [x] 3.1 Patch the pinned SDK for hydrated and per-subscription cursors, independent reconnects and complete-frame advancement; verify actual SDK checks for late same-filter/wider subscriptions, nested tools, partial text and incomplete frames.
- [x] 3.2 Give synthetic seeds stable IDs, retain active raw events and compact completed deltas without losing tool/lifecycle/namespace history; verify replay and deliberate-gap regressions.
- [x] 3.3 Preserve old chats and show unavailable legacy historical detail honestly; verify reopening a legacy compacted fixture.

## 4. Acceptance and delivery

- [x] 4.1 Benchmark isolated large excluded-tree capture and long-conversation replay before and after; record comparable timings in the change or PR.
- [x] 4.2 Run backend default and integration suites, desktop build, shared-contract freshness, and strict OpenSpec validation; record results.
- [x] 4.3 Verify an isolated Windows live-model project run and long Chat replay without changing weights or everyday product data.
- [x] 4.4 Update affected current specs and HANDOVER, then review the implementation diff.
