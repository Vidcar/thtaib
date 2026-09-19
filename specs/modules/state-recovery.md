# State, memory and recovery

[Specification index](../README.md) · [Status and evidence](../catalog.json)

## Ownership, scope and source

Application SQLite records and files store workbench data; the separate LangGraph SQLite checkpointer stores execution state. The application links them. Source: [revision 0.5, pages 4–6](../sources/README.md#application-infrastructure), including [owned records](../sources/README.md#models-and-inference) and [knowledge policy](../sources/README.md#agents-and-workflows).

## Public contracts and collaboration

The application owns run/thread identities, checkpoint namespaces, displayed history, artifact/context references, knowledge versions and snapshot records. LangGraph owns the checkpoint representation/runtime. A snapshot provider captures/restores project files; worker adapters declare environment capabilities and effects. Retrieval is separate from project memory and does not train the model.

Do not infer a distributed transaction between application SQLite, checkpointer SQLite, files and remote services. Their consistency/reconciliation strategy is unresolved and must be decided before recovery or snapshot-aware branching is claimed.

## Lifecycle and failure

Persist enough linkage to explain a run after restart, including selected configuration and recovery outcome. A recoverable checkpoint, a restorable project and a reconnectable environment are separate capabilities. Recovery must reconcile them before resuming effects. A branch creates a linked attempt without overwriting its parent.

Issue #15 locks the STATE-003 snapshot defaults used by Lab reuse: an application-owned directory snapshot (not a git commit), captured at a quiescent boundary, stored under `%LOCALAPPDATA%\LocalAIWorkbench\cases\` and `snapshots\`, restored into a new workspace, with secrets/weights/scratch/venv/node_modules/credentials excluded and no full environment restore. Remaining snapshot policy stays [OQ-005](../open-questions.md#oq-005). External-effect rollback stays [STATE-004](#state-004).

Issue #17 locks the STATE-005 durable-knowledge store defaults used by the backend API and Lab/harness version refs. Retrieval/RAG and cross-surface sharing stay [OQ-006](../open-questions.md#oq-006).

Issue #27 locks the STATE-001 dual SQLite pair and app-owned run→checkpoint-id→file linkage. Remaining identities, event reconciliation, exactly-once and external-effect questions stay [OQ-004](../open-questions.md#oq-004). Deep Agents file tools that target project storage for Chat land with [STATE-002](#state-002) / [Issue #22](https://github.com/Vidcar/thtaib/issues/22). Enabled catalogue includes visibility tools (`echo`, `time_now`) and filesystem tools (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`). Chat transcripts live in `application.sqlite` and are not the working project.

## Requirements and acceptance checks

<a id="state-001"></a>
### STATE-001: Keep application records and execution checkpoints separate

Use separate application/checkpoint databases. Files hold models, projects, versioned knowledge, context captures, snapshots and artifacts. Application run records link profiles, deployments, environments, agent setup, parent/child runs, steps, threads, checkpoints, applied settings, evidence, optional budgets and recovery outcomes.

**Acceptance:** Follow a persisted run to its actual checkpoint and related files after restart. Verify that application records do not require direct mutation of the checkpointer's private tables.

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

**Acceptance:** Crash between an external effect and its local acknowledgement. Recovery reports the uncertainty or reconciles with authoritative evidence rather than blindly retrying the operation.

<a id="state-005"></a>
### STATE-005: Version durable knowledge and enforce its write policy

Preserve user, agent and project knowledge scopes, provenance, versions and reversible edits. Resolve concurrent writes and protect instructions from agent-written knowledge. Retention/redaction of context captures is configurable locally.

**Acceptance:** Demonstrate versioned edits/revert, a concurrent update conflict and an attempted protected-instruction overwrite. Verify the configured context-retention/redaction behaviour.

<a id="locked-milestone-defaults-issue-27-partial-oq-004"></a>
## Locked milestone defaults (Issue #27; partial OQ-004)

These defaults are authorised by [Issue #27](https://github.com/Vidcar/thtaib/issues/27). They satisfy [STATE-001](#state-001) dual-database separation and keep [STATE-002](#state-002) history ≠ project. They do **not** close [OQ-004](../open-questions.md#oq-004): identities, event reconciliation, exactly-once and external-effect remainder stay open.

- **App DB:** `%LOCALAPPDATA%\LocalAIWorkbench\application.sqlite` (or the same filename under the portable product root). Application system of record for runs, chat linkage, profile/deployment refs, checkpoint id links and file/artifact refs.
- **Checkpointer DB:** separate `%LOCALAPPDATA%\LocalAIWorkbench\checkpoints.sqlite` (LangGraph SQLite checkpointer). Application code links by checkpoint id only and never mutates checkpointer private tables.
- **Linkage:** app records link `run → checkpoint id(s) → files`. After restart, follow a persisted run to its checkpoint ids and related files via those application records.
- **Migration:** JSON run/chat linkage under `state\` migrates into the application DB. After cutover the application DB is the only system of record for that linkage (no dual-write).
- **STATE-002:** Chat history is not the working project. Filesystem tools write only to project storage. Editing or clearing displayed history alone neither restores nor deletes project files.
- **Surfaces:** backend persistence plus the existing Chat / Issue #22 history and project-path controls. No Builder canvas ([OQ-016](../open-questions.md#oq-016)).
- **Not claimed:** exactly-once across databases, files and services; event-order/reconnect contracts; external-effect acknowledgement.

<a id="locked-milestone-defaults-issue-17-partial-oq-006"></a>
## Locked milestone defaults (Issue #17; partial OQ-006)

These defaults are authorised by [Issue #17](https://github.com/Vidcar/thtaib/issues/17). They satisfy [STATE-005](#state-005) and support [AGT-004](agents-workflows.md#agt-004) durable-knowledge rules. They do **not** close [OQ-006](../open-questions.md#oq-006): retrieval/RAG and cross-surface sharing stay open.

- **Store:** `%LOCALAPPDATA%\LocalAIWorkbench\knowledge\`. Application-owned files. Not checkpointer tables, not git, not `.scratch/`.
- **Representation:** versioned records — scope ∈ {user, agent, project}, kind ∈ {memory, skill, protected_instruction}, content, provenance, version id, parent/previous version, timestamps.
- **History:** append-only versions. Revert creates a new version that restores prior content; history is retained.
- **Concurrency:** optimistic. Writes require expected `base_version`. A mismatch is an explicit conflict (`knowledge_conflict`); no silent last-write-wins.
- **Protected instructions:** agent-origin writes are rejected. A human or API-maintainer path may edit with provenance.
- **Automatic agent writes:** only when an explicit scope policy allows them. Every write carries provenance (actor, and run id if any).
- **Context captures:** local config for retention duration and redaction mode. Default: retain with secrets redacted (`redact_secrets`). Configurable to retain plaintext or discard.
- **Surfaces:** backend API (`/v1/knowledge/`) and an optional thin debug panel. No Chat or Builder UI.
- **Lab/harness:** knowledge version ids are referenceable from cases and harness setup, using the same pattern as profile and deployment refs.

## Unresolved details

Issue #27 locked the dual-DB and app-linkage defaults above; resolve the remainder of [OQ-004](../open-questions.md#oq-004) for identities/state transitions/effect reconciliation. [OQ-005](../open-questions.md#oq-005) covers remaining snapshot policy. [OQ-006](../open-questions.md#oq-006) remains open for retrieval/RAG, indexing and cross-surface sharing; the store defaults above do not select those. External-effect rollback stays [STATE-004](#state-004). No exactly-once guarantee, snapshot implementation or migration library is selected by revision 0.5.
