# State Recovery

## Purpose

Specify how Local AI Workbench persists enough to explain, continue, branch, restore, and compare runs after restart while keeping chat history, project files, snapshots, external effects, and durable knowledge distinct.

## Requirements

### Requirement: STATE-001 - Keep application records and execution checkpoints separate

The application SHALL keep application records in application.sqlite and LangGraph checkpoint bytes in checkpoints.sqlite. Files SHALL hold models, projects, versioned knowledge bodies, context captures, snapshots, artifacts and logs. Application run records SHALL link profiles, deployments, environments, agent setup, parent and child runs, steps, threads, checkpoint ids, applied settings, evidence, optional budgets and recovery outcomes. Interaction identity mappings and durable public projection/replay records SHALL reuse application persistence; checkpoints SHALL remain execution authority accessed only through supported public APIs. A selected id or frontend projection MUST NOT claim a value was loaded, applied or completed.

#### Scenario: Follow persisted run

- WHEN a persisted run is followed after backend restart
- THEN application records MUST locate its checkpoint ids, interaction identities and related files
- AND the application MUST NOT mutate private checkpointer tables or invoke the model simply to rebuild the display.

### Requirement: STATE-002 - Do not confuse history with the working project

The backend SHALL own thread identities, checkpoint namespaces and displayed history. The readable archive MAY retain more history than compacted runtime context. Hydration SHALL preserve that history while identifying the checkpoint as execution authority. Deep Agents file tools SHALL target project storage; conversation-state and harness internal paths MUST NOT substitute for the working project. Editing or clearing displayed history MUST NOT restore, delete, fork or reset project files or execution state.

Legacy history without IDs SHALL preserve chronological order and repeated-message multiplicity. Runtime identity SHALL use durable identity/provenance or reliable ordered alignment, never an earlier equal-text match alone. Ambiguous records SHALL retain deterministic display-only identity and the original readable archive. Content blocks, reasoning and checkpoint tool calls/results SHALL retain their meaningful ordering relative to confidently matched turns.

#### Scenario: History edit

- WHEN displayed history is changed after a project-bound file-writing turn
- THEN project files MUST remain unchanged by that display edit
- AND harness-internal paths MUST NOT appear in the project or be reconstructed from edited display history.

#### Scenario: Existing compacted conversation

- WHEN a pre-migration conversation is reopened after its runtime context was compacted
- THEN its full retained readable history, project/settings references and checkpoint association MUST survive
- AND continuation MUST use the existing checkpoint rather than replaying the archive.

#### Scenario: Repeated text with compacted suffix

- WHEN an ID-less transcript contains repeated user or assistant text and execution retains only a suffix
- THEN registration and repeated reopening MUST preserve exact readable chronology and multiplicity
- AND stable established identities, content blocks, reasoning and tool outcomes MUST survive without duplicate outcomes or a model/tool invocation.

### Requirement: STATE-003 - Pair branches with consistent project snapshots

Checkpoint branching SHALL be paired with an application-owned project snapshot captured at a quiescent execution boundary. Snapshot records SHALL include included files, exclusions, configuration, and memory versions. Restore SHALL stage into a separate workspace, verify every recorded path, hash, and size, reject unexpected files or missing trees, and register the workspace only after verification.

#### Scenario: Branch from snapshot

- WHEN a branch is created from a captured point
- THEN restored inputs and memory references MUST be verified
- AND changes in the branch MUST NOT modify the original workspace or attempt.

### Requirement: STATE-004 - Do not promise rollback of external effects

Snapshots SHALL NOT undo external actions or restore a whole environment unless an adapter explicitly supports it. External effects without acknowledgement after crash, reconnect, or restart SHALL remain `unknown` until reconciled with authoritative evidence. Unknown operations MUST NOT be silently replayed. `cancel_requested` SHALL remain live until confirmed stop.

#### Scenario: Crash after external effect

- WHEN a crash occurs between external effect dispatch and local acknowledgement
- THEN recovery MUST report uncertainty or reconcile against authoritative evidence
- AND it MUST NOT treat a cancel request as confirmed stop or permission to replay.

### Requirement: STATE-005 - Version durable knowledge and enforce its write policy

