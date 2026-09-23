# Backend Desktop

## Purpose

Specify how the one FastAPI backend coordinates APIs, records, jobs, approvals, events, and artifacts while the one Electron desktop presents them without becoming execution authority.

## Requirements

### Requirement: API-001 - Coordinate without replacing execution owners

The backend SHALL own APIs, jobs, resource scheduling, events, approvals, artifacts, optional budgets, and shared records while hosting Deep Agents and LangGraph integrations. Backend coordination MUST NOT become a second agent loop or workflow engine.

#### Scenario: Desktop task trace

- WHEN a desktop task is traced through backend, harness or graph, and worker
- THEN job tracking MUST coordinate execution
- AND it MUST NOT duplicate the harness reasoning/tool loop or LangGraph sequence.

### Requirement: API-002 - Edit in the desktop, execute in the backend

Electron/React SHALL present controls, previews, context, evidence, memory editing, branches, and tool panels. React Flow SHALL edit workflow definitions. Backend validation and LangGraph SHALL execute workflows. The visual graph MUST NOT be executable authority by itself.

#### Scenario: Invalid definition outside editor

- WHEN an invalid definition is submitted outside the visual editor
- THEN backend validation MUST reject it
- AND successful screen interactions MUST correspond to real backend actions or be explicitly labelled as mock.

### Requirement: API-003 - Separate type validity from permission and capability

Pydantic and JSON Schema SHALL validate data and configuration shapes. Application rules SHALL enforce capabilities, access, connector compatibility, and privileged-route trust. A schema-valid object MUST NOT authorize execution or prove operational support.

#### Scenario: Well-typed unauthorized request

- WHEN a well-typed but unauthorized or incompatible request is sent
- THEN it MUST be rejected at the relevant authorization, capability, or execution boundary.

### Requirement: API-004 - Expose real state and evidence

The backend and desktop SHALL present run hierarchy, streamed progress, approvals, artifacts, checks, applied configuration, and relevant context or knowledge information from records and events. Active, queued, resource-constrained, failing, `cancel_requested`, and `cancelled` states SHALL be distinguishable. Model confidence, preview text, service readiness, or disconnected clients MUST NOT be treated as completed work.

#### Scenario: Cancellation visibility

- WHEN a live run is cancelled
- THEN visible state MUST show `cancel_requested` until the worker records confirmed `cancelled`
- AND a later persisted outcome MUST match execution records.

### Requirement: API-005 - Keep provisioning distinct from job execution

The environment manager SHALL provision workers and access, map project storage, and tear down environments. Adapters SHALL own jobs inside environments. Docker Compose SHALL manage container services. Service readiness MUST NOT be reported as task completion.

#### Scenario: Provision then run

- WHEN a worker is provisioned and then a tracked job executes
- THEN provisioning, job progress, cancellation, and teardown MUST be attributed to the appropriate owners.

### Requirement: API-006 - Stream run and conversation events over SSE

Chat and current live-run consumers SHALL share a versioned upstream-compatible interaction boundary over authenticated loopback HTTP and SSE. Backend registration SHALL bind application conversation, runtime thread, application run and framework execution identities. Submission, hydration, subscription, resume, cancellation and reconnect MUST operate through that binding. Missing tokens MUST return 401 and wrong tokens MUST return 403. The boundary SHALL validate supported command fields and reject unsupported versions, commands, arbitrary state updates, checkpoint selection and workflow jumps. Only controlled public message/state/tool/interrupt projections and declared application extensions SHALL cross the boundary; raw private graph state MUST NOT be exposed. Opening or reconnecting a conversation paints the saved snapshot at its interaction cursor and continues the event subscription after that cursor. Historical token events are not played back onto the screen.

#### Scenario: SSE reconnect

- WHEN a live thread is disconnected and reconnected
- THEN a consistent snapshot/replay boundary MUST restore its ordered projection without duplicate content or a new model invocation
- AND a replay gap MUST cause explicit controlled resynchronization rather than silently dropping output.

#### Scenario: Open a conversation without replaying tokens

- WHEN a client opens or reconnects to a conversation
- THEN it paints the saved snapshot at `interaction_cursor` and continues the subscription after that cursor
- AND historical token events MUST NOT be applied to the screen again
- AND an answer already in progress MUST be visible from that snapshot before newer tokens arrive.

#### Scenario: Run-local sequences across turns

