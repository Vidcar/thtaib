# Tasks

## 1. Reader repair

- [x] 1.1 Correct restricted-reader assembly and middleware authorization/description; verify native selected reads with retrieval, automatic route restrictions and sync/async dispatch regressions.

## 2. Validation and delivery

- [x] 2.1 Run backend default/integration suites, OpenSpec and whitespace validation; verify all applicable checks pass.
- [x] 2.2 Validate isolated real-model Chat across two successive turns with file reading and knowledge search; verify retained outcomes and original model/settings preservation.
- [x] 2.3 Sync and archive the focused OpenSpec change, update HANDOVER.md, record the delivery PR and refresh the idle established backend; verify fresh process identity and preserved saved data/settings.

## Verified delivery

Backend default: 954 tests, one existing skip; integration: 203; focused reader/retrieval: seven; OpenSpec and whitespace passed. Isolated existing Qwen Chat: two turns, six successful tool calls, retained outcomes after reopening. Evidence: `.scratch/chat-file-reader-validation/report.json`. Established backend refreshed from PID4916 to PID26708 through the standard launcher; saved chats/drafts/run records, model processes/residency/settings and desktop preserved, two static previews restored, no failed turn replayed. Evidence: `.scratch/chat-file-reader-refresh/after.json`. Delivery: PR176, implementation `d6c19fa`, base `57605cb`.
