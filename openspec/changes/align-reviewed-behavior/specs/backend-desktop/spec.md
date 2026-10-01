# Spec Delta

## MODIFIED Requirements

### Requirement: API-002 - Edit in the desktop, execute in the backend

Electron/React SHALL present controls, previews, context, evidence, memory editing, and tool panels. Retry and Edit SHALL sit on the person's own sent messages. Regenerate and Branch MUST be absent. React Flow SHALL edit workflow definitions. Backend validation and LangGraph SHALL execute workflows. The visual graph MUST NOT be executable authority by itself.

#### Scenario: Invalid definition outside editor

- WHEN an invalid definition is submitted outside the visual editor
- THEN backend validation MUST reject it
- AND successful screen interactions MUST correspond to real backend actions or be explicitly labelled as mock.

### Requirement: API-017 - Expose compact effective model controls and measurements

Opening a conversation SHALL restore that conversation's explicit Ask or Full access choice. An application preference SHALL seed new conversations and SHALL default to Ask on a fresh installation; project and agent definitions SHALL NOT override access. A chat's explicit choice SHALL survive unrelated preference changes and MUST NOT leak from the previously viewed chat. Access labels SHALL show Ask or Full access in full; supporting policy detail SHALL be available on demand without standing explanatory prose. Descriptions and model instructions SHALL reflect saved permission grants and the actual selected mode, while explicit questions and disabled-tool boundaries remain enforced.

The composer SHALL contain, in order, `+`, access, Plan only while enabled as a removable pill, the one model menu, the agent selector, compact context fill and generation speed in tok/s, and one combined Send/Stop control. A microphone SHALL NOT be shown before speech is delivered. Agent selection SHALL follow AGT-024, including its explicitly assigned-model exception. When an agent assigns the model, the menu SHALL say the model is assigned and that it is changed in Agents. Grouped and individual tool choices SHALL be managed only in Agents setup, not in the agent dropdown or `+`. Access SHALL select Ask or Full access for later messages in that chat. It SHALL NOT enable tools and SHALL NOT own a Windows Off, Selected window, or All windows menu. Changes prepare future submissions without rewriting running or already queued work. Unsupported, overridden or unverified reasoning controls SHALL be labelled truthfully; hiding returned thinking MUST NOT be represented as disabling model reasoning.

Chat and the one-task Workflows page SHALL use that one menu. The bounded searchable menu SHALL show one row per model, with the model name and quantization, and SHALL list saved setups under the model only when there are several. Expansion SHALL NOT load a model. Ready, loading/waiting, attention and idle dots SHALL reflect the exact configuration's observed state, with equivalent accessible hover/focus labels. Saved configurations alone SHALL NOT imply residency. The same menu SHALL include the model's own Thinking levels and a context token slider. The slider SHALL show the token count and a short memory figure. The explanation that a context change reloads the model SHALL be on hover or keyboard focus. There SHALL be no separate Apply or Stage button and no separate tuning icon. The menu MUST NOT use standing "this chat" or "this task" prose. Thinking SHALL apply to the next message, SHALL NOT reload the model, and SHALL NOT change the saved setup. When the conversation or one-task run is idle and the context choice requires a reload, the desktop SHALL post that conversation's or task's startup overrides to `POST /v1/deployments/managed` and the model SHALL reload. That change MUST NOT post `POST /v1/deployments/{id}/reload`. During active work the context choice SHALL wait for the next message and SHALL NOT start a model. Lab SHALL keep its own controls. Applied choices SHALL be remembered separately per model within that conversation or task; first use starts with saved model defaults and returning restores those choices. Sampling, GPU layers, the saved setup, permanent defaults, response-length controls and thinking-token-limit controls SHALL remain in Models. A context change SHALL preserve the draft, attachments, history and reading position. Active-work changes SHALL wait for the next message and SHALL NOT alter the running turn, as API-028 requires. Chat send SHALL keep the label Send and SHALL load an unloaded installed model through the existing manager and admission path rather than a second desktop start.

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

#### Scenario: The model menu is one control

- **WHEN** a person opens the model menu in Chat
- **THEN** that one menu shows the model name and quantization, saved setups under the model when there are several, the model's own Thinking levels, and a context token slider with the token count and a short memory figure
- **AND** there is no tuning icon, no Apply or Stage button, and no response-length or thinking-token-limit control.

#### Scenario: Idle context reloads without a button

- **WHEN** the conversation is idle and the person changes the context slider to a value that requires a reload
- **THEN** the model reloads by posting that conversation's startup overrides to `POST /v1/deployments/managed`
- **AND** the reload explanation is on hover or focus, and the change does not post `POST /v1/deployments/{id}/reload`.

#### Scenario: Busy context waits for the next message

- **WHEN** work is in progress and the person changes the context slider
- **THEN** the choice waits for the next message and does not reload during the current work
- **AND** the menu does not show a Stage button or standing "this chat" or "this task" prose.

#### Scenario: Thinking does not reload or change the saved setup

