## MODIFIED Requirements

### Requirement: API-006 - Stream run and conversation events over SSE

Chat and current live-run consumers SHALL share a versioned upstream-compatible interaction boundary over authenticated loopback HTTP and SSE. Backend registration SHALL bind application conversation, runtime thread, application run and framework execution identities. Submission, hydration, subscription, resume, cancellation and reconnect MUST operate through that binding. Missing tokens MUST return 401 and wrong tokens MUST return 403. The boundary SHALL validate supported command fields and reject unsupported versions, commands, arbitrary state updates, checkpoint selection and workflow jumps. Only controlled public message/state/tool/interrupt projections and declared application extensions SHALL cross the boundary; raw private graph state MUST NOT be exposed.

#### Scenario: SSE reconnect

- WHEN a live thread is disconnected and reconnected
- THEN a consistent snapshot/replay boundary MUST restore its ordered projection without duplicate content or a new model invocation
- AND a replay gap MUST cause explicit controlled resynchronization rather than silently dropping output.

#### Scenario: Run-local sequences across turns

- WHEN consecutive runs reuse a conversation thread
- THEN their native run-local event sequences MUST NOT be mistaken for a thread-global cursor
- AND hydration and replay MUST retain stable message, tool, run and namespace identities.

#### Scenario: Reject while active

- WHEN another submission targets a live or interrupted run
- THEN the backend and frontend MUST reject it without aborting, replacing or implicitly queuing the active task
- AND a client queue MUST NOT be presented as a durable application queue.

#### Scenario: Disconnect and cancel are different

- WHEN navigation or unmount disconnects an observer
- THEN execution MUST continue under backend ownership
- AND explicit cancellation MUST remain cancel_requested until confirmed by the worker, independently of SDK loading state.

### Requirement: API-008 - Preserve terminal Chat hydration

The desktop SHALL reconcile upstream incremental projections and the persisted readable conversation by stable identity. Completed replies SHALL remain visible after final hydration. Optimistic user input, completed messages and tool results MUST NOT duplicate or disappear. Thread switches SHALL dispose the old observation and MUST NOT apply late frames or hydration to the new selection. Readable archive history MUST NOT be shortened to match compacted execution context.

#### Scenario: Final reply remains visible

- WHEN a real desktop Chat turn completes
- THEN its reply MUST have appeared incrementally before completion and MUST remain visible without reopening
- AND reopening MUST restore the saved transcript, selected/applied setup and project binding.

#### Scenario: Late old-thread completion

- WHEN the user selects a fresh conversation while the prior run continues
- THEN old-thread frames and completed hydration MUST NOT contaminate the new conversation
- AND the prior run MUST remain observable when revisited.