- WHEN consecutive runs reuse a conversation thread
- THEN their native run-local event sequences MUST NOT be mistaken for a thread-global cursor
- AND hydration and replay MUST retain stable message, tool, run and namespace identities.

#### Scenario: Reject while active

- WHEN another submission targets a live or interrupted run
- THEN the backend and frontend MUST reject it without aborting, replacing or implicitly queuing the active task
- AND a client queue MUST NOT be presented as a durable application queue.

#### Scenario: Disconnect and cancel are different

- WHEN navigation or unmount disconnects an observer
- THEN execution MUST continue under backend ownership
- AND explicit cancellation MUST remain cancel_requested until confirmed by the worker, independently of SDK loading state.
- AND a finished run MUST NOT have Cancel enabled.

### Requirement: API-007 - Launch locally and keep desktop state honest

The Windows launcher SHALL reuse a healthy product backend or start it hidden, then open the built Electron desktop. Chat SHALL keep the composer visible while transcript and history scroll independently. Recent conversations SHALL appear first. New Chat SHOULD prefer a running chat deployment and MUST NOT apply unrelated saved profiles. Stopped deployments MUST NOT gain healthy labels from stale probes.

#### Scenario: Desktop launch and model state

- WHEN the launcher opens the application and a stopped deployment has an old probe
- THEN the desktop MUST present current backend state
- AND catalogue loading MUST be explicit rather than shown as an empty catalogue.

### Requirement: API-008 - Preserve terminal Chat hydration

The desktop SHALL reconcile upstream incremental projections and the persisted readable conversation by stable identity. Completed replies SHALL remain visible after final hydration. Optimistic user input, completed messages and tool results MUST NOT duplicate or disappear. Thread switches SHALL dispose the old observation and MUST NOT apply late frames or hydration to the new selection. Readable archive history MUST NOT be shortened to match compacted execution context.

The selected conversation and transport binding SHALL remain coherent during registration. Every selection-sensitive asynchronous result SHALL check selection generation and identity, including hydration, cancellation, creation, registration, command acknowledgement and errors. Pending input/configuration SHALL belong to its originating conversation/thread and draft identity. Acknowledgement SHALL clear only the submitted draft. Navigation SHALL neither retarget nor repeat an accepted command and SHALL NOT cancel backend execution.

#### Scenario: Final reply remains visible

- WHEN a real desktop Chat turn completes
- THEN its reply MUST have appeared incrementally before completion and MUST remain visible without reopening
- AND reopening MUST restore the saved transcript, selected/applied setup and project binding.

#### Scenario: Late old-thread completion

- WHEN the user selects a fresh conversation while the prior run continues
- THEN old-thread frames and completed hydration MUST NOT contaminate the new conversation
- AND the prior run MUST remain observable when revisited.

#### Scenario: Deferred hydration and cancellation across navigation

- WHEN A's terminal hydration or cancellation resolves after selecting B or New, including navigating away and back to A
- THEN the old result MUST NOT change current selection, draft, error state or transport
- AND revisiting A MUST show its own durable outcome.

#### Scenario: Atomic registration and submission ownership

- WHEN B's conversation fetch completes while registration is pending and A emits another frame
- THEN no rendered binding MUST combine B with A's transport or run
- AND deferred create/register/submit completion MUST NOT send input or configuration to a newer selection, duplicate an accepted run or clear newer draft text.

### Requirement: API-009 - Keep desktop shared secret out of renderer

The backend SHALL create the same-machine shared secret under product state on first use. Electron main SHALL inject the token for loopback backend requests. The sandboxed renderer SHALL use context isolation, no Node integration, and MUST NOT hold the shared secret. The backend SHALL bind loopback only.

Token injection SHALL require the exact backend destination and a verified trusted application document/frame belonging to its owning WebContents. WebContents identity alone or an opaque null origin SHALL NOT establish trust. Missing, destroyed, navigated or untrusted frames SHALL fail closed. Electron main SHALL deny untrusted windows and document navigation, including redirects, and resolve and validate deliberate external links before opening HTTP(S) targets in the system browser. File and custom schemes SHALL NOT gain external execution authority; relative, fragment and protocol-relative links SHALL be handled explicitly without prefix-based trust decisions.

#### Scenario: Renderer request

- WHEN the renderer initiates a privileged backend request
- THEN Electron main MUST add the shared-secret header
- AND the renderer MUST NOT expose or store that secret.

#### Scenario: External Markdown navigation

