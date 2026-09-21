# Backend Desktop

## Purpose

Specify how the one FastAPI backend coordinates APIs, records, jobs, approvals, events, and artifacts while the one Electron desktop presents them without becoming execution authority.

## Requirements

### Requirement: API-001 - Coordinate without replacing execution owners

The backend SHALL own APIs, jobs, resource scheduling, events, approvals, artifacts, optional budgets, and shared records while hosting Deep Agents and LangGraph integrations. Backend coordination MUST NOT become a second agent loop or workflow engine.

#### Scenario: Desktop task trace

- WHEN a desktop task is traced through backend, harness or graph, and worker
- THEN job tracking MUST coordinate execution
- AND it MUST NOT duplicate the harness reasoning/tool loop or LangGraph sequence.

### Requirement: API-002 - Edit in the desktop, execute in the backend

Electron/React SHALL present controls, previews, context, evidence, memory editing, branches, and tool panels. React Flow SHALL edit workflow definitions. Backend validation and LangGraph SHALL execute workflows. The visual graph MUST NOT be executable authority by itself.

#### Scenario: Invalid definition outside editor

- WHEN an invalid definition is submitted outside the visual editor
- THEN backend validation MUST reject it
- AND successful screen interactions MUST correspond to real backend actions or be explicitly labelled as mock.

### Requirement: API-003 - Separate type validity from permission and capability

Pydantic and JSON Schema SHALL validate data and configuration shapes. Application rules SHALL enforce capabilities, access, connector compatibility, and privileged-route trust. A schema-valid object MUST NOT authorize execution or prove operational support.

#### Scenario: Well-typed unauthorized request

- WHEN a well-typed but unauthorized or incompatible request is sent
- THEN it MUST be rejected at the relevant authorization, capability, or execution boundary.

### Requirement: API-004 - Expose real state and evidence

The backend and desktop SHALL present run hierarchy, streamed progress, approvals, artifacts, checks, applied configuration, and relevant context or knowledge information from records and events. Active, queued, resource-constrained, failing, `cancel_requested`, and `cancelled` states SHALL be distinguishable. Model confidence, preview text, service readiness, or disconnected clients MUST NOT be treated as completed work.

#### Scenario: Cancellation visibility

- WHEN a live run is cancelled
- THEN visible state MUST show `cancel_requested` until the worker records confirmed `cancelled`
- AND a later persisted outcome MUST match execution records.

### Requirement: API-005 - Keep provisioning distinct from job execution

The environment manager SHALL provision workers and access, map project storage, and tear down environments. Adapters SHALL own jobs inside environments. Docker Compose SHALL manage container services. Service readiness MUST NOT be reported as task completion.

#### Scenario: Provision then run

- WHEN a worker is provisioned and then a tracked job executes
- THEN provisioning, job progress, cancellation, and teardown MUST be attributed to the appropriate owners.

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
- AND a finished run MUST NOT have Cancel enabled.

### Requirement: API-007 - Launch locally and keep desktop state honest

The Windows launcher SHALL reuse a healthy product backend or start it hidden, then open the built Electron desktop. Chat SHALL keep the composer visible while transcript and history scroll independently. Recent conversations SHALL appear first. New Chat SHOULD prefer a running chat deployment and MUST NOT apply unrelated saved profiles. Stopped deployments MUST NOT gain healthy labels from stale probes.

#### Scenario: Desktop launch and model state

- WHEN the launcher opens the application and a stopped deployment has an old probe
- THEN the desktop MUST present current backend state
- AND catalogue loading MUST be explicit rather than shown as an empty catalogue.

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

### Requirement: API-009 - Keep desktop shared secret out of renderer

The backend SHALL create the same-machine shared secret under product state on first use. Electron main SHALL inject the token for loopback backend requests. The sandboxed renderer SHALL use context isolation, no Node integration, and MUST NOT hold the shared secret. The backend SHALL bind loopback only.

#### Scenario: Renderer request

- WHEN the renderer initiates a privileged backend request
- THEN Electron main MUST add the shared-secret header
- AND the renderer MUST NOT expose or store that secret.
