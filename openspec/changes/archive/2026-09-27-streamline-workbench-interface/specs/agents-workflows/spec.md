# Spec Delta

## MODIFIED Requirements

### Requirement: AGT-004 - Separate active context from durable knowledge

The product SHALL use application-versioned user, agent, and project memory, skills, and protected instructions through configured backends. Selected versions SHALL be loaded as content: memory through official `memory=`, skills through official `skills=`, and protected instructions through the composed system prompt. Each newly submitted input SHALL atomically resolve the latest saved versions of selected memory, skills and protected instructions by their selected record identities and freeze those exact versions, including explicit deselection, before it is accepted for execution or queueing. Unsaved edits SHALL NOT participate. Running, queued and paused turns SHALL keep their frozen versions; approval or question resumes SHALL NOT refresh them. A missing or deleted selected record SHALL produce an actionable error rather than silently omitting it. A branch SHALL inherit its source selections until explicitly changed. The full selected memory text SHALL be included with visible estimated cost or fail actionably when irreducibly oversized; keyword matching MUST NOT silently omit it. A new user turn SHALL load its admission-frozen current saved skill versions, including saved edits and deselection; an approval or question resume MUST NOT reload them. Automatic writes SHALL require explicit scope policy, provenance, and concurrent-write handling. Protected instructions MUST reject agent-origin writes.

#### Scenario: Versioned knowledge and fresh conversation

- WHEN a fresh conversation selects retained files and knowledge
- THEN durable knowledge and project files MUST be available without inheriting previous active context
- AND memory edit, revert, denied protected-instruction overwrite, and concurrent conflict MUST preserve version policy.

#### Scenario: Knowledge changes between turns

- **WHEN** selected skills, memory or protected instructions receive a new saved version after an input has already been queued
- **THEN** the next new submission resolves those latest saved versions, while the already queued input and resumed interruptions keep their original versions
- **AND** unsaved source/editor changes do not affect any submission.

#### Scenario: Current memory identity after a version change

- **WHEN** a new turn changes or clears selected memory
- **THEN** its current-user context SHALL identify the exact frozen version IDs or explicit absence, and the native memory source paths SHALL identify those same immutable versions
- **AND** the full selected contents SHALL be formatted only through native memory middleware, without duplicating them in the selection notice or rewriting prior messages
- **AND** a helper SHALL receive its own frozen selected versions and an interrupted run SHALL retain its original version paths for permitted reads.

#### Scenario: Save races admission

- **WHEN** knowledge is saved concurrently with a new submission
- **THEN** the accepted input records one consistent exact version selection, and dispatch, request inspection and native content paths use those same versions.

### Requirement: AGT-010 - Keep drafts and queued turns separate from execution

Drafts and queued follow-ups SHALL survive navigation/reopening without becoming submitted history. Each queued item SHALL retain its admission-frozen intended configuration, exact authored versions and attachment identities, remain inspectable/removable, and allow only deliberate revision-checked edits. Successful completion advances automatically; failure/cancellation pauses until deliberate continuation; an approval/input wait is not completion. Admission SHALL freeze that item's resolved setup before queue acceptance. Dispatch SHALL use that snapshot and recheck live authorization, model/history compatibility and shared admission, including active Lab reservation, without refreshing authored agent/knowledge versions. Selector changes MUST NOT silently alter a queued item or cancel a live turn. A queued message MUST NOT interrupt active work; Stop is a separate explicit action and cancellation pauses the queue until deliberate continuation.

#### Scenario: Queue progression

- **WHEN** a turn succeeds, fails, is cancelled or waits for input
- **THEN** only success automatically dispatches the next eligible item; the other outcomes preserve or pause the queue as specified.

#### Scenario: Prepare a different follow-up

- **WHEN** a person changes the model, agent or tuning during a live turn after another message is queued
- **THEN** only a later newly accepted message uses the changed candidate, and current, queued and paused work retain their own snapshots.

#### Scenario: Restart with staged and queued work

- **WHEN** the application restarts with a saved next draft and accepted queued input
- **THEN** the draft restores as editable intent without model warming, and the queued input retains its exact snapshot without becoming a duplicate submitted message.

#### Scenario: Deliberate queued message revision

- **WHEN** a queued message is edited with its current revision
- **THEN** a text-only edit retains its exact authored versions and settings, while an explicit setup edit resolves and freezes the latest saved selected records again
- **AND** a stale edit or retry of the obsolete submission conflicts, while an identical retry of the revised submission reuses its saved snapshot without another queued message.

### Requirement: AGT-019 - Offer only named helpers

Ordinary Chat SHALL keep the general-purpose helper disabled. A person SHALL be able to name saved agents as helpers in the main agent's saved setup, resolved into the conversation's accepted setup. When that list is empty, no helper tool is offered. When it names agents, only those agents are offered, each with the frozen setup shown in the list, and none of them can gain permissions the conversation does not have. Agents setup SHALL show a Helpers section. The empty section SHALL use concise copy and an add action rather than repeated standing explanation. Each chosen helper is a row with its name and model, and it can be removed. Choosing a helper does not start it.

