# Spec Delta

## MODIFIED Requirements

### Requirement: AGT-001 - Use the embedded harness

Agent tasks SHALL run through `create_deep_agent` using LangChain components and LangGraph. Chat SHALL call the same harness with or without a bound project; the application MUST NOT add a model/tool loop. Each run executes once; native streaming, scoped selectors and audit projections observe that invocation while preserving message/block/tool and namespace identities. Without a project, project file tools SHALL be absent or rejected. This computer, when selected, SHALL start commands in the Windows user profile of the account that launched the app. That path SHALL be the resolved profile path, not an invented project and not an empty path. Explicitly supplied session attachments MAY be read through their authorized content/scoped backend without granting project or host access.

The harness SHALL receive the run's backend, filesystem permissions, `interrupt_on`, `memory`, and `skills` through those official parameters when the run uses them. Planning SHALL be the official `write_todos` tool when planning is selected. Exactly one Deep Agents summarization middleware SHALL run with its native model-aware trigger and retention defaults. It SHALL receive full observed per-request capacity and apply its native reservations/headroom once. Supported SDK configuration SHALL own token counting, retention, offloading, summary generation and overflow recovery; application budget overrides and extra percentage/output deductions MUST NOT alter those policies. The application MUST NOT set a separate early compaction threshold or stack another summarizer. Ordinary Chat SHALL disable the general-purpose subagent through the upstream profile switch, and SHALL NOT rely on a parent-only filter that a compiled child does not inherit. The product MUST NOT embed the Deep Agents CLI or a hosted agent runtime.

#### Scenario: Project-bound and project-free chat

- **WHEN** Chat performs a real project file task and then starts a non-project conversation
- **THEN** the shared harness owns iteration in both cases; non-project Chat has no project file authority, a selected This computer starts in the user profile, and authorized attachments remain usable.

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
- **THEN** one Deep Agents summarizer applies its native model-aware compaction defaults against the full observed model capacity with the framework policy applied once
- **AND** no custom early threshold or second summarizer shrinks that budget again.

### Requirement: AGT-004 - Separate active context from durable knowledge

The product SHALL use application-versioned user, agent, and project memory, skills, and protected instructions through configured backends. Selected versions SHALL use explicit loading modes: Always include memories through native memory middleware, When needed reference metadata with full original bodies read through their frozen versioned backend, skills through native progressive skill loading, and included protected instructions through the composed system prompt. Each newly submitted input SHALL atomically resolve the latest saved versions of selected memory, skills and protected instructions by their selected record identities and freeze those exact versions, including explicit deselection, before it is accepted for execution or queueing. Unsaved edits SHALL NOT participate. Running, queued and paused turns SHALL keep their frozen versions; approval or question resumes SHALL NOT refresh them. A missing or deleted selected record SHALL produce an actionable error rather than silently omitting it. A new chat SHALL start with its own selections. There is no second conversation that inherits them. Newly accepted selected references SHALL default to When needed. Always include SHALL include the full original memory text with visible estimated cost or fail actionably when irreducibly oversized. When needed SHALL disclose concise identifying metadata and retain full original readable text at the exact frozen version; it MUST NOT silently substitute keyword excerpts or summaries. Explicit Off/exclusions SHALL suppress future injection without deleting the source. Tools-off with a selected deferred reference SHALL provide actionable Include now, Remove or Enable reading choices without silently enabling tools. A new user turn SHALL load its admission-frozen current saved skill versions, including saved edits and deselection; an approval or question resume MUST NOT reload them. A memory suggestion SHALL remain a proposal until the person accepts or rejects it on the Knowledge page. There SHALL be no automatic-save switch. Full access and an approval card MUST NOT save a memory. Agents MUST NOT write skills or protected instructions. An accepted memory SHALL become a versioned record. Loading an accepted memory or skill into the prompt SHALL use the official memory and skills parameters already required by this capability. Protected instructions MUST reject agent-origin writes.

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

#### Scenario: A suggestion waits

- **WHEN** an agent proposes a memory, including while Full access is on or an approval card is showing
- **THEN** the suggestion waits for Accept or Reject on the Knowledge page
- **AND** there is no automatic-save switch, and neither Full access nor the card saves the memory.

### Requirement: AGT-007 - Preserve Chat continuity and restart truth

A session SHALL permanently belong to one project or the non-project area. One chat SHALL stay bound to that one project or non-project area. A different area requires a fresh session/thread. Removed projects retain historical session identity instead of converting sessions to non-project. Model/profile selection and authorized artifact reuse do not move sessions.

