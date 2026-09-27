# Spec Delta

## MODIFIED Requirements

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

The bounded searchable model picker SHALL show one row per model, expanding named configurations only when more than one exists. Expansion SHALL NOT load a model. Ready, loading/waiting, attention and idle dots SHALL reflect the exact configuration's observed state, with equivalent accessible hover/focus labels. Saved configurations alone SHALL NOT imply residency. The tuning icon SHALL open one combined supported Thinking/effort and context editor with one Apply. Applied chat-local overrides SHALL be remembered separately per model within that chat; first use starts with saved model defaults and returning restores those overrides. Permanent defaults, response-length controls and thinking-token-limit controls SHALL remain in Models. Applying startup changes SHALL reload only when safe and preserve the draft, attachments, history and reading position; active-work changes SHALL use the staging rule in API-028.

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
- **THEN** one bounded editor shows supported Thinking/effort and context with one Apply, and no response-length or thinking-token-limit control.

#### Scenario: Inherited access follows its named source
- **WHEN** the application preference changes after a chat explicitly selected Ask
- **THEN** that chat remains Ask while a new chat takes the current application preference, and Chat names the preference source when no explicit choice exists.

#### Scenario: Bounded everyday reasoning and scoped measurements
- **WHEN** the user selects Balanced or Deep and later an internal summary runs
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

### Requirement: API-023 - Keep one dock beside the conversation

Chat SHALL use one right-hand dock with exactly Files, Browser and Helpers pages. It starts closed; one header control opens/closes it and retains its open choice, page and bounded width across chat navigation. A splitter SHALL resize it while preserving a readable conversation column and reading position. Choosing a page replaces the current page rather than adding another card. Opening SHALL require a person choosing its toggle, page or a file/helper link; new browser/helper/file activity SHALL only update a compact indicator. Files SHALL combine project files, chat uploads/generated outputs and authorized reusable saved copies with clear origins; global Library SHALL remain accessible for bulk catalogue work. Setup and Actions/history pages SHALL be removed, with setup controls in their owning composer or destination and chat/message actions under API-018. Opening adds a side column, closing returns width, and narrow layouts SHALL collapse secondary columns before compromising ordinary chat use. The dock MUST NOT cover the transcript/composer, move above the composer or hide the conversation to grow. Resize/collapse/reopen SHALL retain content and run state and follow the application theme.

#### Scenario: Open, resize, and close

- **WHEN** a person opens the rail to Files, drags the splitter, switches to Helpers, and then closes the rail
- **THEN** the transcript narrows and widens with the rail, only one page is showing, and closing restores the conversation width
- **AND** the answer text is never covered.

#### Scenario: Narrow window

- **WHEN** the conversation column is about half a screen wide and the rail is open
- **THEN** an open dock stays beside the transcript/composer while usable, or closes before crowding them
- **AND** reopening retains its page, width preference and content without covering the answer.

#### Scenario: Activity without automatic opening

- **WHEN** a browser session starts, a helper works or a generated file appears while the dock is closed
- **THEN** a compact indicator updates and the dock stays closed until a person chooses to open it.

#### Scenario: Contextual file origins

- **WHEN** Files lists a live project file, a chat upload and a reusable retained copy
- **THEN** each retains its existing identity, authority and origin, and preview/reuse does not create a second file catalogue.

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

### Requirement: API-030 - Present reusable agents as a calm list

The Agents destination SHALL list saved agents by name and role, with Use Chat model or the assigned model and any missing dependency. New-agent creation SHALL be guided through role/instructions, model/tools/knowledge and review/save; existing agents SHALL open a grouped editor using the same canonical configuration controls. Agents SHALL expose tool groups and individual selection, knowledge defaults, optional fixed model and named helpers. The Chat agent dropdown SHALL select saved agents only, without exposing setup or tool toggles. Create, duplicate, rename and remove SHALL be explicit. Removal SHALL retain past conversations and frozen older versions, with effect detail available on demand. An empty list SHALL offer one create action rather than storage explanation; missing dependencies SHALL be a short actionable row warning rather than blocking the whole page.

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

## ADDED Requirements

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
