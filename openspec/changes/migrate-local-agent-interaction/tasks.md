# Tasks

## 1. Baseline and compatibility gate

- [x] 1.1 Verify current Git, handover, contracts and consumer ownership; record baseline and retained/removable responsibilities in design.md without resetting newer work.
- [x] 1.2 Reproduce baseline default/integration tests, desktop build and generated-contract freshness; record real results and any environment limitation in design.md.
- [x] 1.3 Inspect published frontend tarballs, exact dependencies/peers/exports, adapter requests and installed Python native events; record exact versions/source revisions and effect-free protocol observations in design.md.
- [x] 1.4 Build a reversible isolated proof using installed React SDK, actual FastAPI Chat/Harness services, WorkbenchChatOpenAI and an installed local model; demonstrate incremental output, paired tool call/result, approve and deny, continuation and worker-confirmed cancellation. Record evidence and pass/fail before task group 2 replacement.
- [x] 1.5 Select the proven sync path or move the entire necessary async foundation forward coherently; document the decision, minimal dependency pins and Packet 04 ownership. If the gate fails, retain the working app and record the exact blocker with replacement tasks incomplete.

## 2. Backend interaction boundary (only after compatibility proof passes)

- [x] 2.1 Add backend-owned thread registration/mapping and validated protocol commands through existing Chat/Harness services; test unknown/wrong binding, unsupported fields/commands/version and reject-while-active without extra execution.
- [x] 2.2 Drive each run once through public native events and controlled serialization; test stable message/block/tool/native namespace identities, private-state exclusion and retained application audit/effective-setup projections.
- [x] 2.3 Implement durable hydration/replay cutover, thread cursors, filtering and bounded transient buffers using existing persistence; test late subscribers, multi-turn sequence resets, mid-run reconnect and explicit replay-gap resynchronization with the installed SDK.
- [x] 2.4 Route scoped interrupt decisions and explicit cancellation through existing protections; test approve/deny/pending-input, duplicate/stale/cross-run/namespace rejection, reservations and actual stop confirmation; disconnect must not cancel.
- [x] 2.5 Verify POST/state/cancel/SSE authentication through Electron-main injection; test missing/wrong token and ensure renderer never receives or stores it.

## 3. Shared desktop consumers

- [x] 3.1 Introduce one scoped SDK provider/interaction abstraction for current Chat and Agent-run; verify multiple selector mounts and remounts observe one execution and memoized transport disposal isolates thread switches.
- [x] 3.2 Replace custom message/tool assembly with upstream projections and stable archive reconciliation; test optimistic input, partial/completed messages, tool results, terminal hydration and older retained history without duplicates or lost answers.
- [x] 3.3 Preserve setup controls, progress, context/validated results and backend-targeted approval/cancel controls; test reject-while-active and no client queue claims or privileged headless tools.
- [x] 3.4 Inspect Agent Chat UI at a recorded revision and reuse suitable safe presentation with attribution; verify Markdown/code safety, accessible composer, scrolling and no old/new provider mixing in the rebuilt app.

## 4. Fidelity, data transition and retirement

- [x] 4.1 Verify Packet 01/02 through the new path: selected/applied settings, sync/async adapter cleanup, tools-off, supported blocks, real reasoning, validated structured results and context protection; preserve real partial output/unconfirmed tool outcomes on cancellation/restart.
- [x] 4.2 Validate representative pre-migration data on isolated copies, preserving full readable archive, compacted checkpoint association, project references/settings/files; if records change, test recoverable idempotent migration and interruption/restart through supported APIs.
- [x] 4.3 Migrate every current consumer and remove superseded SSE parser, event/message reducers, subscription controllers, endpoints and envelope shapes; regenerate application-owned contracts and retain behavioral regression coverage. Verify no competing interaction runtime remains.

## 5. Integration and delivery

- [x] 5.1 Align config and Packets 03–08 proposal/design/tasks/deltas with the migration dependency without completing deferred features; verify one async-transition owner and strict OpenSpec validation.
- [x] 5.2 Run backend default and integration tiers, shared-contract freshness, desktop build/typecheck/updated behavioral checks and openspec validate --all; fix relevant failures and record passed/failed/skipped honestly.
- [x] 5.3 Exercise actual rebuilt Windows desktop and real local model: incremental reply, two saved turns and fresh isolation, tools/approval/denial/cancel, reconnect/navigation/restart and retained final output/settings. Keep proof data isolated and preserve ordinary content and weights.
- [ ] 5.4 Review responsibility removal and all completion gates, synchronize/archive only implemented validated deltas, update handover, commit/push/PR/merge and make local result usable. Leave Packet 03 as next feature work without starting it.
