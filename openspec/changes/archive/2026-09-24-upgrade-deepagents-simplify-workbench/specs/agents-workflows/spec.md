# Spec Delta

## MODIFIED Requirements

### Requirement: AGT-001 - Use the embedded harness

Agent tasks SHALL run through `create_deep_agent` using LangChain components and LangGraph. Chat SHALL call the same harness with or without a bound project; the application MUST NOT add a model/tool loop. Each run executes once; native streaming, scoped selectors and audit projections observe that invocation while preserving message/block/tool and namespace identities. Without a project, project-filesystem and host-shell access SHALL be absent or rejected, not assigned an invented working directory. Explicitly supplied session attachments MAY be read through their authorized content/scoped backend without granting project or host access.

The harness SHALL receive the run's backend, filesystem permissions, `interrupt_on`, `memory`, and `skills` through those official parameters when the run uses them. Planning SHALL be the official `write_todos` tool when planning is selected. Exactly one Deep Agents summarization middleware SHALL run with its native model-aware trigger and retention defaults. Only its input-capacity value MAY be adjusted to avoid reserving output space again when the model profile already reports usable input. The application MUST NOT set a separate early compaction threshold or stack another summarizer. Ordinary Chat SHALL disable the general-purpose subagent through the upstream profile switch, and SHALL NOT rely on a parent-only filter that a compiled child does not inherit. The product MUST NOT embed the Deep Agents CLI or a hosted agent runtime.

#### Scenario: Project-bound and project-free chat

- **WHEN** Chat performs a real project file task and then starts a non-project conversation
- **THEN** the shared harness owns iteration in both cases; non-project Chat has no project file/shell authority while authorized attachments remain usable.

#### Scenario: Native identity projection

- WHEN streamed content, a tool call and its result are observed by multiple scoped selectors
- THEN stable message/block/call and namespace identities MUST keep each result paired with its call without extra execution
- AND provider-reported reasoning, answer content and internal compaction output MUST remain distinct.

#### Scenario: Ordinary Chat has no general-purpose child

- **WHEN** ordinary Chat is compiled and a tool exclusion would matter
- **THEN** the general-purpose `task` tool is not offered, including to a child
- **AND** disabling it is the upstream profile switch rather than a filter only the parent runs.

#### Scenario: Summarize once

- **WHEN** a long turn is compacted
- **THEN** one Deep Agents summarizer applies its native model-aware compaction defaults against the configured usable input budget
- **AND** no custom early threshold or second summarizer shrinks that budget again.

### Requirement: AGT-004 - Separate active context from durable knowledge

The product SHALL use application-versioned user, agent, and project memory, skills, and protected instructions through configured backends. Selected versions SHALL be loaded as content: memory through official `memory=`, skills through official `skills=`, and protected instructions through the composed system prompt. The first submitted turn SHALL fix the conversation's exact memory version refs; a branch SHALL inherit the source checkpoint's refs. A later explicit memory change MUST fail before dispatch with a new-chat instruction. A new user turn SHALL load the current selected skill versions, including skill edits and deselection; an approval or question resume MUST NOT reload them. Automatic writes SHALL require explicit scope policy, provenance, and concurrent-write handling. Protected instructions MUST reject agent-origin writes.

#### Scenario: Versioned knowledge and fresh conversation

- WHEN a fresh conversation selects retained files and knowledge
- THEN durable knowledge and project files MUST be available without inheriting previous active context
- AND memory edit, revert, denied protected-instruction overwrite, and concurrent conflict MUST preserve version policy.

#### Scenario: Knowledge changes between turns

- **WHEN** selected skills change after a turn or an existing conversation is offered a different memory version
- **THEN** the next new user turn sees the current selected skills while a resumed interrupt keeps its original skill state
- **AND** the memory change is refused before execution with guidance to start a new chat; the existing conversation shows its pinned version.

### Requirement: AGT-008 - Use framework interrupts for approvals

Protected tool actions SHALL use Deep Agents `interrupt_on` and LangGraph resume on the same checkpointer thread. A pending interrupt SHALL keep the run `running` with typed details, not a new lifecycle status. Cancellation SHALL use `cancel_requested` until the worker confirms `cancelled`. The UI SHALL offer **Approve once**, **Allow for this session**, **Always allow** and **Reject**, showing exact action/resource scope. Once covers the pending action; session covers matching actions in the logical session across window reopening; Always allow creates an inspectable revocable matching grant; Reject does not create a permanent deny rule.