- **WHEN** the person chooses one of the model's Thinking levels
- **THEN** that level applies to the next message, the saved setup is unchanged, and the model does not reload.

#### Scenario: An assigned model points to Agents

- **WHEN** the selected agent assigns the model
- **THEN** the menu says the model is assigned and that it is changed in Agents.

#### Scenario: The one-task page uses the same menu

- **WHEN** a person opens the model menu on the one-task Workflows page
- **THEN** it is the same menu as Chat
- **AND** Lab keeps its own controls.

#### Scenario: Access does not choose a window

- **WHEN** a person opens the access control
- **THEN** it offers Ask or Full access
- **AND** it does not offer Windows Off, Selected window, or All windows.

#### Scenario: Composer order before speech exists

- **WHEN** speech has not been delivered and Plan is enabled
- **THEN** the composer shows, in order, plus, access, the removable Plan pill, the one model menu, the agent selector, compact context fill and generation speed in tok/s, and one Send or Stop control
- **AND** it does not show a microphone.

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

- **WHEN** the person sets Thinking or context on model A, uses model B, then returns to A
- **THEN** A's choices in that conversation are restored without changing either model's saved setup or another conversation's choices.

#### Scenario: Setup stays off the transcript
- **WHEN** a person opens the one model menu
- **THEN** Thinking levels and the context slider are in that menu, the transcript is unchanged, and there is no separate tuning editor and no Apply or Stage button.

#### Scenario: Idle chat settings use managed start
- **WHEN** the chat is idle and the person changes the context slider to a value that requires a reload
- **THEN** the desktop posts that chat's startup overrides to `POST /v1/deployments/managed`
- **AND** the change does not post `POST /v1/deployments/{id}/reload` and there is no Apply this chat's settings button.

### Requirement: API-020 - Separate technical verification from human UX acceptance

Each affected change SHALL demonstrate its end-to-end user journey in the built Windows application and record technical verification separately from Dave's UX acceptance in its existing design/PR. Reviews SHALL cover full and half-screen windows, actual Windows display scaling, keyboard navigation, long conversation/result content and at least one failure/recovery state. Screenshots alone MUST NOT count as interaction verification. Required technical/live checks SHALL remain required; UX acceptance SHALL remain pending until Dave accepts the built experience or explicitly defers review, with deferral recorded as deferred rather than accepted.

Chat layout changes SHALL include an early review after the basic arrangement is exercisable and before the remaining controls accumulate, including the existing Models-to-Chat journey. Everyday workspace, Lab and Workflows changes SHALL include major surface reviews; delegation/approval and media changes SHALL include focused reviews of those paths. The Workflows drawing canvas SHALL require an approved detailed layout before that screen is built. The one-task Workflows form SHALL remain until that canvas exists. Lab is delivered. Lab MUST NOT require an approved layout before use, and this specification MUST NOT call Lab unbuilt or block Lab because a layout is pending. Dave's personal acceptance of Lab MAY remain a process note and MUST NOT be recorded as Lab being unbuilt. Specification approval MUST NOT be treated as visual acceptance of the built product.

#### Scenario: Technical checks pass before user review

- **WHEN** automated checks and agent-driven Windows interaction pass but Dave has not reviewed or explicitly deferred the experience
- **THEN** technical results are recorded as such while UX acceptance remains pending.

#### Scenario: Explicitly deferred review

- **WHEN** Dave explicitly defers a milestone's UX review
- **THEN** its existing design/PR records the deferral separately from technical evidence and does not claim UX acceptance or waive required live checks.

#### Scenario: Lab is not held for a layout

- **WHEN** a Lab change is implemented
- **THEN** it is not blocked by a pending layout approval
- **AND** the specification does not call Lab unbuilt.

#### Scenario: The canvas layout gate remains

- **WHEN** the one-task Workflows form is the current screen and the drawing canvas has no approved layout
- **THEN** the form remains
- **AND** the canvas screen is not built.

### Requirement: API-034 - Finish the page the person is looking at

Every existing destination SHALL retain and repair its current usable functions. Agents remains the named list. Lab is the delivered destination. Its first view SHALL be Performance, then Memory, then Challenges. Lab MUST NOT be called the future suite or Measurements. The visual Workflows canvas remains separately specified work and MUST NOT be represented as completed by polishing the current one-task form.

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

#### Scenario: Lab is the delivered destination

- **WHEN** a person opens Lab
- **THEN** the first view is Performance, then Memory, then Challenges
- **AND** Lab is not presented as a future suite or as Measurements.

### Requirement: API-036 - Keep helper work and capability readiness visible

Named helper progress SHALL appear in an expandable side rail, with the parent answer in the main conversation. Approvals and typed questions SHALL remain actionable from the conversation. Chat SHALL show whether each enabled capability is ready, needs a live grant, is unavailable or is known incompatible. A missing grant SHALL NOT block ordinary chat send. Lab and Workflows SHALL both be in the primary sidebar. Their existing routes, records and Attention recovery remain reachable.

#### Scenario: A missing grant does not block ordinary send

