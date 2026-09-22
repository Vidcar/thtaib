# Spec Delta

## MODIFIED Requirements

### Requirement: API-016 - Present one conversation-led desktop shell

The desktop SHALL provide one collapsible sidebar on every page. Destinations SHALL stay fully visible without their own scrollbar. Below them, one list SHALL show collapsible named project folders containing only their permanently scoped conversations, then chats with no project labelled as having no project. The no-project group SHALL remain in that list when it is empty. A project row SHALL start a new chat in that project, and a separate control SHALL create a project. Right-clicking a project SHALL offer editing it, archiving its chats, and removing it from the sidebar without deleting its folder. New chat, cross-area retained-history search, rename, archive and reopen SHALL remain available from that sidebar. The conversation header SHALL show its project or non-project identity; choosing a different area SHALL open or create another conversation rather than move or detach the current one. Removed-project history SHALL retain its identity.

Adding a project SHALL ask for a name and one existing folder. It SHALL NOT choose memory or grant edit permission beyond the selected folder. Creating a project SHALL NOT start or move a chat.

Compact destinations SHALL stay in that same sidebar, including Settings, as their owning packets deliver functionality. Existing Agent run and its history SHALL remain accessible through the transition to Workflows. The conversation SHALL remain central with a visible composer. Files, previews, and changes open in the dock in API-023, API-024, and API-025. The conversation column stays visible while the dock is open, including when the dock is widened. Full and half-screen windows SHALL be normal supported layouts. On a narrow conversation column the dock stacks with a bounded height or closes before compromising ordinary conversation or composer use. A panel MUST NOT be painted over the transcript or the composer. Primary journeys MUST NOT require interpreting raw JSON, internal identifiers or backend terminology; technical details SHALL remain available on expansion.

Light and dark themes SHALL follow Windows by default with a user override. Compact controls SHALL retain readable labels, accessible names, visible keyboard focus and usable click targets. Reduced motion SHALL be respected. Settings SHALL expose appearance, notifications, saved grants and manual backup/restore; connection management is added by Packet 04 using the same surface.

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

The conversation window SHALL visibly expose selectable model, supported reasoning effort or Thinking off, and the active setup, with compact attachment/tool/permission controls beside the composer and focused popovers for details. Project, agent, and knowledge setup SHALL open as a compact popover. That popover MUST NOT take height from the transcript, and it SHALL close when the dock opens or when another menu opens. Existing profiles SHALL remain usable before Packet 04 delivers reusable agent setups. Changes SHALL affect future submissions without rewriting active turns or queued intended configuration. Unsupported/overridden/unverified reasoning controls SHALL be labelled truthfully; hiding returned thinking MUST NOT be represented as disabling model reasoning.

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

- **WHEN** a person opens project, agent, or knowledge setup during a conversation
- **THEN** the transcript keeps its height and the setup closes when the dock or another menu opens.

### Requirement: API-018 - Keep answer streaming independent of detail visibility

Answer text SHALL always appear incrementally. A compact detailed-stream toggle SHALL default off and remember the user's preference across conversations/reopening. When enabled, available returned thinking, tool input, tool output and other raw detail SHALL be distinctly labelled apart from answers; absent streams MUST NOT be fabricated. When disabled, that expanded detail stays collapsed while answer text continues streaming. The planning checklist and the one-line activity rows in API-026 remain visible in both modes. Motion preferences SHALL be respected.

Each output section SHALL independently expand/collapse through a heading or chevron, overriding the global presentation for that section without disrupting text selection or links. Approvals, typed questions and errors SHALL remain visible in both modes. Toggling presentation MUST NOT change execution, permission, saved content or the user's scroll position. Copy, Regenerate answer and Branch SHALL appear on each saved assistant answer and SHALL NOT appear while that answer is still streaming. Copy on an answer SHALL copy that answer's text. Chat code blocks, tool input, tool output and file differences SHALL each provide a copy icon. Unavailable Regenerate answer or Branch SHALL stay disabled with the truthful reason rather than retrying the task. Retry task, edit-the-task, export and delete SHALL remain in the conversation menu. That menu SHALL be only as large as those actions and MUST NOT cover the dock. Retry task SHALL disclose possible repeated effects before it runs. Branch, Retry task and Regenerate answer SHALL remain visibly distinct and obey AGT-012.

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

## ADDED Requirements

### Requirement: API-023 - Keep one dock beside the conversation

Chat SHALL use one right-hand dock. Opening it adds a column and narrows the transcript. Closing it returns that width. A splitter SHALL resize the dock within bounds. Exactly one page is open at a time; switching pages replaces the dock and MUST NOT open a second card. The first pages are Changes and Files. Later pages register in this same dock. Widening the dock SHALL keep a readable conversation column. On a narrow conversation column the dock SHALL stack with a bounded height or close. The dock MUST NOT be painted over the transcript or the composer, and it MUST NOT hide the conversation in order to grow. Navigation and the dock keep bounded resize, collapse, and reopen without losing content or run state. Light and dark follow the application theme.

#### Scenario: Open, resize, and close

- **WHEN** a person opens Files, drags the splitter, switches to Changes, and then closes the dock
- **THEN** the transcript narrows and widens with the dock, only one page is showing, and closing restores the conversation width
- **AND** the answer text is never covered.

#### Scenario: Narrow window

- **WHEN** the conversation column is about half a screen wide and the dock is open
- **THEN** the dock stacks with a bounded height or closes
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

The unfinished call uses the present-tense verb. The finished call uses the past tense. A failure shows on that line. `+N -M` SHALL appear only from the observed before/after difference for that same call, counting added and removed content lines and excluding diff headers. Missing text omits the counts. The product MUST NOT scrape a number out of tool prose or invent a count. A shell line shows the command truncated to one line; its full output stays on expand. The underlying tool name stays available on expand.

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