Chat SHALL offer Ask for approval and Full access with truthful effective values and named inherited sources. Ask SHALL pause before mutations, every shell command and external side effects unless an explicit saved matching grant applies. Full access SHALL skip approval pauses only for enabled tools. Disabled tools remain disabled, typed questions still wait, and durable memory saving retains its separate policy. Host shell access SHALL be described as Windows-account authority, not a project sandbox. Plan mode SHALL override effectful execution under every access level.

The four approval choices remain whenever a pause still happens. A queued turn keeps the mode it was queued with. Changing the mode applies to a later message and does not rewrite the saved agent.

Grants SHALL be rechecked at dispatch/resume and MUST NOT enable disabled tools, expand denied access/child selection, authorize automatic memory saving or bypass authored workflow approval nodes. Read scope does not imply write/delete or global scope. Every decision SHALL identify its run, thread/checkpoint and exact interrupt. Reject stale/duplicate/wrong-run decisions; retain framework order for all actions inside one interrupt. Resume the saved interruption rather than resending the task. Cancel while interrupted SHALL reject/resume outstanding commands and reach cancelled only after owned work stops; external termination remains separately known or uncertain.

#### Scenario: Approve deny cancel

- **WHEN** a command pauses for approval
- **THEN** the chosen allowed framework decision resumes its saved interrupt, and cancellation prevents further dispatch without falsely claiming external work stopped.

#### Scenario: Approval mode skips a pause

- **WHEN** a chat is set to Full access and the agent runs a selected shell command
- **THEN** that action proceeds without a review card, while Ask pauses unless a saved matching grant applies
- **AND** a typed question still waits, a tool that was not selected is still refused, and a memory proposal is not saved.

#### Scenario: Revoked or mismatched grant

- **WHEN** a queued or paused action no longer matches a valid saved grant
- **THEN** permission is rechecked and the action cannot proceed on stale authority.

#### Scenario: Cross-run or duplicate decision

- WHEN an old approval is submitted twice or against another run, thread or namespace
- THEN it MUST fail without executing the action or reserving another continuation
- AND the current pending approval MUST retain its authoritative identity and state; privileged decisions remain backend-owned, never automatically resolved browser tools.

#### Scenario: Mixed interrupt actions

- **WHEN** one interruption contains several actions with mixed decisions
- **THEN** each action receives its allowed ordered approve, reject or typed respond decision, without approving a different run or inventing unsupported edit payloads.

### Requirement: AGT-010 - Keep drafts and queued turns separate from execution

Drafts and queued follow-ups SHALL survive navigation/reopening without becoming submitted history. Each queued item SHALL show editable intended configuration and attachments and be removable. Successful completion advances automatically; failure/cancellation pauses until deliberate continuation; an approval/input wait is not completion. Dispatch SHALL freeze that item's setup and recheck authorization, model/history compatibility and shared admission, including active Lab reservation. Selector changes MUST NOT silently alter a queued item or cancel a live turn. A queued message MUST NOT interrupt active work; Stop is a separate explicit action and cancellation pauses the queue until deliberate continuation.

#### Scenario: Queue progression

- **WHEN** a turn succeeds, fails, is cancelled or waits for input
- **THEN** only success automatically dispatches the next eligible item; the other outcomes preserve or pause the queue as specified.

### Requirement: AGT-011 - Resume typed user input separately from permission

Supported ask-user operations SHALL present typed text, choice or authorized file/folder questions, validate answers and resume the exact saved run/thread/interrupt through the framework's typed `respond` decision. A pending interruption with questions and protected tools SHALL use one ordered decision batch; every answer and approval MUST match its saved action before the single resume. Model-facing ask-user is a selected tool; an ordinary conversational question does not require one. A selected folder grants only the represented access. Input is not permission approval or credential collection. Cancel/restart SHALL reconcile pending questions rather than leave an unresolvable wait.

#### Scenario: Typed answer

- **WHEN** a user supplies an invalid, stale or valid answer to a saved question
- **THEN** invalid/stale answers are rejected; a valid answer resumes only its intended interruption without broadening access.

#### Scenario: Mixed questions and approvals

- **WHEN** one saved interruption contains typed questions and protected tool calls
- **THEN** the validated responses and approval decisions resume in framework order exactly once, and a stale or incomplete batch executes no action.
