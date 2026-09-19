# State, memory and recovery

[Specification index](../README.md) · [Status and evidence](../catalog.json)

## Ownership, scope and source

Application SQLite records and files store workbench data; the separate LangGraph SQLite checkpointer stores execution state. The application links them. Source: [revision 0.5, pages 4–6](../sources/README.md#application-infrastructure), including [owned records](../sources/README.md#models-and-inference) and [knowledge policy](../sources/README.md#agents-and-workflows).

## Public contracts and collaboration

The application owns run/thread identities, checkpoint namespaces, displayed history, artifact/context references, knowledge versions and snapshot records. LangGraph owns the checkpoint representation/runtime. A snapshot provider captures/restores project files; worker adapters declare environment capabilities and effects. Retrieval is separate from project memory and does not train the model.

Do not infer a distributed transaction between application SQLite, checkpointer SQLite, files and remote services. Their consistency/reconciliation strategy is unresolved and must be decided before recovery or snapshot-aware branching is claimed.

## Lifecycle and failure

Persist enough linkage to explain a run after restart, including selected configuration and recovery outcome. A recoverable checkpoint, a restorable project and a reconnectable environment are separate capabilities. Recovery must reconcile them before resuming effects. A branch creates a linked attempt without overwriting its parent.

Issue #15 locks the STATE-003 snapshot defaults used by Lab reuse: an application-owned directory snapshot (not a git commit), captured at a quiescent boundary, stored under `%LOCALAPPDATA%\LocalAIWorkbench\cases\` and `snapshots\`, restored into a new workspace, with secrets/weights/scratch/venv/node_modules/credentials excluded and no full environment restore. [Issue #66](https://github.com/Vidcar/thtaib/issues/66) locks restore integrity for that directory snapshot: a missing tree, missing expected file, hash mismatch or unexpected tree file fails explicitly and does not register a restored workspace. Remaining snapshot policy stays [OQ-005](../open-questions.md#oq-005). External-effect rollback stays [STATE-004](#state-004).

Issue #17 locks the STATE-005 durable-knowledge store defaults used by the backend API and Lab/harness version refs. Retrieval/RAG and cross-surface sharing stay [OQ-006](../open-questions.md#oq-006).

Issue #27 locks the STATE-001 dual SQLite pair and app-owned run→checkpoint-id→file linkage. Remaining identities, event reconciliation, exactly-once and external-effect questions stay [OQ-004](../open-questions.md#oq-004). Deep Agents file tools that target project storage for Chat land with [STATE-002](#state-002) / [Issue #22](https://github.com/Vidcar/thtaib/issues/22). Enabled catalogue includes visibility tools (`echo`, `time_now`) and filesystem tools (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`). Chat transcripts live in `application.sqlite` and are not the working project. [Issue #56](https://github.com/Vidcar/thtaib/issues/56) adds the Chat conversation→`thread_id`→run link so follow-ups resume the same checkpointer thread; displayed history remains not that thread.

## Requirements and acceptance checks

<a id="state-001"></a>
### STATE-001: Keep application records and execution checkpoints separate

Use separate application/checkpoint databases. Files hold models, projects, versioned knowledge, context captures, snapshots and artifacts. Application run records link profiles, deployments, environments, agent setup, parent/child runs, steps, threads, checkpoints, applied settings, evidence, optional budgets and recovery outcomes.

**Acceptance:** Follow a persisted run to its actual checkpoint and related files after restart. Verify that application records do not require direct mutation of the checkpointer's private tables.

Persisted profile, deployment, agent-setup and applied-setting fields are the durable copy of the [effective setup](../architecture.md#effective-setup-contract). A stored selected id is not by itself a loaded or applied claim.

<a id="state-002"></a>
### STATE-002: Do not confuse history with the working project

The backend owns thread identities, checkpoint namespaces and displayed history. Deep Agents file tools explicitly target project storage; conversation-state files are not a substitute for the working project.

**Acceptance:** Start a fresh conversation and inspect the retained project. Verify that changing displayed history alone neither restores nor deletes project files.

<a id="state-003"></a>
### STATE-003: Pair branches with consistent project snapshots

Pair checkpoint branching with an application-owned project snapshot captured at a consistent execution boundary. Record included files, exclusions, configuration and memory versions. Restore to a separate workspace, create a linked branch run and compare changes/artifacts/checks without modifying the original attempt.

**Acceptance:** Branch from a captured point, verify restored inputs and memory references, make changes in the branch and demonstrate that the original workspace/attempt is unchanged.

<a id="state-004"></a>
### STATE-004: Do not promise rollback of external effects

Snapshots do not undo external actions or restore a whole environment unless an adapter explicitly supports it. Preserve unresolved side effects. Reconnect/resume/restart must not silently repeat an operation whose outcome is unknown.

**Acceptance:** Crash between an external effect and its local acknowledgement. Recovery reports the uncertainty or reconciles with authoritative evidence rather than blindly retrying the operation. A `cancel_requested` run is still live: recovery must not treat that request as a confirmed stop or as permission to replay an unknown effect.

<a id="state-005"></a>
### STATE-005: Version durable knowledge and enforce its write policy

Preserve user, agent and project knowledge scopes, provenance, versions and reversible edits. Resolve concurrent writes and protect instructions from agent-written knowledge. Retention/redaction of context captures is configurable locally.

**Acceptance:** Demonstrate versioned edits/revert, a concurrent update conflict and an attempted protected-instruction overwrite. Verify the configured context-retention/redaction behaviour.

<a id="locked-milestone-defaults-issue-27-partial-oq-004"></a>
## Locked milestone defaults (Issue #27; partial OQ-004)

These defaults are authorised by [Issue #27](https://github.com/Vidcar/thtaib/issues/27). They satisfy [STATE-001](#state-001) dual-database separation and keep [STATE-002](#state-002) history ≠ project. They do **not** close [OQ-004](../open-questions.md#oq-004): identities, event reconciliation and exactly-once stay open. External-effect acknowledgement is the Issue #31 partial below.

- **App DB:** `%LOCALAPPDATA%\LocalAIWorkbench\application.sqlite` (or the same filename under the portable product root). Application system of record for runs, chat linkage, profile/deployment refs, checkpoint id links and file/artifact refs.
- **Checkpointer DB:** separate `%LOCALAPPDATA%\LocalAIWorkbench\checkpoints.sqlite` (LangGraph SQLite checkpointer). Application code links by checkpoint id only and never mutates checkpointer private tables.
- **Linkage:** app records link `run → checkpoint id(s) → files`. After restart, follow a persisted run to its checkpoint ids and related files via those application records.
- **Migration:** JSON run/chat linkage under `state\` migrates into the application DB. After cutover the application DB is the only system of record for that linkage (no dual-write).
- **STATE-002:** Chat history is not the working project. Filesystem tools write only to project storage. Editing or clearing displayed history alone neither restores nor deletes project files.
- **Surfaces:** backend persistence plus the existing Chat / Issue #22 history and project-path controls. No Builder canvas ([OQ-016](../open-questions.md#oq-016)).
- **Not claimed:** exactly-once across databases, files and services; event-order/reconnect contracts. External-effect acknowledgement for [STATE-004](#state-004) lands with Issue #31 as a partial; see the locked defaults below.

<a id="locked-milestone-defaults-issue-31-state-004"></a>
## Locked milestone defaults (Issue #31; STATE-004 / partial OQ-004)

These defaults are authorised by [Issue #31](https://github.com/Vidcar/thtaib/issues/31). They satisfy [STATE-004](#state-004) unknown-effect safety on the application ledger. They do **not** close [OQ-004](../open-questions.md#oq-004): identities, event-order/reconnection contracts and exactly-once across databases, files and services stay open. They are not a catalogue `verified` claim.

- **Ledger:** application-owned `external_effects` rows in `application.sqlite`. Outcomes: `dispatched`, `acknowledged`, `unknown`, `reconciled`, `failed`.
- **Crash/reconnect:** if acknowledgement is missing, recover/reconnect/resume/restart reports `unknown` and **does not** repeat the operation. `replayed` is always false. Authoritative evidence may `reconcile` without replay.
- **Snapshots:** do not undo external actions. `external_effect_rollback` is `not_supported`. `rollback_promise` is `none`. Unresolved side-effect ids are preserved on capture/restore. No whole-environment restore unless an adapter later declares it; the application ledger does not.
- **Surfaces:** `POST /v1/effects`, acknowledge / recover / reconcile, and a rollback path that returns 409. Lab snapshot/restore carry the honesty fields. No Builder canvas.
- **Not claimed:** exactly-once, a real worker-adapter interrupt (see [ENV-003](environments-tools.md#env-003)), or that reconnect event ordering is finished.

<a id="locked-milestone-defaults-issue-66-restore-integrity"></a>
## Locked milestone defaults (Issue #66; restore integrity / partial OQ-005)

These defaults are authorised by [Issue #66](https://github.com/Vidcar/thtaib/issues/66). They tighten [STATE-003](#state-003) restore honesty for the application-owned directory snapshot. They do **not** close [OQ-005](../open-questions.md#oq-005): retention, concurrent-writer details beyond “fail if live tools are writing”, environment-snapshot adapters and any mechanism other than this directory snapshot stay open. They are not a catalogue `verified` claim.

- **Tree is required.** Restore fails (`snapshot_tree_missing`) when the captured tree directory is absent. An empty `included_files` list is not a substitute for the tree. An intentionally empty snapshot keeps an empty tree directory and may restore to an empty workspace.
- **Manifest is authoritative.** Every recorded path/sha256/size must be present. A removed expected file (`snapshot_file_missing`) or changed bytes (`snapshot_hash_mismatch`) fails. Unexpected tree files fail (`snapshot_unexpected_file`).
- **Stage, then register.** Restore copies into a new workspace directory, verifies the destination against the manifest, and registers the restored workspace only after that check. Failed or incomplete staging is discarded. The parent workspace is not overwritten.
- **Not claimed:** retention, environment restore, a second snapshot system, or that a valid restore guarantees identical model output.

<a id="locked-milestone-defaults-issue-42-cancel-honesty"></a>
## Locked milestone defaults (Issue #42; cancel honesty / STATE-004 intersection)

These defaults are authorised by [Issue #42](https://github.com/Vidcar/thtaib/issues/42). They align [STATE-004](#state-004) unknown-effect recovery with harness cancel honesty. They do **not** close [OQ-004](../open-questions.md#oq-004). They are not a catalogue `verified` claim.

- **Cancel request ≠ confirmed stop.** `cancel_requested` means the worker may still be running. `cancelled` is the confirmed stop.
- **No false quiescence.** A workspace with a `cancel_requested` run is not idle. Snapshot capture must fail (`not_quiescent`) until the run is confirmed `cancelled`, `completed` or `failed`.
- **Unknown effects stay unknown.** Recover/reconnect/resume/restart of an effect linked to a `cancel_requested` (or otherwise live) run reports `unknown`, sets `replayed` false, and does not repeat the operation. The cancel request is not acknowledgement.
- **No rollback promise.** Snapshots still do not undo external actions. `rollback_promise` remains `none`.
- **Not claimed:** exactly-once, event-order/reconnection contracts, or worker-adapter interrupt truth.

<a id="locked-milestone-defaults-issue-56-chat-continuity"></a>
## Locked milestone defaults (Issue #56; Chat thread linkage / partial OQ-004)

These defaults are authorised by [Issue #56](https://github.com/Vidcar/thtaib/issues/56). They extend [STATE-001](#state-001) app-owned linkage and keep [STATE-002](#state-002) history ≠ project. They do **not** close [OQ-004](../open-questions.md#oq-004). They are not a catalogue `verified` claim.

- **Chat linkage:** application records store `conversation.id`, `conversation.thread_id`, and `run_ids`. Each Chat run records the same `thread_id` and its checkpoint ids. After restart, reopen the conversation and start again on that thread.
- **History ≠ thread:** replacing or clearing the displayed transcript does not mutate `checkpoints.sqlite` private tables, does not fork/reset the conversation thread, and neither restores nor deletes project files.
- **Fresh conversation:** a new conversation id and `thread_id`. The selected project directory and the application-owned knowledge store are not wiped.
- **Not claimed:** exactly-once, event-order/reconnection, or worker-adapter interrupt. Loading selected knowledge/profile content into the request is [Issue #57](https://github.com/Vidcar/thtaib/issues/57).

<a id="locked-milestone-defaults-issue-17-partial-oq-006"></a>
## Locked milestone defaults (Issue #17; partial OQ-006)

These defaults are authorised by [Issue #17](https://github.com/Vidcar/thtaib/issues/17). They satisfy [STATE-005](#state-005) and support [AGT-004](agents-workflows.md#agt-004) durable-knowledge rules. They do **not** close [OQ-006](../open-questions.md#oq-006): retrieval/RAG and cross-surface sharing stay open.

- **Store:** `%LOCALAPPDATA%\LocalAIWorkbench\knowledge\`. Application-owned files. Not checkpointer tables, not git, not `.scratch/`.
- **Representation:** versioned records — scope ∈ {user, agent, project}, kind ∈ {memory, skill, protected_instruction}, content, provenance, version id, parent/previous version, timestamps.
- **History:** append-only versions. Revert creates a new version that restores prior content; history is retained.
- **Concurrency:** optimistic. Writes require expected `base_version`. A mismatch is an explicit conflict (`knowledge_conflict`); no silent last-write-wins.
- **Protected instructions:** agent-origin writes are rejected. A human or API-maintainer path may edit with provenance.
- **Automatic agent writes:** only when an explicit scope policy allows them. Every write carries provenance (actor, and run id if any).
- **Context captures:** local config for retention duration and redaction mode. Default: retain with secrets redacted (`redact_secrets`). Configurable to retain plaintext or discard. The same config is the diagnostic-copy policy for [AGT-002](agents-workflows.md#agt-002) `model_requests` (including HTTP payloads) before `put_run()` persistence — see [Issue #64](#locked-milestone-defaults-issue-64-diagnostic-and-export-privacy).
- **Surfaces:** backend API (`/v1/knowledge/`) and an optional thin debug panel. No Chat or Builder UI.
- **Lab/harness:** knowledge version ids are referenceable from cases and harness setup, using the same pattern as profile and deployment refs. Those ids are **selected** facts. Loading their content into the configured backends is required by the [effective setup contract](../architecture.md#effective-setup-contract). Validating that an id exists is not applied knowledge. This is not a retrieval/RAG product.

<a id="locked-milestone-defaults-issue-64-diagnostic-and-export-privacy"></a>
## Locked milestone defaults (Issue #64; diagnostic and export privacy)

These defaults are authorised by [Issue #64](https://github.com/Vidcar/thtaib/issues/64) (tracking [Issue #58](https://github.com/Vidcar/thtaib/issues/58) finding 6). They satisfy the existing [STATE-005](#state-005) capture-policy acceptance and the [LAB-003](lab-evaluation.md#lab-003) export acceptance. They do **not** close [OQ-006](../open-questions.md#oq-006): retrieval/RAG and cross-surface sharing stay open.

- **One policy for diagnostic copies.** Knowledge context-capture `redaction_mode` / `retention_seconds` apply to persisted AGT-002 diagnostic copies (`run.model_requests`, including `http_payload` and other run-linked diagnostic fields) before SQLite persistence. Discard does not leave the raw capture in an alternate model-request or HTTP-payload field.
- **Separate operational retention.** Conversation transcripts, LangGraph checkpoints, and operational run event history are **not** discarded by the context-capture discard setting. Those records follow a separate operational retention policy so execution recovery is not silently broken.
- **Safe provenance kept.** Tool names, knowledge version refs, capture gaps and timestamps remain when diagnostic bodies are redacted, discarded or expired.
- **Shareable case export.** `export_case` sanitizes detectable unsafe content in task text, tool fixtures and ordinary included files, or **blocks** the export. `secret_scan_clean` is true only when the original scan found no detector hit. A false scan-clean flag beside unchanged unsafe output is a defect.
- **Detector limits.** The detector is the pattern list in the Knowledge redaction module. It is incomplete. A clean scan is not proof that no secret is present. Tests and evidence use synthetic credentials only — never real secrets.

## Unresolved details

Issue #27 locked the dual-DB and app-linkage defaults above. Issue #31 locked the [STATE-004](#state-004) unknown-effect ledger (no silent replay; no external-effect rollback promise). Issue #42 locked cancel request versus confirmed stop and the [STATE-004 intersection](#locked-milestone-defaults-issue-42-cancel-honesty) (no false quiescence; no silent replay while `cancel_requested`). [Issue #52](https://github.com/Vidcar/thtaib/issues/52) records the high-level [conversation ↔ execution-thread ↔ run](agents-workflows.md#high-level-agent-chat-continuity-issue-52) product mapping and the [STATE-002 intersection](#high-level-agent-chat-continuity-issue-52) below. Resolve the remainder of [OQ-004](../open-questions.md#oq-004) for identities, event ordering/reconnection and exactly-once. [Issue #66](https://github.com/Vidcar/thtaib/issues/66) locked [restore integrity](#locked-milestone-defaults-issue-66-restore-integrity) (missing tree / hash mismatch / unexpected files fail; no silent empty restore). [OQ-005](../open-questions.md#oq-005) covers remaining snapshot policy. [OQ-006](../open-questions.md#oq-006) remains open for retrieval/RAG, indexing and cross-surface sharing; the store defaults above do not select those. Issue #64 locked diagnostic-copy and export privacy against the existing capture policy; it does not close OQ-006. No exactly-once guarantee or migration library is selected by revision 0.5.

<a id="high-level-agent-chat-continuity-issue-52"></a>
## High-level Agent Chat continuity (Issue #52; STATE-001 / STATE-002 intersection)

These defaults are authorised by [Issue #52](https://github.com/Vidcar/thtaib/issues/52). They restate the persistence side of Agent Chat continuity. Behavioural Chat rules live in [agents and workflows](agents-workflows.md#high-level-agent-chat-continuity-issue-52). They do **not** close [OQ-004](../open-questions.md#oq-004). They are not a catalogue `verified` claim and not an implementation.

- **Conversation** is an application Chat record in `application.sqlite`: displayed history, bound project / deployment / profile refs, and links to runs. It is not the working project and not the harness loop.
- **Execution thread** is the application-owned continuation identity. LangGraph owns checkpoint bytes. The application stores thread / checkpoint ids only and never mutates checkpointer private tables ([STATE-001](#state-001)).
- **Run** is one harness invocation. Application records keep `conversation → run → thread id → checkpoint id(s) → files`. After restart, continue follows that linkage. Missing linkage is an explicit gap, not a silent new thread presented as the same conversation.
- **Continue** reuses the conversation and execution thread and starts a new run. The displayed transcript is not a substitute for that thread.
- **Fresh** creates a new conversation and a new execution thread. Selected project files and permitted durable knowledge are retained. Previous active context is not inherited ([AGT-004](agents-workflows.md#agt-004)).
- **STATE-002:** editing or clearing displayed history alone neither restores nor deletes project files. A display-only history edit does not silently become the next model request. Making edited history into execution context is an explicit new attempt; the branch / checkpoint mechanism stays [OQ-004](../open-questions.md#oq-004) / [STATE-003](#state-003).
- **Surfaces:** Chat. Agent-run is not Chat. No Builder canvas. No Model Lab and no Task-case replay in this mapping.
- **Not claimed:** identity formats; event-order / reconnection; exactly-once; Chat polish. Effective setup apply-for-real is [Issue #57](https://github.com/Vidcar/thtaib/issues/57).
