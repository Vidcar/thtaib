## MODIFIED Requirements

### Requirement: STATE-003 - Pair branches with consistent project snapshots

Checkpoint branching SHALL be paired with an application-owned project snapshot. Only one root task family SHALL hold an actual project/workspace folder at a time. Aliases and overlapping folders SHALL conflict. Other submitted Chat tasks SHALL wait durably in the existing conversation queue before loading models, taking starting snapshots or executing. Direct Agent/Lab start APIs SHALL reject a busy root before those effects rather than bypass the shared reservation or create a second queue. Helpers share the root reservation. Ownership SHALL remain through approvals, questions, cancellation settlement and final snapshots. Known settled outcomes release ownership; uncertain effects require bounded read-only reconciliation before another task advances. If evidence remains inconclusive, explicit acknowledgement SHALL preserve the uncertain result and record the decision without replaying the action. Lab case capture SHALL hold the same folder reservation throughout capture, and application backup SHALL retain its global maintenance exclusion. Snapshot records SHALL include included files, exclusions, configuration, and memory versions. Restore SHALL stage into a separate workspace, verify every recorded path, hash, and size, reject unexpected files or missing trees, and register the workspace only after verification.

#### Scenario: Branch from snapshot

- WHEN a branch is created from a captured point
- THEN restored inputs and memory references MUST be verified
- AND changes in the branch MUST NOT modify the original workspace or attempt.

#### Scenario: Second run in a busy folder

- WHEN a new Chat task is submitted in a project or workspace that already has a live run
- THEN the task MUST wait with its accepted input and frozen setup retained, and unrelated non-overlapping folders SHALL continue independently
- AND Lab case capture and application backup MUST still refuse to copy while a run is live.

#### Scenario: Direct API cannot bypass a busy project
- **WHEN** an Agent or Lab start API targets an owned folder or an overlapping alias
- **THEN** it SHALL return `project_busy` before model loading, snapshots or execution, with the current owner identified when available.

#### Scenario: Waiting order is stable within the same timestamp
- **WHEN** several messages are accepted within one clock timestamp
- **THEN** their durable admission order SHALL determine FIFO progression, and paused work SHALL NOT obstruct other eligible chats.

#### Scenario: Projectless continuation after an unconfirmed action
- **WHEN** an earlier run on the same thread has unacknowledged uncertain browser, desktop or external-tool effects, with or without a project folder
- **THEN** a new Chat or direct Agent run SHALL be refused before model preparation or new effects, and queued continuation SHALL remain paused for inspection
- **AND** acknowledgement SHALL preserve the original uncertain evidence and allow continuation without replay, while live approval and question resumes SHALL retain their existing owned-run path.

#### Scenario: Restart and waiting cancellation
- **WHEN** the backend restarts or a waiting message is cancelled
- **THEN** accepted input identities SHALL remain idempotent, uncertain work SHALL NOT replay, and cancelling a waiter SHALL NOT cancel its current project owner.

### Requirement: STATE-006 - Retrieve through LangChain components, not a second knowledge store

Selected retained documents and explicitly allowed project text SHALL support bounded local text search without an embedding model. Optional similarity search SHALL use a derived run-owned index constructed lazily on its first query and discarded with the run. Automatically loaded memory, protected instructions and progressively loaded skills SHALL NOT be redundantly embedded. A deliberately selected unavailable embedding model SHALL report its actual availability and MUST NOT label lexical results as similarity results. Mutable project sources SHALL be revalidated before reuse.

#### Scenario: Retrieval with and without embedder
- **WHEN** a user selects documents without an embedding model
- **THEN** text search SHALL return bounded matches with source identity, location and truthful continuation information
- **AND** choosing similarity search SHALL build its index only when used and preserve source facts in scratch offloads and captures.

#### Scenario: Selected context is already loaded
- **WHEN** only memory, skills or protected instructions are selected
- **THEN** their normal context paths SHALL remain available and no redundant embedding request SHALL occur.

#### Scenario: Selected document search becomes idle
- **WHEN** the last selected document or allowed project source is removed while document search remains selected
- **THEN** the next turn SHALL remain usable with that search tool absent until authorized sources are selected again
- **AND** Tools off SHALL never enable document search, while Plan MAY use authorized read-only document search without an embedding model.

### Requirement: STATE-020 - Extract supported documents without a source-inspection journey

A retained text, code, CSV, JSON, text-bearing PDF, or DOCX file SHALL be extractable locally. The result keeps the parser outcome: read, empty, encrypted, malformed, or unsupported. A scanned document without optical character recognition MUST NOT be described as understood. Accepted attachments SHALL remain available throughout their conversation until removed from future selection. Each submitted turn SHALL freeze its selected document identities; future catalogue injection SHALL remain compact and text SHALL be read on demand. Source links SHALL open the existing retained viewer at the available page/section/line. Search limits and match pagination SHALL be truthful; removal MUST NOT widen other conversations' access.

Document reading SHALL bound the complete serialized model-visible result, including citation metadata and escaping. Ready-to-copy immutable source links SHALL identify original content and exact locations; continuation SHALL cover remaining matches or clipped content without silently dropping it. Source identity SHOULD be shared within a result where it does not require the model to construct its own citation URL.

#### Scenario: Encrypted PDF

- **WHEN** a retained PDF is encrypted
- **THEN** the extraction says it could not be read
- **AND** the product does not present invented document text.

#### Scenario: Follow-up document question
- **WHEN** a later turn searches a previously attached document without an embedding model or reattachment
- **THEN** the selected document SHALL remain readable with the correct original source location
- **AND** removing it excludes it from future submitted turns while already submitted turns keep their frozen selections.

### Requirement: STATE-021 - Finalize runs and snapshots safely

Execution settlement SHALL be persisted before project capture, and restart recovery SHALL use that settlement without rerunning model or tool effects. Project capture SHALL run without holding the harness-wide lock, stage and verify its files before publishing a snapshot, and remove only incomplete owned staging after a failure. Capture failure SHALL leave the execution outcome intact and identify branching as unavailable. Final branch snapshots SHALL include safe project files created by the run. The captured folder SHALL retain its project-family reservation through finalization while unrelated non-overlapping projects can progress.

#### Scenario: Concurrent run during capture

- **WHEN** one run is saving a large project snapshot while another run in a non-overlapping project makes progress
- **THEN** the second run's observation and execution can progress without acquiring the captured folder
- **AND** the first run publishes one terminal outcome after capture settles.

#### Scenario: Terminal write retry while another worker is live

- **WHEN** one run's terminal record write fails transiently while another worker remains active
- **THEN** recovery retries the settled run without marking the owned worker orphaned
- **AND** each run publishes at most one confirmed terminal outcome.

#### Scenario: Restart or capture failure

- **WHEN** the application restarts or capture fails after execution settles
- **THEN** finalization uses the saved outcome without replaying effects
- **AND** a failed capture has no published partial snapshot and reports branching unavailable.