- **WHEN** a chat is reopened after a Windows grant is gone and the person sends an ordinary message
- **THEN** Chat can show that the grant is missing
- **AND** that absence does not block the send.

#### Scenario: Reopen a chat after window grant expires
- **WHEN** a chat with One window is reopened and no window is picked, and the person sends an ordinary message
- **THEN** the message still sends
- **AND** Windows checks run when a Windows tool is about to be used.

#### Scenario: Helper activity is separate

- **WHEN** a named helper works and returns a result
- **THEN** its activity is expandable in the rail while the parent's final answer remains in the conversation.

#### Scenario: Lab and Workflows stay in the sidebar

- **WHEN** a person looks at the primary sidebar
- **THEN** both Lab and Workflows are present.

### Requirement: API-037 - Say when a saved permission let the tool proceed

When Ask proceeds because of a saved permission, that call's activity line SHALL say a saved permission was used. The line names the grant in plain words. The full grant remains available on the further disclosure and in Settings, where it can still be revoked. The backend captures the exact matched grant when authorizing the call; later edits or revocation do not rewrite that recorded evidence. Historical records without a captured grant identity show only proven saved-permission use, never an invented identity. Saved grants remain explicit exceptions to the access rules, are attributed by the backend, and MUST NOT override Plan mode or enable a disabled tool.

#### Scenario: Ask uses a saved grant

- **WHEN** Ask would pause a shell command and a saved grant lets that command proceed
- **THEN** the activity line says a saved permission was used
- **AND** the person can still revoke that grant in Settings.

### Requirement: API-039 - Show settled execution while saving project state

After graph execution settles, the app MAY show that execution has settled. The app MUST NOT copy the project. It MUST NOT show “Saving project state” or any project-copy progress. The short project outline is not a snapshot and is not a progress state. Exactly one terminal outcome SHALL be published for the run. The app MUST NOT enter a project-capture saving phase and MUST NOT hold Stop for a project copy.

#### Scenario: Settled execution is not a project copy

- **WHEN** graph execution settles for a project-bound run
- **THEN** settled execution can be shown
- **AND** the app does not copy the project, does not show “Saving project state” or copy progress, and the short project outline is not a snapshot or a progress state.

#### Scenario: Stop after execution settled
- **WHEN** graph execution has settled and the person presses Stop
- **THEN** Stop is not held for a project copy and the settled outcome stays
- **AND** the app does not show “Saving project state”.

### Requirement: API-043 - Show visual testing access and evidence in Chat

Agents setup SHALL own Browser and Windows tool selection, including grouped and individual choices. One window SHALL be chosen on the agent and confirmed in the chat when the agent tries to use it. Chat SHALL NOT offer Windows Off, Selected window, or All windows. Chat MUST NOT require a fresh Windows grant before sending. Settings SHALL own worker installation and connection configuration and remain usable before a model is selected. Browser SHALL own live session status, recovery and takeover. Neither `+` nor the Chat agent dropdown SHALL expose tool toggles. A selected capability whose worker or grant is unavailable SHALL show a concise corrective action without claiming readiness. Chat SHALL show retained capture thumbnails and Open actions with source and observation time; Library SHALL expose those same authorized records. Text-only or unverified vision SHALL report pixel-inspection limits while preserving authorized structural browser/accessibility inspection. Screenshot reading SHALL remain distinct from attached-image vision capability.

#### Scenario: Capture is inspectable

- **WHEN** an agent captures a permitted page or window
- **THEN** Chat shows the capture, its target and time, and the same retained item can be opened in Library without a second media store.

#### Scenario: One window is confirmed in chat

- **WHEN** an agent with one chosen window tries to use that window
- **THEN** Chat confirms that window
- **AND** Chat does not offer Off, Selected window, or All windows, and does not require a fresh Windows grant before an ordinary send.

#### Scenario: Windows scope changes
- **WHEN** a person looks for All windows or a chat Windows menu
- **THEN** Chat does not offer Off, Selected window, or All windows
- **AND** One window is chosen on the agent and confirmed in the chat when the agent tries to use it.

#### Scenario: Worker installation without a model

- **WHEN** no model is selected and the optional Browser worker is absent
- **THEN** Settings offers installation and truthful availability without creating a chat, enabling an agent tool or granting access.

### Requirement: API-050 - Keep routine interface prose minimal

Every everyday screen in the app SHALL show a short label and a value. Explanation SHALL be on hover or keyboard focus. A disabled control's reason SHALL be on hover or focus. An error SHALL be one short line. A non-local address SHALL show a short status such as "Not local". This SHALL apply to the whole app, including an empty permissions state. Everyday screens MUST NOT show instructional paragraphs. Model-facing notices that the agent reads MAY stay. Memory rings stay quiet: the percentage is the value, and they SHALL have no tooltip.

Preparing a future message SHALL use at most a concise changed-state indicator when it differs from current work; routine controls SHALL NOT require repeated "for next message" prose. Accessible names SHALL remain available. A permission or effect that the person must see before choosing SHALL stay on that choice and MUST NOT become an instructional paragraph on an everyday screen. Meaningful unavailable or estimated states SHALL remain available, with detail that is not required to act on hover or focus.

