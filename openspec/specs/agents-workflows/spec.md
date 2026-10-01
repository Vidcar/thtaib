# Agents Workflows

## Purpose

Specify how Chat and Workflows use the embedded Deep Agents harness and LangGraph runtime while keeping active context, displayed history, configuration links, workflow sequencing, and durable knowledge distinct.

Chat and named helpers are implemented. The canvas contract remains WF-012 and is delivered by [consolidate-product-contract](../../changes/consolidate-product-contract/tasks.md). Until that screen exists, the sidebar page is the one-task form.

## Requirements

### Requirement: AGT-001 - Use the embedded harness

Agent tasks SHALL run through `create_deep_agent` using LangChain components and LangGraph. Chat SHALL call the same harness with or without a bound project; the application MUST NOT add a model/tool loop. Each run executes once; native streaming, scoped selectors and audit projections observe that invocation while preserving message/block/tool and namespace identities. Without a project, project-filesystem and host-shell access SHALL be absent or rejected, not assigned an invented working directory. Explicitly supplied session attachments MAY be read through their authorized content/scoped backend without granting project or host access.

The harness SHALL receive the run's backend, filesystem permissions, `interrupt_on`, `memory`, and `skills` through those official parameters when the run uses them. Planning SHALL be the official `write_todos` tool when planning is selected. Exactly one Deep Agents summarization middleware SHALL run with its native model-aware trigger and retention defaults. It SHALL receive full observed per-request capacity and apply its native reservations/headroom once. Supported SDK configuration SHALL own token counting, retention, offloading, summary generation and overflow recovery; application budget overrides and extra percentage/output deductions MUST NOT alter those policies. The application MUST NOT set a separate early compaction threshold or stack another summarizer. Ordinary Chat SHALL disable the general-purpose subagent through the upstream profile switch, and SHALL NOT rely on a parent-only filter that a compiled child does not inherit. The product MUST NOT embed the Deep Agents CLI or a hosted agent runtime.

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
- **THEN** one Deep Agents summarizer applies its native model-aware compaction defaults against the full observed model capacity with the framework policy applied once
- **AND** no custom early threshold or second summarizer shrinks that budget again.

### Requirement: WF-001 - Keep configuration links out of execution sequencing

Configuration connections SHALL supply model profile, tools, skills, memory, environment, access, and execution policy to the owning agent or step through explicit inheritance and overrides. Workflow connections SHALL define next steps and typed data or artifact handovers. Only workflow connections SHALL compile into workflow sequencing.

#### Scenario: Mixed definition compile

- WHEN a definition contains configuration links and workflow links for multiple owners
- THEN configuration links MUST affect only the intended owner setup
- AND they MUST NOT become executable steps or flatten every agent into one global setup.

### Requirement: WF-002 - Make delegation and cycle ownership explicit

Workflows SHALL invoke Deep Agents as named subgraphs with declared inputs and outputs. Subagents SHALL remain child runs within their owning step and MUST receive the intended model, tools, context policy, and access restrictions without escalation. Exactly one owner, either the outer LangGraph workflow or its agent step, SHALL control each review cycle. Planning through upstream middleware is allowed; general delegation and declared workflow cycles MUST remain explicit implementation capabilities, not assumed.

#### Scenario: Review loop ownership

- WHEN an outer review loop contains a delegating step
- THEN the run hierarchy MUST show which owner decides to repeat
- AND the same cycle MUST NOT be duplicated by both workflow and harness logic.

### Requirement: AGT-002 - Capture the actual model request

The product SHALL instrument the final model-adapter boundary after context middleware, including official memory, skills, retrieval, summaries, and offloaded content when applied. Captures SHALL link actual instructions, selected knowledge versions, available tools, usage, provenance, redaction, and capture gaps to each call. Captures MUST expose request visibility only and MUST NOT claim access to hidden model reasoning.

Chat and agent preview SHALL share a What the agent sees inspector. It SHALL distinguish the next-request candidate from each actual model request, identify source origin, loading mode, inclusion reason, estimated cost and immutable versions, and permit lazy expansion of permitted verbatim text and tool definitions. Redaction, capture gaps, model-native formatting and estimates SHALL be explicit. Opening inspection MUST NOT execute a model or tool.

