# Backend Desktop

## Purpose

Specify how the one FastAPI backend coordinates APIs, records, jobs, approvals, events, and artifacts while the one Electron desktop presents them without becoming execution authority.

The built desktop does not yet offer the planned Lab views or a visual workflow editor. Their delivery is tracked by [lab-workbench](../../changes/lab-workbench/tasks.md) and [consolidate-product-contract](../../changes/consolidate-product-contract/tasks.md). Initial catalogue failure recovery remains open in [startup-catalogue](../../changes/startup-catalogue/tasks.md).

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

Chat and current live-run consumers SHALL share a versioned upstream-compatible interaction boundary over authenticated loopback HTTP and SSE. Backend registration SHALL bind application conversation, runtime thread, application run and framework execution identities. Submission, hydration, subscription, resume, cancellation and reconnect MUST operate through that binding. Missing tokens MUST return 401 and wrong tokens MUST return 403. The boundary SHALL validate supported command fields and reject unsupported versions, commands, arbitrary state updates, checkpoint selection and workflow jumps. Only controlled public message/state/tool/interrupt projections and declared application extensions SHALL cross the boundary; raw private graph state MUST NOT be exposed. Opening or reconnecting a conversation paints the saved snapshot at its interaction cursor and continues the event subscription after that cursor. Historical token events are not played back onto the screen. A direct new-turn submission MUST reject an active turn; a separate explicit enqueue request SHALL add durable queued work without interrupting that turn.

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

- WHEN a direct new-turn submission targets a live or interrupted run
- THEN the backend MUST reject that direct submission without aborting, replacing or implicitly queuing the active task
- AND an explicit Queue action MUST retain the draft as durable queued work under backend ownership without interrupting the active turn.

#### Scenario: Disconnect and cancel are different

- WHEN navigation or unmount disconnects an observer
- THEN execution MUST continue under backend ownership
- AND explicit cancellation MUST remain cancel_requested until confirmed by the worker, independently of SDK loading state.
- AND a finished run MUST NOT have Cancel enabled.

### Requirement: API-007 - Launch locally and keep desktop state honest

The Windows launcher SHALL reuse a healthy product backend or start it hidden, then open the built Electron desktop. The first screen SHALL request projects and chats independently. Each list SHALL be readable before either request finishes. A list that has not finished SHALL NOT be presented as empty. Failure to reach the service SHALL retry until the first success. Chat SHALL keep the composer visible while transcript and history scroll independently. Recent conversations SHALL appear first. New Chat SHALL retain an explicit current Chat model choice. When no choice exists, it SHALL select the sole healthy running chat deployment; with several healthy running choices it SHALL request an explicit choice. It MUST NOT apply unrelated saved profiles. Stopped deployments MUST NOT gain healthy labels from stale probes.

The lower-left status dot is the only startup status. Its hover is one short phrase for reading the catalogue, starting the model, ready, or the service being unavailable. The visible word stays "Local" while the service is up, including while the rail is collapsed down to the dot.

Opening a finished chat SHALL show its saved transcript and latest display snapshot. It MUST NOT scan that chat's token log. The chat list MUST NOT include transcripts, run bodies, or model-request logs.

#### Scenario: Desktop launch and model state

- WHEN the launcher opens the application and a stopped deployment has an old probe
- THEN the desktop MUST present current backend state
- AND catalogue loading MUST be explicit rather than shown as an empty catalogue
- AND projects MAY appear before chats

#### Scenario: Finished chat opens from the saved transcript

- WHEN a person opens a chat whose answer is already saved
- THEN the saved answer is shown
- AND the token log is not read to paint it

#### Scenario: New Chat with a running model

- **WHEN** no Chat model has been chosen and exactly one healthy chat deployment is running
- **THEN** New Chat shows and submits that deployment's exact configuration without starting it again.

#### Scenario: Several running models

- **WHEN** no Chat model has been chosen and several healthy chat deployments are running
- **THEN** New Chat asks for an explicit model choice rather than silently selecting one.

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

Submitted user text SHALL display literally with original backslashes, punctuation, line breaks and indentation preserved, while long text wraps within the bubble. Model-only context additions MUST NOT appear as user-authored text. Assistant replies SHALL retain safe Markdown, code and table rendering.

Expose effective setup, actual selected tools/results, observed planning, context capacity/usage/compaction, approvals and loading/empty/error/reconnect states. Provide safe Markdown/code/table rendering, copy and access-checked open/save actions, keyboard controls and scrolling that respects the user's position. Generated HTML/scripts MUST NOT execute in the trusted renderer; opening/saving is not execution authority.

The `repair-local-interaction-boundaries` prerequisite SHALL remain satisfied: selection and transport binding stay atomic, stale callbacks are generation-guarded, command configuration and draft ownership are isolated, and accepted work is never retargeted or repeated by navigation. External links SHALL retain main-owned HTTP(S) validation and requesting-document/frame authorization; neither untrusted windows nor replacement documents gain the backend token.

#### Scenario: Reconnect and terminal result

- **WHEN** a streamed turn reconnects or completes while the user switches conversations
- **THEN** snapshots/events and final hydration produce one correctly attributed saved answer with partial/tool content intact.

#### Scenario: History and rendering

- **WHEN** history is archived or generated code/HTML is displayed
- **THEN** archive does not erase execution context and content cannot execute with desktop privileges.


#### Scenario: Exact submitted user text
- **WHEN** a person submits a Windows path, backticks, Markdown punctuation, blank lines or indented text
- **THEN** the user bubble SHALL retain those characters and spacing literally without interpreting them as Markdown or HTML
- **AND** assistant Markdown and code remain formatted, attachments remain accessible, and model-only context notices remain outside the user bubble.

### Requirement: API-011 - Keep background work visible and quit deliberately

Closing the main window or event stream SHALL NOT cancel or resubmit a run. Ongoing work SHALL have visible tray/background state and a route back. Explicit Quit with active work SHALL offer keep running or stop owned work and exit. Shutdown SHALL reconcile owned runs/clients/savers/processes and retain unresolved external outcomes; externally connected engines MUST NOT be terminated as owned processes. Reopening reconnects to existing work.

#### Scenario: Close reopen and quit

- **WHEN** a user closes/reopens the desktop or explicitly quits during work
- **THEN** close/reopen preserves the same run; Quit makes the keep-running versus stop-owned-work decision explicit and reconciles its outcome.

### Requirement: API-016 - Present one conversation-led desktop shell

The desktop SHALL provide a compact persistent icon rail on every page and a separate independently collapsible and resizable project/chat list in Chat. Search and Notifications SHALL be small icons at the top of the rail; Settings SHALL remain directly reachable on it. Icon names SHALL be available on hover and keyboard focus, with visible focus and usable targets. The chat list SHALL NOT duplicate a permanent search box or notification button. Destinations SHALL stay visible without their own scrollbar. The separate chat list SHALL show collapsible named project folders containing only their permanently scoped conversations, then chats with no project labelled as having no project. The no-project group SHALL remain in that list when it is empty. A project row SHALL start a new chat in that project, and a separate control SHALL create a project. Right-clicking a project SHALL offer editing it, archiving its chats, and removing it from the sidebar without deleting its folder. New chat, cross-area retained-history search, rename, archive and reopen SHALL remain available through the rail and chat list. The conversation header SHALL show its project or non-project identity; choosing a different area SHALL open or create another conversation rather than move or detach the current one. Removed-project history SHALL retain its identity.

The main New chat button SHALL start a conversation with no project, regardless of the previously selected chat or project. Each project's new-chat control SHALL start a conversation in that project, including when the project has no existing chats. Both paths SHALL preserve the selected main model and save the previous draft before leaving it.

Adding a project SHALL ask for a name and one existing folder. It SHALL NOT choose memory or grant edit permission beyond the selected folder. Creating a project SHALL NOT start or move a chat.

Compact destinations SHALL stay in the rail, including Settings, as their owning packets deliver functionality. Existing Agent run and its history SHALL remain accessible through the transition to Workflows. The conversation SHALL remain central with a visible composer. Files and previews open in the dock through API-023 and API-025. The conversation column stays visible while the dock is open, including when the dock is widened. Full and half-screen windows SHALL be normal supported layouts. On a narrow conversation column the dock stays a side column or closes before compromising ordinary conversation or composer use. A panel MUST NOT be painted over the transcript or the composer. Primary journeys MUST NOT require interpreting raw JSON, internal identifiers or backend terminology; technical details SHALL remain available on expansion.

