# Spec Delta

## ADDED Requirements

### Requirement: API-045 - Show delegated Chat work at its source and in the helper rail

Chat SHALL show each named helper delegation in the parent transcript when the call starts, including the frozen helper name, the exact request sent, and its current status. Selecting the delegation SHALL open that helper's user-visible messages, tool calls, results, and errors in the existing expandable rail, live and after reopening the chat. The parent answer SHALL remain in the main transcript; child output and the raw helper tool result SHALL NOT appear there as separate answers. The existing rail toggle SHALL be the sole top-level helper entry point, indicate live helper activity, and SHALL NOT open automatically. Approvals and typed questions SHALL remain actionable in the conversation. Unavailable historical child detail SHALL be labelled as incomplete rather than invented.

#### Scenario: Delegate while the helper waits for a model

- **WHEN** a parent starts a named helper call that must wait for its model
- **THEN** the exact delegation request and waiting status appear before model admission finishes, and the helper appears in the rail without opening it automatically.

#### Scenario: Inspect live and reopened work

- **WHEN** a helper emits messages, tool calls, or a failure and the person selects it during execution or after reopening Chat
- **THEN** those public events appear under that helper in the rail, while the parent's answer remains in the main transcript.

#### Scenario: Delegation identifiers repeat in later turns

- **WHEN** separate turns reuse a tool-call identifier for differently named helpers
- **THEN** each delegation retains its frozen name and opens only its own transcript, and an unrelated tool result in a later turn remains visible.

## MODIFIED Requirements

### Requirement: API-043 - Show visual testing access and evidence in Chat

The Chat composer `+` capability menu SHALL be the single home for Browser and Windows control selection, browser availability and session recovery, and Windows Off, Selected window and All windows controls with resolved access and active session state. The menu SHALL remain reachable for installation and status before a model is selected. Window selection and broad access SHALL be explicit and revocable. A selected capability whose worker or grant is unavailable SHALL show its intended selection and a corrective action, not claim readiness. Chat SHALL show a retained capture thumbnail and Open action with its page or window source and observation time, and Library SHALL expose the same authorized record. A text-only or unverified vision setup SHALL explain why pixel inspection is unavailable while keeping structural browser and accessibility inspection usable.

#### Scenario: Capture is inspectable

- **WHEN** an agent captures a permitted page or window
- **THEN** Chat shows the capture, its target and time, and the same retained item can be opened in Library without a second media store.

#### Scenario: Windows scope changes

- **WHEN** a person changes a conversation from All windows to Selected window
- **THEN** the shown effective access narrows immediately and subsequent calls cannot use the former broad grant.

#### Scenario: Worker installation without a model

- **WHEN** no model is selected and the optional Browser worker is absent
- **THEN** the `+` menu offers its installation and truthful availability without creating a chat or granting access.