Durable knowledge SHALL preserve user, agent, and project scopes; `memory`, `skill`, and `protected_instruction` kinds; provenance; append-only versions; and reversible edits through new versions. Writes SHALL name an expected base version and report conflicts. Protected instructions SHALL reject agent-origin writes. Context-capture retention and redaction SHALL be local configuration and SHALL govern persisted diagnostic copies of model requests.

#### Scenario: Knowledge write policy

- WHEN memory is edited, reverted, concurrently updated, or a protected instruction is overwritten by an agent
- THEN version history, conflict behavior, and protected-instruction rejection MUST be enforced
- AND configured context-retention and redaction behavior MUST be applied.

### Requirement: STATE-006 - Retrieve through LangChain components, not a second knowledge store

Retrieval SHALL be requested only when the run names an embedding deployment. Knowledge-only runs SHALL load selected versions through the normal memory, skills, and protected-instruction paths and MUST NOT fail closed just because retrieval is absent. When retrieval is requested for a live-tool run, `search_knowledge` SHALL be auto-presented over a derived in-memory index built from selected content and discarded with the run. The vector index MUST NOT become a durable knowledge owner.

#### Scenario: Retrieval with and without embedder

- WHEN a live-tool run names a loaded embedding deployment and selected knowledge
- THEN search results MUST be written under harness scratch, not the project, and captures MUST list retrieved sources
- AND when the named embedder is missing, unloaded, unconfigured, has no pooling, or the corpus is empty, the run MUST fail closed and invent no hits.

### Requirement: STATE-007 - Use SQLite for new mutable application records

New mutable application records SHALL use the existing `application.sqlite`, transaction, schema metadata, and migration log. LangGraph checkpoints SHALL remain separately owned. Existing JSON record families SHALL remain authoritative until an inventory-checked, backed-up, interruption-tested, idempotent import and cutover is validated. The product MUST NOT dual-write two authorities or introduce another database framework for those records.

#### Scenario: JSON family migration

- WHEN a JSON-backed record family is prepared for migration
- THEN the migration MUST inventory records and references, back up SQLite, retain original JSON, validate a copied data root, compare every record and reference, test interrupted imports and restart, and make cutover explicit
- AND rollback claims MUST NOT be made after new writes unless replay or export has been tested.

### Requirement: STATE-008 - Keep harness scratch out of project and durable stores

Harness-internal files, including large tool results, conversation history, retrieval offloads, materialized memory files, and materialized skill files, SHALL route to harness scratch under the product data root or state backend. They MUST NOT appear in the project, knowledge store, or invented stand-in folders. Durable memory write-through, when enabled by policy, SHALL create a STATE-005 version rather than treating scratch files as the source of truth.

#### Scenario: Harness file routing

- WHEN a live run materializes memory, skills, retrieval output, or filesystem middleware files
- THEN those paths MUST resolve under harness scratch or state backend
- AND project storage and durable knowledge bodies MUST remain separate.

### Requirement: STATE-015 - Recover interaction projections without replaying effects

Interaction hydration and replay SHALL provide an atomic cutover to live events with stable identities and bounded transient buffering. Thread-level cursors SHALL remain distinct from run-local native sequences. Unavailable or expired replay positions SHALL trigger explicit resynchronization from durable application records. Restart recovery SHALL preserve real partial output and actual tool outcomes; uncertain effects MUST remain unknown and MUST NOT be repeated to repair presentation. Any required application-record migration SHALL be recoverable, idempotent and verified on isolated copies before cutover.

Already-registered faulty legacy projections SHALL be repaired narrowly and idempotently from original readable history and available durable provenance. Repair SHALL preserve subsequent turns, partial output, tool history, explicit display-only edits and replay cutovers. It SHALL NOT blindly reseed all bindings, restore deliberately hidden messages, reset runtime threads, mutate private checkpoint tables or claim uncertain reconstruction is exact.

#### Scenario: Gap and backend restart

- WHEN an observer reconnects after a replay gap or backend restart
- THEN it MUST receive controlled resynchronization and truthful persisted outcome or uncertainty
- AND neither resubscription nor hydration MUST execute a tool or create another run.

#### Scenario: Existing faulty archive and later edits

