# Spec Delta

## ADDED Requirements

### Requirement: API-048 - Watch and control Chrome from the Chat rail

Chat SHALL provide a Browser rail page showing the selected conversation's live Chrome page, address, tabs, navigation, actual resolution, lifecycle and takeover controls. Browser activity SHALL open that rail for the currently selected chat. Closing the rail SHALL stop live viewing without closing the session. Frames SHALL remain bounded and temporary while explicit captures use the retained Library. Typed controls SHALL require backend-validated conversation/session/page identity and current control ownership. External page content MUST NOT acquire desktop/backend credentials. Disabled or unsupported browser features SHALL explain their corrective action.

#### Scenario: Hide and reopen the viewer
- **WHEN** a person closes and reopens the Browser rail during browsing
- **THEN** it reconnects to the same active page without navigation or lost browser state.

#### Scenario: Take control of a scaled page
- **WHEN** a person takes control and clicks or types in the scaled live view
- **THEN** input reaches the observed page at the corresponding actual viewport location only after the task has paused
- **AND** switching chats rejects delayed frames and input from the earlier chat.

#### Scenario: Change resolution
- **WHEN** an agent or person selects desktop, tablet, phone or custom resolution
- **THEN** the page layout uses those dimensions and the rail displays the applied size.
