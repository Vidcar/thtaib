# Tasks

Reviewed 2026-09-27 against the current implementation. Catalogue and token work remains delivered; the first-read failure path is incomplete. Automatic model warming was superseded by [the archived model-residency delivery](../archive/2026-09-25-simplify-chat-model-agent-setup/tasks.md), not left as future work.

## 1. Catalogue and status

- [x] 1.1 Keep project and chat lists small, independent and read-only; verify the catalogue path omits transcripts, full runs and token history.
- [ ] 1.2 Keep failed first reads unresolved and retry until first success; verify a mounted fake-clock regression beyond thirty failures cannot show empty lists or ready status, a later success recovers, independent-list failure stays visible, and unmount stops retries.
- [x] 1.3 Retain the single lower-left status dot and reading, model-start, ready and unavailable hover states; verify it uses authoritative list/service/model state without passive model starts.
- [x] 1.4 Keep attention and finished-chat opening off token logs and full run bodies; verify existing operational-read and saved-snapshot tests.

## 2. Token history

- [x] 2.1 Keep raw ordered events while a turn is live and compact finished message deltas only after terminal projection, preserving final messages, partial/tool/nested outcomes and reconnect seeds; verify snapshot-race and measurement-replay regressions.
- [x] 2.2 Compact substantial finished logs after catalogue request and reclaim freed space without deleting chats; verify the existing maintenance path and completion-compaction checks.

## 3. Delivery checks

- [ ] 3.1 Run the mounted catalogue-recovery checks, existing affected backend regressions, desktop build and `openspec validate --all`; verify initial failure, late recovery and cold launch in the built Windows desktop before archiving.