- WHEN a user activates an HTTP(S), relative or protocol-relative Markdown link
- THEN main-process URL validation MUST control any system-browser opening
- AND no untrusted in-app window or redirected document MUST inherit desktop privileges.

#### Scenario: Same-session untrusted requests

- WHEN an untrusted window/frame or a replacement document in a formerly trusted window requests the backend
- THEN the receiver MUST NOT receive the application-granted token, regardless of CORS response visibility
- AND genuine development and packaged application command, state/history, subscription and cancellation requests MUST retain authenticated access.

### Requirement: API-010 - Present durable Chat state without duplicating or inventing work

Every displayed snapshot SHALL pair message text, run state and resume cursor from the same observation. Completion and token-log compaction MUST NOT remove a message while hydration or reconnect prepares it. A native finished message SHALL remain readable until its authoritative graph message arrives. The desktop MUST advance its resume cursor only after a complete event frame has arrived; disconnecting inside a frame MUST replay that frame.

Existing Chat SHALL support new, rename, archive, retained-title/message search and reopen. Archive changes visibility, not memory/context. Incremental answers, separate returned reasoning, tool content and partial failures SHALL reconcile by run/thread/message/call identity into one final saved result. Internal summaries MUST NOT appear as answers. After the verified `migrate-local-agent-interaction` prerequisite, consume the supported `@langchain/react` interaction boundary for message/tool/state projections and scoped subscriptions; do not extend the superseded custom `snapshot` / `run_event` / `stream_end` contract. Application-owned durable history, run identity, reconnect/hydration and authorization remain authoritative; reconcile SDK updates into one saved result and avoid rewriting the entire growing run for every token.

Expose effective setup, actual selected tools/results, observed planning, context capacity/usage/compaction, approvals and loading/empty/error/reconnect states. Provide safe Markdown/code/table rendering, copy and access-checked open/save actions, keyboard controls and scrolling that respects the user's position. Generated HTML/scripts MUST NOT execute in the trusted renderer; opening/saving is not execution authority.

The `repair-local-interaction-boundaries` prerequisite SHALL remain satisfied: selection and transport binding stay atomic, stale callbacks are generation-guarded, command configuration and draft ownership are isolated, and accepted work is never retargeted or repeated by navigation. External links SHALL retain main-owned HTTP(S) validation and requesting-document/frame authorization; neither untrusted windows nor replacement documents gain the backend token.

#### Scenario: Reconnect and terminal result

- **WHEN** a streamed turn reconnects or completes while the user switches conversations
- **THEN** snapshots/events and final hydration produce one correctly attributed saved answer with partial/tool content intact.

#### Scenario: History and rendering

- **WHEN** history is archived or generated code/HTML is displayed
- **THEN** archive does not erase execution context and content cannot execute with desktop privileges.

### Requirement: API-011 - Keep background work visible and quit deliberately

Closing the main window or event stream SHALL NOT cancel or resubmit a run. Ongoing work SHALL have visible tray/background state and a route back. Explicit Quit with active work SHALL offer keep running or stop owned work and exit. Shutdown SHALL reconcile owned runs/clients/savers/processes and retain unresolved external outcomes; externally connected engines MUST NOT be terminated as owned processes. Reopening reconnects to existing work.

#### Scenario: Close reopen and quit

- **WHEN** a user closes/reopens the desktop or explicitly quits during work
- **THEN** close/reopen preserves the same run; Quit makes the keep-running versus stop-owned-work decision explicit and reconciles its outcome.

### Requirement: API-016 - Present one conversation-led desktop shell

The desktop SHALL provide one collapsible sidebar on every page. Destinations SHALL stay fully visible without their own scrollbar. Below them, one list SHALL show collapsible named project folders containing only their permanently scoped conversations, then chats with no project labelled as having no project. The no-project group SHALL remain in that list when it is empty. A project row SHALL start a new chat in that project, and a separate control SHALL create a project. Right-clicking a project SHALL offer editing it, archiving its chats, and removing it from the sidebar without deleting its folder. New chat, cross-area retained-history search, rename, archive and reopen SHALL remain available from that sidebar. The conversation header SHALL show its project or non-project identity; choosing a different area SHALL open or create another conversation rather than move or detach the current one. Removed-project history SHALL retain its identity.

Adding a project SHALL ask for a name and one existing folder. It SHALL NOT choose memory or grant edit permission beyond the selected folder. Creating a project SHALL NOT start or move a chat.

