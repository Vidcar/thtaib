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

#### Scenario: Temporary project reservation ends without a run event
- **WHEN** a Lab capture or failed pre-run admission releases a project folder after a Chat task has queued for it
- **THEN** the existing queue SHALL resume eligible work after release without requiring another user action or run event
- **AND** no work SHALL start while the reservation remains held.

#### Scenario: Cancel a queued input with no worker
- **WHEN** cancellation safely pauses a queued-only input and no admission or dispatch remains in flight for it
- **THEN** pending cancellation SHALL settle without waiting for a nonexistent worker or requiring restart
- **AND** its cancellation identity SHALL continue to prevent a late duplicate dispatch and SHALL NOT cancel the other project owner.

### Requirement: STATE-004 - Do not promise rollback of external effects

Snapshots SHALL NOT undo external actions or restore a whole environment unless an adapter explicitly supports it. External effects without acknowledgement after crash, reconnect, or restart SHALL remain `unknown` until reconciled with authoritative evidence. Unknown operations MUST NOT be silently replayed. `cancel_requested` SHALL remain live until confirmed stop.

#### Scenario: Crash after external effect

- WHEN a crash occurs between external effect dispatch and local acknowledgement
- THEN recovery MUST report uncertainty or reconcile against authoritative evidence
- AND it MUST NOT treat a cancel request as confirmed stop or permission to replay.

#### Scenario: Desktop control outcome is uncertain after dispatch
- **WHEN** a desktop control action is dispatched and acknowledgement times out or the target window identity changes before its result is verified
- **THEN** its durable outcome SHALL remain uncertain and require inspection or explicit acknowledgement before dependent continuation
- **AND** it SHALL NOT be converted to an ordinary correctable tool failure or automatically replayed; a refusal before dispatch remains distinguishable.