#### Scenario: Everyday screens stay short

- **WHEN** a person looks at any everyday screen, including an empty permissions state
- **THEN** each control shows a short label and a value, with explanation on hover or focus
- **AND** a disabled control's reason is on hover or focus, an error is one short line, and the screen has no instructional paragraph.

#### Scenario: Routine and exceptional setup states

- **WHEN** a person changes a next-message setting during work and then encounters a missing dependency
- **THEN** the routine change uses a compact indicator, while the missing dependency shows its specific corrective action with further detail on hover or focus.

#### Scenario: A model-facing notice may stay

- **WHEN** a notice is written for the agent to read
- **THEN** that notice may remain
- **AND** it is not used as an instructional paragraph on an everyday screen.

#### Scenario: Memory rings stay quiet

- **WHEN** the memory rings are visible
- **THEN** the percentage is the value
- **AND** the rings have no tooltip.

### Requirement: API-054 - Keep unified controls in their owning surface

Models SHALL own saved model setups, response recipes/budgets/sampling, GPU layers, memory and hardware controls. Its primary Save action SHALL record settings without starting/reloading a model or navigating to Chat. Model load/unload SHALL be separate lifecycle actions. Naming/copy actions SHALL be secondary. Agents SHALL own agent settings and save without a cross-page launch action. Settings SHALL own shared engine connections/residency. Lab SHALL keep its own controls and MAY display the settings a run used. The one-task Workflows page SHALL use the same one model menu as Chat and SHALL NOT add a second tuning control.

Chat and the one-task Workflows page SHALL use that one menu for the model, saved setups when there are several, the model's own Thinking levels, and the context token slider. Thinking SHALL apply to the next message without reloading, and without changing the saved setup, explicit saved samplers, or already accepted work. The slider SHALL show the token count and a short memory figure. When idle and a reload is required, context SHALL reload through `POST /v1/deployments/managed` and MUST NOT post `POST /v1/deployments/{id}/reload`. When work is busy, the context choice SHALL wait for the next message and SHALL NOT interrupt the active model call. There SHALL be no Apply this chat's settings button, no Stage button, and no separate tuning icon. The menu MUST NOT use standing "this chat" or "this task" prose. Sampling, GPU layers, and the saved setup SHALL stay on Models. No Chat promotion action SHALL change model defaults.

#### Scenario: Save stays in Models

- **WHEN** a model setup is edited and saved
- **THEN** its revision and response/loading choices are saved without loading, reloading or navigation.

#### Scenario: Local chat tuning

- **WHEN** Thinking or context is changed in one chat
- **THEN** that chat retains the local choice, other chats and saved setups remain unchanged, and already accepted work keeps the setup it started with.

#### Scenario: Busy context choice

- **WHEN** a context change is made during active work
- **THEN** the choice waits for the next message and no active model call is interrupted
- **AND** there is no Stage button.

#### Scenario: Idle context reloads through the one menu

- **WHEN** the chat is idle and the person changes context to a value that requires a reload
- **THEN** that change posts the startup overrides to managed start without an Apply this chat's settings button
- **AND** Chat and the one-task Workflows page share that menu, while Lab keeps its own controls.

#### Scenario: Idle context uses the chat's settings
- **WHEN** the chat is idle and the person changes context to a value that requires a reload
- **THEN** that change posts the startup overrides to managed start without an Apply this chat's settings button
- **AND** there is no separate Stage button.

#### Scenario: Compact accessible controls

- **WHEN** controls are used in either theme, a narrow container or scaled Windows layout
- **THEN** their labels, values, source/timing, focus and actionable errors remain readable; slider values permit exact keyboard input and drafts survive closing/navigation.

### Requirement: Chat model choices show a compact hierarchy

Chat and the one-task Workflows page SHALL use one menu. It SHALL show the model name and quantization, saved setups listed under the model when there are several, the model's own Thinking levels, and a context token slider. The slider SHALL show the token count and a short memory figure. Reload explanation SHALL be on hover or keyboard focus. Thinking SHALL apply to the next message, SHALL NOT reload, and SHALL NOT change the saved setup. When idle and a reload is required, context SHALL reload. When work is busy, context SHALL wait for the next message. There SHALL be no separate Apply or Stage button and no separate tuning icon. The menu MUST NOT use standing "this chat" or "this task" prose. Sampling, GPU layers, and the saved setup SHALL stay on Models. Lab SHALL keep its own controls. An agent-assigned model SHALL say the model is assigned and that it is changed in Agents. Full weight filenames SHALL be available through search and hover rather than repeated beside setup names. Small expand arrows SHALL be absent. Distinct installed choices SHALL remain distinguishable, and selection, readiness, compatibility, loading and keyboard navigation SHALL retain their existing guarantees. A known quantization token SHALL show even when a dot precedes it. An unknown name SHALL stay unknown. The menu MUST NOT requantize.

#### Scenario: Choosing a named configuration

