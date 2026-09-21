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