Light and dark themes SHALL follow Windows by default with a user override. Settings appearance SHALL expose one shared control for each visual role, including the settings surface itself. Roles cover the colour palette, the type scale, corner styles, inset, the space between items, line thickness, and layout sizes such as page width, reading width, message width, dialog width, side columns, and control height. Near-identical values SHALL share a control. Inset, the padding inside a surface, stays separate from the space between items. Those scales keep only the steps a person can tell apart: tight, row, card, section, and page insets, and tight, item, block, and section gaps. Reading text stays separate from interface text. The file editor text size and chat code size stay separate from both. Each numeric control SHALL offer a slider and a typeable value. The typeable value SHALL accept any valid measurement and SHALL NOT impose an upper bound chosen for an assumed screen size. Colour controls SHALL include transparency. Font weight, opacity, and colour-mix strength stay inside their valid ranges. Applying SHALL store overrides in appearance.json in the product data root. A draft SHALL be visible in the open window, including Settings, before it is applied. A separate preview window SHALL show a representative window of that draft, and the person SHALL be able to move and resize that window beside Settings. While a control is pointed at or changed, that preview SHALL mark the parts the control changes. Cancelling SHALL restore the last applied values. Resetting one row SHALL restore its shipped value. Media and container breakpoints, viewport-tied layout, and one-off positions stay fixed. Compact controls SHALL retain readable labels, accessible names, visible keyboard focus and usable click targets. Reduced motion SHALL be respected. Settings SHALL expose appearance, notifications, saved grants and manual backup/restore; connection management is available in Settings through Connections using the same surface.

#### Scenario: Appearance draft is visible before it is saved

- **WHEN** a person changes a colour or a measurement in Settings and has not applied it
- **THEN** the open window, including Settings, shows that draft, and Apply stores the overrides in appearance.json on that computer

#### Scenario: Projects sit above chats with no project

- **WHEN** the chat list is expanded
- **THEN** the separate rail remains visible, each named project contains only its chats, and chats with no project follow those folders even when none exist.

#### Scenario: Add a project without starting a chat

- **WHEN** a user adds a project with a name and one existing folder
- **THEN** the project appears in the sidebar, no chat is created or moved, and memory is not chosen in that dialog.

#### Scenario: Start outside the last-used project

- **WHEN** a person selects the main New chat button after using a project chat
- **THEN** the new conversation has no project, retains the selected model, and the previous conversation and its draft retain their original project.

#### Scenario: Start a project's first chat

- **WHEN** a person selects the new-chat control on a project with no chats
- **THEN** the composer opens for that project and its first submitted message creates a conversation in that project.

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

#### Scenario: Collapse the chat list

- **WHEN** the person collapses the project/chat list or leaves Chat for another destination
- **THEN** the rail, Search and Notifications remain available, the destination gains the released width, and returning preserves the chat selection, draft and list preference
- **AND** narrow layouts collapse secondary columns before compromising ordinary transcript or composer use.

### Requirement: API-017 - Expose compact effective model controls and measurements

Opening a conversation SHALL restore that conversation's explicit Ask or Full access choice. An application preference SHALL seed new conversations and SHALL default to Ask on a fresh installation; project and agent definitions SHALL NOT override access. A chat's explicit choice SHALL survive unrelated preference changes and MUST NOT leak from the previously viewed chat. Access labels SHALL show Ask or Full access in full; supporting policy detail SHALL be available on demand without standing explanatory prose. Descriptions and model instructions SHALL reflect saved permission grants and the actual selected mode, while explicit questions and disabled-tool boundaries remain enforced.

The composer SHALL contain, in order, `+`, access, Plan only while enabled as a removable pill, the model selector with an adjacent tuning icon, the agent selector, compact context/speed and one combined Send/Stop control. A microphone SHALL NOT be shown before speech is delivered. Agent selection SHALL follow AGT-024, including its explicitly assigned-model exception. Grouped and individual tool choices SHALL be managed only in Agents setup, not in the agent dropdown or `+`. The shield selects Ask or Full access for later messages in that chat, does not enable tools and owns live window-grant controls. Changes prepare future submissions without rewriting running or already queued work. Unsupported, overridden or unverified reasoning controls SHALL be labelled truthfully; hiding returned thinking MUST NOT be represented as disabling model reasoning.

The bounded searchable model picker SHALL show one row per model, expanding named configurations only when more than one exists. Expansion SHALL NOT load a model. Ready, loading/waiting, attention and idle dots SHALL reflect the exact configuration's observed state, with equivalent accessible hover/focus labels. Saved configurations alone SHALL NOT imply residency. The tuning icon SHALL open a compact Thinking and Conversation capacity editor. Effective Thinking changes apply to the next accepted message immediately; context choices show memory impact and require one deliberate Reload when idle or Stage for the next submission during active work. Applied chat-local overrides SHALL be remembered separately per model within that chat; first use starts with saved model defaults and returning restores those overrides. Permanent defaults, response-length controls and thinking-token-limit controls SHALL remain in Models. Applying startup changes SHALL reload only when safe and preserve the draft, attachments, history and reading position; active-work changes SHALL use the staging rule in API-028.

Compact status elements SHALL expose current context fill and generation speed in tok/s, with capacity, counting/measurement basis and relevant interval available on expansion. Observed measurements, labelled estimates and unavailable values SHALL remain distinguishable. Stream chunks MUST NOT be counted as tokens; absent usage MUST NOT appear as zero. Context changes/compaction and current versus completed-turn measurements SHALL remain attributable rather than silently showing stale values as current.

Context details SHALL open on pointer hover and keyboard focus, with touch access and Escape dismissal. Prefer model-reported request input/output counts over preflight estimates once available. Supported llama.cpp timing streams SHALL supply live generation speed with bounded updates and no shared-slot polling; measurements SHALL reset at each model-call boundary and retain their current/completed/interrupted status. Compact settings SHALL avoid redundant default-value cards while preserving actionable failures, meaningful choices and accessible explanations.

Opening the application or restoring a chat SHALL NOT warm its selected model. Sending with an unloaded installed managed model SHALL load the selected setup through the existing manager and admission path, show waiting/loading/readiness, then submit once ready. Failure SHALL preserve input and offer recovery. A passive status probe MUST NOT cause loading. Active-work protections and connected-endpoint ownership MUST NOT be bypassed and models/settings MUST NOT be silently substituted.

Chat SHALL expose one live activity status beside the composer Stop control. Model output SHALL be labelled Generating without inferring current reasoning from retained content. Current tool execution, prompt preparation, summarization, approval waiting, finalization and cancellation SHALL remain distinguishable; pending admission SHALL show Starting and unknown active activity SHALL show Working. Activity-only changes SHALL update the status even without a new audit event. Terminal work SHALL NOT retain a live activity label, and late observations from another selection or run SHALL NOT replace the selected status. Measurement updates SHALL remain isolated from transcript rendering.

The context/speed hover panel SHALL retain total context, capacity, percentage and available input-total, cached-input, newly-processed-input and output counts in aligned label/value rows. Numbers SHALL remain intact at narrow widths and larger text sizes. Cached and newly processed input SHALL be identified as subdivisions of input total. Current and last-request speed, estimates and unavailable measurements SHALL remain explicit.

#### Scenario: Unsupported reasoning and unavailable telemetry
- **WHEN** the selected model lacks a supported thinking-off control or supplies no usable token measurement
- **THEN** the control/measurement explicitly reflects that limitation rather than claiming thinking is off or showing an invented tok/s value.

#### Scenario: Cold launch and first Send
- **WHEN** Workbench opens a chat whose selected model is unloaded, then the person submits a draft
- **THEN** launch remains cold, Send shows loading and submits once that exact configuration is ready, while failure preserves the draft and cannot duplicate accepted work.

#### Scenario: Start from Chat with a resource conflict or failure
- **WHEN** a submitted draft needs an unloaded model while another request holds the only slot or loading fails
- **THEN** Chat shows waiting or the failure with a corrective action, preserves the draft and cannot duplicate accepted work.

#### Scenario: Setup stays off the transcript
- **WHEN** a person opens tuning beside the selected model
- **THEN** one bounded editor shows effective Thinking choices and context with deliberate Reload or Stage, and no response-length or thinking-token-limit control.

#### Scenario: Inherited access follows its named source
- **WHEN** the application preference changes after a chat explicitly selected Ask
- **THEN** that chat remains Ask while a new chat takes the current application preference, and Chat names the preference source when no explicit choice exists.

#### Scenario: Bounded everyday reasoning and scoped measurements
- **WHEN** the user selects a template-effective Thinking level and later an internal summary runs
- **THEN** Chat SHALL show the supported effective effort and distinguish work, summary, cached input, current measurements and completed measurements without inventing unavailable values or adding response/thinking-token-limit controls.

#### Scenario: Tool activity changes without an audit event

- **WHEN** an owned live run changes from tools to model generation without increasing its audit event count
- **THEN** the composer status changes from Using tools to Generating with the current measurements
- **AND** late events from another conversation or completed run cannot restore stale activity.

#### Scenario: Read measurements in a narrow panel

- **WHEN** all four token counts are available in a narrow window or with larger text
- **THEN** each label and intact number occupies a readable aligned row
- **AND** the panel explains input subdivisions and whether the speed is current or from the last request.

#### Scenario: Return to a model in the same chat

- **WHEN** the person applies chat-local tuning to model A, uses model B, then returns to A
- **THEN** A's chat-local tuning is restored without changing either model's permanent defaults or another chat's overrides.