- **WHEN** the model menu opens for a model with several saved setups
- **THEN** the model name and quantization head that group, and the setups are listed under the model
- **AND** the model's Thinking levels and the context token slider are in that same menu.

#### Scenario: Searching by the original filename

- **WHEN** the person searches for an installed model's original weight filename
- **THEN** the correct model remains discoverable and selectable
- **AND** the filename is not repeated beside each setup name.

#### Scenario: One saved setup is not listed as several

- **WHEN** a model has one saved setup
- **THEN** the menu shows the model name and quantization without a list of several setups under it.

#### Scenario: Quantization token after a dot

- **WHEN** the menu shows `Qwen3.5-0.8B.Q4_K_M.gguf`
- **THEN** the quantization shown is `Q4_K_M`
- **AND** an unknown name stays unknown and the menu does not requantize.

### Requirement: API-056 - Present deliberate scoped autonomy and reusable workflows

The desktop SHALL show the project-edit permission on its own screen. The screen SHALL show the project, the allowed edits, the excluded paths, and the words "Until revoked". `.git` SHALL always be excluded and MUST NOT be removed from that excluded list. Secret files SHALL start excluded, and the person SHALL be able to remove a secret file from that list. The permission MUST NOT use a timer. It SHALL accurately describe which edits it covers, and it MUST NOT cover `.git`. Settings SHALL permit inspecting and revoking this permission and existing exact-action approvals. An already pending approval SHALL keep its exact-action response choices.

Agents and Knowledge SHALL provide opt-in setup templates and bundled conditional runtime skills as drafts or installations using the existing editors, selections and versioning. Suggested Chat-owned modes, access, or window requirements SHALL remain visible guidance and SHALL NOT be silently granted by a template.

#### Scenario: Open the project-edit permission

- **WHEN** the person opens the project-edit permission
- **THEN** the screen shows the project, the allowed edits, the excluded paths, and "Until revoked"
- **AND** `.git` stays excluded, secret files start excluded and can be removed from that list, and no timer is shown.

#### Scenario: Approve scoped file changes
- **WHEN** the person creates the project-edit permission in Settings
- **THEN** a later matching edit uses it, an excluded path keeps its own approval, and Settings can revoke it
- **AND** an already pending approval keeps its exact-action response choices.

#### Scenario: Matching edits use the permission

- **WHEN** a project-edit permission is in force and a selected edit matches its allowed edits and is not excluded
- **THEN** that edit uses the permission
- **AND** an excluded path, including `.git`, keeps its own approval, and Settings can revoke the permission.

#### Scenario: Choose a template

- **WHEN** a person chooses a reusable agent template or installs a bundled skill
- **THEN** they can inspect its actual choices in existing authoring controls before using it, with current unrelated records preserved.

### Requirement: API-035 - Open a Settings section, and preview the real window

Settings SHALL remain directly reachable on the destination rail. Within it, the person SHALL be able to open Appearance, Notifications, Defaults, Connections, and Permissions directly. There SHALL be no Backup section. Appearance SHALL show compact basic controls and explicitly opened advanced customization, preserving every existing shared control, slider and typeable value, Apply, Cancel, and per-row Reset within bounded responsive columns. Help for Apply, Cancel, and Reset SHALL open on hover or keyboard focus. It MUST NOT be a standing paragraph above the controls.

The separate preview window SHALL show a small conversation of the draft: rail and chat list, a short transcript with one tool line and an unboxed answer, the compact composer, and one settings card. Spacing guides SHALL start off and remain available. Pointing at a control, or changing it, still marks the parts that control changes. The preview MUST NOT replace the open Settings page.

#### Scenario: Backup is reachable without the colour list

- **WHEN** a person opens Settings and chooses Permissions
- **THEN** permissions are shown
- **AND** the appearance controls are not required to scroll past first
- **AND** Backup is not a section.

#### Scenario: The sample looks like the conversation

- **WHEN** a person opens the appearance preview
- **THEN** the sample shows the rail and collapsible chat list, a short transcript, compact composer and settings card using the draft
- **AND** spacing guides are off until the person turns them on.

### Requirement: Chat permission controls explain remembered approvals

The Chat access menu SHALL keep its help icon inline with a named row and explain future-message access and Plan restrictions concisely. Its Saved permissions shortcut SHALL appear only after existing remembered approvals are confirmed, with their presence refreshed on opening. Settings SHALL always offer permission management and explain creating remembered approvals from an action card, their exact action, input, and project or starting-folder scope, and revocation. Empty-state copy SHALL NOT imply that Full access pauses for every later command, and SHALL NOT imply that Full access creates saved permissions. The first This-computer card is not empty-state copy and does not by itself create a saved permission. The first This-computer confirmation in a chat SHALL still show one card. Empty-state copy MUST NOT be an instructional paragraph.

#### Scenario: No remembered approvals

- **WHEN** no remembered approvals exist and the person opens Chat access
- **THEN** the empty shortcut is absent and the help icon shares the Access heading's row
- **AND** Settings explains Allow for this session and Always allow, without promising a pause for every later Full access command and without implying that Full access creates saved permissions
- **AND** the first This-computer card is not that empty-state copy and does not by itself create a saved permission.