Compact destinations SHALL stay in that same sidebar, including Settings, as their owning packets deliver functionality. Existing Agent run and its history SHALL remain accessible through the transition to Workflows. The conversation SHALL remain central with a visible composer. Files, previews, and changes open in the dock in API-023, API-024, and API-025. The conversation column stays visible while the dock is open, including when the dock is widened. Full and half-screen windows SHALL be normal supported layouts. On a narrow conversation column the dock stays a side column or closes before compromising ordinary conversation or composer use. A panel MUST NOT be painted over the transcript or the composer. Primary journeys MUST NOT require interpreting raw JSON, internal identifiers or backend terminology; technical details SHALL remain available on expansion.

Light and dark themes SHALL follow Windows by default with a user override. Settings appearance SHALL expose one shared control for each visual role, including the settings surface itself. Roles cover the colour palette, the type scale, corner styles, inset, the space between items, line thickness, and layout sizes such as page width, reading width, message width, dialog width, side columns, and control height. Near-identical values SHALL share a control. Inset, the padding inside a surface, stays separate from the space between items. Those scales keep only the steps a person can tell apart: tight, row, card, section, and page insets, and tight, item, block, and section gaps. Reading text stays separate from interface text. The file editor text size and chat code size stay separate from both. Each numeric control SHALL offer a slider and a typeable value. The typeable value SHALL accept any valid measurement and SHALL NOT impose an upper bound chosen for an assumed screen size. Colour controls SHALL include transparency. Font weight, opacity, and colour-mix strength stay inside their valid ranges. Applying SHALL store overrides in appearance.json in the product data root. A draft SHALL be visible in the open window, including Settings, before it is applied. A separate preview window SHALL show a representative window of that draft, and the person SHALL be able to move and resize that window beside Settings. While a control is pointed at or changed, that preview SHALL mark the parts the control changes. Cancelling SHALL restore the last applied values. Resetting one row SHALL restore its shipped value. Media and container breakpoints, viewport-tied layout, and one-off positions stay fixed. Compact controls SHALL retain readable labels, accessible names, visible keyboard focus and usable click targets. Reduced motion SHALL be respected. Settings SHALL expose appearance, notifications, saved grants and manual backup/restore; connection management is added by Packet 04 using the same surface.

#### Scenario: Appearance draft is visible before it is saved

- **WHEN** a person changes a colour or a measurement in Settings and has not applied it
- **THEN** the open window, including Settings, shows that draft, and Apply stores the overrides in appearance.json on that computer

#### Scenario: Projects sit above chats with no project

- **WHEN** the sidebar is expanded
- **THEN** destinations stay fully visible, each named project is a folder containing only that project's chats, and chats with no project follow those folders in the same list even when none exist.

#### Scenario: Add a project without starting a chat

- **WHEN** a user adds a project with a name and one existing folder
- **THEN** the project appears in the sidebar, no chat is created or moved, and memory is not chosen in that dialog.

#### Scenario: Switch project without relocating a conversation

- **WHEN** a user selects another project from the shared sidebar and then reopens an earlier chat
- **THEN** each chat retains its original area, the header identifies that area and the composer/draft belongs to the selected chat.

#### Scenario: Compact window and keyboard use

- **WHEN** the application uses a half-screen window, Windows scaling or keyboard-only navigation
- **THEN** secondary panels can collapse or stack while navigation, readable replies, composer and labelled settings remain accessible without ordinary controls requiring horizontal scrolling.

#### Scenario: Dock does not cover the answer

- **WHEN** the dock is open and the conversation actions menu is open
- **THEN** the transcript and composer remain readable beside or above the dock
- **AND** neither the dock nor the menu is painted over the answer text.

### Requirement: API-017 - Expose compact effective model controls and measurements

Opening a conversation SHALL restore that conversation's effective Access choice, including an explicit Ask override. Changing to a setup whose access is unspecified SHALL use Ask unless a current explicit override applies; it MUST NOT inherit Full access from the previous setup or conversation. A user's explicit choice SHALL survive unrelated default changes. Access labels SHALL show Ask, Approve for me, or Full access in full and explain that running and already queued messages keep their selected policy. Descriptions and model instructions SHALL reflect saved permission grants and the actual selected mode, while explicit questions and disabled-tool boundaries remain enforced.

