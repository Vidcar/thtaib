# Spec Delta

## MODIFIED Requirements

### Requirement: API-030 - Present reusable agents as a calm list

The Agents destination SHALL list saved agents by name and role, with Use Chat model or the assigned model and any missing dependency. New-agent creation SHALL be guided through role/instructions, model/tools/knowledge and review/save; existing agents SHALL open a grouped editor using the same canonical configuration controls. Agents SHALL expose tool groups and individual selection, knowledge defaults, optional fixed model and named helpers. The Chat agent dropdown SHALL select saved agents only, without exposing setup or tool toggles. Create, duplicate, rename and remove SHALL be explicit. Removal SHALL retain past conversations and frozen older versions, with effect detail available on demand. An empty list SHALL offer one create action rather than storage explanation; missing dependencies SHALL be a short actionable row warning rather than blocking the whole page.

Agent creation and editing SHALL present each tool group as one compact rounded row, with its name on the left, one selected/total count on the right and the group switch at the far right. Clicking the row SHALL expand or collapse its indented individual tools without a group expansion arrow or separate individual-tools heading. Individual switches and tool information SHALL remain available. Group expansion and selection SHALL be independent keyboard-accessible controls with visible focus and an announced expanded state. Groups SHALL initially be collapsed, open independently and retain their expansion while selections change. The group switch SHALL be on only when all tools in that group are selected; turning it on SHALL enable the remaining tools, and turning it off SHALL clear the group. Toggles SHALL NOT change expansion. Existing bulk actions, loading/unavailable information and disabled selection states SHALL remain available. Expansion SHALL be local presentation state; selection SHALL use the existing saved agent configuration and SHALL NOT grant access.

#### Scenario: Repair a missing model

- **WHEN** a saved agent points at a model that is no longer installed
- **THEN** its row says what is missing
- **AND** the person can open it and choose another model without losing the agent's name.

#### Scenario: Save agent edits while Chat works

- **WHEN** an agent's tools or knowledge defaults are saved during an active chat
- **THEN** a later new submission resolves the latest saved agent, while running and already queued work keeps its exact earlier setup.

#### Scenario: Review an unsaved new agent

- **WHEN** a person advances through Role, Setup and Review or goes Back between those steps
- **THEN** the complete local draft remains available and no saved agent version is created until explicit Save on Review
- **AND** a failed Save retains the draft for correction and retry.

#### Scenario: Expand a group independently of selection

- **WHEN** a person clicks a collapsed group row in agent creation or editing
- **THEN** its individual tool choices appear underneath and the selected tools do not change
- **AND** another group can remain expanded, each group count appears once, and clicking an individual or group toggle retains the expansion.

#### Scenario: Complete and clear a partial group

- **WHEN** some tools in a group are selected and the person turns on its group switch
- **THEN** the remaining tools in that group become selected and tools in other groups retain their selections
- **AND** turning the group switch off clears that group without changing expansion or granting access.

#### Scenario: Use keyboard disclosure during a disabled edit

- **WHEN** selection controls are disabled during a save and the person focuses a group row
- **THEN** Enter or Space can still inspect its individual choices with visible focus and an announced expanded state
- **AND** disabled group and individual switches cannot change the draft.
