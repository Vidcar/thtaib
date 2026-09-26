## MODIFIED Requirements

### Requirement: AGT-004 - Separate active context from durable knowledge

The product SHALL use application-versioned user, agent, and project memory, skills, and protected instructions through configured backends. Selected versions SHALL be loaded as content: memory through official `memory=`, skills through official `skills=`, and protected instructions through the composed system prompt. Each submitted turn SHALL freeze exact selected memory versions, including deselection. Changes apply to future submissions; running, queued and paused turns keep their frozen selections. Use latest version SHALL be explicit. A branch SHALL inherit its source selections until explicitly changed. The full selected memory text SHALL be included with visible estimated cost or fail actionably when irreducibly oversized; keyword matching MUST NOT silently omit it. A new user turn SHALL load the current selected skill versions, including skill edits and deselection; an approval or question resume MUST NOT reload them. Automatic writes SHALL require explicit scope policy, provenance, and concurrent-write handling. Protected instructions MUST reject agent-origin writes.

#### Scenario: Versioned knowledge and fresh conversation

- WHEN a fresh conversation selects retained files and knowledge
- THEN durable knowledge and project files MUST be available without inheriting previous active context
- AND memory edit, revert, denied protected-instruction overwrite, and concurrent conflict MUST preserve version policy.

#### Scenario: Knowledge changes between turns

- **WHEN** selected skills change after a turn or an existing conversation is offered a different memory version
- **THEN** the next new user turn sees the current selected skills while a resumed interrupt keeps its original skill state
- **AND** the next submitted turn uses the explicitly selected memory versions, while queued and resumed turns keep their original versions.

#### Scenario: Current memory identity after a version change

- **WHEN** a new turn changes or clears selected memory
- **THEN** its current-user context SHALL identify the exact frozen version IDs or explicit absence, and the native memory source paths SHALL identify those same immutable versions
- **AND** the full selected contents SHALL be formatted only through native memory middleware, without duplicating them in the selection notice or rewriting prior messages
- **AND** a helper SHALL receive its own frozen selected versions and an interrupted run SHALL retain its original version paths for permitted reads.

### Requirement: AGT-007 - Preserve Chat continuity and restart truth

A session SHALL permanently belong to one project or the non-project area. A different area requires a fresh session/thread; branches retain their source area. Removed projects retain historical session identity instead of converting sessions to non-project. Model/profile selection and authorized artifact reuse do not move sessions.

Continuing SHALL use the same saved thread with a new application run for only the new user input; fresh starts create new context. One turn per session SHALL execute at a time. Persist model/profile/tool/setup selections and snapshot each turn's resolved setup, preserving omitted versus empty tools. Edits affect future work, not live/paused settings or history. Revalidate current access at dispatch/resume. Display-only history edits MUST NOT reset context or project files. Restart SHALL reconcile persisted linkage and terminal state; missing linkage is an explicit gap, not a silently substituted thread.

#### Scenario: Restart then continue

- **WHEN** the backend restarts with a saved conversation and run linkage
- **THEN** continuation uses that conversation/thread and recorded configuration; missing linkage is reported rather than silently starting fresh.

#### Scenario: Different session area

- **WHEN** a user changes project area or branches an existing conversation
- **THEN** changing area creates fresh context, while a branch retains the original project/non-project identity.

#### Scenario: Continue after an ordinary tool failure
- **WHEN** a terminal turn contains complete tool calls without final protocol results
- **THEN** safe native history normalization SHALL permit the next user turn without replaying previous effects
- **AND** successful siblings remain successful, uncertain effects require evidence inspection, and live approvals use their original resume path.

### Requirement: AGT-021 - Keep delegated work within the conversation authority

Only explicitly selected frozen named agent versions SHALL be available as helpers. Each helper SHALL have isolated context, intersected parent authority, observable named activity and correctly owned approvals, cancellation and durable child identity. No recursive or general-purpose delegation SHALL be added by this selection. Calls sharing a managed model SHALL be serialized within a parent run initially; separate conversations with no overlapping project reservation MAY progress concurrently on the same or distinct loaded models within actual server capacity. A root task and its helpers SHALL share one project-family reservation. An alternate-model helper MAY hand off a single loaded-model slot after the parent's current model call completes, and the parent SHALL reload its exact model before continuing. The handoff MUST NOT widen authority, interrupt an in-flight model call or report a stopped parent as ready. Explicit tool-call budgets SHALL be enforced atomically across root and child calls, while unset budgets remain unset.

#### Scenario: Frozen helper and shared budget
- **WHEN** saved helper settings change after queueing and several helper calls compete for the last allowed tool call
- **THEN** the queued version and intersected authority are used and the explicit budget is not exceeded.

#### Scenario: Alternate model with one slot
- **WHEN** a parent delegates to a helper using a different installed model while the loaded-model limit is one
- **THEN** helper and parent calls run in sequence with visible loading or waiting and each uses its selected configuration.

#### Scenario: Replayed helper discovery in a later turn
- **WHEN** the public stream replays helpers from earlier turns while a new parent turn is active
- **THEN** each helper SHALL retain its owning parent-run and tool-call identity, even when call IDs repeat
- **AND** replay arrival timestamps MUST NOT establish ownership; the current parent's recorded task calls and child references SHALL determine membership
- **AND** child tool events from helper namespaces SHALL appear only in the scoped helper transcript, while the parent feed retains its compact delegation and parent-owned tools.

#### Scenario: Stop child work
- **WHEN** a conversation is stopped while a helper is generating or awaiting approval
- **THEN** new dispatch stops, owned cancellation is confirmed before terminal cancellation, and partial/uncertain outcomes remain truthful.

## ADDED Requirements

### Requirement: AGT-026 - Supply a bounded authorized project outline

Project chats with authorized file reading SHALL offer an optional outline capped at 1024 estimated tokens, showing relevant paths, declarations and headings. It SHALL respect exclusions and project boundaries, remain derived and disposable, reflect changed files, label partial coverage, and yield context space to user input. Tools-off and project-free requests MUST NOT receive it.

The outline SHALL reuse existing project exclusions and the actual enclosing repository's ignore rules. It SHALL use bounded file discovery and confined reads with a disposable bounded cache, not a durable repository index or unrestricted traversal. A project folder ignored by its enclosing repository MAY therefore have an empty outline.

#### Scenario: Changed project and limited context
- **WHEN** project files change or a request has insufficient room for its optional outline
- **THEN** stale entries SHALL be invalidated and the outline SHALL be reduced or omitted without blocking the user's request.