#### Scenario: Permissions are saved or revoked

- **WHEN** a remembered approval is created or the last one is revoked
- **THEN** reopening Chat access reflects the current presence of saved permissions.

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

#### Scenario: Submission accepted into a busy project's queue

- **WHEN** Send is durably accepted in a second chat while another task is using the same project folder
- **THEN** the second chat SHALL NOT be queued behind a folder owner, and the folder SHALL NOT be reported busy
- **AND** acknowledgement and desktop reconciliation SHALL identify that exact accepted input without inventing a run or associating a previous completed run
- **AND** recovery after a lost acknowledgement SHALL recognise that same accepted identity, clear only its submitted draft revision, and observe its later execution without submitting it again.

### Requirement: API-016 - Present one conversation-led desktop shell

The desktop SHALL provide a compact persistent icon rail on every page and a separate independently collapsible and resizable project/chat list in Chat. Search and Notifications SHALL be small icons at the top of the rail; Settings SHALL remain directly reachable on it. Icon names SHALL be available on hover and keyboard focus, with visible focus and usable targets. The chat list SHALL NOT duplicate a permanent search box or notification button. Destinations SHALL stay visible without their own scrollbar. The separate chat list SHALL show collapsible named project folders containing only their permanently scoped conversations, then chats with no project labelled as having no project. The no-project group SHALL remain in that list when it is empty. A project row SHALL start a new chat in that project, and a separate control SHALL create a project. Right-clicking a project SHALL offer editing it, archiving its chats, and removing it from the sidebar without deleting its folder. New chat, cross-area retained-history search, rename, archive and reopen SHALL remain available through the rail and chat list. The conversation header SHALL show its project or non-project identity; choosing a different area SHALL open or create another conversation rather than move or detach the current one. Removed-project history SHALL retain its identity.

The main New chat button SHALL start a conversation with no project, regardless of the previously selected chat or project. Each project's new-chat control SHALL start a conversation in that project, including when the project has no existing chats. Both paths SHALL preserve the selected main model and save the previous draft before leaving it.

Adding a project SHALL ask for a name and one existing folder. It SHALL NOT choose memory or grant edit permission beyond the selected folder. Creating a project SHALL NOT start or move a chat.

Compact destinations SHALL stay in the rail, including Settings, as their owning packets deliver functionality. Existing Agent run and its history SHALL remain accessible through the transition to Workflows. The conversation SHALL remain central with a visible composer. Files and previews open in the dock through API-023 and API-025. The conversation column stays visible while the dock is open, including when the dock is widened. Full and half-screen windows SHALL be normal supported layouts. On a narrow conversation column the dock stays a side column or closes before compromising ordinary conversation or composer use. A panel MUST NOT be painted over the transcript or the composer. Primary journeys MUST NOT require interpreting raw JSON, internal identifiers or backend terminology; technical details SHALL remain available on expansion.

Light and dark themes SHALL follow Windows by default with a user override. Settings appearance SHALL expose one shared control for each visual role, including the settings surface itself. Roles cover the colour palette, the type scale, corner styles, inset, the space between items, line thickness, and layout sizes such as page width, reading width, message width, dialog width, side columns, and control height. Near-identical values SHALL share a control. Inset, the padding inside a surface, stays separate from the space between items. Those scales keep only the steps a person can tell apart: tight, row, card, section, and page insets, and tight, item, block, and section gaps. Reading text stays separate from interface text. The file editor text size and chat code size stay separate from both. Each numeric control SHALL offer a slider and a typeable value. The typeable value SHALL accept any valid measurement and SHALL NOT impose an upper bound chosen for an assumed screen size. Colour controls SHALL include transparency. Font weight, opacity, and colour-mix strength stay inside their valid ranges. Applying SHALL store overrides in appearance.json in the product data root. A draft SHALL be visible in the open window, including Settings, before it is applied. A separate preview window SHALL show a representative window of that draft, and the person SHALL be able to move and resize that window beside Settings. While a control is pointed at or changed, that preview SHALL mark the parts the control changes. Cancelling SHALL restore the last applied values. Resetting one row SHALL restore its shipped value. Media and container breakpoints, viewport-tied layout, and one-off positions stay fixed. Compact controls SHALL retain readable labels, accessible names, visible keyboard focus and usable click targets. Reduced motion SHALL be respected. Settings SHALL expose appearance, notifications, and saved grants, and MUST NOT expose manual backup or restore. Connection management SHALL stay available through Connections using the same surface.

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

#### Scenario: Backup is not a Settings section

- **WHEN** a person opens Settings
- **THEN** appearance, notifications, and saved grants are exposed, and connection management stays available through Connections
- **AND** Backup is not a Settings section and manual restore is not exposed.

### Requirement: API-018 - Keep answer streaming independent of detail visibility