The conversation window SHALL visibly expose selectable model, supported reasoning effort or Thinking off, and the active setup, with compact attachment and permission controls beside the composer and focused popovers for details. The shield selects Ask, Approve for me, or Full access for later messages in that chat. It does not turn the agent's tool list on or off. Project, agent, and knowledge setup SHALL live on the Setup page of the conversation rail. The rail starts closed and MUST NOT take height from the transcript while it is closed. Existing profiles SHALL remain usable before Packet 04 delivers reusable agent setups. Changes SHALL affect future submissions without rewriting active turns or queued intended configuration. Unsupported/overridden/unverified reasoning controls SHALL be labelled truthfully; hiding returned thinking MUST NOT be represented as disabling model reasoning.

Compact status elements SHALL expose current context fill and generation speed in tok/s, with capacity, counting/measurement basis and relevant interval available on expansion. Observed measurements, labelled estimates and unavailable values SHALL remain distinguishable. Stream chunks MUST NOT be counted as tokens; absent usage MUST NOT appear as zero. Context changes/compaction and current versus completed-turn measurements SHALL remain attributable rather than silently showing stale values as current.

Context details SHALL open on pointer hover and keyboard focus, with touch access and Escape dismissal. Prefer model-reported request input/output counts over preflight estimates once available. Supported llama.cpp timing streams SHALL supply live generation speed with bounded updates and no shared-slot polling; measurements SHALL reset at each model-call boundary and retain their current/completed/interrupted status. Compact settings SHALL avoid redundant default-value cards while preserving actionable failures, meaningful choices and accessible explanations.

Sending with a stopped installed managed model SHALL load the selected setup through the existing model manager/admission path, show waiting/loading/readiness and submit once ready. Failure SHALL preserve the user's input and offer recovery. Conflicts SHALL be explained before disruptive action; active-work protections and connected-endpoint ownership MUST NOT be bypassed and models/settings MUST NOT be silently substituted.

#### Scenario: Unsupported reasoning and unavailable telemetry

- **WHEN** the selected model lacks a supported thinking-off control or supplies no usable token measurement
- **THEN** the control/measurement explicitly reflects that limitation rather than claiming thinking is off or showing an invented tok/s value.

#### Scenario: Start from Chat with a resource conflict or failure

- **WHEN** a submitted draft selects an installed stopped model and loading conflicts with existing work or fails
- **THEN** the draft remains recoverable, the conflict/failure and corrective action are visible, no protected work is silently disrupted and retry cannot duplicate accepted work.

#### Scenario: Setup stays off the transcript

- **WHEN** a person opens the conversation rail to Setup
- **THEN** setup sits in that rail and the transcript remains readable beside or above it.

### Requirement: API-018 - Keep answer streaming independent of detail visibility

Answer text SHALL always appear incrementally, including through a long reply. Painting the reply MUST stay with generation: earlier finished messages, and finished parts of the same reply, stay in place and remain readable. A compact reasoning button beside the model name SHALL default off and remember the user's preference across conversations/reopening. It uses an icon distinct from context and speed, and the accent colour when it is on. It is a pressed button, not a tick box. The composer Stop control is the only stop. Chat does not show a separate Activity row with its own cancel control. When enabled, available returned thinking, tool input, tool output and other raw detail SHALL be distinctly labelled apart from answers; absent streams MUST NOT be fabricated. When disabled, that expanded detail stays collapsed while answer text continues streaming. The planning checklist and the one-line activity rows in API-026 remain visible in both modes. Motion preferences SHALL be respected.

While a reply is running and the person is already at the bottom, the transcript SHALL follow the newest line immediately. Scrolling away stops following. Returning to the bottom follows again. Following sets the position directly. Smooth scrolling is reserved for an explicit jump, such as opening a chat or a notice, and reduced motion stays immediate. A text selection inside the transcript MUST be left in place. An open reasoning section follows the newest line the same way until the person scrolls inside that section, and the full reasoning text stays reachable by scrolling. Token growth MUST NOT be announced as a stream of accessibility updates. One status announces that a reply is being written, has stopped, or is waiting.

A speed or context measurement SHALL update its readout only. It MUST NOT rebuild the transcript, move the scroll position, delay the next tokens, or change execution.