Continuing SHALL use the same saved thread with a new application run for only the new user input; fresh starts create new context. One turn per session SHALL execute at a time. Follow-ups SHALL wait in line. Persist model/profile/tool/setup selections and snapshot each turn's resolved setup, preserving omitted versus empty tools. Setup edits affect future work, not live/paused settings or history. Revalidate current access at dispatch/resume. Display-only history edits MUST NOT reset context or project files. Retry and Edit, specified as rewind, are not display-only edits. A display-only edit still MUST NOT reset context or project files. Rewind is specified by the rewind requirement. Restart SHALL reconcile persisted linkage and terminal state; missing linkage is an explicit gap, not a silently substituted thread.

#### Scenario: Restart then continue

- **WHEN** the backend restarts with a saved conversation and run linkage
- **THEN** continuation uses that conversation/thread and recorded configuration; missing linkage is reported rather than silently starting fresh.

#### Scenario: Different session area

- **WHEN** a user changes project area
- **THEN** changing area creates a fresh chat, while the original chat stays bound to its project or non-project area
- **AND** Retry and Edit rewind this chat rather than starting another conversation.

#### Scenario: One turn with a follow-up waiting

- **WHEN** a turn is already running in a chat and the person sends a follow-up
- **THEN** that chat stays bound to its one project or non-project area and only one turn runs at a time
- **AND** the follow-up waits in line.

#### Scenario: Display-only edit is not rewind

- **WHEN** a person makes a display-only history edit
- **THEN** that edit MUST NOT reset context or project files
- **AND** Retry and Edit are not display-only edits and follow the rewind requirement.

#### Scenario: Continue after an ordinary tool failure
- **WHEN** a terminal turn contains complete tool calls without final protocol results
- **THEN** safe native history normalization SHALL permit the next user turn without replaying previous effects
- **AND** successful siblings remain successful, uncertain effects require evidence inspection, and live approvals use their original resume path.

### Requirement: AGT-008 - Use framework interrupts for approvals

Protected tool actions SHALL use Deep Agents `interrupt_on` and LangGraph resume on the same checkpointer thread. A pending interrupt SHALL keep the run `running` with typed details, not a new lifecycle status. Cancellation SHALL use `cancel_requested` until the worker confirms `cancelled`. The UI SHALL offer **Approve once**, **Allow for this session**, **Always allow** and **Reject**, showing exact action/resource scope. Approve once SHALL be the pending action. Session allow SHALL be this conversation. Always allow for a command SHALL remember the exact command and the resolved starting folder, never an empty folder, for every chat that starts in that same folder. It MUST NOT skip the first This-computer card in a chat, and the stored grant SHALL apply only after this chat confirms. A user-profile command MUST NOT match a project-folder command. Other exact grants SHALL match the action name, its arguments, and the resolved project path. Every grant SHALL remain inspectable and revocable. There MUST NOT be a command-prefix grant. Reject does not create a permanent deny rule.

Chat SHALL offer Ask for approval and Full access with truthful effective values and named inherited sources. Ask SHALL pause before mutations, every shell command, window action, and external side effect unless an explicit saved matching grant applies. That grant MUST NOT skip the first This-computer card in a chat. After this chat has confirmed This computer, Full access SHALL skip those pauses for later enabled tools, including Delete of `.git` or a secret file, and the first This-computer card in that chat SHALL still show. Disabled tools SHALL stay off. Plan mode SHALL still block effects. A typed question SHALL still wait. Grants MUST NOT save durable memory and MUST NOT enable a tool that is off. Host shell SHALL be described as Windows-account authority, not a project sandbox. Plan mode SHALL override effectful execution under every access level.

The first time This computer is used in a chat, one card SHALL show the command and the resolved starting folder, in Ask and in Full access. A matching Always allow from another chat MUST NOT skip that card. The stored grant SHALL apply only after this chat confirms. Reject SHALL NOT confirm This computer, so the next This-computer command in that chat SHALL show the card again, and the other chat's grant SHALL remain. After this chat confirms, Ask SHALL pause unless a matching grant applies, including an Always allow from another chat for the same command and the same resolved starting folder. Full access SHALL NOT pause for a later enabled tool.

The four approval choices remain whenever a pause still happens. A queued turn keeps the mode it was queued with. Changing the mode applies to a later message and does not rewrite the saved agent.

Grants SHALL be rechecked at dispatch/resume and MUST NOT enable a tool that is off, expand denied access/child selection, save durable memory, or bypass authored workflow approval nodes. Read scope does not imply write/delete or global scope. Every decision SHALL identify its run, thread/checkpoint and exact interrupt. Reject stale/duplicate/wrong-run decisions; retain framework order for all actions inside one interrupt. Resume the saved interruption rather than resending the task. Cancel while interrupted SHALL reject/resume outstanding commands and reach cancelled only after owned work stops; external termination remains separately known or uncertain.