- WHEN a provably affected persisted projection is reopened after subsequent output or a display-only edit
- THEN safe repair MUST preserve later content and hidden-message/cutover semantics and be idempotent on repeat
- AND project files and checkpoint association MUST remain unchanged, with continuation on the existing runtime thread and no additional model/tool invocation from repair.

### Requirement: STATE-009 - Retain authorized files and verify actual outputs

This requirement SHALL retain the verified `repair-local-interaction-boundaries` guarantees: repeated-text legacy chronology and multiplicity, stable or deterministic display identity, narrow idempotent repair, preserved later/partial/tool output and display-edit replay cutovers, with no hidden-message resurrection or execution replay. That prerequisite does not implement retained uploads, deletion or backup features.

One retained-file/artifact contract SHALL identify origin, session/project/access scope, storage ownership, content type, size/hash, observation time and source run/tool where applicable. Mutable project references SHALL be distinct from immutable retained upload/output snapshots; access and mutable identity are rechecked on open/reuse. Old path-only records remain unverified until checked. Tool arguments/model-written paths are attempted operations, not artifacts: successful result and required file observations establish outputs. Scratch/history/offloads are not project outputs.

Chat SHALL support text/code picker and drag/drop, actual content/encoding/limit validation, removable staging and attachment-only turns. Sent originals are retained session-scoped by default without a project or automatic knowledge promotion. Fitting source-labelled content SHALL enter current-user input even with tools off. Larger material requires authorized scoped reading or an actionable capacity outcome, not silent truncation or tool/host authority. Copy bytes only for deliberate retention; persist attachment provenance across reopening.

A shared Library SHALL browse retained attachments and verified outputs across authorized conversations/projects with scope filters and original conversation/project provenance. Inline reply entries and the on-demand Files panel SHALL use the same records and distinguish retained copies from mutable project references. Supported preview/open/save/reuse/delete actions SHALL preserve access checks and dependency-aware deletion. Library MUST NOT create a second artifact authority, grant additional access or indiscriminately catalogue project files; later project and media views extend this contract.

#### Scenario: Attachment with tools off

- **WHEN** a non-project turn contains only a fitting supported text/code attachment
- **THEN** the retained authorized original and labelled content are usable without enabling filesystem/shell/retrieval tools.

#### Scenario: Attempt versus verified output

- **WHEN** a write fails or a previously observed project file changes
- **THEN** no successful artifact is invented and stale content verification is not reused.

#### Scenario: Find a retained output from another conversation

- **WHEN** a user filters Library by project and opens or reuses an older retained output
- **THEN** its source conversation/project and retained-versus-mutable identity remain visible, current access is checked and reuse does not move the source session or grant project access.

### Requirement: STATE-010 - Delete deliberately while preserving shared dependencies

This requirement SHALL retain the verified `repair-local-interaction-boundaries` guarantees: repeated-text legacy chronology and multiplicity, stable or deterministic display identity, narrow idempotent repair, preserved later/partial/tool output and display-edit replay cutovers, with no hidden-message resurrection or execution replay. That prerequisite does not implement retained uploads, deletion or backup features.

Conversations, sent originals and verified retained outputs SHALL remain until deliberate dependency-aware deletion. Diagnostics SHALL have separately inspectable collection/retention controls; staging cleanup must not erase submitted assets. Deletion SHALL preview affected/retained sessions, runs, branches, checkpoints, scratch, originals, outputs and diagnostics; coordinate active work and use supported checkpoint APIs. Surviving branches, Lab cases and Workflows retain needed shared content. Project source files, committed knowledge, remote copies and earlier backups/exports MUST NOT be incidentally deleted. Unlink, archive, delete and diagnostic cleanup have distinct effects; secure physical erasure or complete forgetting MUST NOT be claimed.

#### Scenario: Shared asset deletion

- **WHEN** a deleted conversation shares checkpoints/assets with retained consumers
- **THEN** the preview and cleanup preserve required references and state accurately what remains, including external/backup copies.

### Requirement: STATE-011 - Back up manually and restore to a clean verified destination

