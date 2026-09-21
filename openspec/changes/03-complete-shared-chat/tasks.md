# Tasks: Complete persistent shared-agent Chat

Prerequisites: change 02 and `migrate-local-agent-interaction` must be implemented and verified before this change starts. Use the verified `@langchain/react` interaction boundary; do not extend the replaced custom snapshot/event protocol. SDK migration does not satisfy any task below. Before changing an existing path, run its relevant acceptance checks and retain passing behaviour. The implementation tasks below mean verify and complete only missing behaviour; do not rebuild a satisfied requirement. Keep the acceptance checks even when no code change is needed. Import-time source review is not execution evidence, so all tasks remain unchecked until their full scope is verified.

## 1. Verify existing behaviour and implement gaps

Additional prerequisite: `repair-local-interaction-boundaries` must be delivered and verified. Retain its actual-component deferred hydration/cancellation/registration/submission/draft tests, real Electron requesting-document/navigation checks and legacy repeated-text/repair/edit-cutover tests while implementing this packet. Repairs do not complete any feature task here; Packet 04 retains async ownership.

- [ ] 1.1 Implement immutable project/non-project session binding, new/rename/archive/search/reopen and stable per-turn threads/runs with frozen setup.
- [ ] 1.2 Persist drafts and editable queued turns, advance only after success, and revalidate setup/permissions/admission at dispatch.
- [ ] 1.3 Integrate Chat with the prerequisite's verified `@langchain/react` message/tool/state projections, scoped subscription and interrupt boundary; reconcile incremental answers/reasoning/tool results by application run/call identity, preserve durable terminal hydration and expose observed planning/context. Verify migration compatibility and do not extend the superseded custom `snapshot` / `run_event` / `stream_end` transport.
- [ ] 1.4 Verify existing tools-off, host-shell parsing, framework approvals and resume/cancel protections in `agents/host_shell.py` and `agents/harness.py`; complete missing presentation/execution guards, four scoped approval choices, revocation, exact resume identities and typed ask-user interruptions.
- [ ] 1.5 Implement supported checkpoint branches, explicit effectful retry and answer-only regeneration or a truthful unavailable state where unsupported.
- [ ] 1.6 Add text/code picker and drag/drop, attachment-only send, scoped immutable originals, fitting source-labelled input and verified shared artifact references.
- [ ] 1.7 Implement dependency-aware retention/deletion, readable export and consistent versioned manual backup/clean restore.
- [ ] 1.8 Complete cancellation, tray/reopen and explicit Quit handling; preserve partial results, safe rendering and accessible existing controls.

## 2. Verify

- [ ] 2.1 Test same-thread continuation and fresh-session isolation; reject session moves; verify branches retain area and historical removed-project identity.
- [ ] 2.2 Test queue edits/navigation/restart, selector changes, approval/input waits, automatic success advance and failure/cancel pause.
- [ ] 2.3 Test empty tools in sync/async/restore hooks, unexpected calls, four approval scopes, revoked grants, mixed ordered decisions and stale/duplicate/wrong-run answers.
- [ ] 2.4 Test SDK-scoped reconnect/resynchronization, late events and terminal hydration with no duplicated or cross-conversation content; retain partial text and actual tool results against durable application history.
- [ ] 2.5 Test branch heads, supported snapshot integrity, answer-only regeneration without tool effects, explicit retry disclosure and crash boundaries around effects/approval acceptance.
- [ ] 2.6 Test denied/failed writes not becoming artifacts, changed mutable files, scoped attachments with tools off, safe HTML/code rendering and capacity failures without silent truncation.
- [ ] 2.7 Test shared-branch/case asset deletion, checkpoint API cleanup, diagnostic retention separation, backup integrity and clean restore with missing external dependencies and no automatic replay.
- [ ] 2.8 Run a real local-model conversation across reopen/restart, a disposable file task with approval/denial/cancel, and Windows drag/drop, scrolling, tray and Quit checks.

Use the repository validation commands in `AGENTS.md`. Keep actual test outcomes and any blocker in this change/its PR; do not create another tracker. Required real checks stay incomplete when the necessary runtime, endpoint or Windows device is unavailable.