#### Scenario: Approve deny cancel

- **WHEN** a command pauses for approval
- **THEN** the chosen allowed framework decision resumes its saved interrupt, and cancellation prevents further dispatch without falsely claiming external work stopped.

#### Scenario: First This computer use in a chat

- **WHEN** This computer is used for the first time in a chat
- **THEN** one card shows the command and the starting folder, in Ask and in Full access
- **AND** after this chat confirms, Full access does not pause for a later enabled tool, while Ask still pauses unless a matching grant applies, including an Always allow from another chat for the same command and the same resolved starting folder.

#### Scenario: Another chat does not skip the first This-computer card

- **WHEN** another chat has Always allow for the same command and the same resolved starting folder, and this chat uses This computer for the first time, in Ask or in Full access
- **THEN** this chat still shows one card, and that grant does not skip it
- **AND** the stored grant applies only after this chat confirms.

#### Scenario: Reject does not confirm This computer

- **WHEN** this chat rejects the first This-computer card
- **THEN** that rejection does not confirm This computer, and the next This-computer command in that chat shows the card again
- **AND** the other chat's matching grant remains.

#### Scenario: Approval mode skips a pause

- **WHEN** a chat is set to Full access and the agent runs a later enabled command after This computer was confirmed in that chat
- **THEN** that action proceeds without a review card, while Ask pauses unless a saved matching grant applies
- **AND** a typed question still waits, a tool that is off is still refused, and a memory proposal is not saved.

#### Scenario: Full access deletes a protected path

- **WHEN** Full access is on and an enabled Delete targets `.git` or a secret file
- **THEN** that pause is skipped
- **AND** a disabled tool stays off, a typed question still waits, and Plan mode still blocks the effect.

#### Scenario: Ask pauses a window action

- **WHEN** Ask is selected and an enabled tool takes a window action, and no saved matching grant applies
- **THEN** the action pauses
- **AND** Full access skips that pause only while the tool is enabled.

#### Scenario: Always allow matches the starting folder

- **WHEN** Always allow is chosen for a command
- **THEN** it remembers the exact command and the resolved starting folder, never an empty folder, for every chat that starts in that same folder
- **AND** it does not skip the first This-computer card in a chat
- **AND** a user-profile command does not match a project-folder command, and there is no command-prefix grant.

#### Scenario: Session allow is this conversation

- **WHEN** Allow for this session is chosen
- **THEN** that allow covers the matching action in this conversation
- **AND** Approve once covers only the pending action.

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

Drafts and queued follow-ups SHALL survive navigation/reopening without becoming submitted history. A follow-up sent while a reply is running SHALL wait with the model, agent, access, and mode it had when sent. Changing the menu MUST NOT rewrite it. Retry and Edit SHALL use the choices selected when they start, and SHALL resolve knowledge, tools, and permissions as they are then. Shortcut text already in the message SHALL stay as sent. The admission freeze applies to a waiting follow-up and MUST NOT be applied to Retry or Edit. When an edited run is accepted, waiting follow-ups SHALL be removed with the later messages. If that run is refused, they SHALL stay. Closing the editor without sending SHALL leave them. Retry, when accepted, SHALL also clear the waiting line. Each queued item SHALL retain its admission-frozen intended configuration, exact authored versions and attachment identities, remain inspectable and removable, and allow only deliberate revision-checked edits. Success SHALL advance the queue. Failure or cancellation SHALL pause the queue until the person continues. An approval or input wait is not completion. Admission SHALL freeze that item's resolved setup before queue acceptance. Dispatch SHALL use that snapshot and recheck live authorization, model/history compatibility, and shared admission that is not a folder hold, without refreshing authored agent/knowledge versions. The recheck MUST NOT wait because another chat or Lab holds the project folder. Selector changes MUST NOT silently alter a queued item or cancel a live turn. A queued message MUST NOT interrupt active work; Stop is a separate explicit action and cancellation pauses the queue until deliberate continuation.

#### Scenario: Queue progression

- **WHEN** a turn succeeds, fails, is cancelled or waits for input
- **THEN** only success automatically dispatches the next eligible item; the other outcomes preserve or pause the queue as specified
- **AND** failure or cancellation pauses the queue until the person continues.

#### Scenario: Prepare a different follow-up

- **WHEN** a person changes the model, agent, access, mode, or tuning during a live turn after another message is queued
- **THEN** the queued follow-up keeps the model, agent, access, and mode it had when sent, and changing the menu does not rewrite it
- **AND** only a later newly accepted message uses the changed candidate, and current, queued and paused work retain their own snapshots.

