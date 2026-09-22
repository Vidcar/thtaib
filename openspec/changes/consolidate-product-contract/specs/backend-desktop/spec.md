# Spec Delta

## ADDED Requirements

### Requirement: API-027 - Keep every destination compact and readable

Every destination SHALL use the same compact type, spacing, and icon actions as Chat. Headings stay short. The product name is not repeated on every panel. Help that is not required to act SHALL open on hover or keyboard focus and close on Escape. Primary actions, the current setup, errors, and permissions stay visible without opening a raw detail view. Keyboard focus is visible. Labels stay readable at the person's Windows text size. A disclosure is allowed to use a chevron. Resizing or collapsing navigation and the Chat dock MUST NOT drop content or run state.

#### Scenario: Move between destinations

- **WHEN** a person moves from Chat to Lab, Workflows, and Settings
- **THEN** the type, spacing, and focus treatment match
- **AND** the composer or the destination's primary action stays reachable without horizontal scrolling.

### Requirement: API-028 - Confirm before swapping the loaded model

Changing or unloading a model SHALL open a confirmation. The confirmation names the conversation that will be kept and any work that must finish or be stopped. It MUST NOT unload a model as a side effect of choosing a different row. After confirmation, the conversation, its draft, and its history remain. The screen shows waiting, loading, or the failure, and the draft is still there if loading fails.

#### Scenario: Swap during a quiet chat

- **WHEN** a person chooses another model and confirms
- **THEN** the same conversation stays open
- **AND** the previous model is not unloaded until that confirmation.

#### Scenario: Swap while work is running

- **WHEN** a reply or a Lab run is still using the model
- **THEN** the confirmation names that work and does not unload it silently.

### Requirement: API-029 - Show who is working and who is waiting

When a named helper or a workflow step is running, the activity view SHALL show that agent or step by its name under the parent conversation or workflow. Status uses plain words: working, waiting for approval, waiting for a typed answer, waiting for the model, or failed. The reason for a wait is one line. Child tool rows use the same one-line activity labels as API-026 and stay indented under that name. Stopping names what will stop. The view MUST NOT be the only place a person can approve or answer. Those cards stay in the conversation or on the workflow step.

#### Scenario: Helper waits for approval

- **WHEN** a named helper asks to edit a file
- **THEN** the activity row shows that helper's name and that it is waiting for approval
- **AND** the approval card remains the control that allows or rejects the edit.

### Requirement: API-030 - Present reusable agents as a calm list

The Agents destination SHALL list saved agents by name and role, with the model and whether anything they need is missing. Opening one shows its instructions, tools, knowledge, and helpers in the same controls as the chat setup popover. Create, duplicate, rename, and remove are explicit actions. Remove keeps past conversations that used an older version and says so. The list is empty with a single create action, not an explanation of storage. Missing dependencies are a short warning on the row, not a blocked page.

#### Scenario: Repair a missing model

- **WHEN** a saved agent points at a model that is no longer installed
- **THEN** its row says what is missing
- **AND** the person can open it and choose another model without losing the agent's name.