Each output section SHALL independently expand/collapse through a heading or chevron, overriding the global presentation for that section without disrupting text selection or links. Approvals, typed questions and errors SHALL remain visible in both modes. Toggling presentation MUST NOT change execution, permission, saved content or the user's scroll position. Copy, Regenerate answer and Branch SHALL appear on each saved assistant answer and SHALL NOT appear while that answer is still streaming. Copy on an answer SHALL copy that answer's text. Chat code blocks, tool input, tool output and file differences SHALL each provide a copy icon. Unavailable Regenerate answer or Branch SHALL stay disabled with the truthful reason rather than retrying the task. Retry task, edit-the-task, export and delete SHALL remain on the Actions page of the conversation rail. That page MUST NOT cover the transcript. Retry task SHALL disclose possible repeated effects before it runs. Branch, Retry task and Regenerate answer SHALL remain visibly distinct and obey AGT-012.

#### Scenario: Hide details while an answer streams

- **WHEN** a user disables detailed streams during generation and expands one tool result
- **THEN** answer text continues, other raw tool input and output stay collapsed, the chosen result opens independently and execution/content identity remains unchanged.

#### Scenario: Interrupt during compact presentation

- **WHEN** an approval, typed question or error occurs with detailed streams hidden
- **THEN** the actionable card remains visible and cannot be mistaken for continuing generation or hidden by collapsing activity.

#### Scenario: Actions on a saved answer

- **WHEN** a saved assistant answer is shown
- **THEN** Copy, Regenerate answer and Branch are on that answer, and Retry task stays in the conversation menu until the user confirms the possible repeated effects.

#### Scenario: Copy a presented chat block

- **WHEN** a user copies a chat code block, tool input, tool output or file difference
- **THEN** that block's text is copied without changing the conversation.

#### Scenario: Planning stays visible while details are hidden

- **WHEN** detailed streams are off and the agent updates its todo list or edits a file
- **THEN** the checklist and the one-line activity row stay visible
- **AND** the raw tool arguments stay collapsed.

#### Scenario: Follow the newest line while a reply is written

- **WHEN** a long reply is streaming and the person is at the bottom of the transcript
- **THEN** the newest text stays in view as it arrives
- **AND** earlier finished messages stay where they were.

#### Scenario: Scrolling away keeps the person's place

- **WHEN** the person scrolls up during a reply, or selects text in the transcript
- **THEN** the view stays where they left it until they return to the bottom
- **AND** the selected text is not cleared by the next tokens.

#### Scenario: Speed updates leave the text alone

- **WHEN** generation speed or context usage updates during a long reply
- **THEN** the readout changes and the transcript text, scroll position, and next tokens are undisturbed.

#### Scenario: Open reasoning stays fully readable

- **WHEN** reasoning is open during a long trace and the person then scrolls up inside that section
- **THEN** the section was following the newest line until that scroll
- **AND** the earlier reasoning remains reachable.

### Requirement: API-019 - Present queued work and scoped attention clearly

During active work Enter queues the draft. The send control stays the send arrow, with a separate Stop control. A compact row inside the composer SHALL expose each queued message with edit, remove, and steer. Steer stops the live model or tool step, keeps the partial transcript and completed file changes, and sends that message on the same conversation thread. It does not start a new chat. The pinned Deep Agents library has no mid-stream inject, so steer is this stop-and-continue until an inject API exists. A queued message that is not steered still sends itself when the turn finishes successfully. AGT-010 SHALL govern persistence, dispatch and progression: only success advances automatically, failure/cancellation pauses, and approval/input waits do not advance. Header setting changes MUST NOT silently mutate queued items.

Inline approval cards SHALL show exact action/resource scope and the four AGT-008 choices, explaining broader grant scope before selection. Saved grants SHALL remain inspectable/revocable in Settings. Sidebar badges and a compact attention list SHALL identify conversations waiting for approval/input or needing failure recovery. The count is the same small circle on the bell in the expanded and collapsed navigation. A notice can be dismissed. Opening a notice selects its existing conversation and dismisses that notice. If that conversation is gone, the notice is dismissed and a new chat is not created. Deleting a conversation dismisses notices for runs that leave with it, and the bell count updates immediately. A dismissed notice does not return. The list finds the conversation that contains the run, including when that run is no longer the latest turn. Windows notifications SHALL default on for those events while the application is backgrounded, subject to OS/user settings; successful completion notifications SHALL default off. Notifications MUST NOT steal focus, auto-switch conversation or answer interruptions. User activation SHALL navigate to the corresponding current conversation/attention state without replaying work; in-app attention SHALL remain usable when OS notifications are unavailable.

#### Scenario: Queue with independent configuration

- **WHEN** a user queues a follow-up, changes the selected model and then the active turn fails
- **THEN** the queue pauses with its original intended model/setup visible and editable, and Stop/Queue remain distinct from approval actions.

