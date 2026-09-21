# Tasks: Complete persistent shared-agent Chat

Prerequisites: change 02 and `migrate-local-agent-interaction` must be implemented and verified before this change starts. Use the verified `@langchain/react` interaction boundary; do not extend the replaced custom snapshot/event protocol. SDK migration does not satisfy any task below. Before changing an existing path, run its relevant acceptance checks and retain passing behaviour. The implementation tasks below mean verify and complete only missing behaviour; do not rebuild a satisfied requirement. Keep the acceptance checks even when no code change is needed. Import-time source review is not execution evidence, so all tasks remain unchecked until their full scope is verified.

## 1. Verify existing behaviour and implement gaps

Apply the shared UX contract and acceptance protocol in `design.md` (API-016 through API-020). Build the basic shell in 1.9 alongside 1.1-1.3 and hold checkpoint 3.1 before accumulating the remaining controls; task numbering does not postpone that review. Preserve the existing Models journey and current execution owners.

Additional prerequisite: `repair-local-interaction-boundaries` must be delivered and verified. Retain its actual-component deferred hydration/cancellation/registration/submission/draft tests, real Electron requesting-document/navigation checks and legacy repeated-text/repair/edit-cutover tests while implementing this packet. Repairs do not complete any feature task here; Packet 04 retains async ownership.

- [ ] 1.1 Implement immutable project/non-project session binding, new/rename/archive/search/reopen and stable per-turn threads/runs with frozen setup.
- [ ] 1.2 Persist drafts and editable queued turns, advance only after success, and revalidate setup/permissions/admission at dispatch.
- [ ] 1.3 Integrate Chat with the prerequisite's verified `@langchain/react` message/tool/state projections, scoped subscription and interrupt boundary; reconcile incremental answers/reasoning/tool results by application run/call identity, preserve durable terminal hydration and expose observed planning/context. Verify migration compatibility and do not extend the superseded custom `snapshot` / `run_event` / `stream_end` transport.
- [ ] 1.4 Verify existing tools-off, host-shell parsing, framework approvals and resume/cancel protections in `agents/host_shell.py` and `agents/harness.py`; complete missing presentation/execution guards, four scoped approval choices, revocation, exact resume identities and typed ask-user interruptions.
- [ ] 1.5 Implement supported checkpoint branches, explicit effectful retry and answer-only regeneration or a truthful unavailable state where unsupported.
- [ ] 1.6 Add text/code picker and drag/drop, attachment-only send, scoped immutable originals, fitting source-labelled input and verified shared artifact references.
- [ ] 1.7 Implement dependency-aware retention/deletion, readable export and consistent versioned manual backup/clean restore.
- [ ] 1.8 Complete cancellation, tray/reopen and explicit Quit handling; preserve partial results, safe rendering and accessible existing controls.
- [ ] 1.9 Implement the shared collapsible project/conversation sidebar, fixed-area header, on-demand Files/activity panel, functional destination rollout and Settings entry; support system/light/dark themes, full/half-screen layouts, keyboard access and reduced motion.
- [ ] 1.10 Implement compact model/reasoning/setup and composer controls, truthful context/tok/s indicators and stopped-installed-model start from Chat using existing lifecycle/admission protections; preserve draft and actionable conflicts/failures.
- [ ] 1.11 Implement remembered detailed-stream visibility (default off), independent output expansion, always-streamed answers, compact progress and visible interrupts/errors; present distinct branch/retry/regenerate actions.
- [ ] 1.12 Implement Queue/Stop presentation and editable queue above the composer, inline scoped approvals, saved-grant Settings controls, sidebar attention/list and background Windows notifications without focus stealing or success alerts by default.
- [ ] 1.13 Implement the initial retained-file Library with scope filters/provenance and shared inline/panel previews/actions; expose manual backup/restore in Settings without a parallel store.

## 2. Verify

- [ ] 2.1 Test same-thread continuation and fresh-session isolation; reject session moves; verify branches retain area and historical removed-project identity.
- [ ] 2.2 Test queue edits/navigation/restart, selector changes, approval/input waits, automatic success advance and failure/cancel pause.
- [ ] 2.3 Test empty tools in sync/async/restore hooks, unexpected calls, four approval scopes, revoked grants, mixed ordered decisions and stale/duplicate/wrong-run answers.
- [ ] 2.4 Test SDK-scoped reconnect/resynchronization, late events and terminal hydration with no duplicated or cross-conversation content; retain partial text and actual tool results against durable application history.
- [ ] 2.5 Test branch heads, supported snapshot integrity, answer-only regeneration without tool effects, explicit retry disclosure and crash boundaries around effects/approval acceptance.
- [ ] 2.6 Test denied/failed writes not becoming artifacts, changed mutable files, scoped attachments with tools off, safe HTML/code rendering and capacity failures without silent truncation.
- [ ] 2.7 Test shared-branch/case asset deletion, checkpoint API cleanup, diagnostic retention separation, backup integrity and clean restore with missing external dependencies and no automatic replay.
- [ ] 2.8 Run a real local-model conversation across reopen/restart, a disposable file task with approval/denial/cancel, and Windows drag/drop, scrolling, tray and Quit checks.
- [ ] 2.9 Verify observed versus estimated/unavailable context and tok/s, unsupported reasoning controls, setting changes versus queued/live setup, model-start failure/conflicts and no duplicated submission after recovery.
- [ ] 2.10 Exercise stream toggle persistence and per-output expansion during generation, text selection/links, reduced motion, visible approvals/questions/errors, queue edits/reopen, Library scope/access and notifications without changing run ownership or stealing focus.

## 3. Human UX checkpoints

- [ ] 3.1 Demonstrate the basic Chat arrangement early after 1.1-1.3 and the basic 1.9 shell, including Models -> Chat selection/install/settings/start/send/cancel/reopen; resolve requested layout changes before accumulating controls or record Dave's explicit review deferral.
- [ ] 3.2 Demonstrate the completed Chat/history/queue/approval/files/recovery journey in the built Windows application using full and half-screen windows, Windows scaling, keyboard navigation, long content and a failure/recovery state; record actual conditions and technical results separately from Dave's acceptance or explicit deferral in `design.md`/PR.

Specification approval does not complete these tasks. UX acceptance is pending until Dave accepts the built experience or explicitly defers review; mark a deferral as deferred, not accepted, and retain every required technical/live check.

Use the repository validation commands in `AGENTS.md`. Keep actual test outcomes and any blocker in this change/its PR; do not create another tracker. Required real checks stay incomplete when the necessary runtime, endpoint or Windows device is unavailable.