### Requirement: API-018 - Keep answer streaming independent of detail visibility

Answer text SHALL always appear incrementally, including through a long reply. Painting the reply MUST stay with generation: earlier finished messages, and finished parts of the same reply, stay in place and remain readable. A compact Reasoning and tools switch in the header's Conversation view menu SHALL default off and remember the user's preference across conversations/reopening. Its presentation controls stay distinct from model Thinking and effort controls. Changing this switch SHALL only change the visibility of returned detail, never model reasoning or tool permissions. The composer Stop control is the only stop. Chat does not show a separate Activity row with its own cancel control. When enabled, available returned thinking, tool input, tool output and other raw detail SHALL be distinctly labelled apart from answers; absent streams MUST NOT be fabricated. When disabled, that expanded detail stays collapsed while answer text continues streaming. The planning checklist and the one-line activity rows in API-026 remain visible in both modes. Motion preferences SHALL be respected.

While a reply is running and the person is already at the bottom, the transcript SHALL follow the newest line immediately. Scrolling away stops following. Returning to the bottom follows again. Following sets the position directly. Smooth scrolling is reserved for an explicit jump, such as opening a chat or a notice, and reduced motion stays immediate. A text selection inside the transcript MUST be left in place. An open reasoning section follows the newest line the same way until the person scrolls inside that section, and the full reasoning text stays reachable by scrolling. Token growth MUST NOT be announced as a stream of accessibility updates. The composer status is the sole generic live activity announcement. Main Chat SHALL NOT repeat it as active response badges or generic transcript progress lines. Returned reasoning and named tool/helper activity SHALL remain visible according to the presentation preference; interrupted historical responses SHALL retain their Partial markers.

A speed or context measurement SHALL update its readout only. It MUST NOT rebuild the transcript, move the scroll position, delay the next tokens, or change execution.

Each output section SHALL independently expand/collapse through a heading or chevron, overriding the global presentation for that section without disrupting text selection or links. Approvals, typed questions and errors SHALL remain visible in both modes. Toggling presentation MUST NOT change execution, permission, saved content or the user's scroll position. Copy, Regenerate answer and Branch SHALL appear on each saved assistant answer and SHALL NOT appear while that answer is still streaming. Copy on an answer SHALL copy that answer's text. Chat code blocks, tool input and tool output SHALL each provide a copy icon. Unavailable Regenerate answer or Branch SHALL stay disabled with the truthful reason rather than retrying the task. Retry task and edit-the-task SHALL be available beside their owning messages; export and delete SHALL be in the conversation header menu. Chat SHALL NOT retain an Actions/history dock page. Retry task SHALL disclose possible repeated effects before it runs. Branch, Retry task and Regenerate answer SHALL remain visibly distinct and obey AGT-012.

#### Scenario: Hide details while an answer streams

- **WHEN** a user disables detailed streams during generation and expands one tool result
- **THEN** answer text continues, other raw tool input and output stay collapsed, the chosen result opens independently and execution/content identity remains unchanged.

#### Scenario: Interrupt during compact presentation

- **WHEN** an approval, typed question or error occurs with detailed streams hidden
- **THEN** the actionable card remains visible and cannot be mistaken for continuing generation or hidden by collapsing activity.

#### Scenario: Actions on a saved answer

- **WHEN** a saved assistant answer is shown
- **THEN** Copy, Regenerate answer and Branch are on that answer, and Retry task is beside its owning message with possible repeated effects disclosed before execution.

#### Scenario: Copy a presented chat block

- **WHEN** a user copies a chat code block, tool input or tool output
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

#### Scenario: One live status with retained reasoning

- **WHEN** a response emits reasoning, executes tools and then generates an answer
- **THEN** the composer alone shows the generic current activity while reasoning and named tool details remain inspectable
- **AND** cancellation retains partial content, its Partial marker and actionable failures or approvals.

User messages SHALL appear in small right-aligned bubbles; assistant answers SHALL flow on the conversation background without enclosing answer cards. Markdown, code, tables, diffs, retained media and named tool/helper attribution SHALL remain readable and usable. Default-collapsed detail SHALL remain individually inspectable.

#### Scenario: Read a compact answer with code and tools

- **WHEN** the assistant returns markdown, a code block and a named tool result
- **THEN** the answer flows on the background, its code remains selectable/copyable, and the tool row remains visible with independently expandable detail.

### Requirement: API-019 - Present queued work and scoped attention clearly

During active work Enter queues the draft. One combined action SHALL show Send when idle and Stop for the complete active turn, including tool activity, approval/input waits, finalization and cancellation settlement. It SHALL NOT toggle back to Send merely because a token stream ended. During the atomic save phase, the action SHALL keep Stop's position but disable it with truthful Finishing feedback. Shift+Enter SHALL insert a newline; hover and keyboard focus SHALL provide concise action feedback. A compact row inside the composer SHALL expose each queued message with edit and remove. Stop SHALL cancel the active turn separately; cancelling leaves the queue paused until deliberate continuation. A queued message sends itself when the turn finishes successfully. AGT-010 SHALL govern persistence, dispatch and progression: only success advances automatically, failure/cancellation pauses, and approval/input waits do not advance. Header setting changes MUST NOT silently mutate queued items.

Inline approval cards SHALL show exact action/resource scope and the four AGT-008 choices, explaining broader grant scope before selection. Saved grants SHALL remain inspectable/revocable in Settings. Sidebar badges and a compact attention list SHALL identify conversations waiting for approval/input or needing failure recovery. The count SHALL remain on the small Notifications icon at the top of the rail, whether the separate chat list is open or closed. A notice can be dismissed. Opening a notice selects its existing conversation and dismisses that notice. If that conversation is gone, the notice is dismissed and a new chat is not created. Deleting a conversation dismisses notices for runs that leave with it, and the bell count updates immediately. A dismissed notice does not return. The list finds the conversation that contains the run, including when that run is no longer the latest turn. Windows notifications SHALL default on for those events while the application is backgrounded, subject to OS/user settings; successful completion notifications SHALL default off. Notifications MUST NOT steal focus, auto-switch conversation or answer interruptions. User activation SHALL navigate to the corresponding current conversation/attention state without replaying work; in-app attention SHALL remain usable when OS notifications are unavailable.

#### Scenario: Queue with independent configuration

- **WHEN** a user queues a follow-up, changes the selected model and then the active turn fails
- **THEN** the queue pauses with its original intended model/setup visible and editable, and Stop/Queue remain distinct from approval actions.

#### Scenario: Background approval and notification navigation

- **WHEN** another conversation requests approval while the app is backgrounded
- **THEN** its badge/attention entry and allowed Windows notification identify it without moving focus, and opening it presents the current interruption rather than accepting a stale decision.

Project waiting SHALL be distinct from a follow-up behind the same conversation. A known settled outcome in one chat SHALL permit another eligible chat in that project to advance after revalidation; failed-conversation follow-ups keep their existing pause rule. The waiting row SHALL name its owner and offer Open active chat and Cancel waiting message.

#### Scenario: Another chat owns the project
- **WHEN** a submitted message waits for an overlapping project task
- **THEN** the message SHALL show that project wait rather than model loading and its cancellation SHALL affect only itself.

#### Scenario: Stop during tool execution

- **WHEN** generation pauses while the same active turn executes a tool
- **THEN** the action stays Stop, Enter queues the follow-up, and Stop cancels that turn through its existing lifecycle without sending the draft.

### Requirement: API-020 - Separate technical verification from human UX acceptance

Each affected change SHALL demonstrate its end-to-end user journey in the built Windows application and record technical verification separately from Dave's UX acceptance in its existing design/PR. Reviews SHALL cover full and half-screen windows, actual Windows display scaling, keyboard navigation, long conversation/result content and at least one failure/recovery state. Screenshots alone MUST NOT count as interaction verification. Required technical/live checks SHALL remain required; UX acceptance SHALL remain pending until Dave accepts the built experience or explicitly defers review, with deferral recorded as deferred rather than accepted.

Chat layout changes SHALL include an early review after the basic arrangement is exercisable and before the remaining controls accumulate, including the existing Models-to-Chat journey. Everyday workspace, Lab and Workflows changes SHALL include major surface reviews; delegation/approval and media changes SHALL include focused reviews of those paths. Lab and Workflows SHALL each require an approved detailed layout before substantial interface implementation. Specification approval MUST NOT be treated as visual acceptance of the built product.

#### Scenario: Technical checks pass before user review

- **WHEN** automated checks and agent-driven Windows interaction pass but Dave has not reviewed or explicitly deferred the experience
- **THEN** technical results are recorded as such while UX acceptance remains pending.

#### Scenario: Explicitly deferred review

- **WHEN** Dave explicitly defers a milestone's UX review
- **THEN** its existing design/PR records the deferral separately from technical evidence and does not claim UX acceptance or waive required live checks.

### Requirement: API-023 - Keep one dock beside the conversation