#### Scenario: Capture after context middleware

- WHEN a request is captured after compaction with memory or skills selected
- THEN the capture MUST match what the adapter sends, after configured redaction
- AND unread skill bodies MUST remain off the wire.

### Requirement: AGT-003 - Leave task budgets unset by default

The product SHALL NOT impose arbitrary task-level time, token, model/tool-call, reasoning-effort, or revision ceilings by default. Optional budgets SHALL be user-selected. Framework and middleware limits SHALL be explicitly configured and reported. Checkpointed continuation SHALL be supported when user budgets permit. A limit, cancellation request, or stalled-progress warning MUST NOT be reported as successful completion.

#### Scenario: Budget and stop reason

- WHEN a run continues beyond a framework boundary, is cancelled, completes, or hits a selected budget
- THEN the run MUST record the actual stop reason
- AND `cancel_requested` MUST remain live until the worker records confirmed `cancelled`.

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

### Requirement: AGT-006 - Keep completion evidence distinct from judgement

Tasks with definitions of done SHALL preserve executable checks, expected artifacts, and review criteria separately. Test outcomes SHALL remain distinct from model assessments. Rubric middleware MAY extend review, but MUST NOT be required for basic completion checking.

#### Scenario: Evidence report

- WHEN a task result is inspected
- THEN executable success or failure, expected artifacts, and model review MUST be reported separately
- AND removal of rubric integration MUST NOT remove basic acceptance checks.

### Requirement: AGT-007 - Preserve Chat continuity and restart truth

A session SHALL permanently belong to one project or the non-project area. A different area requires a fresh session/thread; branches retain their source area. Removed projects retain historical session identity instead of converting sessions to non-project. Model/profile selection and authorized artifact reuse do not move sessions.

Continuing SHALL use the same saved thread with a new application run for only the new user input; fresh starts create new context. One turn per session SHALL execute at a time. Persist model/profile/tool/setup selections and snapshot each turn's resolved setup, preserving omitted versus empty tools. Edits affect future work, not live/paused settings or history. Revalidate current access at dispatch/resume. Display-only history edits MUST NOT reset context or project files. Restart SHALL reconcile persisted linkage and terminal state; missing linkage is an explicit gap, not a silently substituted thread.

#### Scenario: Restart then continue

- **WHEN** the backend restarts with a saved conversation and run linkage
- **THEN** continuation uses that conversation/thread and recorded configuration; missing linkage is reported rather than silently starting fresh.

#### Scenario: Different session area

- **WHEN** a user changes project area or branches an existing conversation
- **THEN** changing area creates fresh context, while a branch retains the original project/non-project identity.

#### Scenario: Continue after an ordinary tool failure
- **WHEN** a terminal turn contains complete tool calls without final protocol results
- **THEN** safe native history normalization SHALL permit the next user turn without replaying previous effects
- **AND** successful siblings remain successful, uncertain effects require evidence inspection, and live approvals use their original resume path.

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

### Requirement: AGT-009 - Enforce tools-off without disabling context housekeeping

Omitted tool selection SHALL inherit and an explicitly empty selection SHALL mean no tools. Tools-off SHALL remove filesystem, shell, planning, retrieval, delegation and synthetic formatting definitions and block unexpected/unrecognized/restored handlers at every sync/async execution hook. Projects, knowledge or connections MUST NOT silently re-enable them. Ordinary answer completion SHALL require no tool. Checkpoints and internal context housekeeping remain available. Selected official planning SHALL expose its observed task states, not invented progress or proof of task correctness. Those states are the arguments of the latest successful `write_todos` call. The desktop checklist presents them. The product MUST NOT keep a second todo list.

#### Scenario: Unexpected restored tool call

- **WHEN** a call appears while tools are off, including on checkpoint resume
- **THEN** the handler cannot execute; normal text and internal context housekeeping remain available.

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

### Requirement: AGT-011 - Resume typed user input separately from permission

Supported ask-user operations SHALL present typed text, choice or authorized file/folder questions, validate answers and resume the exact saved run/thread/interrupt through the framework's typed `respond` decision. A pending interruption with questions and protected tools SHALL use one ordered decision batch; every answer and approval MUST match its saved action before the single resume. Model-facing ask-user is a selected tool; an ordinary conversational question does not require one. A selected folder grants only the represented access. Input is not permission approval or credential collection. Cancel/restart SHALL reconcile pending questions rather than leave an unresolvable wait.