#### Scenario: Background approval and notification navigation

- **WHEN** another conversation requests approval while the app is backgrounded
- **THEN** its badge/attention entry and allowed Windows notification identify it without moving focus, and opening it presents the current interruption rather than accepting a stale decision.

### Requirement: API-020 - Separate technical verification from human UX acceptance

Each affected packet SHALL demonstrate its end-to-end user journey in the built Windows application and record technical verification separately from Dave's UX acceptance in its existing design/PR. Reviews SHALL cover full and half-screen windows, actual Windows display scaling, keyboard navigation, long conversation/result content and at least one failure/recovery state. Screenshots alone MUST NOT count as interaction verification. Required technical/live checks SHALL remain required; UX acceptance SHALL remain pending until Dave accepts the built experience or explicitly defers review, with deferral recorded as deferred rather than accepted.

Packet 03 SHALL include an early Chat layout review after the basic arrangement is exercisable and before the remaining controls accumulate, including the existing Models-to-Chat journey. Packets 04, 05 and 07 SHALL include major everyday-workspace, Lab and Workflows reviews; 06 and 08 SHALL include focused activity/approval and media reviews. Lab and Workflows SHALL each require an approved detailed layout before substantial interface implementation. Specification approval MUST NOT be treated as visual acceptance of the built product.

#### Scenario: Technical checks pass before user review

- **WHEN** automated checks and agent-driven Windows interaction pass but Dave has not reviewed or explicitly deferred the experience
- **THEN** technical results are recorded as such while UX acceptance remains pending.

#### Scenario: Explicitly deferred review

- **WHEN** Dave explicitly defers a milestone's UX review
- **THEN** its existing design/PR records the deferral separately from technical evidence and does not claim UX acceptance or waive required live checks.

### Requirement: API-023 - Keep one dock beside the conversation

Chat SHALL use one right-hand rail. It starts closed. One header control opens and closes it, and that choice stays while the person moves between chats. Opening it adds a column and narrows the transcript. Closing it returns that width. A splitter SHALL resize the rail within bounds. Exactly one page is open at a time; switching pages replaces the rail and MUST NOT open a second card. The pages are Setup, Changes, Files, Library, and Actions. Choosing a file or a change in the transcript opens the rail on that item. That is the only automatic open. Widening the rail SHALL keep a readable conversation column. The rail stays beside the transcript and composer at every window width, including about half a screen. It MUST NOT move above the composer. The rail MUST NOT be painted over the transcript or the composer, and it MUST NOT hide the conversation in order to grow. Navigation and the rail keep bounded resize, collapse, and reopen without losing content or run state. Light and dark follow the application theme.

#### Scenario: Open, resize, and close

- **WHEN** a person opens the rail to Files, drags the splitter, switches to Changes, and then closes the rail
- **THEN** the transcript narrows and widens with the rail, only one page is showing, and closing restores the conversation width
- **AND** the answer text is never covered.

#### Scenario: Narrow window

- **WHEN** the conversation column is about half a screen wide and the rail is open
- **THEN** the rail remains a column on the right of the transcript and composer
- **AND** the transcript and composer remain usable.

### Requirement: API-024 - Review changes in the loaded diff editor

The Changes page SHALL list recorded project-file changes for the selected turn and open the selected change in the loaded Monaco diff editor. The editor shows the stored before text and after text, side by side when the dock is wide enough and inline when it is narrow. The editor is read-only. Its assets ship inside the desktop package. The application theme applies. When the text difference is unavailable, the page says why and does not invent a diff. Reverse remains the existing confirmed reverse of that one change. A pending change SHALL be shown when the before text and the proposed result text are both already known. Approval buttons stay on the transcript card. The page MUST NOT implement its own diff algorithm.

#### Scenario: Review an edit

- **WHEN** a turn has a recorded text edit and the person selects it
- **THEN** Monaco shows the stored before and after text
- **AND** reverse still requires the existing confirmation that the file matches the recorded result.

#### Scenario: Binary change

- **WHEN** a recorded change has no text difference
- **THEN** the page says the difference is unavailable
- **AND** it does not show an empty or invented diff.

### Requirement: API-025 - Browse project files in the loaded editor

