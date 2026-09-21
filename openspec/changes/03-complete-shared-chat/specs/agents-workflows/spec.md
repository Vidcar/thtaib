# agents-workflows delta

## MODIFIED Requirements

### Requirement: AGT-001 - Use the embedded harness

Agent tasks SHALL run through the existing Deep Agents harness using LangChain components and LangGraph. Chat SHALL call the same harness with or without a bound project; the application MUST NOT add a model/tool loop. Each run executes once; native streaming, scoped selectors and audit projections observe that invocation while preserving message/block/tool and namespace identities. Without a project, project-filesystem and host-shell access SHALL be absent or rejected, not assigned an invented working directory. Explicitly supplied session attachments MAY be read through their authorized content/scoped backend without granting project or host access.

#### Scenario: Project-bound and project-free chat

- **WHEN** Chat performs a real project file task and then starts a non-project conversation
- **THEN** the shared harness owns iteration in both cases; non-project Chat has no project file/shell authority while authorized attachments remain usable.

#### Scenario: Native identity projection

- WHEN streamed content, a tool call and its result are observed by multiple scoped selectors
- THEN stable message/block/call and namespace identities MUST keep each result paired with its call without extra execution
- AND provider-reported reasoning, answer content and internal compaction output MUST remain distinct.

### Requirement: AGT-007 - Preserve Chat continuity and restart truth

A session SHALL permanently belong to one project or the non-project area. A different area requires a fresh session/thread; branches retain their source area. Removed projects retain historical session identity instead of converting sessions to non-project. Model/profile selection and authorized artifact reuse do not move sessions.

Continuing SHALL use the same saved thread with a new application run for only the new user input; fresh starts create new context. One turn per session SHALL execute at a time. Persist model/profile/tool/setup selections and snapshot each turn's resolved setup, preserving omitted versus empty tools. Edits affect future work, not live/paused settings or history. Revalidate current access at dispatch/resume. Display-only history edits MUST NOT reset context or project files. Restart SHALL reconcile persisted linkage and terminal state; missing linkage is an explicit gap, not a silently substituted thread.

#### Scenario: Restart then continue

- **WHEN** the backend restarts with a saved conversation and run linkage
- **THEN** continuation uses that conversation/thread and recorded configuration; missing linkage is reported rather than silently starting fresh.

#### Scenario: Different session area

- **WHEN** a user changes project area or branches an existing conversation
- **THEN** changing area creates fresh context, while a branch retains the original project/non-project identity.

### Requirement: AGT-008 - Use framework interrupts for approvals

Protected tool actions SHALL use Deep Agents `interrupt_on` and LangGraph resume on the same checkpointer thread. A pending interrupt SHALL keep the run `running` with typed details, not a new lifecycle status. Cancellation SHALL use `cancel_requested` until the worker confirms `cancelled`. The UI SHALL offer **Approve once**, **Allow for this session**, **Always allow** and **Reject**, showing exact action/resource scope. Once covers the pending action; session covers matching actions in the logical session across window reopening; Always allow creates an inspectable revocable matching grant; Reject does not create a permanent deny rule. Explicit rename/delete grants MAY satisfy matching future approvals.

Grants SHALL be rechecked at dispatch/resume and MUST NOT enable disabled tools, expand denied access/child selection, authorize automatic memory saving or bypass authored workflow approval nodes. Read scope does not imply write/delete or global scope. Every decision SHALL identify its run, thread/checkpoint and exact interrupt. Reject stale/duplicate/wrong-run decisions; retain framework order for all actions inside one interrupt. Resume the saved interruption rather than resending the task. Cancel while interrupted SHALL reject/resume outstanding commands and reach cancelled only after owned work stops; external termination remains separately known or uncertain.

#### Scenario: Approve deny cancel

- **WHEN** a command pauses for approval
- **THEN** the chosen allowed framework decision resumes its saved interrupt, and cancellation prevents further dispatch without falsely claiming external work stopped.

#### Scenario: Revoked or mismatched grant

- **WHEN** a queued or paused action no longer matches a valid saved grant
- **THEN** permission is rechecked and the action cannot proceed on stale authority.

#### Scenario: Cross-run or duplicate decision

- WHEN an old approval is submitted twice or against another run, thread or namespace
- THEN it MUST fail without executing the action or reserving another continuation
- AND the current pending approval MUST retain its authoritative identity and state; privileged decisions remain backend-owned, never automatically resolved browser tools.

#### Scenario: Mixed interrupt actions

- **WHEN** one interruption contains several actions with mixed decisions
- **THEN** each action receives its allowed ordered decision, without approving a different run or inventing unsupported edit payloads.

