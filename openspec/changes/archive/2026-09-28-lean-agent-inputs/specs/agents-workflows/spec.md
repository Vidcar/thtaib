# Spec Delta

## MODIFIED Requirements

### Requirement: AGT-002 - Capture the actual model request

The product SHALL instrument the final model-adapter boundary after context middleware, including official memory, skills, retrieval, summaries, and offloaded content when applied. Captures SHALL link actual instructions, selected knowledge versions, available tools, usage, provenance, redaction, and capture gaps to each call. Captures MUST expose request visibility only and MUST NOT claim access to hidden model reasoning.

Chat and agent preview SHALL share a What the agent sees inspector. It SHALL distinguish the next-request candidate from each actual model request, identify source origin, loading mode, inclusion reason, estimated cost and immutable versions, and permit lazy expansion of permitted verbatim text and tool definitions. Redaction, capture gaps, model-native formatting and estimates SHALL be explicit. Opening inspection MUST NOT execute a model or tool.

#### Scenario: Capture after context middleware

- WHEN a request is captured after compaction with memory or skills selected
- THEN the capture MUST match what the adapter sends, after configured redaction
- AND unread skill bodies MUST remain off the wire.

### Requirement: AGT-004 - Separate active context from durable knowledge

The product SHALL use application-versioned user, agent, and project memory, skills, and protected instructions through configured backends. Selected versions SHALL use explicit loading modes: Always include memories through native memory middleware, When needed reference metadata with full original bodies read through their frozen versioned backend, skills through native progressive skill loading, and included protected instructions through the composed system prompt. Each newly submitted input SHALL atomically resolve the latest saved versions of selected memory, skills and protected instructions by their selected record identities and freeze those exact versions, including explicit deselection, before it is accepted for execution or queueing. Unsaved edits SHALL NOT participate. Running, queued and paused turns SHALL keep their frozen versions; approval or question resumes SHALL NOT refresh them. A missing or deleted selected record SHALL produce an actionable error rather than silently omitting it. A branch SHALL inherit its source selections until explicitly changed. Newly accepted selected references SHALL default to When needed. Always include SHALL include the full original memory text with visible estimated cost or fail actionably when irreducibly oversized. When needed SHALL disclose concise identifying metadata and retain full original readable text at the exact frozen version; it MUST NOT silently substitute keyword excerpts or summaries. Explicit Off/exclusions SHALL suppress future injection without deleting the source. Tools-off with a selected deferred reference SHALL provide actionable Include now, Remove or Enable reading choices without silently enabling tools. A new user turn SHALL load its admission-frozen current saved skill versions, including saved edits and deselection; an approval or question resume MUST NOT reload them. Automatic writes SHALL require explicit scope policy, provenance, and concurrent-write handling. Protected instructions MUST reject agent-origin writes.

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
- **AND** Always include contents SHALL be formatted only through native memory middleware and When needed contents SHALL be loaded only from frozen original version paths, without duplicating them in the selection notice or rewriting prior messages
- **AND** a helper SHALL receive its own frozen selected versions and an interrupted run SHALL retain its original version paths for permitted reads.

#### Scenario: Save races admission

- **WHEN** knowledge is saved concurrently with a new submission
- **THEN** the accepted input records one consistent exact version selection, and dispatch, request inspection and native content paths use those same versions.

#### Scenario: Deferred reference then saved edit
- **WHEN** an accepted turn has a When needed memory and its source is subsequently edited
- **THEN** initial input contains only its identifying metadata and a later read returns the entire originally accepted version
- **AND** the next newly accepted turn may resolve the newer saved version.

### Requirement: AGT-005 - Do not silently remove enabled tools

Tool-selection middleware MAY narrow tools presented for a call, but product discovery SHALL keep the current enabled catalogue visible and SHALL distinguish implemented planning from deferred delegation. Selection SHALL optimize context and MUST NOT become a new access-policy owner.

Newly accepted inputs SHALL default enabled tools to When needed, with explicit Always include pins and an eager mode available. A compact discovery interface SHALL expose only the accepted enabled capability envelope and activate a small matching tool set without another selector model call. Active tool schemas SHALL be deterministic within a turn, persisted for resume and reset for the next newly accepted input except for pins. Disclosure MUST NOT grant permission, activate disabled tools or bypass context capacity.

#### Scenario: Narrowed tool list

- WHEN a call receives a narrowed tool list
- THEN enabled tools outside the list MUST remain discoverable
- AND denied tools MUST remain denied while authorized tools are not permanently hidden.

#### Scenario: Discover and pin
- **WHEN** an agent needs an enabled unpinned tool
- **THEN** discovery activates its applicable schema for subsequent model requests and execution retains the same access checks
- **AND** explicitly pinned tools are supplied initially while unrelated enabled definitions remain deferred.

### Requirement: AGT-024 - Keep agent role independent of conversation model

A conversation SHALL own its inherited main-model choice, main-agent selection, access and mode; the selected saved main agent SHALL own instructions, named helpers, enabled tool groups/individual choices, connections and knowledge defaults. A saved agent SHALL default to Use Chat model and SHALL optionally select a specific saved model/configuration. Choosing an inherited-model agent SHALL retain the chat model; choosing a fixed-model agent SHALL intentionally select its assigned model with the same idle-loading or active-staging rules as direct selection. The chat's inherited model choice SHALL remain available when returning to an inherited-model agent. Editing or selecting an agent MUST NOT grant access, widen live window scope or change running/queued/paused snapshots. New submissions SHALL resolve the latest saved selected agent and freeze its exact version before admission. A helper's assigned model SHALL remain optional and an unbound helper SHALL inherit its parent's effective model. Project context SHALL NOT supply model, agent, mode, tools or access defaults. The backend SHALL resolve these owners once for the accepted input and expose consistent effective values/reasons to Chat.

