# Spec Delta

## MODIFIED Requirements

### Requirement: AGT-008 - Use framework interrupts for approvals

Chat SHALL offer Ask for approval, Approve for me and Full access with truthful effective values and named inherited sources. Ask SHALL pause before mutations, shell commands and external side effects unless an explicit saved matching grant applies. Approve for me SHALL automatically allow project edits only when verified recovery covers the operation; non-recoverable changes, shell and external side effects still require approval unless explicitly granted. Full access SHALL skip approval pauses only for enabled tools. Disabled tools remain disabled, typed questions still wait, and durable memory saving retains its separate policy. Host shell access SHALL be described as Windows-account authority, not a project sandbox. Plan mode SHALL override effectful execution under every access level.

#### Scenario: Approve deny cancel

- **WHEN** a command pauses for approval
- **THEN** the chosen allowed framework decision resumes its saved interrupt, and cancellation prevents further dispatch without falsely claiming external work stopped.

#### Scenario: Approval mode skips a pause

- **WHEN** a chat is set to Approve for me and the agent renames a selected file, or it is set to Full access and the agent runs a selected shell command
- **THEN** that action proceeds without a review card
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
- **THEN** each action receives its allowed ordered decision, without approving a different run or inventing unsupported edit payloads.

## ADDED Requirements

### Requirement: AGT-020 - Enforce explicit Plan mode

Work SHALL be the default mode. Explicit Plan mode SHALL permit authorized reading, questions and task planning while blocking file mutations, shell execution, durable memory changes and effectful or unclassified external tools at backend dispatch. Internal checkpoints/context housekeeping remain available. The mode SHALL be frozen with queued turns and enforced for restored calls and helpers. Full access MUST NOT override it; returning to Work requires explicit user selection and a new submission.

#### Scenario: Plan with Full access
- **WHEN** a parent or helper in Plan attempts a write or shell call with Full access selected
- **THEN** the receiver observes no prohibited effect while authorized reads and questions remain usable.

### Requirement: AGT-021 - Keep delegated work within the conversation authority

Only explicitly selected frozen named agent versions SHALL be available as helpers. Each helper SHALL have isolated context, intersected parent authority, observable named activity and correctly owned approvals, cancellation and durable child identity. No recursive or general-purpose delegation SHALL be added by this selection. Calls sharing a managed model SHALL be serialized initially; alternate models MUST NOT silently unload a parent. Explicit tool-call budgets SHALL be enforced atomically across root and child calls, while unset budgets remain unset.

#### Scenario: Frozen helper and shared budget
- **WHEN** saved helper settings change after queueing and several helper calls compete for the last allowed tool call
- **THEN** the queued version and intersected authority are used and the explicit budget is not exceeded.

#### Scenario: Stop child work
- **WHEN** a conversation is stopped while a helper is generating or awaiting approval
- **THEN** new dispatch stops, owned cancellation is confirmed before terminal cancellation, and partial/uncertain outcomes remain truthful.

### Requirement: AGT-022 - Review only when requested and report genuine judgement

Review SHALL be off by default. Explicit Review before finishing SHALL show criteria and a limit of at most two revisions. Its grader SHALL be read-only and use the conversation model; one upstream review owner controls revisions. Executable checks, expected artifacts and model judgement SHALL remain distinct. Unresolved findings after the limit SHALL remain visible without autonomous continuation. The final answer alone MUST NOT be labelled an independent model review.

#### Scenario: Review disabled and bounded
- **WHEN** review is disabled
- **THEN** no reviewer call runs
- **AND** when explicitly enabled, genuine review results are retained and stop visibly after the chosen revision allowance without reviewer side effects.