## ADDED Requirements

### Requirement: AGT-009 - Enforce tools-off without disabling context housekeeping

Omitted tool selection SHALL inherit and an explicitly empty selection SHALL mean no tools. Tools-off SHALL remove filesystem, shell, planning, retrieval, delegation and synthetic formatting definitions and block unexpected/unrecognized/restored handlers at every sync/async execution hook. Projects, knowledge or connections MUST NOT silently re-enable them. Ordinary answer completion SHALL require no tool. Checkpoints and internal context housekeeping remain available. Selected official planning SHALL expose its observed task states, not invented progress or proof of task correctness.

#### Scenario: Unexpected restored tool call

- **WHEN** a call appears while tools are off, including on checkpoint resume
- **THEN** the handler cannot execute; normal text and internal context housekeeping remain available.

### Requirement: AGT-010 - Keep drafts and queued turns separate from execution

Drafts and queued follow-ups SHALL survive navigation/reopening without becoming submitted history. Each queued item SHALL show editable intended configuration and attachments and be removable. Successful completion advances automatically; failure/cancellation pauses until deliberate continuation; an approval/input wait is not completion. Dispatch SHALL freeze that item's setup and recheck authorization, model/history compatibility and shared admission, including active Lab reservation. Selector changes MUST NOT silently alter a queued item or steer a live turn.

#### Scenario: Queue progression

- **WHEN** a turn succeeds, fails, is cancelled or waits for input
- **THEN** only success automatically dispatches the next eligible item; the other outcomes preserve or pause the queue as specified.

### Requirement: AGT-011 - Resume typed user input separately from permission

Supported ask-user operations SHALL present typed text, choice or authorized file/folder questions, validate answers and resume the exact saved run/thread/interrupt. Model-facing ask-user is a selected tool; an ordinary conversational question does not require one. A selected folder grants only the represented access. Input is not permission approval or credential collection. Cancel/restart SHALL reconcile pending questions rather than leave an unresolvable wait.

#### Scenario: Typed answer

- **WHEN** a user supplies an invalid, stale or valid answer to a saved question
- **THEN** invalid/stale answers are rejected; a valid answer resumes only its intended interruption without broadening access.

### Requirement: AGT-012 - Distinguish branches, answer regeneration and effectful retry

Edit-and-retry and Retry task SHALL preserve original history and create an explicit branch/attempt with source checkpoint and saved head. Reopen/follow-ups continue that head; writes sharing a thread SHALL be serialized. Project-state branches SHALL obey the existing consistent snapshot contract and retain session area. Unsupported checkpoint granularity SHALL be explicit.

Regenerate answer SHALL use retained task results/supported saved state to produce an alternative answer without repeating tools, file edits or remote submissions or duplicating the user input. Where unsupported, it SHALL be unavailable rather than silently retry the task. Effectful Retry task SHALL disclose possible repeated actions/interruptions, recheck permissions and reconcile external operations. Neither branching nor retry promises to undo files, committed knowledge or remote actions. Model requests use the shared adapter/admission path, never transcript-only reconstruction.

#### Scenario: Regenerate answer

- **WHEN** another answer is requested after a file or external task
- **THEN** retained results are reused without task effects, or answer-only regeneration is explicitly unavailable.

#### Scenario: Branch and retry

- **WHEN** a prompt is edited or the task is deliberately retried
- **THEN** original results survive, the source/head and possible repeat effects are explicit, and subsequent turns continue the selected branch.

### Requirement: AGT-013 - Reconcile cancellation and crash boundaries honestly

Cancellation SHALL prevent further model/tool dispatch, including rejection/resume loops, pause follow-ups and clean only owned request resources. Partial output and completed changes remain inspectable. Application stop and host/remote termination SHALL remain separate; shared inference processes are not killed to cancel one request. Restart SHALL verify genuine pending framework interrupts, reconcile decision acceptance/checkpoint advancement/external dispatch, and resolve orphaned live runs. Historical checkpoints alone do not prove resumability; uncertain effects MUST NOT be blindly replayed. Checkpointing is neither exactly-once execution nor rollback.

#### Scenario: Crash around an effect

- **WHEN** the backend stops between external dispatch and acknowledgement
- **THEN** recovery keeps the outcome unknown or uses authoritative reconciliation, never silent replay or fabricated success.

#### Scenario: Cancel turn

- **WHEN** a cancellation arrives during streaming, tool work or an interrupt
- **THEN** new dispatch stops, the queue pauses and owned cancellation completes only when confirmed, preserving partial and uncertain outcomes.