#### Scenario: Accepted edit removes waiting follow-ups

- **WHEN** an edited run is accepted
- **THEN** waiting follow-ups are removed with the later messages
- **AND** if that run is refused, the waiting follow-ups stay.

#### Scenario: Edit closed without sending leaves the queue

- **WHEN** the person closes the editor without sending
- **THEN** the waiting follow-ups stay
- **AND** the queue remains inspectable and removable.

#### Scenario: Accepted retry clears the waiting line

- **WHEN** Retry is accepted
- **THEN** the waiting line is cleared
- **AND** Retry uses the choices selected when it starts.

#### Scenario: Restart with staged and queued work

- **WHEN** the application restarts with a saved next draft and accepted queued input
- **THEN** the draft restores as editable intent without model warming, and the queued input retains its exact snapshot without becoming a duplicate submitted message.

#### Scenario: Deliberate queued message revision

- **WHEN** a queued message is edited with its current revision
- **THEN** a text-only edit retains its exact authored versions and settings, while an explicit setup edit resolves and freezes the latest saved selected records again
- **AND** a stale edit or retry of the obsolete submission conflicts, while an identical retry of the revised submission reuses its saved snapshot without another queued message.

#### Scenario: Dispatch does not wait on a folder hold

- **WHEN** dispatch rechecks a queued item while another chat or Lab is using the same project folder
- **THEN** the recheck covers live authorization, model/history compatibility, and shared admission that is not a folder hold
- **AND** it MUST NOT wait because another chat or Lab holds the project folder, and it does not refresh authored agent or knowledge versions.

### Requirement: AGT-013 - Reconcile cancellation and crash boundaries honestly

Cancellation SHALL prevent further model/tool dispatch, including rejection/resume loops, pause follow-ups and clean only owned request resources. Partial output and completed changes remain inspectable. Application stop and host/remote termination SHALL remain separate; shared inference processes are not killed to cancel one request. Restart SHALL verify genuine pending framework interrupts, reconcile decision acceptance/checkpoint advancement/external dispatch, and resolve orphaned live runs. Historical checkpoints alone do not prove resumability; uncertain effects MUST NOT be blindly replayed. Checkpointing is neither exactly-once execution nor rollback. An uncertain command SHALL pause only that task. Other tasks in the folder SHALL continue. Cancellation MUST NOT restore files. The product MUST NOT require a project copy before another task may start.

#### Scenario: Crash around an effect

- **WHEN** the backend stops between external dispatch and acknowledgement
- **THEN** recovery keeps the outcome unknown or uses authoritative reconciliation, never silent replay or fabricated success.

#### Scenario: Cancel turn

- **WHEN** a cancellation arrives during streaming, tool work or an interrupt
- **THEN** new dispatch stops, the queue pauses and owned cancellation completes only when confirmed, preserving partial and uncertain outcomes
- **AND** cancellation does not restore files.

#### Scenario: Uncertain command in a shared folder

- **WHEN** a command's outcome is uncertain
- **THEN** only that task pauses
- **AND** other tasks in the folder continue, and another task does not need a project copy to start.

### Requirement: AGT-020 - Enforce explicit Plan mode

Work SHALL be the default mode. Explicit Plan mode SHALL present only authorized non-mutating project/context reading, questions, checklist and discovery capabilities, and selected trusted built-in public-web search/page reading. It SHALL reject shell execution, file mutation, delete, durable memory changes, browser, Windows control, and effectful or unclassified external operations under every approval level and invocation path. External read-only annotations or names SHALL NOT establish Plan eligibility. Internal checkpoints/context housekeeping SHALL remain available. The mode SHALL be frozen with queued turns and enforced for restored calls and helpers. Full access MUST NOT override it. Rewind in Plan SHALL stay Plan. Returning to Work SHALL require explicit user selection and a new submission.

#### Scenario: Plan with Full access
- **WHEN** a Plan-mode run attempts an effectful tool call
- **THEN** the call is rejected before execution regardless of Full access or saved grants.

#### Scenario: Rewind while Plan is selected

- **WHEN** a person rewinds a chat that is in Plan
- **THEN** the run stays Plan
- **AND** Full access does not override Plan, and shell, file mutation, delete, durable memory changes, browser, and Windows control stay blocked.

#### Scenario: Trusted web tools with arbitrary MCP selection
- **WHEN** Plan includes selected built-in public-web tools and an unrelated MCP tool claiming read-only behavior
- **THEN** only the trusted search/page reader can be disclosed and dispatched.

### Requirement: AGT-021 - Keep delegated work within the conversation authority