Chat MAY replace supplied agent behaviour text, exclude optional instruction/context sources and adjust loading modes locally without saving the agent or widening its enabled capability envelope. The inspector SHALL clearly identify the local override. Save to agent SHALL explicitly create a reusable saved version; omitted changes SHALL remain chat-local. Model-authored optional instructions SHALL be visible and editable/resettable in their owning saved setup; model-native formatting remains automatic.

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

### Requirement: AGT-026 - Supply a bounded authorized project outline

Project chats with authorized file reading SHALL offer an optional outline capped at 1024 estimated tokens, showing relevant paths, declarations and headings. It SHALL respect exclusions and project boundaries, remain derived and disposable, label partial coverage, and yield context space to user input when the run starts. Tools-off and project-free requests MUST NOT receive it.

The outline SHALL reuse existing project exclusions and the actual enclosing repository's ignore rules. It SHALL use bounded file discovery and confined reads with a disposable bounded cache, not a durable repository index or unrestricted traversal. A project folder ignored by its enclosing repository MAY therefore have an empty outline.

An admitted run's outline SHALL be labelled as its initial project snapshot and remain stable across model/tool continuations. Project changes SHALL remain available through appended tool results and fresh authorized reads, without rebuilding early system context after each tool. A subsequent run SHALL take a fresh bounded snapshot. Native context recovery SHALL remain available if the optional snapshot contributes to an overflow.

The project outline SHALL be an optional inspectable source controlled by the input loading policy. Excluding it MUST preserve bound project identity and authorized file-tool operation without automatic outline injection.

#### Scenario: Project changes during a run
- **WHEN** a tool adds or renames a declaration or file during an admitted run
- **THEN** the initial outline remains unchanged in subsequent model requests and the changed project facts are available through the tool history and authorized reads.

#### Scenario: Changed project and limited context
- **WHEN** a new run starts after project files change or has insufficient room for its optional outline
- **THEN** its fresh outline reflects the current project and is reduced or omitted without blocking the user's request.

### Requirement: AGT-031 - Author saved skills through guided fields and native source

Knowledge SHALL retain searchable Skills, Memories and Instructions lists with their existing scope, version and import/resource controls. Skill authoring SHALL default to guided Name, When to use, Instructions and supporting-file fields, with a Source tab for native SKILL.md editing. Both views SHALL edit one draft; switching views SHALL preserve metadata, source content and supporting resources, including imported fields not represented by the guided controls. Backend native parsing and lossless source edits SHALL validate the draft; pending or failed guided transformations SHALL preserve editable fields and prevent saving stale source. Invalid or unrepresentable source SHALL report an actionable validation issue without discarding it or replacing it with fabricated guided values. A valid native source that Guided cannot represent SHALL remain savable in Source. Saving SHALL validate native identity and uniqueness among active skill records in the same scope and scope identity, create one immutable source/resources version and update the saved record for future submissions. Disabled active records SHALL still reserve their skill identity. Supporting files SHALL allow draft add, replacement and removal within existing safe-path, link, count and size limits without executing scripts or installing dependencies. Unsaved changes SHALL NOT update agents or accepted work. Existing memory proposal policies and protected-instruction write restrictions SHALL remain enforced.

Guided and Source skill editing SHALL preserve declared required tools, selected connections and project context. Declarations SHALL describe dependencies without enabling tools, widening access or revealing credentials. An unmet declaration SHALL produce a specific setup action when the skill is needed; task-specific choices SHALL use the existing typed user-question path.

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

#### Scenario: Skill requirement round trip
- **WHEN** required tools, connections or project context are edited through Guided fields and reopened in Source
- **THEN** the declared values survive save, import, duplication and exact-version selection
- **AND** the required capability remains subject to the user's selected tools and access.

## ADDED Requirements

### Requirement: AGT-033 - Keep agent inputs compact and under user control

Automatic operating guidance SHALL be concise, feature-specific and inspectable. Repeated application guidance SHALL be supplied once; tool argument documentation SHALL match actual routing and execution without changing validation. User-authored text MUST NOT be automatically rewritten. Users SHALL be able to explicitly suppress inherited optional information, replace agent instruction text for one chat, and choose reference loading without changing reusable defaults.

#### Scenario: Explicit exclusion of inherited knowledge
- **WHEN** a person excludes optional material inherited from an agent or project
- **THEN** the next accepted input suppresses that source despite inherited selections
- **AND** running, queued and paused snapshots remain unchanged.

#### Scenario: Exclusion after earlier disclosure
- **WHEN** excluded text was previously supplied in retained conversation context
- **THEN** the inspector explains that earlier context remains and offers a fresh chat with the current choices
- **AND** it does not claim that exclusion makes the model forget historical content.

#### Scenario: Chat-local instruction replacement
- **WHEN** a person edits supplied agent behaviour through Chat
- **THEN** the local text replaces that instruction block without duplicating it
- **AND** only explicit Save to agent updates reusable defaults.