#### Scenario: Typed answer

- **WHEN** a user supplies an invalid, stale or valid answer to a saved question
- **THEN** invalid/stale answers are rejected; a valid answer resumes only its intended interruption without broadening access.

#### Scenario: Mixed questions and approvals

- **WHEN** one saved interruption contains typed questions and protected tool calls
- **THEN** the validated responses and approval decisions resume in framework order exactly once, and a stale or incomplete batch executes no action.

### Requirement: AGT-012 - Distinguish branches, answer regeneration and effectful retry

Edit-and-retry and Retry task SHALL preserve original history and create an explicit branch/attempt with source checkpoint and saved head. Reopen/follow-ups continue that head; writes sharing a thread SHALL be serialized. Project-state branches SHALL obey the existing consistent snapshot contract and retain session area. Unsupported checkpoint granularity SHALL be explicit.

Regenerate answer SHALL use retained task results/supported saved state to produce an alternative answer without repeating tools, file edits or remote submissions or duplicating the user input. Where unsupported, it SHALL be unavailable rather than silently retry the task. Effectful Retry task SHALL disclose possible repeated actions/interruptions, recheck permissions and reconcile external operations. Neither branching nor retry promises to undo files, committed knowledge or remote actions. Model requests use the shared adapter/admission path, never transcript-only reconstruction.

#### Scenario: Regenerate answer

- **WHEN** another answer is requested after a file or external task
- **THEN** retained results are reused without task effects, or answer-only regeneration is explicitly unavailable.

#### Scenario: Branch and retry

- **WHEN** a prompt is edited or the task is deliberately retried
- **THEN** original results survive, the source/head and possible repeat effects are explicit, and subsequent turns continue the selected branch.

### Requirement: AGT-013 - Reconcile cancellation and crash boundaries honestly

Cancellation SHALL prevent further model/tool dispatch, including rejection/resume loops, pause follow-ups and clean only owned request resources. Partial output and completed changes remain inspectable. Application stop and host/remote termination SHALL remain separate; shared inference processes are not killed to cancel one request. Restart SHALL verify genuine pending framework interrupts, reconcile decision acceptance/checkpoint advancement/external dispatch, and resolve orphaned live runs. Historical checkpoints alone do not prove resumability; uncertain effects MUST NOT be blindly replayed. Checkpointing is neither exactly-once execution nor rollback.

#### Scenario: Crash around an effect

- **WHEN** the backend stops between external dispatch and acknowledgement
- **THEN** recovery keeps the outcome unknown or uses authoritative reconciliation, never silent replay or fabricated success.

#### Scenario: Cancel turn

- **WHEN** a cancellation arrives during streaming, tool work or an interrupt
- **THEN** new dispatch stops, the queue pauses and owned cancellation completes only when confirmed, preserving partial and uncertain outcomes.

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

### Requirement: WF-012 - Present a canvas that matches the running workflow

Workflows SHALL be one destination. The screen SHALL show a step palette, a canvas, and an inspector for the selected step. The palette SHALL offer these steps, using ordinary names: sequence, branch, parallel and join, repeat, run an agent, run another workflow, ask a person, typed input, and a registered direct action. A step does nothing until it is placed and the person starts the workflow. The inspector edits that step's setup in the same controls used elsewhere, including the named agent or workflow it calls. A grader is a workflow or agent step the person placed, not a hidden reviewer.

Invalid steps SHALL show the reason on the step before a run starts. Run and a history of earlier runs sit above the canvas. During a run, the active step is marked, and waiting for a person uses the same approval or question card as Chat. Stopping names the work that will stop. An imported graph MUST NOT run arbitrary code. Automatic schedules are not part of this screen. A later schedule would be another step, not a ban on adding one.

The canvas SHALL be the loaded React Flow editor. It MUST NOT be a second workflow engine. The main path MUST NOT require reading raw graph JSON.

#### Scenario: Place a grader and run it

- **WHEN** a person places an agent step and a second workflow step labelled as grading, then starts the workflow
- **THEN** those steps run in the order shown
- **AND** the grader does not run unless it was placed.