Chat SHALL use one right-hand dock with exactly Files, Browser and Helpers pages. It starts closed; one header control opens/closes it and retains its open choice, page and bounded width across chat navigation. All pages SHALL share one remembered preferred width, seeded from the existing Files preference, with common resize/reset behaviour; browser resolution SHALL remain separate. A smaller window SHALL clamp displayed width without overwriting the preference, and the resize handle SHALL reflect displayed width. A splitter SHALL resize it while preserving a readable conversation column and reading position. Choosing a page replaces the current page rather than adding another card. Opening SHALL require a person choosing its toggle, page or a file/helper link; new browser/helper/file activity SHALL only update a compact indicator. Files SHALL combine project files, chat uploads/generated outputs and authorized reusable saved copies with clear origins; global Library SHALL remain accessible for bulk catalogue work. Setup and Actions/history pages SHALL be removed, with setup controls in their owning composer or destination and chat/message actions under API-018. Opening adds a side column, closing returns width, and narrow layouts SHALL collapse secondary columns before compromising ordinary chat use. The dock MUST NOT cover the transcript/composer, move above the composer or hide the conversation to grow. Resize/collapse/reopen SHALL retain content and run state and follow the application theme. Per-conversation filters, expanded folders, previews, helper selection and reading position SHALL survive tab changes and closing. Hidden Browser views SHALL release frame subscriptions while retaining the session. The idle Browser connection label SHALL describe its actual state and its download shortcut SHALL read Show in Files. Each page SHALL use one outer scroll owner, with separate tree/editor/transcript scrolling only when needed.

#### Scenario: Open, resize, and close
- **WHEN** a person opens the rail to Files, drags the splitter, switches to Helpers and Browser, and then closes the rail
- **THEN** the transcript narrows and widens with the same dock width, only one page is showing, and closing restores the conversation width
- **AND** the answer text is never covered and reopening retains view state.

#### Scenario: Narrow window
- **WHEN** the conversation column is about half a screen wide and the rail is open
- **THEN** an open dock stays beside the transcript/composer while usable, or closes before crowding them
- **AND** reopening retains its page, width preference and content without covering the answer, and widening restores the preferred width.

#### Scenario: Activity without automatic opening
- **WHEN** a browser session starts, a helper works or a generated file appears while the dock is closed
- **THEN** a compact indicator updates and the dock stays closed until a person chooses to open it.

#### Scenario: Contextual file origins
- **WHEN** Files lists a live project file, a chat upload and a reusable retained copy
- **THEN** each retains its existing identity, authority and origin, and preview/reuse does not create a second file catalogue.

#### Scenario: Hidden browser viewing
- **WHEN** a person changes from Browser to Files or closes the dock
- **THEN** live frame subscriptions stop, the browser session remains available, and selecting Browser reconnects to that session.

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

### Requirement: API-026 - Show planning and native tool activity as it happens

While an assistant turn runs, and when that turn is reopened, Chat SHALL show planning and tool activity from the projected tool calls. This is visible with detailed streams on or off.

`write_todos` SHALL appear as one checklist for that turn. Each item shows its task content and its status: pending, in progress, or completed. The status is a mark on that row, separate from the sentence. The sentence is the task content alone. The checklist is the arguments of the latest successful `write_todos` call. A later successful call replaces the list. A failed call leaves the previous list and shows the failure. The product MUST NOT keep a second todo list or read private graph state. Raw arguments remain available on a further disclosure. The checklist appears only once those arguments parse as the todo list.

Each other filesystem, search, shell, MCP, and memory tool keeps one identity line, one per call identity, in order, without a duplicate when live and retained records join:

- Reading or Read, plus the path. When the call includes an offset and limit, the line includes that line range.
- Creating or Created, Editing or Edited, using the recorded operation.
- Listing or Listed, Finding or Found files matching, Searching or Searched for, Running or Ran, Calling or Called, Proposing or Proposed a memory.

An actively running unfinished call uses the present-tense verb. The finished call uses the past tense. A failure shows on that line. Retained incomplete arguments from a stopped or failed turn SHALL be labelled as partial input, never as ongoing work or a completed file. Starting a later turn MUST NOT reactivate that label. Tool activity MUST NOT claim a file difference or line count that was not recorded. A shell line shows the command truncated to one line.

A single finished call stays as that identity line. Two or more consecutive finished successful calls that share the same verb, and that are not waiting for a person, collapse into one summary line. The summary names the verb and how many calls it covers, for example "Read 6 files" or "Ran 3 commands". It does not invent a combined file result. Opening the summary shows the identity lines in their original order. A call that is still running, a call that failed, and a call that is waiting for approval or a typed answer each stay on their own line and are not folded into a summary. Closing the summary does not discard the calls.

The first opening of an identity line shows the plain result: the path, the command, the output, or the short description of the change. The internal tool name and the raw arguments stay on a further disclosure. They MUST NOT be the first thing that opening shows.

While a call is unfinished and its body is open, that body follows the newest line until the person scrolls inside it. The open body shows the full text produced so far. Every line stays reachable by scrolling, and copy copies that full text. The product MUST NOT drop earlier text to keep the view small. Completed file content SHALL remain readable with its original line breaks; raw arguments remain available separately.

Choosing a file identity line opens the Files page on that file when available. Choosing a summary line does not open the dock. The choice MUST NOT send a chat message or call the model. Approvals and typed questions keep their existing cards. The activity line MUST NOT offer a second set of approval buttons.

#### Scenario: Todo list updates in place

- **WHEN** the agent writes a todo list and later marks an item complete
- **THEN** one checklist shows the latest successful items and statuses
- **AND** detailed streams being off does not hide it.

#### Scenario: Checklist status stays off the sentence

- **WHEN** a checklist item is pending and its content is "Fix the frame step"
- **THEN** the row shows that content as the sentence and shows pending as a separate mark
- **AND** the sentence does not begin with the word pending.

#### Scenario: Native file edit line

- **WHEN** an edit of `thistest.md` finishes
- **THEN** the transcript shows one line equivalent to "Edited thistest.md"
- **AND** choosing it opens the live file when available, without claiming an undoable difference.

#### Scenario: Read activity

- **WHEN** the agent reads `SKILL.md`
- **THEN** the transcript shows a line equivalent to "Read SKILL.md"
- **AND** no invented change count is shown.

#### Scenario: Incomplete file call stays partial

- **WHEN** an edit has started and its result is not yet available
- **THEN** the line shows that the file is being edited
- **AND** only genuinely incomplete arguments are labelled as partial input; complete calls show undispatched, failed or uncertain outcome according to available evidence, without an invented result or line count.

#### Scenario: Failed todo does not wipe the list

- **WHEN** a todo update fails after a successful list
- **THEN** the previous checklist remains and the failure is visible.

#### Scenario: A long write stays fully readable

- **WHEN** a file write is still streaming, the person has the row open, and they then scroll toward the start of that body
- **THEN** the newest lines were in view while the body was following
- **AND** scrolling reaches the earlier lines and copy copies the full text written so far.

#### Scenario: A burst of reads is one line

- **WHEN** a turn finishes six successful reads in a row and none of them is waiting for a person
- **THEN** the transcript shows one summary equivalent to "Read 6 files"
- **AND** opening it shows the six paths in the order they ran.

#### Scenario: The live call stays visible

- **WHEN** five reads have finished and a sixth read is still running
- **THEN** the finished reads are one summary and the running read is its own line
- **AND** a failed read is not folded into the successful summary.

#### Scenario: Opening a tool shows the result first

- **WHEN** a person opens a finished shell line
- **THEN** the command and its output are the first content
- **AND** the internal tool name and the raw arguments stay behind a further disclosure.

The original durable parent-turn error SHALL remain visible after reopening, with its category and relevant recovery action. Review setup SHALL be offered only for setup problems. Known recoverable tool errors SHALL be returned to the agent for correction; uncertain effects SHALL be inspected before continuation.

#### Scenario: Parallel batch partially succeeds
- **WHEN** two file writes succeed and four fail
- **THEN** the two confirmed results SHALL remain successful and the four failures SHALL show their original causes
- **AND** the chat SHALL stay usable without relabelling all six calls as unfinished input.

#### Scenario: Read-only decoding failure remains correctable

- **WHEN** a native file read or search cannot decode text while another tool in the same batch succeeds
- **THEN** the failed call SHALL retain its original identity and an explanatory error, and the successful sibling SHALL retain its confirmed result
- **AND** the error SHALL be returned to the agent so it can finish or correct its task without automatically replaying the failed call or reporting incomplete search results as successful
- **AND** both outcomes SHALL remain inspectable after reopening, while cancellation, persistence failures and uncertain write or shell effects retain their existing recovery guarantees.

### Requirement: API-027 - Keep every destination compact and readable

Every destination SHALL use the same compact type, spacing, and icon actions as Chat. Headings stay short. The product name is not repeated on every panel. Help that is not required to act SHALL open on hover or keyboard focus and close on Escape. Primary actions, the current setup, errors, and permissions stay visible without opening a raw detail view. Keyboard focus is visible. Labels stay readable at the person's Windows text size. A disclosure is allowed to use a chevron. Resizing or collapsing navigation and the Chat dock MUST NOT drop content or run state.