Only explicitly selected frozen named agent versions SHALL be available as helpers. Each helper SHALL have isolated context, the intersection of its tool ticks and the parent's tool ticks, the parent's window, and the same starting folder. It MUST NOT widen access. A helper SHALL run a skill script only when the helper and the parent both have that tool and the chat has a project. Observable named activity and correctly owned approvals, cancellation and durable child identity SHALL remain. No recursive or general-purpose delegation SHALL be added by this selection. Calls sharing a managed model SHALL be serialized within a parent run. That serialization MUST NOT make another task wait and is not a folder ban. If only one model fits, the next model call SHALL wait for the processor. That wait is not a folder ban. Several helpers and chats MAY use one folder at the same time. The application MUST NOT copy the folder, MUST NOT create a git branch or worktree to separate that work, and MUST NOT make the second task wait. An agent with This computer MAY create a branch or worktree when the person asks. Project file tools MUST NOT create a worktree. One file write SHALL finish before the next write to that same file. A read of that file SHALL wait, then see the new contents. Other files SHALL continue. An alternate-model helper MAY hand off a single loaded-model slot after the parent's current model call completes, and the parent SHALL reload its exact model before continuing. The handoff MUST NOT widen authority, interrupt an in-flight model call or report a stopped parent as ready. Explicit tool-call budgets SHALL be enforced atomically across root and child calls, while unset budgets remain unset.

#### Scenario: Frozen helper and shared budget
- **WHEN** saved helper settings change after queueing and several helper calls compete for the last allowed tool call
- **THEN** the queued version and intersected authority are used and the explicit budget is not exceeded.

#### Scenario: Helper keeps the parent's window and folder

- **WHEN** a helper is started
- **THEN** it receives the intersection of its tool ticks and the parent's tool ticks, the parent's window, and the same starting folder
- **AND** it cannot widen access, and it can run a skill script only when both have that tool and the chat has a project.

#### Scenario: Several tasks use one folder

- **WHEN** several helpers and chats use one folder at the same time
- **THEN** the application does not copy the folder, does not create a git branch or worktree, and does not make the second task wait
- **AND** one write finishes before the next write to that same file, a read of that file waits and then sees the new contents, and other files continue.

#### Scenario: One processor is not a folder ban

- **WHEN** only one model fits and another model call is ready
- **THEN** the next model call waits for the processor
- **AND** that wait is not a folder ban.

#### Scenario: Shared model calls in one parent run

- **WHEN** calls in one parent run share a managed model
- **THEN** those calls SHALL be serialized within that parent run
- **AND** that serialization does not make another task wait and is not a folder ban.

#### Scenario: Alternate model with one slot
- **WHEN** a parent delegates to a helper using a different installed model while the loaded-model limit is one
- **THEN** helper and parent calls run in sequence with visible loading or waiting and each uses its selected configuration
- **AND** that wait is for the processor and is not a folder ban.

#### Scenario: Replayed helper discovery in a later turn
- **WHEN** the public stream replays helpers from earlier turns while a new parent turn is active
- **THEN** each helper SHALL retain its owning parent-run and tool-call identity, even when call IDs repeat
- **AND** replay arrival timestamps MUST NOT establish ownership; the current parent's recorded task calls and child references SHALL determine membership
- **AND** child tool events from helper namespaces SHALL appear only in the scoped helper transcript, while the parent feed retains its compact delegation and parent-owned tools.

#### Scenario: Stop child work
- **WHEN** a conversation is stopped while a helper is generating or awaiting approval
- **THEN** new dispatch stops, owned cancellation is confirmed before terminal cancellation, and partial/uncertain outcomes remain truthful.

### Requirement: AGT-026 - Supply a bounded authorized project outline

Project chats with authorized file reading SHALL offer an optional outline capped at 1024 estimated tokens, showing relevant paths, declarations and headings. It SHALL respect exclusions and project boundaries, remain derived and disposable, label partial coverage, and yield context space to user input when the run starts. Tools-off and project-free requests MUST NOT receive it. The outline MUST NOT be called a snapshot. It is not a file copy. The product MUST NOT require a project copy before or after a run.

The outline SHALL reuse existing project exclusions and the actual enclosing repository's ignore rules. It SHALL use bounded file discovery and confined reads with a disposable bounded cache, not a durable repository index or unrestricted traversal. A project folder ignored by its enclosing repository MAY therefore have an empty outline.

An admitted run's outline SHALL remain its initial outline across model/tool continuations and MUST NOT be labelled a snapshot. Project changes SHALL remain available through appended tool results and fresh authorized reads, without rebuilding early system context after each tool. A subsequent run SHALL take a fresh bounded outline. Native context recovery SHALL remain available if the optional outline contributes to an overflow.