#### Scenario: No helpers configured

- **WHEN** a conversation has an empty helpers list
- **THEN** the model cannot call a helper
- **AND** Agents setup offers a concise empty Helpers section without enabling general-purpose delegation.

#### Scenario: Named helper cannot widen access

- **WHEN** a conversation names one saved agent and that agent attempts a tool the conversation is not allowed
- **THEN** the tool is refused
- **AND** the activity row shows that helper by name.

### Requirement: AGT-024 - Keep agent role independent of conversation model

A conversation SHALL own its inherited main-model choice, main-agent selection, access and mode; the selected saved main agent SHALL own instructions, named helpers, enabled tool groups/individual choices, connections and knowledge defaults. A saved agent SHALL default to Use Chat model and SHALL optionally select a specific saved model/configuration. Choosing an inherited-model agent SHALL retain the chat model; choosing a fixed-model agent SHALL intentionally select its assigned model with the same idle-loading or active-staging rules as direct selection. The chat's inherited model choice SHALL remain available when returning to an inherited-model agent. Editing or selecting an agent MUST NOT grant access, widen live window scope or change running/queued/paused snapshots. New submissions SHALL resolve the latest saved selected agent and freeze its exact version before admission. A helper's assigned model SHALL remain optional and an unbound helper SHALL inherit its parent's effective model. Project context SHALL NOT supply model, agent, mode, tools or access defaults. The backend SHALL resolve these owners once for the accepted input and expose consistent effective values/reasons to Chat.

#### Scenario: Main agent changes without model switch
- **WHEN** a person chooses another compatible main agent configured to Use Chat model
- **THEN** the inherited chat model remains selected and no model is loaded solely because of that agent change.

#### Scenario: Project supplies context only
- **WHEN** a project chat selects a model, agent and access choice
- **THEN** the project folder and knowledge are available within that chat's authority while the model, agent and access come from the conversation and application preference.

#### Scenario: Model selected before agent

- **WHEN** a person chooses a model and then an inherited-model main agent for a new chat
- **THEN** the displayed exact chat model remains in the submitted setup, just as when the inherited-model agent is chosen first.

#### Scenario: Fixed-model agent selection

- **WHEN** a person selects an agent assigned to a specific model/configuration
- **THEN** that exact assignment becomes the effective model and loads immediately when idle or stages for a later new submission when active
- **AND** the prior inherited chat-model choice remains available when selecting an inherited-model agent again.

#### Scenario: Agent tools remain inside chat authority

- **WHEN** a saved agent includes Browser, shell or Windows tools
- **THEN** the new submission resolves those selected tools but current chat/project authority, access, mode and live grants still restrict their presentation and execution.

## ADDED Requirements

### Requirement: AGT-031 - Author saved skills through guided fields and native source

Knowledge SHALL retain searchable Skills, Memories and Instructions lists with their existing scope, version and import/resource controls. Skill authoring SHALL default to guided Name, When to use, Instructions and supporting-file fields, with a Source tab for native SKILL.md editing. Both views SHALL edit one draft; switching views SHALL preserve metadata, source content and supporting resources, including imported fields not represented by the guided controls. Backend native parsing and lossless source edits SHALL validate the draft; pending or failed guided transformations SHALL preserve editable fields and prevent saving stale source. Invalid or unrepresentable source SHALL report an actionable validation issue without discarding it or replacing it with fabricated guided values. A valid native source that Guided cannot represent SHALL remain savable in Source. Saving SHALL validate native identity and uniqueness among active skill records in the same scope and scope identity, create one immutable source/resources version and update the saved record for future submissions. Disabled active records SHALL still reserve their skill identity. Supporting files SHALL allow draft add, replacement and removal within existing safe-path, link, count and size limits without executing scripts or installing dependencies. Unsaved changes SHALL NOT update agents or accepted work. Existing memory proposal policies and protected-instruction write restrictions SHALL remain enforced.

#### Scenario: Imported skill round trip
- **WHEN** a native package contains extra frontmatter and supporting files and the person edits a guided field then inspects Source
- **THEN** the changed field and retained source metadata/resources remain consistent without silently losing imported content.

#### Scenario: Save updates future agent use
- **WHEN** a skill selected by an agent is saved and another new message is submitted
- **THEN** that message resolves the latest saved skill while older queued/running/paused messages retain their exact versions.

#### Scenario: Invalid source remains editable
- **WHEN** edited native source cannot be represented or validated
- **THEN** the source draft remains available with its specific issue, invalid native source cannot create a saved version, and valid native source remains savable through Source even if Guided is unavailable.

#### Scenario: Supporting files save with the source

- **WHEN** supporting files are added, replaced or removed and the skill is explicitly saved
- **THEN** one new immutable version contains the matching source and resources, while earlier versions retain their original files
- **AND** unsafe paths, links, collisions or exceeded package limits reject the save without replacing the saved record.

#### Scenario: Skill identity belongs to its scope

- **WHEN** a skill is saved using the same native name as another active skill in the same scope and scope identity
- **THEN** the save reports a conflict even when the other record is disabled
- **AND** an identical name in a different scope or scope identity remains valid.