Answer text SHALL always appear incrementally, including through a long reply. Painting the reply MUST stay with generation: earlier finished messages, and finished parts of the same reply, stay in place and remain readable. A compact Reasoning and tools switch in the header's Conversation view menu SHALL default off and remember the user's preference across conversations/reopening. Its presentation controls stay distinct from model Thinking and effort controls. Changing this switch SHALL only change the visibility of returned detail, never model reasoning or tool permissions. The composer Stop control is the only stop. Chat does not show a separate Activity row with its own cancel control. When enabled, available returned thinking, tool input, tool output and other raw detail SHALL be distinctly labelled apart from answers; absent streams MUST NOT be fabricated. When disabled, that expanded detail stays collapsed while answer text continues streaming. The planning checklist and the one-line activity rows in API-026 remain visible in both modes. Motion preferences SHALL be respected.

While a reply is running and the person is already at the bottom, the transcript SHALL follow the newest line immediately. Scrolling away stops following. Returning to the bottom follows again. Following sets the position directly. Smooth scrolling is reserved for an explicit jump, such as opening a chat or a notice, and reduced motion stays immediate. A text selection inside the transcript MUST be left in place. An open reasoning section follows the newest line the same way until the person scrolls inside that section, and the full reasoning text stays reachable by scrolling. Token growth MUST NOT be announced as a stream of accessibility updates. The composer status is the sole generic live activity announcement. Main Chat SHALL NOT repeat it as active response badges or generic transcript progress lines. Returned reasoning and named tool/helper activity SHALL remain visible according to the presentation preference; interrupted historical responses SHALL retain their Partial markers.

A speed or context measurement SHALL update its readout only. It MUST NOT rebuild the transcript, move the scroll position, delay the next tokens, or change execution.

Each output section SHALL independently expand/collapse through a heading or chevron, overriding the global presentation for that section without disrupting text selection or links. Approvals, typed questions and errors SHALL remain visible in both modes. Toggling presentation MUST NOT change execution, permission, saved content or the user's scroll position. Copy SHALL appear on each saved assistant answer and SHALL NOT appear while that answer is still streaming. Regenerate and Branch MUST NOT appear on a saved answer. Copy on an answer SHALL copy that answer's text. Chat code blocks, tool input and tool output SHALL each provide a copy icon. Regenerate and Branch MUST NOT remain as disabled controls. Retry and Edit SHALL sit on the person's own sent messages. Neither SHALL ask for confirmation or a repeated-effects disclosure. Header export SHALL be the Markdown transcript, not a JSON export, and delete SHALL remain in the conversation header menu. Chat SHALL NOT retain an Actions/history dock page. Retry and Edit MUST NOT disclose possible repeated effects before they run. Branch and Regenerate are absent, so they are not distinct controls beside Retry and Edit, and Retry and Edit MUST NOT follow the removed AGT-012 disclosure.

#### Scenario: Hide details while an answer streams

- **WHEN** a user disables detailed streams during generation and expands one tool result
- **THEN** answer text continues, other raw tool input and output stay collapsed, the chosen result opens independently and execution/content identity remains unchanged.

#### Scenario: Interrupt during compact presentation

- **WHEN** an approval, typed question or error occurs with detailed streams hidden
- **THEN** the actionable card remains visible and cannot be mistaken for continuing generation or hidden by collapsing activity.

#### Scenario: Actions on a saved answer

- **WHEN** a saved assistant answer is shown
- **THEN** Copy is on that answer, and Regenerate and Branch are not
- **AND** Retry and Edit sit on the person's own sent messages, and neither asks for confirmation or a repeated-effects disclosure
- **AND** header export is the Markdown transcript, not a JSON export.

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

During active work Enter queues the draft. One combined action SHALL show Send when idle and Stop for the complete active turn, including tool activity, approval/input waits, finalization and cancellation settlement. It SHALL NOT toggle back to Send merely because a token stream ended. During the atomic save phase, the action SHALL keep Stop's position but disable it with truthful Finishing feedback. That Finishing hold SHALL last only while the settled run record is saved. It is not a project copy, it MUST NOT show "Saving project state", and it MUST NOT lock the folder. Shift+Enter SHALL insert a newline; hover and keyboard focus SHALL provide concise action feedback. A compact row inside the composer SHALL expose each queued message with edit and remove. Stop SHALL cancel the active turn separately; cancelling leaves the queue paused until deliberate continuation. A queued message sends itself when the turn finishes successfully. AGT-010 SHALL govern persistence, dispatch and progression: only success advances automatically, failure/cancellation pauses, and approval/input waits do not advance. Header setting changes MUST NOT silently mutate queued items.