The project outline SHALL be an optional inspectable source controlled by the input loading policy. Excluding it MUST preserve bound project identity and authorized file-tool operation without automatic outline injection.

#### Scenario: Project changes during a run
- **WHEN** a tool adds or renames a declaration or file during an admitted run
- **THEN** the initial outline remains unchanged in subsequent model requests and the changed project facts are available through the tool history and authorized reads.

#### Scenario: Changed project and limited context
- **WHEN** a new run starts after project files change or has insufficient room for its optional outline
- **THEN** its fresh outline reflects the current project and is reduced or omitted without blocking the user's request.

#### Scenario: Outline is not a project copy

- **WHEN** a project chat prepares or finishes a run
- **THEN** the short outline MUST NOT be called a snapshot and is not a file copy
- **AND** a project copy is not required before or after the run.

### Requirement: AGT-032 - Preserve omitted capture policy settings

The product no longer has a stored model-request capture policy. Omitted fields MUST NOT revive one. Independent Knowledge catalogue, configuration and proposal failures SHALL not make otherwise available editing unusable.

#### Scenario: Omitted fields do not revive a capture policy

- **WHEN** an update omits fields that used to name capture redaction or retention
- **THEN** those omitted fields MUST NOT revive a stored model-request capture policy
- **AND** a Knowledge catalogue, configuration, or proposal failure does not make otherwise available editing unusable.

#### Scenario: Change redaction alone
- **WHEN** a person sends an update that used to change capture redaction without specifying retention
- **THEN** no stored model-request capture policy is created or changed.

#### Scenario: Change or clear retention
- **WHEN** a person sends an update that used to change or clear retention
- **THEN** no stored model-request capture policy is created or changed.

### Requirement: AGT-035 - Offer explicit conditional runtime workflows

The product SHALL offer an opt-in versioned library of project-change, failure-diagnosis, Windows-execution, delivery-verification, browser-validation, desktop-validation, evidence-research, delegate-review and memory-curation skills. Installation, selection, metadata discovery and body/resource reading SHALL remain distinct. Setup templates SHALL use real saved selections and disclose Chat-owned access/mode requirements without granting them. No template or skill SHALL silently enable capabilities, save durable memory, grant project/window/shell access or import repository development skills into ordinary Chat. The evidence-researcher template SHALL be usable for attached documents and retained results without a bound project. Project discovery in that template SHALL remain available only when a project is bound and SHALL NOT be required for a projectless run. The definition-loading preference SHALL NOT decide whether unpinned project reads can exist. A projectless run SHALL omit unpinned `glob` and `grep` under both Always include all and When needed. Unpinned `ls` and `read_file` SHALL NOT be project readers on that run: they are omitted unless a selected knowledge or capture route keeps them for its virtual paths, and that schema SHALL name those paths and SHALL NOT describe a project root. The saved tool list SHALL NOT be rewritten. Pinned project reads, skill-required project or shell tools, eager file mutations, and eager shell or preview SHALL still fail when no project is bound. New stock templates that consume retained evidence SHALL select the retained-result reader. Applying a template SHALL NOT rewrite an existing saved setup.

A skill script SHALL require This computer, the command shell, and a project. Preview SHALL remain separate, SHALL still require a project, and MUST NOT turn the shell on. Both SHALL fail without a project. No template SHALL silently enable shell, windows, delete, or memory saving.

#### Scenario: Install without applying
- **WHEN** a person installs the bundled skills or chooses an agent template
- **THEN** the existing selected agent, conversation permissions and knowledge versions are preserved until explicitly edited and submitted.

#### Scenario: Conditional activation and exclusion
- **WHEN** a meaningful project change or unrelated simple answer is requested
- **THEN** the relevant selected workflow can be loaded progressively while unrelated bodies remain deferred
- **AND** deselection and interrupt/resume retain the existing immutable version rules.

#### Scenario: Projectless document research
- **WHEN** the evidence-researcher template is saved and admitted with an attached document and no project, with or without the research skill, under either definition-loading preference
- **THEN** admission accepts the run and the document and retained-result readers are available
- **AND** the saved tool list is unchanged, project discovery is not authorized, and no public-web connection is created. With the research skill, a project path read is refused and any virtual skill reader names `/skills/` without describing a project root.

#### Scenario: Projectless eager mutation, shell, or pinned project read
- **WHEN** a projectless run keeps an eager file mutation, eager shell or preview, or a pinned project read
- **THEN** admission fails with an actionable project requirement and the tool is not executed.

#### Scenario: Skill script and preview without a project

- **WHEN** a skill script or a preview is requested and the chat has no project
- **THEN** both fail and neither runs
- **AND** preview does not turn the shell on, and no template silently enables shell, windows, delete, or memory saving.