The Files page SHALL show the bound project's files in a loaded virtualized tree, using the existing one-directory listing as each folder opens. A filter SHALL narrow names already loaded. Choosing a text file opens it read-only in the loaded Monaco editor. The read is a read-only project-file request with the same confinement as the listing: inside the project, no links, and no framework routes. The read MUST NOT call the model or the agent's read tool. Text follows the existing captured-text limit. Images use the existing image preview. Other files say they cannot be shown. Retained copies on this page stay labelled as retained copies and stay distinct from live project files. The page MUST NOT become a second catalogue of the project, and it MUST NOT implement its own tree widget. The new read is published through the existing shared contract. Opening a file does not require git.

#### Scenario: Open a project file

- **WHEN** a person expands a folder and opens a text file from the dock
- **THEN** the tree uses the existing listing and Monaco shows the file
- **AND** the model is not called.

#### Scenario: File outside the project

- **WHEN** a read asks for a path outside the project, through a link, or on a framework route
- **THEN** the read is refused
- **AND** no file content is shown.

#### Scenario: Retained copy

- **WHEN** a retained attachment and a live project file are both on the Files page
- **THEN** the retained copy is labelled as retained and the project file is labelled as the live file.

### Requirement: API-026 - Show planning and file activity as it happens

While an assistant turn runs, and when that turn is reopened, Chat SHALL show planning and tool activity from the projected tool calls. This is visible with detailed streams on or off.

`write_todos` SHALL appear as one checklist for that turn. Each item shows its content and its status: pending, in progress, or completed. The checklist is the arguments of the latest successful `write_todos` call. A later successful call replaces the list. A failed call leaves the previous list and shows the failure. The product MUST NOT keep a second todo list or read private graph state. Raw arguments remain available on expand. The checklist appears only once those arguments parse as the todo list.

Each other filesystem, search, shell, MCP, and memory tool SHALL appear as one line, one per call identity, in order, without a duplicate when live and retained records join:

- Reading or Read, plus the path. When the call includes an offset and limit, the line includes that line range.
- Creating or Created, Editing or Edited, Deleting or Deleted, Renaming or Renamed, using the recorded operation. A rename shows the source and destination.
- Listing or Listed, Finding or Found files matching, Searching or Searched for, Running or Ran, Calling or Called, Proposing or Proposed a memory.

An actively running unfinished call uses the present-tense verb. The finished call uses the past tense. A failure shows on that line. Retained incomplete arguments from a stopped or failed turn SHALL be labelled as partial input, never as ongoing work or a completed file. Starting a later turn MUST NOT reactivate that label. `+N -M` SHALL appear only from the observed before/after difference for that same call, counting added and removed content lines and excluding diff headers. Missing text omits the counts. The product MUST NOT scrape a number out of tool prose or invent a count. A shell line shows the command truncated to one line; its full output stays on expand. The underlying tool name stays available on expand.

While a call is unfinished and its body is open, that body follows the newest line until the person scrolls inside it. The open body shows the full text produced so far. Every line stays reachable by scrolling, and copy copies that full text. The product MUST NOT drop earlier text to keep the view small. Completed file content SHALL remain readable with its original line breaks; raw arguments remain available separately.

Choosing a file line opens the dock on that change, or on the file when no change record exists. The choice MUST NOT send a chat message or call the model. Approvals and typed questions keep their existing cards. The activity line MUST NOT offer a second set of approval buttons.

#### Scenario: Todo list updates in place

- **WHEN** the agent writes a todo list and later marks an item complete
- **THEN** one checklist shows the latest successful items and statuses
- **AND** detailed streams being off does not hide it.

#### Scenario: File line with counts

- **WHEN** an edit of `thistest.md` finishes and the observed difference is five added lines and four removed lines
- **THEN** the transcript shows a line equivalent to "Edited thistest.md +5 -4"
- **AND** choosing it opens that change in the dock.

#### Scenario: Read without a diff

- **WHEN** the agent reads `SKILL.md`
- **THEN** the transcript shows a line equivalent to "Read SKILL.md"
- **AND** no added or removed count is shown.

#### Scenario: Counts wait for the observation

- **WHEN** an edit has started and the before/after text is not available yet
- **THEN** the line shows that the file is being edited
- **AND** the counts appear only after the observed difference exists.

#### Scenario: Failed todo does not wipe the list

- **WHEN** a todo update fails after a successful list
- **THEN** the previous checklist remains and the failure is visible.

#### Scenario: A long write stays fully readable

- **WHEN** a file write is still streaming, the person has the row open, and they then scroll toward the start of that body
- **THEN** the newest lines were in view while the body was following
- **AND** scrolling reaches the earlier lines and copy copies the full text written so far.

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
