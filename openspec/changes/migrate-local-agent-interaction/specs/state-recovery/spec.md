## MODIFIED Requirements

### Requirement: STATE-001 - Keep application records and execution checkpoints separate

The application SHALL keep application records in application.sqlite and LangGraph checkpoint bytes in checkpoints.sqlite. Files SHALL hold models, projects, versioned knowledge bodies, context captures, snapshots, artifacts and logs. Application run records SHALL link profiles, deployments, environments, agent setup, parent and child runs, steps, threads, checkpoint ids, applied settings, evidence, optional budgets and recovery outcomes. Interaction identity mappings and durable public projection/replay records SHALL reuse application persistence; checkpoints SHALL remain execution authority accessed only through supported public APIs. A selected id or frontend projection MUST NOT claim a value was loaded, applied or completed.

#### Scenario: Follow persisted run

- WHEN a persisted run is followed after backend restart
- THEN application records MUST locate its checkpoint ids, interaction identities and related files
- AND the application MUST NOT mutate private checkpointer tables or invoke the model simply to rebuild the display.

### Requirement: STATE-002 - Do not confuse history with the working project

The backend SHALL own thread identities, checkpoint namespaces and displayed history. The readable archive MAY retain more history than compacted runtime context. Hydration SHALL preserve that history while identifying the checkpoint as execution authority. Deep Agents file tools SHALL target project storage; conversation-state and harness internal paths MUST NOT substitute for the working project. Editing or clearing displayed history MUST NOT restore, delete, fork or reset project files or execution state.

#### Scenario: History edit

- WHEN displayed history is changed after a project-bound file-writing turn
- THEN project files MUST remain unchanged by that display edit
- AND harness-internal paths MUST NOT appear in the project or be reconstructed from edited display history.

#### Scenario: Existing compacted conversation

- WHEN a pre-migration conversation is reopened after its runtime context was compacted
- THEN its full retained readable history, project/settings references and checkpoint association MUST survive
- AND continuation MUST use the existing checkpoint rather than replaying the archive.

## ADDED Requirements

### Requirement: STATE-009 - Recover interaction projections without replaying effects

Interaction hydration and replay SHALL provide an atomic cutover to live events with stable identities and bounded transient buffering. Thread-level cursors SHALL remain distinct from run-local native sequences. Unavailable or expired replay positions SHALL trigger explicit resynchronization from durable application records. Restart recovery SHALL preserve real partial output and actual tool outcomes; uncertain effects MUST remain unknown and MUST NOT be repeated to repair presentation. Any required application-record migration SHALL be recoverable, idempotent and verified on isolated copies before cutover.

#### Scenario: Gap and backend restart

- WHEN an observer reconnects after a replay gap or backend restart
- THEN it MUST receive controlled resynchronization and truthful persisted outcome or uncertainty
- AND neither resubscription nor hydration MUST execute a tool or create another run.