Inline approval cards SHALL show exact action/resource scope and the four AGT-008 choices, explaining broader grant scope before selection. Saved grants SHALL remain inspectable/revocable in Settings. Sidebar badges and a compact attention list SHALL identify conversations waiting for approval/input or needing failure recovery. The count SHALL remain on the small Notifications icon at the top of the rail, whether the separate chat list is open or closed. A notice can be dismissed. Opening a notice selects its existing conversation and dismisses that notice. If that conversation is gone, the notice is dismissed and a new chat is not created. Deleting a conversation dismisses notices for runs that leave with it, and the bell count updates immediately. A dismissed notice does not return. The list finds the conversation that contains the run, including when that run is no longer the latest turn. Windows notifications SHALL default on for those events while the application is backgrounded, subject to OS/user settings; successful completion notifications SHALL default off. Notifications MUST NOT steal focus, auto-switch conversation or answer interruptions. User activation SHALL navigate to the corresponding current conversation/attention state without replaying work; in-app attention SHALL remain usable when OS notifications are unavailable.

#### Scenario: Queue with independent configuration

- **WHEN** a user queues a follow-up, changes the selected model and then the active turn fails
- **THEN** the queue pauses with its original intended model/setup visible and editable, and Stop/Queue remain distinct from approval actions.

#### Scenario: Background approval and notification navigation

- **WHEN** another conversation requests approval while the app is backgrounded
- **THEN** its badge/attention entry and allowed Windows notification identify it without moving focus, and opening it presents the current interruption rather than accepting a stale decision.

A submitted message in a second chat SHALL NOT wait on the project folder and SHALL NOT show a project-wait row. Same-file write order stays in the environment spec. There SHALL be no project-wait row that names an owner or offers Open active chat and Cancel waiting message. A known settled outcome in one chat SHALL NOT make another chat wait on the folder. Failed-conversation follow-ups keep their existing pause rule.

#### Scenario: Another chat owns the project

- **WHEN** a person submits a message in a second chat while another chat uses the same project folder
- **THEN** that message SHALL NOT wait on the folder and SHALL NOT show a project-wait row
- **AND** same-file write order stays in the environment spec, and cancellation of that message affects only itself.

#### Scenario: Stop during tool execution

- **WHEN** generation pauses while the same active turn executes a tool
- **THEN** the action stays Stop, Enter queues the follow-up, and Stop cancels that turn through its existing lifecycle without sending the draft.

### Requirement: API-052 - Keep saved-record editing calm and recoverable

Models, Agents and Knowledge SHALL use searchable catalogue/detail editing, with an accessible selector when a side catalogue cannot fit. Shared headings, fields, actions, disclosures and states SHALL follow existing theme, spacing and density controls. Navigation within the open app SHALL preserve unsaved drafts; restoring saved values SHALL clear dirty state. Agent rows SHALL identify role, model assignment and actionable missing dependencies. Helper selections SHALL remain visible and removable when missing. Creation Review SHALL summarize the entire draft, including helpers and requirements, and Back or failed Save SHALL retain it. Knowledge creation SHALL occupy the editor pane, preserve lossless Guided/Source/resources/scopes, and distinguish display names from native skill identity. Knowledge editing SHALL have no stored model-request capture policy and no capture controls. Independent editing failures SHALL NOT block the rest of editing. Agent/browser/record actions SHALL use recognizable consistent icons.

#### Scenario: Navigate with an unsaved draft

- **WHEN** a person edits a saved record, visits Chat, then returns to its editor
- **THEN** the unsaved draft remains available, and reverting it to saved values clears its changed indicator.

#### Scenario: Repair a deleted helper

- **WHEN** a saved agent selects a helper that is no longer available
- **THEN** that selection remains visible with a corrective Remove action, and creation Review includes selected helpers and their requirements.

#### Scenario: Knowledge editing has no capture controls

- **WHEN** a person edits Knowledge
- **THEN** there is no stored model-request capture policy and no capture controls
- **AND** an independent editing failure does not block the rest of editing.

### Requirement: Capture-free routine run observation

Existing run list/detail routes SHALL accept `view=operational` and return typed capture-free operational responses under existing authentication and identity rules. The desktop SHALL use this view for routine observation. Routine observation SHALL stay capture-free. There SHALL be no diagnostic read of a stored model request, because that copy is not kept. Lifecycle, hierarchy, configuration, approvals, and recovery information SHALL remain. No observation SHALL create or dispatch execution.

#### Scenario: Operational detail and list

- **WHEN** routine desktop observation requests operational run detail or lists
- **THEN** captures SHALL be absent, and there SHALL be no diagnostic read of a stored model request, because that copy is not kept
- **AND** lifecycle, hierarchy, configuration, approvals, and recovery information remain truthful, and the observation does not create or dispatch execution.

## ADDED Requirements

### Requirement: API-057 - Say when a connection is ready and has no tools

After a successful connection test, a tool server SHALL show how many tools are ready. A resources-only success SHALL say it is ready and has no tools. It MUST NOT say "0 tools ready". A failed test SHALL say it needs attention.

#### Scenario: A resources-only connection succeeds

- **WHEN** a connection test succeeds and the connection exposes no tools
- **THEN** the row says it is ready and has no tools
- **AND** it does not say "0 tools ready".

#### Scenario: A tool server succeeds

- **WHEN** a connection test succeeds and the server exposes tools
- **THEN** the row shows how many tools are ready.

#### Scenario: A connection test fails

- **WHEN** a connection test fails
- **THEN** the row says it needs attention.