#### Scenario: Invalid step is visible

- **WHEN** a branch has no outgoing path
- **THEN** the step shows that reason and the workflow does not pretend to start
- **AND** the canvas remains editable.

#### Scenario: Imported code is refused

- **WHEN** an imported graph contains an arbitrary code step
- **THEN** that step is rejected
- **AND** no code from the graph is executed.

### Requirement: AGT-020 - Enforce explicit Plan mode

Work SHALL be the default mode. Explicit Plan mode SHALL present only authorized non-mutating project/context reading, questions, checklist and discovery capabilities, and selected trusted built-in public-web search/page reading. It SHALL reject shell execution, file mutation/deletion, durable memory changes, browser/desktop interaction and effectful or unclassified external operations under every approval level and invocation path. External read-only annotations or names SHALL NOT establish Plan eligibility. Internal checkpoints/context housekeeping SHALL remain available. The mode SHALL be frozen with queued turns and enforced for restored calls and helpers. Full access MUST NOT override it; returning to Work SHALL require explicit user selection and a new submission.

#### Scenario: Plan with Full access
- **WHEN** a Plan-mode run attempts an effectful tool call
- **THEN** the call is rejected before execution regardless of Full access or saved grants.

#### Scenario: Trusted web tools with arbitrary MCP selection
- **WHEN** Plan includes selected built-in public-web tools and an unrelated MCP tool claiming read-only behavior
- **THEN** only the trusted search/page reader can be disclosed and dispatched.

### Requirement: AGT-021 - Keep delegated work within the conversation authority

Only explicitly selected frozen named agent versions SHALL be available as helpers. Each helper SHALL have isolated context, intersected parent authority, observable named activity and correctly owned approvals, cancellation and durable child identity. No recursive or general-purpose delegation SHALL be added by this selection. Calls sharing a managed model SHALL be serialized within a parent run initially; separate conversations with no overlapping project reservation MAY progress concurrently on the same or distinct loaded models within actual server capacity. A root task and its helpers SHALL share one project-family reservation. An alternate-model helper MAY hand off a single loaded-model slot after the parent's current model call completes, and the parent SHALL reload its exact model before continuing. The handoff MUST NOT widen authority, interrupt an in-flight model call or report a stopped parent as ready. Explicit tool-call budgets SHALL be enforced atomically across root and child calls, while unset budgets remain unset.

#### Scenario: Frozen helper and shared budget
- **WHEN** saved helper settings change after queueing and several helper calls compete for the last allowed tool call
- **THEN** the queued version and intersected authority are used and the explicit budget is not exceeded.

#### Scenario: Alternate model with one slot
- **WHEN** a parent delegates to a helper using a different installed model while the loaded-model limit is one
- **THEN** helper and parent calls run in sequence with visible loading or waiting and each uses its selected configuration.

#### Scenario: Replayed helper discovery in a later turn
- **WHEN** the public stream replays helpers from earlier turns while a new parent turn is active
- **THEN** each helper SHALL retain its owning parent-run and tool-call identity, even when call IDs repeat
- **AND** replay arrival timestamps MUST NOT establish ownership; the current parent's recorded task calls and child references SHALL determine membership
- **AND** child tool events from helper namespaces SHALL appear only in the scoped helper transcript, while the parent feed retains its compact delegation and parent-owned tools.

#### Scenario: Stop child work
- **WHEN** a conversation is stopped while a helper is generating or awaiting approval
- **THEN** new dispatch stops, owned cancellation is confirmed before terminal cancellation, and partial/uncertain outcomes remain truthful.

### Requirement: AGT-022 - Review only when requested and report genuine judgement

Review SHALL be off by default. Explicit Review before finishing SHALL show criteria and a limit of at most two revisions. Its grader SHALL be read-only and use the conversation model; one upstream review owner controls revisions. Executable checks, expected artifacts and model judgement SHALL remain distinct. Unresolved findings after the limit SHALL remain visible without autonomous continuation. The final answer alone MUST NOT be labelled an independent model review.

#### Scenario: Review disabled and bounded
- **WHEN** review is disabled
- **THEN** no reviewer call runs
- **AND** when explicitly enabled, genuine review results are retained and stop visibly after the chosen revision allowance without reviewer side effects.