#### Scenario: Move between destinations

- **WHEN** a person moves from Chat to Lab, Workflows, and Settings
- **THEN** the type, spacing, and focus treatment match
- **AND** the composer or the destination's primary action stays reachable without horizontal scrolling.

### Requirement: API-028 - Switch the selected model without interrupting work

When idle, choosing a different or unloaded model/named configuration or a fixed-model agent SHALL start loading that exact managed selection without a second confirmation. Choosing the exact currently selected healthy configuration SHALL leave the binding unchanged and SHALL NOT request a model start. Idle selection remains pending until readiness is observed; a failed load SHALL retain the previous observed chat binding and the exact editable draft candidate with an actionable reason. The failed candidate SHALL remain available for adjustment or retry and MUST NOT be represented as a loaded runtime. During active work model, agent and applied tuning changes SHALL prepare only the next submission; they SHALL NOT load/reload a candidate in a way that changes running, queued or paused snapshots. A later accepted message freezes that candidate and loads/reloads through safe shared admission when it can start. Draft-only changes SHALL NOT start queued work, cancel current work or edit already accepted inputs. A compact changed-state indicator SHALL be used only when needed, without repeated explanatory prose. Known-incompatible choices SHALL carry reasons; unknown or failed previews MUST NOT imply compatibility. The chat and its compatible history remain open; selection SHALL NOT create a new chat. Explicit stop/unload/destructive changes retain their existing protection.

#### Scenario: Swap during a quiet chat
- **WHEN** a person chooses a different installed model while the previous model is idle
- **THEN** the selected model loads under the configured limit without asking for another confirmation and the conversation stays open.

#### Scenario: Swap while work is running
- **WHEN** one slot is occupied by an in-flight request and a different model is chosen
- **THEN** that request and any already queued snapshots stay unchanged, the candidate is prepared for the next submission, and its exact configuration loads only through safe admission when that message can start.

#### Scenario: Apply a named model variant in Chat
- **WHEN** a person chooses a named configuration with different launch settings
- **THEN** idle Workbench loads those exact settings before binding the same chat, while active Workbench stages them for a later submission, retaining draft and history on failure.

#### Scenario: Failed selection
- **WHEN** the requested model cannot become ready
- **THEN** the previous observed conversation binding remains, the exact failed selection remains in editable draft intent for adjustment or retry, and the failure is visible without claiming the candidate is loaded.

#### Scenario: Reselect the current healthy configuration

- **WHEN** a person selects the current installed model row while its exact named configuration is healthy and loaded
- **THEN** the same configuration remains selected and no readiness, start or load request is made.

#### Scenario: Compatibility is not known

- **WHEN** a model choice has not been checked or its preview failed
- **THEN** the picker does not label it compatible and checks the exact choice before loading.

#### Scenario: A staged queued configuration cannot load

- **WHEN** a newly accepted follow-up's exact staged model/settings fail to load at dispatch
- **THEN** its saved input, attempted setup and prior conversation remain recoverable, the queue pauses with an actionable error, and another model is not substituted.

### Requirement: API-029 - Show who is working and who is waiting

When a named helper or a workflow step is running, the activity view SHALL show that agent or step by its name under the parent conversation or workflow. Status uses plain words: working, waiting for approval, waiting for a typed answer, waiting for the model, or failed. The reason for a wait is one line. Child tool rows use the same one-line activity labels as API-026 and stay indented under that name. Stopping names what will stop. The view MUST NOT be the only place a person can approve or answer. Those cards stay in the conversation or on the workflow step.

#### Scenario: Helper waits for approval

- **WHEN** a named helper asks to edit a file
- **THEN** the activity row shows that helper's name and that it is waiting for approval
- **AND** the approval card remains the control that allows or rejects the edit.

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

### Requirement: API-031 - Hold the place where the answer will appear

From the moment a person sends a message until the first checklist, tool line, or answer text of that turn is visible, the transcript SHALL show that turn in the place the answer will grow. The existing context and speed readout remains the measurement. The composer Stop control remains the only stop. Chat MUST NOT add an activity row with its own cancel control. When the first checklist, tool line, or answer text appears, it replaces that waiting place. It MUST NOT leave a second empty block above the real turn.

#### Scenario: The wait sits where the answer will be

- **WHEN** a person sends a message and no checklist, tool line, or answer text has appeared yet
- **THEN** the transcript shows that turn in progress where the answer will grow
- **AND** the only stop is the composer Stop control.

#### Scenario: The first real line takes that place

- **WHEN** the first tool line or answer text of that turn appears
- **THEN** it occupies the waiting place
- **AND** no empty waiting block remains above it.

### Requirement: API-032 - Keep the composer clear of the answer

The transcript SHALL be able to scroll so the last line of the conversation sits clear of the composer. Model settings, the approval menu, and the context readout SHALL open without covering that last line. When there is not room below the composer control, the menu opens above it inside the conversation column. The shield's visible label SHALL be the same words as the menu: Ask or Full access.

#### Scenario: The end of an answer can be read

- **WHEN** a person scrolls to the end of a finished answer
- **THEN** the last line sits clear of the composer
- **AND** it can be read without the composer covering it.

#### Scenario: A composer menu leaves the answer visible

- **WHEN** a person opens model settings or the approval menu at the end of a conversation
- **THEN** the last line of the answer remains readable
- **AND** the menu can be dismissed with Escape.

#### Scenario: The shield uses the menu's words

- **WHEN** the chat is set to full access
- **THEN** the shield reads Full access
- **AND** the menu uses that same name.

### Requirement: API-033 - Use one title and a distinct model label

The sidebar row for a conversation and that conversation's header SHALL show the same current title. A new conversation may read "New conversation" until it has a title. When the title changes, both update together.

Each model chooser SHALL show one primary row per installed model or connected endpoint, with an installed model's named configurations as secondary choices, rather than duplicate historical runtime instances. Sibling model rows or configuration choices MUST NOT share the same visible label. A repeated file name gains the fact that distinguishes it, such as ready or stopped, context, or size. An internal prefix such as `managed:` MUST NOT appear in the label. Meaningfully distinct configurations SHALL remain selectable; equivalent duplicate runtime records SHALL not become duplicate user choices.

In the library, rows that share a file name stay separate, and each row shows when it was added and where it belongs without opening the file.

#### Scenario: The sidebar matches the header

- **WHEN** a conversation's title changes from "New conversation" to a sentence
- **THEN** the sidebar row and the header both show that sentence
- **AND** a second conversation that is still untitled stays "New conversation".

#### Scenario: Repeated model files stay distinguishable

- **WHEN** two selectable configurations of one installed model use the same file name and one is ready
- **THEN** both remain distinguishable as secondary choices under the single model row
- **AND** each choice has its own visible label without an internal prefix.

### Requirement: API-034 - Finish the page the person is looking at

Every existing destination SHALL retain and repair its current usable functions. Agents remains the named list. The future Lab Measurements/Memory/Challenges suite and visual Workflows canvas remain separately specified work and MUST NOT be represented as completed by polishing their current surfaces.

The page frame is the same on every destination: a short title, one primary action, and the content. An empty destination says what to do next in that content area. A destination that is working says what is in progress there. A failure says what failed and what to do next, in that same area. The empty, working, and failed states use Chat's type and spacing.

A closed disclosure SHALL show one plain status, such as ready, a count, or that it is empty. An empty disclosure that offers no action is omitted. A closed disclosure MUST NOT appear as a blank bordered bar. Opening it shows the controls that disclosure already has.

#### Scenario: An empty page says what to do

- **WHEN** Attention has no notices
- **THEN** the content area says the person is caught up
- **AND** the page does not leave that sentence alone in an otherwise empty frame.

#### Scenario: A closed section reports its status

- **WHEN** a model section is closed and eight models are stopped
- **THEN** the closed row says that eight are stopped
- **AND** opening it shows those models.

#### Scenario: An empty agent section is honest

- **WHEN** a saved agent has no knowledge selected
- **THEN** that section says none is selected, or it is omitted when there is nothing to choose
- **AND** it is not a blank heading.

#### Scenario: The frame wraps the destination that is already there

- **WHEN** a person opens a destination that already has its specified content
- **THEN** that content remains, inside the same title and primary action
- **AND** this change does not add a second layout beside it.

### Requirement: API-035 - Open a Settings section, and preview the real window

Settings SHALL remain directly reachable on the destination rail. Within it, the person SHALL be able to open Appearance, Notifications, Defaults, Connections, Permissions, and Backup directly. Appearance SHALL show compact basic controls and explicitly opened advanced customization, preserving every existing shared control, slider and typeable value, Apply, Cancel, and per-row Reset within bounded responsive columns. Help for Apply, Cancel, and Reset SHALL open on hover or keyboard focus. It MUST NOT be a standing paragraph above the controls.