This requirement SHALL retain the verified `repair-local-interaction-boundaries` guarantees: repeated-text legacy chronology and multiplicity, stable or deterministic display identity, narrow idempotent repair, preserved later/partial/tool output and display-edit replay cutovers, with no hidden-message resurrection or execution replay. That prerequisite does not implement retained uploads, deletion or backup features.

The system SHALL provide readable conversation export and a separate on-demand versioned application backup; no automatic backup schedule is required or activated. Backup SHALL consistently capture application records, compatible checkpoints, retained assets and linkage through verified snapshot/quiescence handling, with manifests/integrity checks. Exclude credentials by default, flag sensitive content and distinguish included bytes from external project/model references.

Restore SHALL use a clean application-data destination, validate data/checkpoint/runtime compatibility and integrity, retain branch/asset linkage and expose missing models, project paths and credential bindings. Reconcile runs without restarting uncertain effects. Later knowledge, setup, Lab, Workflow and media records extend this same format. A readable export or inconsistent live database copy is not a restorable application backup.

#### Scenario: Backup and restore

- **WHEN** an on-demand backup is restored with some external dependencies absent
- **THEN** integrity and linkage are verified in a clean root, missing dependencies are shown and no uncertain action is automatically replayed.

### Requirement: STATE-017 - Render file changes from the stored images

A project-file change SHALL keep its before and after images, including text when the existing capture rules can read it, keyed by the tool call that made the change. The Changes page and the activity-line counts SHALL use those images. Added and removed counts are the added and removed content lines of that observed difference, excluding diff headers. A pre-rendered unified-diff string remains available to copy. It MUST NOT be the view and MUST NOT be a second record. When the text is unavailable, the view says so and the counts are omitted. Presenting the change MUST NOT call the model, write the file, or treat the diff as a rollback of anything beyond the existing single-file reverse.

#### Scenario: Counts match the stored texts

- **WHEN** a change has before and after text and the activity line shows added and removed counts
- **THEN** those counts are the observed difference of those two texts
- **AND** a copied unified diff is not stored as another change.

#### Scenario: No text

- **WHEN** a change has no captured text
- **THEN** the diff view explains that the difference is unavailable and the activity line omits added and removed counts.

### Requirement: STATE-018 - Archive immediately and delete a chat without its project files

Archiving a conversation SHALL remove it from the active list and from active search at once. It remains available under archived conversations and can be reopened. Permanently deleting a chat SHALL remove that chat's history, drafts, queue, and its own run records after confirmation. The confirmation says project files and model files stay. Project files MUST remain byte for byte. Deletion waits until that chat's own work has stopped. Shared records another conversation still needs are kept, and the confirmation says so when that is the case.

#### Scenario: Archive from the active list

- **WHEN** a person archives the conversation they are reading
- **THEN** it leaves the active list immediately
- **AND** they can reopen it from archived conversations.

#### Scenario: Delete a project chat

- **WHEN** a person confirms deletion of a chat whose project contains files the agent wrote
- **THEN** the chat history is gone
- **AND** those project files are still in the project folder.

### Requirement: STATE-019 - Import a skill package without running it

A skill SHALL be importable as one skill file or as a folder or archive that contains the skill file plus relative scripts, references, and assets. The import SHALL reject path traversal, links that escape the package, and Windows reserved names. Imported scripts MUST NOT run as part of import. The Knowledge screen lists the skill by name, shows the files it contains, and lets the person select or clear it for a later conversation. Selecting it uses the official skills path on the next turn. It does not execute the package.

#### Scenario: Import does not execute

- **WHEN** a person imports a skill package that contains a script
- **THEN** the skill appears in the list with its files
- **AND** the script has not been run.

### Requirement: STATE-020 - Extract supported documents without a source-inspection journey

A retained text, code, CSV, JSON, text-bearing PDF, or DOCX file SHALL be extractable locally. The result keeps the parser outcome: read, empty, encrypted, malformed, or unsupported. A scanned document without optical character recognition MUST NOT be described as understood. Extraction does not add a screen for inspecting a quote's source location. That journey stays out of this contract. The file itself remains openable in the Files dock when it is text or an image the dock already shows.

#### Scenario: Encrypted PDF

- **WHEN** a retained PDF is encrypted
- **THEN** the extraction says it could not be read
- **AND** the product does not present invented document text.