#### Scenario: Skill script with the shell and a project

- **WHEN** a chat has This computer and a project, and both the skill and the chat have the command shell
- **THEN** the skill script SHALL be allowed to run
- **AND** preview stays a separate action and does not turn the shell on.

#### Scenario: Project-bound research keeps project reading
- **WHEN** the same template is admitted with a bound project
- **THEN** the project reading operations in the template remain available with the source readers.

#### Scenario: New template can read retained evidence
- **WHEN** a new stock template that consumes retained evidence is saved and compiled
- **THEN** its accepted selection includes the retained-result reader
- **AND** an existing saved setup is left unchanged.

### Requirement: AGT-036 - Approve project file changes without widening exact grants

The product SHALL offer a separately approved, inspectable and revocable project file-change grant for create and edit in one concrete project, including the exact multi-edit action. It MUST NOT authorize delete, shell, browser, connections, or memory saves. The grant SHALL last until revoked. It SHALL retain path exclusions and reject traversal, symbolic-link/junction escapes, managed knowledge routes and operations outside the granted set. `.git` SHALL always be excluded and MUST NOT be removed from this grant. `.env` and `.env.*` SHALL start excluded, and the person MAY remove that exclusion. More paths MAY be added. Another chat in the same project MAY use the grant. Turning it off SHALL stop the next edit. For one excluded-file edit, Approve once, Allow for this session, and Always allow each SHALL allow only that pending edit. A later identical edit SHALL pause again. The standing project-edit grant MUST NOT grow. Reject SHALL leave the exclusion. Those three buttons SHALL keep their usual durations for every other pause. This exception is only the excluded-file edit. This computer MAY still change those files with a command. Settings SHALL show the project, the allowed edits, the excluded paths, and "Until revoked". Existing exact-argument session/persistent grants SHALL keep their original meaning. All dispatch and resume paths SHALL recheck current selection, project identity and grant revocation. File-change authority MUST NOT imply deletion, shell, browser, external connection, protected instruction or durable memory authority.

#### Scenario: Two different edits within approved project scope
- **WHEN** a person deliberately grants create and edit in one concrete project, including an exact multi-edit, with exclusions
- **THEN** distinct eligible edits can proceed under Ask, including that multi-edit
- **AND** delete, shell, browser, connections, and memory saves still require their own authorization.

#### Scenario: Git stays excluded

- **WHEN** the person tries to remove `.git` from this grant
- **THEN** `.git` stays excluded and cannot be removed
- **AND** `.env` and `.env.*` start excluded, the person may remove that exclusion, and more paths may be added.

#### Scenario: Another chat uses the grant until it is turned off

- **WHEN** another chat in the same project edits an allowed file and the grant is then turned off
- **THEN** that other chat may use the grant while it is on
- **AND** turning it off stops the next edit.

#### Scenario: One exact edit of an excluded file

- **WHEN** the person chooses Approve once, Allow for this session, or Always allow for one excluded-file edit
- **THEN** each of those three buttons allows only that pending edit, and a later identical edit pauses again
- **AND** the standing grant does not grow, Reject leaves the exclusion, and This computer can still change those files with a command
- **AND** those three buttons keep their usual durations for every other pause.

#### Scenario: Revoke between approval and dispatch
- **WHEN** the grant is revoked or the selected project identity changes before an action dispatches
- **THEN** the stale grant does not authorize that action or a helper.

#### Scenario: Settings shows the standing grant

- **WHEN** the person opens the grant in Settings
- **THEN** Settings shows the project, the allowed edits, the excluded paths, and "Until revoked".

## ADDED Requirements

### Requirement: AGT-037 - Rewind this chat from Retry or Edit

Retry and Edit SHALL sit on the person's own sent messages. Copy SHALL stay on answers. Regenerate and Branch MUST be absent. There SHALL be no checkpoint dropdown and no "edit and branch" box. Retry SHALL keep the request text. Edit SHALL put that text and its attachments into the composer and SHALL cut only when that edited request is sent. Closing without sending SHALL leave the chat, the waiting line, and the previous composer draft unchanged, including that draft's attachments. Neither action SHALL ask for confirmation. When the run is accepted, including while an approval card is waiting, later messages SHALL be deleted from this chat and from search. They MUST NOT be kept as another chat. Their later checkpoints MAY go. The checkpoint used to return to the chosen request SHALL stay. That return SHALL use the public checkpoint API on this same thread. The application MUST NOT read or write checkpointer tables or build a second history store. Shortcut text already in the message SHALL stay as sent. Rejecting the approval MUST NOT restore the messages. If the run is refused, or the checkpoint is missing, nothing SHALL be removed and the run MUST NOT start. An unsent edit SHALL stay in the composer. A running turn MUST NOT be rewound; the hover SHALL say why. The run SHALL use the model, agent, access, and mode selected on the chat now. The current window selection and This-computer confirmation SHALL stay. Knowledge, tools, and permissions SHALL resolve as they are now. Files MUST NOT be restored. Library files, project files, and model files SHALL stay. A downloaded transcript file on disk MUST NOT be deleted. Rewind MUST NOT need a project copy. The one-task Workflows form MUST NOT grow this rewind. These actions SHALL be Chat only.