The separate preview window SHALL show a small conversation of the draft: rail and chat list, a short transcript with one tool line and an unboxed answer, the compact composer, and one settings card. Spacing guides SHALL start off and remain available. Pointing at a control, or changing it, still marks the parts that control changes. The preview MUST NOT replace the open Settings page.

#### Scenario: Backup is reachable without the colour list

- **WHEN** a person opens Settings and chooses Backup
- **THEN** backup and restore are shown
- **AND** the appearance controls are not required to scroll past first.

#### Scenario: The sample looks like the conversation

- **WHEN** a person opens the appearance preview
- **THEN** the sample shows the rail and collapsible chat list, a short transcript, compact composer and settings card using the draft
- **AND** spacing guides are off until the person turns them on.

### Requirement: API-037 - Say when a saved permission let the tool proceed

When the chat is on Ask, and a tool that would have paused proceeds because a saved grant allows it, that call's activity line SHALL say a saved permission was used. The line names the grant in plain words. The full grant remains available on the further disclosure and in Settings, where it can still be revoked. The backend captures the exact matched grant when authorizing the call; later edits or revocation do not rewrite that recorded evidence. Historical records without a captured grant identity show only proven saved-permission use, never an invented identity. Saved grants remain explicit exceptions to the access rules, are attributed by the backend, and MUST NOT override Plan mode or enable a disabled tool.

#### Scenario: Ask uses a saved grant

- **WHEN** Ask would pause a shell command and a saved grant lets that command proceed
- **THEN** the activity line says a saved permission was used
- **AND** the person can still revoke that grant in Settings.

### Requirement: API-038 - Keep everyday controls compact and stable

Every existing desktop surface SHALL use concise labels, bounded form widths, compact switches for binary choices and notched sliders with exact entry for appropriate numeric settings. Longer explanations belong in accessible hover/focus help. Disabled actions SHALL expose their reason. Overlaid menus, speed measurements and loading labels MUST NOT move the composer or adjacent controls. Only selected attachment chips occupy composer space; attachment actions open from its compact menu. Project management SHALL open contextually from the existing project rail without a duplicate Projects destination.

#### Scenario: Open a composer menu
- **WHEN** the model or access menu opens, closes, or updates a live measurement
- **THEN** composer bounds and transcript reading position remain stable, except deliberate text/file content changes
- **AND** keyboard focus, dismissal and narrow-window containment work.

#### Scenario: Return to a conversation
- **WHEN** a person leaves Chat for another destination and returns
- **THEN** the same selected conversation, draft, attachments and reading position are restored
- **AND** only explicit New chat resets selection.

#### Scenario: Wide and narrow workspaces
- **WHEN** the desktop is resized from a narrow window to an ultrawide display
- **THEN** forms remain readable and bounded while useful tables/previews can use additional space
- **AND** controls remain keyboard accessible without unintended horizontal overflow.

### Requirement: API-039 - Show settled execution while saving project state

After graph execution settles, a project-bound run SHALL expose a durable saving phase until its final project capture is committed or declared unavailable. Chat and Agent run SHALL show “Saving project state” during that phase and disable Stop. A Stop request during saving MUST return `run_finalizing` and MUST NOT change the settled execution outcome. Exactly one terminal outcome SHALL be published after finalization.

#### Scenario: Stop after execution settled

- **WHEN** a project-bound run has entered saving and a person presses Stop or sends a Stop request
- **THEN** the run keeps its settled outcome and the request reports `run_finalizing`
- **AND** Chat and Agent run show saving until one terminal outcome appears.

### Requirement: API-040 - Keep measurements independent of generated output

Replaceable generation measurements SHALL NOT delay answer tokens, change model exceptions or cancellation, or determine the execution outcome. The final valid measurement available for a request SHALL be included in its terminal record. Message, tool, lifecycle and audit events SHALL retain ordered durable delivery. If essential interaction persistence fails, dispatch SHALL stop with an explicit `interaction_persistence_failed` outcome rather than reporting a model failure or silently dropping events.

#### Scenario: Measurement publisher stalls

- **WHEN** measurement publication stalls or fails while a model streams a token or raises an error
- **THEN** the token or original error reaches execution independently of the publisher
- **AND** the terminal record retains the latest valid measurement available.

#### Scenario: Essential projection cannot persist

- **WHEN** a native message or tool event cannot be durably recorded
- **THEN** further dispatch stops and the run reports `interaction_persistence_failed`
- **AND** it does not claim the model caused that failure.

### Requirement: API-041 - Replay according to each subscription

A hydrated root view SHALL continue after the cursor paired with its saved state without briefly replacing its in-progress answer with older tokens. A newly opened same-filter or wider subscription SHALL receive its available matching message, tool, lifecycle and namespace history, while existing subscribers SHALL skip events at or before their own cursor. A reconnect SHALL continue after the last complete event consumed by that stream handle; an incomplete frame MUST be replayed. Synthetic recovery events SHALL carry stable identities. Existing chats with unavailable historical detail SHALL say that detail is unavailable rather than inventing it.

#### Scenario: Open details during an active answer

- **WHEN** a hydrated answer is in progress and a new tool or nested-namespace selector opens
- **THEN** the answer remains visible and continues from its saved cursor
- **AND** the new selector receives available matching prior and live events without duplicates.

#### Scenario: Disconnect inside a frame

- **WHEN** a stream disconnects after an event ID but before the complete event frame
- **THEN** its reconnect cursor remains before that event
- **AND** the completed event is delivered once.

### Requirement: API-042 - Use one control grammar across settings

Every settings form in the desktop SHALL use one row grammar: the label, hover/focus help and a short provenance line (value, source and state, omitting unknown parts) on the left, the control on the right, and an optional hint underneath. Binary settings SHALL use a switch, two to five options a segmented choice, ordered numbers a slider with exact entry, long lists a select, and destructive confirmations a dialog. Default-following values SHALL appear as their resolved value in the control or a named default choice, with a reset action naming its verified target and exposing its known value on hover/focus; displaying the value MUST NOT create an override. Following a saved configuration and using the model's own default SHALL remain distinguishable when their resolver meanings differ. Unknown values SHALL remain explicit, and generic Inherited or Reset to inherited wording SHALL be replaced. Cards and controls SHALL take radius, padding, height and colour from the existing appearance tokens, so compact and comfortable densities and light and dark themes apply everywhere without a second appearance system.

#### Scenario: Edit an inherited model setting

- **WHEN** a person opens a model's settings, Defaults, or the chat model menu
- **THEN** each setting shows its effective value and where it came from beside the control
- **AND** following or resetting to the named default clears only that layer's value while preserving the target's distinct resolver meaning.

#### Scenario: Narrow window and comfortable density

- **WHEN** the window is about 360 px wide or density is comfortable, in light or dark
- **THEN** rows stack the control under the label without horizontal scrolling
- **AND** section actions stay on one line.

### Requirement: API-043 - Show visual testing access and evidence in Chat

Agents setup SHALL own Browser and Windows tool selection, including grouped and individual choices. Settings SHALL own worker installation and connection configuration and remain usable before a model is selected. Browser SHALL own live session status, recovery and takeover. Chat access SHALL own Windows Off, Selected window and All windows grant controls; target selection and broad access SHALL remain explicit and revocable. Neither `+` nor the Chat agent dropdown SHALL expose tool toggles. A selected capability whose worker or grant is unavailable SHALL show a concise corrective action without claiming readiness. Chat SHALL show retained capture thumbnails and Open actions with source and observation time; Library SHALL expose those same authorized records. Text-only or unverified vision SHALL report pixel-inspection limits while preserving authorized structural browser/accessibility inspection. Screenshot reading SHALL remain distinct from attached-image vision capability.

#### Scenario: Capture is inspectable
- **WHEN** an agent captures a permitted page or window
- **THEN** Chat shows the capture, its target and time, and the same retained item can be opened in Library without a second media store.

#### Scenario: Windows scope changes
- **WHEN** a person changes a conversation from All windows to Selected window
- **THEN** the shown effective access narrows immediately and subsequent calls cannot use the former broad grant.

#### Scenario: Worker installation without a model

- **WHEN** no model is selected and the optional Browser worker is absent
- **THEN** Settings offers installation and truthful availability without creating a chat, enabling an agent tool or granting access.

### Requirement: API-036 - Keep helper work and capability readiness visible

Named helper progress SHALL appear in an expandable side rail, with the parent answer in the main conversation. Approvals and typed questions SHALL remain actionable from the conversation. Chat SHALL show whether each enabled capability is ready, needs a live grant, is unavailable or is known incompatible before dispatch. A selected-window capability SHALL require a current window choice and All windows SHALL require that conversation's live grant. A missing grant SHALL offer regrant instead of dispatching a turn that predictably fails with an access conflict. Unfinished Lab and Workflows SHALL be absent from the primary navigation while their existing routes, records and Attention recovery remain reachable.

#### Scenario: Reopen a chat after window grant expires
- **WHEN** a chat with Windows control enabled is reopened after its live grant is gone
- **THEN** Chat shows the missing grant and a route to grant it before a Windows-capable turn can start.

