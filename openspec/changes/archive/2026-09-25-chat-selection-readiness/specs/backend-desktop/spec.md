# Spec Delta

## MODIFIED Requirements

### Requirement: API-006 - Stream run and conversation events over SSE

Chat and current live-run consumers SHALL share a versioned upstream-compatible interaction boundary over authenticated loopback HTTP and SSE. Backend registration SHALL bind application conversation, runtime thread, application run and framework execution identities. Submission, hydration, subscription, resume, cancellation and reconnect MUST operate through that binding. Missing tokens MUST return 401 and wrong tokens MUST return 403. The boundary SHALL validate supported command fields and reject unsupported versions, commands, arbitrary state updates, checkpoint selection and workflow jumps. Only controlled public message/state/tool/interrupt projections and declared application extensions SHALL cross the boundary; raw private graph state MUST NOT be exposed. Opening or reconnecting a conversation paints the saved snapshot at its interaction cursor and continues the event subscription after that cursor. Historical token events are not played back onto the screen. A direct new-turn submission MUST reject an active turn; a separate explicit enqueue request SHALL add durable queued work without interrupting that turn.

#### Scenario: SSE reconnect

- WHEN a live thread is disconnected and reconnected
- THEN a consistent snapshot/replay boundary MUST restore its ordered projection without duplicate content or a new model invocation
- AND a replay gap MUST cause explicit controlled resynchronization rather than silently dropping output.

#### Scenario: Open a conversation without replaying tokens

- WHEN a client opens or reconnects to a conversation
- THEN it paints the saved snapshot at `interaction_cursor` and continues the subscription after that cursor
- AND historical token events MUST NOT be applied to the screen again
- AND an answer already in progress MUST be visible from that snapshot before newer tokens arrive.

#### Scenario: Run-local sequences across turns

- WHEN consecutive runs reuse a conversation thread
- THEN their native run-local event sequences MUST NOT be mistaken for a thread-global cursor
- AND hydration and replay MUST retain stable message, tool, run and namespace identities.

#### Scenario: Reject while active

- WHEN a direct new-turn submission targets a live or interrupted run
- THEN the backend MUST reject that direct submission without aborting, replacing or implicitly queuing the active task
- AND an explicit Queue action MUST retain the draft as durable queued work under backend ownership without interrupting the active turn.

#### Scenario: Disconnect and cancel are different

- WHEN navigation or unmount disconnects an observer
- THEN execution MUST continue under backend ownership
- AND explicit cancellation MUST remain cancel_requested until confirmed by the worker, independently of SDK loading state.
- AND a finished run MUST NOT have Cancel enabled.

### Requirement: API-007 - Launch locally and keep desktop state honest

The Windows launcher SHALL reuse a healthy product backend or start it hidden, then open the built Electron desktop. Chat SHALL keep the composer visible while transcript and history scroll independently. Recent conversations SHALL appear first. New Chat SHALL retain an explicit current Chat model choice. When no choice exists, it SHALL select the sole healthy running chat deployment; with several healthy running choices it SHALL request an explicit choice. It MUST NOT apply unrelated saved profiles. Stopped deployments MUST NOT gain healthy labels from stale probes.

#### Scenario: Desktop launch and model state

- WHEN the launcher opens the application and a stopped deployment has an old probe
- THEN the desktop MUST present current backend state
- AND catalogue loading MUST be explicit rather than shown as an empty catalogue.

#### Scenario: New Chat with a running model

- **WHEN** no Chat model has been chosen and exactly one healthy chat deployment is running
- **THEN** New Chat shows and submits that deployment's exact configuration without starting it again.

#### Scenario: Several running models

- **WHEN** no Chat model has been chosen and several healthy chat deployments are running
- **THEN** New Chat asks for an explicit model choice rather than silently selecting one.

### Requirement: API-028 - Switch the selected model without interrupting work

Choosing a different or unloaded model or named configuration SHALL start loading that exact managed selection without a second confirmation. Choosing the exact currently selected healthy configuration SHALL leave the binding unchanged and SHALL NOT request a model start. A selection remains pending until readiness is observed; a failed load SHALL retain the previous chat binding and draft with an actionable reason. When the loaded-model limit is reached, a busy model request SHALL finish before capacity changes, and the new selection SHALL show waiting then loading. The chat and its compatible history remain open. Known-incompatible choices SHALL be disabled with reasons; failed or unperformed compatibility checks MUST NOT be represented as compatible; Workbench SHALL NOT create a new chat as a side effect of a setting change. An explicit stop, unload or destructive configuration change SHALL retain its own reviewed protection.