### Requirement: AGT-023 - Read visual evidence through the existing agent loop

The shared Chat harness SHALL use native `read_file` for authorized project images and retained captures, including in a project-free conversation that has capture access. A browser navigation or snapshot SHALL return the page address and the headings and links to cite, including when the worker stored the snapshot in a file. A consent or block page SHALL be named and SHALL NOT be presented as the requested result. A screenshot result SHALL include that page text. The retained image SHALL be sent to the model only after the tool-image check for that loaded setup has passed; an untested vision setup runs that check once. A failed or text-only setup SHALL say the model cannot read the image and SHALL still return the page text. A supported image read SHALL reach the selected vision deployment as image content paired with its tool result; text-only or unverified visual support SHALL produce an actionable capability result rather than a fabricated visual description. Capture and browser/window tools SHALL remain subject to the frozen run setup, Work mode, helper authority intersection, tool budgets and cancellation rules.

#### Scenario: Visual capture in project-free Chat
- **WHEN** a browser screenshot is retained during a project-free conversation and its agent reads the capture path
- **THEN** the image is delivered to a verified vision model without granting project file or shell access.

#### Scenario: Helper cannot widen visual access
- **WHEN** a named helper attempts a browser or window tool outside its parent conversation's selected access
- **THEN** dispatch refuses it before the worker acts.

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

### Requirement: AGT-025 - Retain correctly owned helper observations

Each named helper call SHALL have a durable parent call identity, frozen helper identity and request, and a child observation scope that cannot be confused with a parallel helper. Its waiting, working, approval, completed, failed, and cancelled states and public messages, tool calls, results, and errors SHALL remain inspectable during execution and after reconnect or reopen. Observation SHALL NOT execute a child twice or expand its permissions. An early failure before child admission SHALL still settle the visible parent call. Historical events that cannot be attributed to one child SHALL NOT be guessed into a transcript.

#### Scenario: Parallel helpers have separate output

- **WHEN** a parent starts two named helper calls that emit overlapping events
- **THEN** each event is visible only under its owning helper, and both remain distinguishable after reopening.

#### Scenario: Admission failure settles delegation

- **WHEN** a helper request fails before its child model is ready
- **THEN** the parent delegation shows the failure rather than remaining indefinitely queued.

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

### Requirement: AGT-027 - Preserve retained visual context across tool continuations

Verified retained tool images SHALL be reconstructed at deterministic positions associated with their canonical tool results while those results remain in the active conversation context. An unrelated later tool SHALL NOT silently remove the previous image from the model-visible history. Capture references SHALL remain durable; raw image bytes SHALL remain bounded and excluded from checkpoints. Native compaction SHALL count active visual context and may remove or summarize it at an explicit context boundary. Failed capability checks and unavailable captures SHALL retain truthful text fallback.

#### Scenario: Screenshot followed by another tool
- **WHEN** a verified screenshot is followed by an assistant call and an unrelated tool result
- **THEN** the prior image remains at its original position in the next model request, preserving the unchanged prefix.

#### Scenario: Compaction removes older capture context
- **WHEN** native context compaction removes the older screenshot tool results
- **THEN** their images are no longer reconstructed, and the remaining visual context is counted under the same request budget.

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

### Requirement: AGT-032 - Preserve omitted capture policy settings

Updates to context-capture policy SHALL merge only fields explicitly provided into the current saved settings under the existing service concurrency boundary. Omitted retention or redaction settings SHALL remain unchanged; an explicitly provided null SHALL retain its supported clearing semantics. Independent Knowledge catalogue, configuration and proposal failures SHALL not make otherwise available editing unusable.

#### Scenario: Change redaction alone
- **WHEN** a person updates capture redaction without specifying retention
- **THEN** the saved retention policy remains unchanged.

#### Scenario: Change or clear retention
- **WHEN** a person updates retention alone or explicitly clears a nullable retention value
- **THEN** redaction remains unchanged and the provided retention change is applied.

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

### Requirement: AGT-034 - Preserve executable tool contracts and complete discovery