#### Scenario: Helper activity is separate
- **WHEN** a named helper works and returns a result
- **THEN** its activity is expandable in the rail while the parent's final answer remains in the conversation.

### Requirement: API-044 - Keep Chat readiness advisory and current

Chat readiness previews SHALL evaluate the candidate without loading weights, changing saved setup, or granting access. Invalid unsupported override values SHALL return a structured client error rather than HTTP 500. Readiness results SHALL belong to the selected conversation, candidate setup and run lifecycle that requested them; an obsolete active-turn result MUST NOT block a completed turn. An explicitly queued turn SHALL use durable backend queue admission while a turn is live. A pending or unverified preview, or a selected model that can load on Send, MUST NOT prevent dispatch to the authoritative backend admission path. Known current capability or compatibility blockers SHALL remain visible with their recovery action. Opening a saved conversation SHALL display its fetched content while live observation and setup details settle; passive previews SHALL NOT fan out across every closed-picker model choice.

#### Scenario: Preview input mismatch

- **WHEN** a candidate contains nullable inherited fields or an unsupported non-null field
- **THEN** supported explicit clears retain their meaning and unsupported input receives a client error without changing a model, chat or configuration.

#### Scenario: Turn finishes after an active preview

- **WHEN** an active-turn preview completes after the selected turn has become terminal or the selected chat has changed
- **THEN** its active warning is ignored and Send becomes available subject to current setup blockers.

#### Scenario: Queue during an active turn

- **WHEN** a person queues a draft during a live turn
- **THEN** active-turn readiness does not block durable queue admission and the active run continues.

#### Scenario: Direct submission is awaiting admission

- **WHEN** a submitted message has not yet been accepted as a live run
- **THEN** Chat shows it as starting, retains any next draft, and does not offer Queue until the run identity is confirmed.

#### Scenario: Live update is delayed after admission

- **WHEN** the backend accepts a direct submission but its live update is delayed
- **THEN** Chat reconciles that exact saved input and run without repeating the submission or losing the next draft.

#### Scenario: Queue admission races terminal completion

- **WHEN** Queue is clicked behind a known run and that run finishes before the queue request is admitted
- **THEN** the request identifies that predecessor, the backend retains the queued turn, and its terminal coordinator advances or pauses the queue according to the run result
- **AND** a changed predecessor is rejected without saving the queued draft as a different turn
- **AND** an ordinary Queue request made while idle still waits for an explicit Resume.

#### Scenario: Cold selected model on Send

- **WHEN** a selected installed configuration is unloaded and its preview reports that loading is required
- **THEN** Send can initiate the existing authoritative loading and admission path without first warming the model through a passive preview.

#### Scenario: Open a saved conversation

- **WHEN** a saved chat is fetched while its live observation and setup details are still resolving
- **THEN** its saved transcript appears with a truthful connecting state, and late results from an earlier selection cannot replace it.

#### Scenario: Interaction registration fails after a saved chat appears

- **WHEN** the saved transcript is visible but its interaction thread cannot be registered
- **THEN** Chat keeps the transcript visible, disables Send, and offers a retry for that same chat
- **AND** Send becomes available only after a successful retry binds the conversation to its interaction thread.

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

### Requirement: API-046 - Keep uninterrupted Chat chronological and stable

Chat SHALL retain chronological turn, response and tool placement while the same conversation remains open across successive replies. Every call and result SHALL have one visible location owned by its originating turn, including when different runs reuse a call identifier. Retained activity MUST NOT become current activity merely because it is absent from the newest turn. Intermediate assistant responses and tools SHALL remain ordered before the final answer for that turn. Refreshing SHALL produce equivalent visible chronology and content, not repair an incorrect live order.

Historical row identity, disclosure state, readable content and text selection SHALL survive asynchronous run-detail loading and admission of later replies. Queued-run handoffs SHALL keep verified history visible continuously. New output SHALL grow below its originating user message; run or measurement metadata changes MUST NOT remount or collapse previous output. The transcript SHALL follow latest output when already at the bottom and preserve manual reading position when scrolled away.

The interaction boundary SHALL attribute native tool activity to its actual run, originating input and namespace before displaying it. Partial-response reconstruction SHALL reset at run boundaries while preserving cursor/snapshot consistency. Internal bookkeeping MUST NOT leak into public output or become execution authority.

#### Scenario: Successive replies without reopening

- **WHEN** three or more replies with intermediate responses and tool calls complete in one continuously open conversation
- **THEN** the visible rows remain chronological, every scoped tool appears once, and earlier turns remain unchanged as the newest turn grows
- **AND** refreshing yields the same visible content and order.

#### Scenario: Delayed metadata and queued handoff

- **WHEN** a later reply is admitted before its stream catches up and historical details are loading
- **THEN** verified history stays visible, existing disclosures and rows retain identity, and active controls target only the admitted owned run.

#### Scenario: Tool identity reused after cancellation

- **WHEN** a stopped turn retains partial tool activity and a later run emits a call with the same identifier before its assistant message arrives
- **THEN** each call stays under its own input, the later call does not inherit the older result, and live/replayed output stays equivalent.

#### Scenario: Read earlier output during another reply

- **WHEN** the person scrolls away or selects earlier text while another reply streams
- **THEN** new output and metadata leave that reading position and selection in place
- **AND** returning to the bottom resumes following the newest line.

### Requirement: API-047 - Explain model-call latency and cache reuse

Chat measurement details SHALL expose available prefill duration and first-output delay alongside cached and newly processed input counts, distinguishing them from decoding speed. A bounded call history SHALL retain request identity, purpose and completion status across model/tool boundaries and reopened runs. Measurement history SHALL update at call boundaries without copying or re-rendering the full transcript on every token. Unavailable measurements SHALL be labelled rather than invented.

#### Scenario: Inspect a completed tool continuation
- **WHEN** the next model request starts after a tool and resets current measurements
- **THEN** the previous call's cache and timing evidence remains inspectable and cannot be confused with the current call.

#### Scenario: Timing is unsupported
- **WHEN** an endpoint supplies no valid prefill measurement
- **THEN** Chat identifies prefill as unavailable while preserving whatever usage and generation measurements were actually supplied.

### Requirement: API-048 - Watch and control Chrome from the Chat rail

Chat SHALL provide a Browser rail page showing the selected conversation's live Chrome page, address, tabs, navigation, actual resolution, lifecycle and takeover controls. Browser activity SHALL update a compact indicator and MUST NOT automatically open the dock. A person selecting Browser SHALL connect the viewer to that chat's current owned session. Closing the rail SHALL stop live viewing without closing the session. Frames SHALL remain bounded and temporary while explicit captures use the retained Library. Typed controls SHALL require backend-validated conversation/session/page identity and current control ownership. External page content MUST NOT acquire desktop/backend credentials. Disabled or unsupported browser features SHALL explain their corrective action.

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

#### Scenario: Start browsing with a closed dock

- **WHEN** the agent opens a browser page while the person is reading with the dock closed
- **THEN** the page/session remains observable through its indicator and the dock does not open or move the person's reading position.

### Requirement: Capture-free routine run observation
Existing run list/detail routes SHALL accept `view=operational` and return typed capture-free operational responses under existing authentication and identity rules. The desktop SHALL use this view for routine observation. Existing diagnostic reads SHALL remain available. No observation SHALL create or dispatch execution.

#### Scenario: Operational detail and list
- **WHEN** routine desktop observation requests operational run detail or lists
- **THEN** captures SHALL be absent while lifecycle, hierarchy, configuration, approvals and recovery information remain truthful.

### Requirement: Long tool runs retain timely native output
Plan and Work SHALL retain their current permissions and native ordering, actual tool results, cancellation, approvals and uncertain-effect recovery. A continuously mounted Chat SHALL keep successive turns, helper/tool transitions and refresh-equivalent content responsive with Browser viewing and attention polling active. Status SHALL reflect the actual phase rather than disguise delivery delay.

#### Scenario: Sustained real-model workload
- **WHEN** three uninterrupted real-model turns make at least 30 combined Browser/filesystem calls while the Browser rail and attention polling remain active, plus a Plan run uses repeated investigation tools
- **THEN** no growing event/render backlog SHALL develop
- **AND** model-stream completion SHALL follow provider completion within 2 seconds and local status/event delivery SHALL have p95 below 250 ms.

### Requirement: API-049 - Prepare context and skills through shared composer pickers

The composer `+` SHALL offer attachments, Add context, Skills & actions and Plan without tools or connection setup. Add context and `@` SHALL open the same searchable authorized file/document/memory reference picker. Skills & actions and `/` SHALL open the same searchable saved-skill/task-shortcut picker. Selection SHALL create removable named draft chips and MUST NOT execute until submission. The registered task shortcuts SHALL include Summarize, Explain and Review as versioned inert prompts. They SHALL use only already enabled tools when those tools are needed and SHALL NOT directly call a tool, enable a tool, change an agent or grant authority. Admission SHALL copy the selected shortcut version and prompt into that input's immutable snapshot, so a later catalogue edit cannot change accepted work or its identical retry. Slash additions SHALL apply only to the next accepted message; saved agent skills remain available separately. Failed admission SHALL retain the draft and its selections; accepted inputs SHALL retain their exact selected versions and attachment identities.