#### Scenario: Retry accepted

- **WHEN** the person chooses Retry on their own sent message and that run is accepted
- **THEN** the request text stays, later messages are deleted from this chat and from search, and they are not kept as another chat
- **AND** the checkpoint used to return to that request stays, later checkpoints may go, files are not restored, and no confirmation is asked
- **AND** library files, project files, and model files stay, a downloaded transcript file on disk is not deleted, rewind does not need a project copy, and the one-task Workflows form does not grow this rewind.

#### Scenario: Edit sent

- **WHEN** the person sends an edited request from their own sent message and that run is accepted
- **THEN** the chat is cut at that sent edit and later messages are deleted from this chat and from search
- **AND** the run uses the model, agent, access, and mode selected on the chat now, the current window selection and This-computer confirmation stay, and knowledge, tools, and permissions resolve as they are now
- **AND** Copy stays on answers, and Regenerate and Branch are absent.

#### Scenario: Edit closed without sending

- **WHEN** the person opens Edit and closes it without sending
- **THEN** the previous composer draft, including its attachments, the waiting line, and the messages are left unchanged
- **AND** the chat is not cut.

#### Scenario: Run refused

- **WHEN** Retry or a sent Edit is refused
- **THEN** nothing is removed and the run does not start
- **AND** an unsent edit stays in the composer.

#### Scenario: Missing checkpoint

- **WHEN** the checkpoint needed to return to the chosen request is missing
- **THEN** nothing is removed and the run does not start
- **AND** there is no checkpoint dropdown and no "edit and branch" box.

#### Scenario: Running turn

- **WHEN** a turn is running and the person points at Retry or Edit
- **THEN** the chat cannot be rewound
- **AND** the hover says why.

#### Scenario: Approval rejected after acceptance

- **WHEN** a rewind run has been accepted while an approval card is waiting and the person rejects that approval
- **THEN** the later messages stay deleted from this chat and from search
- **AND** rejecting the approval does not restore the messages.

### Requirement: AGT-038 - Preview the next message without storing the request

The product MUST NOT persist a copy of the request the model received. There SHALL be no stored actual-request list, no redaction setting for those copies, and no paste-a-capture box. Inputs SHALL preview only the next message: which instructions, memories, skills, and files will go out. The person MAY replace agent instructions for this chat and MAY explicitly save those instructions back onto the agent. Opening the preview MUST NOT call the model. Earlier turns remain the chat messages, not a stored request dump. Deep Agents compaction MAY keep its own scratch note of summarized turns; that note is not this preview and MUST NOT be shown as a stored request inspector.

#### Scenario: Preview the next message only

- **WHEN** a person opens Inputs
- **THEN** the preview shows only the next message, including which instructions, memories, skills, and files will go out
- **AND** opening it MUST NOT call the model, and earlier turns remain the chat messages rather than a stored request dump.

#### Scenario: No stored request copy

- **WHEN** a model request is sent
- **THEN** the product MUST NOT persist a copy of the request the model received
- **AND** there is no stored actual-request list, no redaction setting for those copies, and no paste-a-capture box.

#### Scenario: Replace instructions for this chat

- **WHEN** a person replaces agent instructions in the preview
- **THEN** the replacement applies to this chat
- **AND** those instructions are saved back onto the agent only when the person explicitly saves them.

#### Scenario: Compaction note is not the preview

- **WHEN** Deep Agents compaction keeps a scratch note of summarized turns
- **THEN** that note is not this preview
- **AND** it MUST NOT be shown as a stored request inspector.

## REMOVED Requirements

### Requirement: AGT-002 - Capture the actual model request
**Reason**: The product does not keep a copy of the request the model received. A requirement titled as capture would keep that store.
**Migration**: Inputs previews only the next message. Deep Agents may still keep its own scratch note of summarized turns. That note is not a request inspector.

### Requirement: AGT-012 - Distinguish branches, answer regeneration and effectful retry
**Reason**: Regenerate and a second conversation (Branch) are removed.
**Migration**: Retry and Edit rewind this chat. See the added rewind requirement.