Cold input inspection and actual model requests SHALL preserve tool-schema semantics, including property names, nested alternatives, references and literal defaults/examples. Model-facing arguments SHALL state enforced types, bounds, units and mutually exclusive modes. Bounded tool discovery SHALL make every accepted selected match reachable through query/selection-bound continuation, with human-readable aliases, grouping and exact lookup. Discovery SHALL retain new-turn reset and resume behavior and MUST NOT enable excluded tools or trust external annotations as authority. Plan SHALL permit only selected built-in public-web search/page-reading capabilities through trusted connection identity. When tools are not off, admission SHALL include the trusted search and page-reading operations of an already selected built-in public-web connection without requiring each remote name in the saved tool list and without adding any other connection operation. An explicit empty tool selection SHALL add none.

#### Scenario: Title is an argument or literal data
- **WHEN** a selected tool includes required or nested title fields and title-bearing default data
- **THEN** inspection and compiled projection retain those fields and runtime validation accepts the same conforming arguments.

#### Scenario: Sixth selected match and changed selection
- **WHEN** a search has more matches than one result batch
- **THEN** continuation can reach the remainder without repeating the first batch
- **AND** a changed selection or query rejects an obsolete continuation.

#### Scenario: Read-only public research
- **WHEN** Plan selects the tested built-in public-web connection
- **THEN** its search/page tools remain usable while arbitrary external tools and browser mutations remain unavailable.

#### Scenario: Selected connection without naming each remote tool
- **WHEN** a saved selection names the tested built-in public-web connection and does not turn tools off
- **THEN** only that connection's trusted search and page-reading operations are added
- **AND** an explicit empty selection adds no connection operation.

### Requirement: AGT-035 - Offer explicit conditional runtime workflows

The product SHALL offer an opt-in versioned library of project-change, failure-diagnosis, Windows-execution, delivery-verification, browser-validation, desktop-validation, evidence-research, delegate-review and memory-curation skills. Installation, selection, metadata discovery and body/resource reading SHALL remain distinct. Setup templates SHALL use real saved selections and disclose Chat-owned access/mode requirements without granting them. No template or skill SHALL silently enable capabilities, save durable memory, grant project/window/shell access or import repository development skills into ordinary Chat. The evidence-researcher template SHALL be usable for attached documents and retained results without a bound project. Project discovery in that template SHALL remain available only when a project is bound and SHALL NOT be required for a projectless run. The definition-loading preference SHALL NOT decide whether unpinned project reads can exist. A projectless run SHALL omit unpinned `glob` and `grep` under both Always include all and When needed. Unpinned `ls` and `read_file` SHALL NOT be project readers on that run: they are omitted unless a selected knowledge or capture route keeps them for its virtual paths, and that schema SHALL name those paths and SHALL NOT describe a project root. The saved tool list SHALL NOT be rewritten. Pinned project reads, skill-required project or shell tools, eager file mutations, and eager shell or preview SHALL still fail when no project is bound. New stock templates that consume retained evidence SHALL select the retained-result reader. Applying a template SHALL NOT rewrite an existing saved setup.

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

#### Scenario: Project-bound research keeps project reading
- **WHEN** the same template is admitted with a bound project
- **THEN** the project reading operations in the template remain available with the source readers.

#### Scenario: New template can read retained evidence
- **WHEN** a new stock template that consumes retained evidence is saved and compiled
- **THEN** its accepted selection includes the retained-result reader
- **AND** an existing saved setup is left unchanged.

### Requirement: AGT-036 - Approve project file changes without widening exact grants

The product SHALL offer a separately approved, inspectable and revocable project file-change grant bound to the concrete selected project and explicit operation set. It SHALL retain path exclusions and reject traversal, symbolic-link/junction escapes, managed knowledge routes and operations outside the granted set. Existing exact-argument session/persistent grants SHALL keep their original meaning. All dispatch and resume paths SHALL recheck current selection, project identity and grant revocation. File-change authority MUST NOT imply deletion, shell, browser, external connection, protected instruction or durable memory authority.

#### Scenario: Two different edits within approved project scope
- **WHEN** a person deliberately grants selected project file changes with exclusions
- **THEN** distinct eligible edits can proceed under Ask while excluded paths and other effect classes still require their own authorization.

#### Scenario: Revoke between approval and dispatch
- **WHEN** the grant is revoked or the selected project identity changes before an action dispatches
- **THEN** the stale grant does not authorize that action or a helper.
