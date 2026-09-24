# Spec Delta

## MODIFIED Requirements

### Requirement: API-016 - Present one conversation-led desktop shell

The desktop SHALL provide one collapsible sidebar on every page. Destinations SHALL stay fully visible without their own scrollbar. Below them, one list SHALL show collapsible named project folders containing only their permanently scoped conversations, then chats with no project labelled as having no project. The no-project group SHALL remain in that list when it is empty. A project row SHALL start a new chat in that project, and a separate control SHALL create a project. Right-clicking a project SHALL offer editing it, archiving its chats, and removing it from the sidebar without deleting its folder. New chat, cross-area retained-history search, rename, archive and reopen SHALL remain available from that sidebar. The conversation header SHALL show its project or non-project identity; choosing a different area SHALL open or create another conversation rather than move or detach the current one. Removed-project history SHALL retain its identity.

Adding a project SHALL ask for a name and one existing folder. It SHALL NOT choose memory or grant edit permission beyond the selected folder. Creating a project SHALL NOT start or move a chat.

Compact destinations SHALL stay in that same sidebar, including Settings, as their owning packets deliver functionality. Existing Agent run and its history SHALL remain accessible through the transition to Workflows. The conversation SHALL remain central with a visible composer. Files and previews open in the dock through API-023 and API-025. The conversation column stays visible while the dock is open, including when the dock is widened. Full and half-screen windows SHALL be normal supported layouts. On a narrow conversation column the dock stays a side column or closes before compromising ordinary conversation or composer use. A panel MUST NOT be painted over the transcript or the composer. Primary journeys MUST NOT require interpreting raw JSON, internal identifiers or backend terminology; technical details SHALL remain available on expansion.

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

Opening a conversation SHALL restore that conversation's effective Access choice, including an explicit Ask override. When a setup leaves access unspecified, the backend SHALL resolve the current application, project, agent and conversation layers and show the effective value with its named source. Ask is the fallback when no selected layer supplies a value. An explicit conversation override, including Ask, takes precedence; choosing inherited access removes that override and uses the current resolved source. Access MUST NOT leak from the previously viewed setup or conversation. A user's explicit choice SHALL survive unrelated default changes. Access labels SHALL show Ask or Full access in full and explain that running and already queued messages keep their selected policy. Descriptions and model instructions SHALL reflect saved permission grants and the actual selected mode, while explicit questions and disabled-tool boundaries remain enforced.

The conversation window SHALL visibly expose selectable model, supported reasoning effort or Thinking off, and the active setup, with compact attachment and permission controls beside the composer and focused popovers for details. The shield selects Ask or Full access for later messages in that chat. It does not turn the agent's tool list on or off. Project, agent, and knowledge setup SHALL live on the Setup page of the conversation rail. The rail starts closed and MUST NOT take height from the transcript while it is closed. Existing profiles SHALL remain usable before Packet 04 delivers reusable agent setups. Changes SHALL affect future submissions without rewriting active turns or queued intended configuration. Unsupported/overridden/unverified reasoning controls SHALL be labelled truthfully; hiding returned thinking MUST NOT be represented as disabling model reasoning.

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

#### Scenario: Inherited access follows its named source

- **WHEN** a selected setup leaves access unspecified and an applicable saved default supplies Full access
- **THEN** the control shows Full access with that named source, while an explicit conversation Ask override remains Ask
- **AND** choosing inherited access removes the local override and restores the current resolved value without changing an active or queued turn.

### Requirement: API-018 - Keep answer streaming independent of detail visibility

Answer text SHALL always appear incrementally, including through a long reply. Painting the reply MUST stay with generation: earlier finished messages, and finished parts of the same reply, stay in place and remain readable. A compact Reasoning and tools switch in the header's Conversation view menu SHALL default off and remember the user's preference across conversations/reopening. Its presentation controls stay distinct from model Thinking and effort controls. Changing this switch SHALL only change the visibility of returned detail, never model reasoning or tool permissions. The composer Stop control is the only stop. Chat does not show a separate Activity row with its own cancel control. When enabled, available returned thinking, tool input, tool output and other raw detail SHALL be distinctly labelled apart from answers; absent streams MUST NOT be fabricated. When disabled, that expanded detail stays collapsed while answer text continues streaming. The planning checklist and the one-line activity rows in API-026 remain visible in both modes. Motion preferences SHALL be respected.

While a reply is running and the person is already at the bottom, the transcript SHALL follow the newest line immediately. Scrolling away stops following. Returning to the bottom follows again. Following sets the position directly. Smooth scrolling is reserved for an explicit jump, such as opening a chat or a notice, and reduced motion stays immediate. A text selection inside the transcript MUST be left in place. An open reasoning section follows the newest line the same way until the person scrolls inside that section, and the full reasoning text stays reachable by scrolling. Token growth MUST NOT be announced as a stream of accessibility updates. One status announces that a reply is being written, has stopped, or is waiting.

A speed or context measurement SHALL update its readout only. It MUST NOT rebuild the transcript, move the scroll position, delay the next tokens, or change execution.

Each output section SHALL independently expand/collapse through a heading or chevron, overriding the global presentation for that section without disrupting text selection or links. Approvals, typed questions and errors SHALL remain visible in both modes. Toggling presentation MUST NOT change execution, permission, saved content or the user's scroll position. Copy, Regenerate answer and Branch SHALL appear on each saved assistant answer and SHALL NOT appear while that answer is still streaming. Copy on an answer SHALL copy that answer's text. Chat code blocks, tool input and tool output SHALL each provide a copy icon. Unavailable Regenerate answer or Branch SHALL stay disabled with the truthful reason rather than retrying the task. Retry task, edit-the-task, export and delete SHALL remain on the Actions page of the conversation rail. That page MUST NOT cover the transcript. Retry task SHALL disclose possible repeated effects before it runs. Branch, Retry task and Regenerate answer SHALL remain visibly distinct and obey AGT-012.

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

### Requirement: API-023 - Keep one dock beside the conversation

Chat SHALL use one right-hand rail. It starts closed. One header control opens and closes it, and that choice stays while the person moves between chats. Opening it adds a column and narrows the transcript. Closing it returns that width. A splitter SHALL resize the rail within bounds. Exactly one page is open at a time; switching pages replaces the rail and MUST NOT open a second card. The pages are Setup, Files, Library, and Actions. Choosing a file in the transcript opens the rail on that item. That is the only automatic open. Widening the rail SHALL keep a readable conversation column. The rail stays beside the transcript and composer at every window width, including about half a screen. It MUST NOT move above the composer. The rail MUST NOT be painted over the transcript or the composer, and it MUST NOT hide the conversation in order to grow. Navigation and the rail keep bounded resize, collapse, and reopen without losing content or run state. Light and dark follow the application theme.

#### Scenario: Open, resize, and close

- **WHEN** a person opens the rail to Files, drags the splitter, switches to Setup, and then closes the rail
- **THEN** the transcript narrows and widens with the rail, only one page is showing, and closing restores the conversation width
- **AND** the answer text is never covered.

#### Scenario: Narrow window

- **WHEN** the conversation column is about half a screen wide and the rail is open
- **THEN** the rail remains a column on the right of the transcript and composer
- **AND** the transcript and composer remain usable.

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
- **AND** a stopped call is labelled as partial input, without an invented result or line count.

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