#### Scenario: Swap during a quiet chat
- **WHEN** a person chooses a different installed model while the previous model is idle
- **THEN** the selected model loads under the configured limit without asking for another confirmation and the conversation stays open.

#### Scenario: Swap while work is running
- **WHEN** one slot is occupied by an in-flight request and a different model is chosen
- **THEN** that request continues, the new selection shows waiting, and loading begins when capacity is safe.

#### Scenario: Apply a named model variant in Chat
- **WHEN** a person chooses a named configuration with different launch settings
- **THEN** Workbench loads those exact settings before binding the same chat, retaining its draft and history on failure.

#### Scenario: Failed selection
- **WHEN** the requested model cannot become ready
- **THEN** the previous conversation binding and draft remain and the failed attempt is visible.

#### Scenario: Reselect the current healthy configuration

- **WHEN** a person selects the current installed model row while its exact named configuration is healthy and loaded
- **THEN** the same configuration remains selected and no readiness, start or load request is made.

#### Scenario: Compatibility is not known

- **WHEN** a model choice has not been checked or its preview failed
- **THEN** the picker does not label it compatible and checks the exact choice before loading.

## ADDED Requirements

### Requirement: API-044 - Keep Chat readiness advisory and current

Chat readiness previews SHALL evaluate the candidate without loading weights, changing saved setup, or granting access. Invalid unsupported override values SHALL return a structured client error rather than HTTP 500. Readiness results SHALL belong to the selected conversation, candidate setup and run lifecycle that requested them; an obsolete active-turn result MUST NOT block a completed turn. An explicitly queued turn SHALL use durable backend queue admission while a turn is live. A pending or unverified preview, or a selected model that can load on Send, MUST NOT prevent dispatch to the authoritative backend admission path. Known current capability or compatibility blockers SHALL remain visible with their recovery action. Opening a saved conversation SHALL display its fetched content while live observation and setup details settle; passive previews SHALL NOT fan out across every closed-picker model choice.

#### Scenario: Preview input mismatch

- **WHEN** a candidate contains nullable inherited fields or an unsupported non-null field
- **THEN** supported explicit clears retain their meaning and unsupported input receives a client error without changing a model, chat or configuration.

#### Scenario: Turn finishes after an active preview

- **WHEN** an active-turn preview completes after the selected turn has become terminal or the selected chat has changed
- **THEN** its active warning is ignored and Send becomes available subject to current setup blockers.

#### Scenario: Queue during an active turn

- **WHEN** a person queues a draft during a live turn
- **THEN** active-turn readiness does not block durable queue admission and the active run continues.

#### Scenario: Direct submission is awaiting admission

- **WHEN** a submitted message has not yet been accepted as a live run
- **THEN** Chat shows it as starting, retains any next draft, and does not offer Queue until the run identity is confirmed.

#### Scenario: Live update is delayed after admission

- **WHEN** the backend accepts a direct submission but its live update is delayed
- **THEN** Chat reconciles that exact saved input and run without repeating the submission or losing the next draft.

#### Scenario: Queue admission races terminal completion

- **WHEN** Queue is clicked behind a known run and that run finishes before the queue request is admitted
- **THEN** the request identifies that predecessor, the backend retains the queued turn, and its terminal coordinator advances or pauses the queue according to the run result
- **AND** a changed predecessor is rejected without saving the queued draft as a different turn
- **AND** an ordinary Queue request made while idle still waits for an explicit Resume.

#### Scenario: Cold selected model on Send

- **WHEN** a selected installed configuration is unloaded and its preview reports that loading is required
- **THEN** Send can initiate the existing authoritative loading and admission path without first warming the model through a passive preview.

#### Scenario: Open a saved conversation

- **WHEN** a saved chat is fetched while its live observation and setup details are still resolving
- **THEN** its saved transcript appears with a truthful connecting state, and late results from an earlier selection cannot replace it.

#### Scenario: Interaction registration fails after a saved chat appears

- **WHEN** the saved transcript is visible but its interaction thread cannot be registered
- **THEN** Chat keeps the transcript visible, disables Send, and offers a retry for that same chat
- **AND** Send becomes available only after a successful retry binds the conversation to its interaction thread.
