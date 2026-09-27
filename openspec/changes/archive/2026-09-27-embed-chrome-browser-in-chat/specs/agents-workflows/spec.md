# Spec Delta

## ADDED Requirements

### Requirement: AGT-030 - Pause the complete task during browser takeover

Browser takeover SHALL immediately prevent further model and tool dispatch for the task and its inline helpers, allow current operations to settle, and enable manual input only after settlement. Native durable interruption SHALL preserve task continuation, cancellation and independently pending approvals. Return to agent SHALL inspect the changed page before further interaction and SHALL not execute a stale proposed browser mutation against changed page state. Takeover SHALL remain distinguishable from an access approval and MUST NOT broaden tool or helper rights. Human keystrokes and clipboard contents MUST NOT be recorded in the transcript.

#### Scenario: Takeover while a helper works
- **WHEN** a person takes browser control during concurrent parent/helper work
- **THEN** no additional model/tool dispatch occurs after the takeover barrier, current operations settle without deadlock, and the complete task waits until control is returned.

#### Scenario: Return after navigation
- **WHEN** a person changes the page and returns control
- **THEN** the agent receives current page structure and supported visual observation before choosing its next browser action rather than blindly applying a prior target.

#### Scenario: Stop or pending approval
- **WHEN** a task is stopped during takeover or already awaits an approval
- **THEN** Stop remains effective and returning browser control does not approve or replay another pending action.
