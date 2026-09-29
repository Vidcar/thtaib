# Tasks

Completed 2026-09-29. Catalogue and token work remains intact; the first-read failure path now retains independent errors and retries until success or disposal. Automatic model warming was superseded by [the archived model-residency delivery](../2026-09-25-simplify-chat-model-agent-setup/tasks.md), not left as future work.

## 1. Catalogue and status

- [x] 1.1 Keep project and chat lists small, independent and read-only; verify the catalogue path omits transcripts, full runs and token history.
- [x] 1.2 Keep failed first reads unresolved and retry until first success; verify a mounted fake-clock regression beyond thirty failures cannot show empty lists or ready status, a later success recovers, independent-list failure stays visible, and unmount stops retries.
- [x] 1.3 Retain the single lower-left status dot and reading, model-start, ready and unavailable hover states; verify it uses authoritative list/service/model state without passive model starts.
- [x] 1.4 Keep attention and finished-chat opening off token logs and full run bodies; verify existing operational-read and saved-snapshot tests.

## 2. Token history

- [x] 2.1 Keep raw ordered events while a turn is live and compact finished message deltas only after terminal projection, preserving final messages, partial/tool/nested outcomes and reconnect seeds; verify snapshot-race and measurement-replay regressions.
- [x] 2.2 Compact substantial finished logs after catalogue request and reclaim freed space without deleting chats; verify the existing maintenance path and completion-compaction checks.

## 3. Delivery checks

- [x] 3.1 Run the mounted catalogue-recovery checks, existing affected backend regressions, desktop build and `openspec validate --all`; verify initial failure, late recovery and cold launch in the built Windows desktop before archiving.

## Delivery evidence

- Mounted fake-clock coverage runs in the desktop build: more than thirty failures, capped backoff, both independent outcomes, owner replacement, late success/rejection, unmount and action-error recovery. A disposable original sidebar fails the false-readiness assertion.
- Focused verification: 68 backend tests plus desktop typecheck/regression passed (`.scratch/verification/20260929T212627Z-d7b9f5c8/`). Backend acceptance passed 1,253 default tests (one symlink skip) and 213 integration tests (three Chrome-worker prerequisite skips) in `20260929T212722Z-57b6e978`. Final desktop build and OpenSpec acceptance passed in `20260929T214434Z-a6df2590`.
- Two test preconditions exposed by acceptance were repaired without reducing coverage: close Vite before fake clocks (twelve cold-cache passes), and wait for bound Chat ownership in the existing memory-selection test (five focused passes; removing its generation guard in a disposable copy fails the retained assertion). Independent review resolved the action-error finding and accepted these corrections.
- Built Windows checks used the unmodified built main/preload/renderer, real isolated backend and profile under `.scratch/startup-catalogue/native/`: cold launch, 38 injected failures per list with virtual time, both independent recovery directions, automatic saved transcript recovery before any click/reload, and restoration in another process. Reports record artifact hashes, file URL and process identities; screenshots were inspected. No model/work start was attempted; test processes were cleaned up.
- Limits: ChatPanel's separate initial-read warning remains visible after the sidebar and saved transcript recover from the injected outage; that bootstrap/error owner is unchanged. The native fixture has no configured model; configured-model no-warming behavior is covered by existing backend regressions. Failure injection redirects requests to the isolated backend; the ordinary launcher and existing product window were not exercised or restarted. Backend maintenance scheduling was source-audited; compaction safety has existing executable coverage. GitHub CI remains disabled. No broader stabilisation claim.