#### Scenario: Choose a skill without running it
- **WHEN** a person chooses a skill through `/` or the `+` picker
- **THEN** it appears as a removable draft chip, no work runs, and the next accepted message freezes it without attaching it to later messages automatically.

#### Scenario: Keyboard suggestion selection
- **WHEN** a suggestion is highlighted and Enter is pressed
- **THEN** Enter selects the suggestion instead of sending or queueing; Escape dismisses the picker, and ordinary Enter, Shift+Enter and IME behaviour remain available after it closes.

#### Scenario: Shortcut with tools disabled
- **WHEN** a person chooses Review while the selected agent has no tools enabled
- **THEN** the prompt remains a removable draft selection and the accepted input retains the empty tool selection
- **AND** choosing or submitting the shortcut cannot directly call or enable a tool.

#### Scenario: Shortcut catalogue changes after admission

- **WHEN** a registered shortcut receives a changed prompt or version after an input is accepted
- **THEN** the accepted input and its identical retry retain the original copied prompt and version, while a later new input can use the newly registered version.

### Requirement: API-050 - Keep routine interface prose minimal

Chat, Models, Agents, Knowledge and Settings SHALL use short labels and compact indicators for intuitive controls. Supporting explanation SHALL be available on hover, keyboard focus or expansion rather than repeated standing paragraphs. Preparing a future message SHALL use at most a concise changed-state indicator when it differs from current work; routine controls SHALL NOT require repeated 'for next message' prose. Accessible names, actual errors, permission/effect disclosures and meaningful unavailable or estimated states SHALL remain available.

#### Scenario: Routine and exceptional setup states
- **WHEN** a person changes a next-message setting during work and then encounters a missing dependency
- **THEN** the routine change uses a compact indicator, while the missing dependency shows its specific corrective action with further detail available on demand.

### Requirement: API-051 - Show applied values and specific default targets

Shared controls throughout the desktop SHALL make known backend-resolved values the main readout and their source secondary. Default-following options SHALL include the resolved value, and numeric controls and sliders SHALL visibly represent it without manufacturing a requested override. Reset actions SHALL name their verified target and expose its value on hover or focus. Following a saved configuration and selecting the underlying model default SHALL remain distinct when they have different semantics. Unknown, unsupported and unbounded values SHALL use truthful labels; Automatic SHALL describe only an actual automatic engine mode. Redundant inherited badges and prose SHALL be removed while internal default-following semantics remain unchanged.

#### Scenario: A following control updates with its default
- **WHEN** a default-following control is displayed and its saved default changes
- **THEN** the control reflects the new resolved value without having pinned the earlier value
- **AND** an explicitly selected value remains explicit.

#### Scenario: Different reset targets
- **WHEN** a saved configuration default differs from the model template default
- **THEN** both available actions name their target and its known value, and each preserves its existing resolver meaning.

### Requirement: API-052 - Keep saved-record editing calm and recoverable

Models, Agents and Knowledge SHALL use searchable catalogue/detail editing, with an accessible selector when a side catalogue cannot fit. Shared headings, fields, actions, disclosures and states SHALL follow existing theme, spacing and density controls. Navigation within the open app SHALL preserve unsaved drafts; restoring saved values SHALL clear dirty state. Agent rows SHALL identify role, model assignment and actionable missing dependencies. Helper selections SHALL remain visible and removable when missing. Creation Review SHALL summarize the entire draft, including helpers and requirements, and Back or failed Save SHALL retain it. Knowledge creation SHALL occupy the editor pane, preserve lossless Guided/Source/resources/scopes, and distinguish display names from native skill identity. Policy/capture controls SHALL be compact and independent failures SHALL not block editing. Agent/browser/record actions SHALL use recognizable consistent icons.

#### Scenario: Navigate with an unsaved draft
- **WHEN** a person edits a saved record, visits Chat, then returns to its editor
- **THEN** the unsaved draft remains available, and reverting it to saved values clears its changed indicator.

#### Scenario: Repair a deleted helper
- **WHEN** a saved agent selects a helper that is no longer available
- **THEN** that selection remains visible with a corrective Remove action, and creation Review includes selected helpers and their requirements.

### Requirement: API-053 - Keep file browsing scoped and reusable in Chat

Library SHALL retain its table/detail preview, save-copy, deletion and selection-dependent bulk controls. All files, Project and Chat filters SHALL work using existing retained-file authority and recognizable source names; unavailable sources and previews SHALL be explicit. Image detail previews SHALL use available space. Library SHALL NOT offer Use in Chat or global reuse handoff; Chat attachment/context/Files reuse SHALL remain available. Chat Files SHALL retain authorized uploads and reused copies after responses, provide concise provenance/capture time and loading/empty states, and preserve response-specific filters beside their answers. Pickers SHALL keep highlighted choices visible, restore focus, handle filtered reopening and no matches. Broken agents SHALL offer Review in Agents. Access popovers SHALL use the agreed compact presentation.

#### Scenario: Scope the retained catalogue
- **WHEN** a person selects a Project or Chat Library filter
- **THEN** the query uses that one selected scope, origin labels remain recognizable, and selected records retain preview/save/delete authority.

#### Scenario: Files after a response
- **WHEN** an uploaded or reused file has no run owner and a response finishes
- **THEN** it remains available in Chat Files while individual answer sections retain their own response filters.

### Requirement: Chat permission controls explain remembered approvals

The Chat access menu SHALL keep its help icon inline with a named row and explain future-message access and Plan restrictions concisely. Its Saved permissions shortcut SHALL appear only after existing remembered approvals are confirmed, with their presence refreshed on opening. Settings SHALL always offer permission management and explain creating remembered approvals from an Ask-mode action card, their exact action/input/project scope, and revocation. Empty-state copy SHALL NOT imply that Full access pauses for approval or creates saved permissions.

#### Scenario: No remembered approvals

- **WHEN** no remembered approvals exist and the person opens Chat access
- **THEN** the empty shortcut is absent and the help icon shares the Access heading's row
- **AND** Settings explains Allow for this session and Always allow, without promising pauses under Full access.

#### Scenario: Permissions are saved or revoked

- **WHEN** a remembered approval is created or the last one is revoked
- **THEN** reopening Chat access reflects the current presence of saved permissions.

### Requirement: Chat model choices show a compact hierarchy

Chat SHALL present each installed model with a readable model name and visible quantization, with named configurations directly available as indented secondary choices. Full weight filenames SHALL be available through search and tooltips rather than repeated beside configuration names. Small expand arrows SHALL be absent. Distinct installed choices SHALL remain distinguishable, and selection, readiness, compatibility, loading and keyboard navigation SHALL retain their existing guarantees.

#### Scenario: Choosing a named configuration

- **WHEN** Chat's model picker opens for a model with several configurations
- **THEN** the model name and quantization head a group of immediately available named settings
- **AND** choosing a setting uses its exact saved configuration without displaying a repeated weight filename.

#### Scenario: Searching by the original filename

- **WHEN** the person searches for an installed model's original weight filename
- **THEN** the correct compact model group remains discoverable and selectable.

### Requirement: API-054 - Keep unified controls in their owning surface

Models SHALL own saved model setups, response recipes/budgets/sampling, memory and hardware controls. Its primary Save action SHALL record settings without starting/reloading a model or navigating to Chat. Model load/unload SHALL be separate lifecycle actions. Naming/copy actions SHALL be secondary. Agents SHALL own agent settings and save without a cross-page launch action. Settings SHALL own shared engine connections/residency. Lab and Workflows SHALL reuse saved setups and display executed settings with their task-specific controls.

Chat SHALL expose model/setup selection and chat-local Thinking and context-size adjustments. Thinking SHALL apply to the next accepted input without changing the saved setup, explicit saved samplers or already accepted work. Context changes SHALL show an impact preview and require a deliberate reload when idle; active work SHALL stage the next submission through safe admission. Detailed budget/sampling/hardware editing SHALL stay in Models. No Chat promotion action SHALL change model defaults.

#### Scenario: Save stays in Models
- **WHEN** a model setup is edited and saved
- **THEN** its revision and response/loading choices are saved without loading, reloading or navigation.

#### Scenario: Local chat tuning
- **WHEN** Thinking or context is changed in one chat
- **THEN** that chat retains the local choice, other chats and saved setups remain unchanged, and already accepted work retains its snapshot.

#### Scenario: Busy context choice
- **WHEN** a context change is made during active work
- **THEN** the candidate is staged for the next submission and no active model call is interrupted.

#### Scenario: Compact accessible controls
- **WHEN** controls are used in either theme, a narrow container or scaled Windows layout
- **THEN** their labels, values, source/timing, focus and actionable errors remain readable; slider values permit exact keyboard input and drafts survive closing/navigation.
