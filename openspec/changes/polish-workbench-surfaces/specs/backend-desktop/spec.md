# Spec Delta

## MODIFIED Requirements

### Requirement: API-017 - Expose compact effective model controls and measurements

Opening a conversation SHALL restore that conversation's effective Access choice, including an explicit Ask override. When a setup leaves access unspecified, the backend SHALL resolve the current application, project, agent and conversation layers and show the effective value with its named source. Ask is the fallback when no selected layer supplies a value. An explicit conversation override, including Ask, takes precedence; choosing inherited access removes that override and uses the current resolved source. Access MUST NOT leak from the previously viewed setup or conversation. A user's explicit choice SHALL survive unrelated default changes. Access labels SHALL show Ask, Approve for me, or Full access in full and explain that running and already queued messages keep their selected policy. Descriptions and model instructions SHALL reflect saved permission grants and the actual selected mode, while explicit questions and disabled-tool boundaries remain enforced.

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

#### Scenario: Inherited access follows its named source

- **WHEN** a selected setup leaves access unspecified and an applicable saved default supplies Full access
- **THEN** the control shows Full access with that named source, while an explicit conversation Ask override remains Ask
- **AND** choosing inherited access removes the local override and restores the current resolved value without changing an active or queued turn.

### Requirement: API-018 - Keep answer streaming independent of detail visibility

Answer text SHALL always appear incrementally, including through a long reply. Painting the reply MUST stay with generation: earlier finished messages, and finished parts of the same reply, stay in place and remain readable. A compact Reasoning and tools switch in the header's Conversation view menu SHALL default off and remember the user's preference across conversations/reopening. Its presentation controls stay distinct from model Thinking and effort controls. Changing this switch SHALL only change the visibility of returned detail, never model reasoning or tool permissions. The composer Stop control is the only stop. Chat does not show a separate Activity row with its own cancel control. When enabled, available returned thinking, tool input, tool output and other raw detail SHALL be distinctly labelled apart from answers; absent streams MUST NOT be fabricated. When disabled, that expanded detail stays collapsed while answer text continues streaming. The planning checklist and the one-line activity rows in API-026 remain visible in both modes. Motion preferences SHALL be respected.

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

### Requirement: API-026 - Show planning and file activity as it happens

While an assistant turn runs, and when that turn is reopened, Chat SHALL show planning and tool activity from the projected tool calls. This is visible with detailed streams on or off.

`write_todos` SHALL appear as one checklist for that turn. Each item shows its task content and its status: pending, in progress, or completed. The status is a mark on that row, separate from the sentence. The sentence is the task content alone. The checklist is the arguments of the latest successful `write_todos` call. A later successful call replaces the list. A failed call leaves the previous list and shows the failure. The product MUST NOT keep a second todo list or read private graph state. Raw arguments remain available on a further disclosure. The checklist appears only once those arguments parse as the todo list.

Each other filesystem, search, shell, MCP, and memory tool keeps one identity line, one per call identity, in order, without a duplicate when live and retained records join:

- Reading or Read, plus the path. When the call includes an offset and limit, the line includes that line range.
- Creating or Created, Editing or Edited, Deleting or Deleted, Renaming or Renamed, using the recorded operation. A rename shows the source and destination.
- Listing or Listed, Finding or Found files matching, Searching or Searched for, Running or Ran, Calling or Called, Proposing or Proposed a memory.

An actively running unfinished call uses the present-tense verb. The finished call uses the past tense. A failure shows on that line. Retained incomplete arguments from a stopped or failed turn SHALL be labelled as partial input, never as ongoing work or a completed file. Starting a later turn MUST NOT reactivate that label. `+N -M` SHALL appear only from the observed before/after difference for that same call, counting added and removed content lines and excluding diff headers. Missing text omits the counts. The product MUST NOT scrape a number out of tool prose or invent a count. A shell line shows the command truncated to one line.

A single finished call stays as that identity line. Two or more consecutive finished successful calls that share the same verb, and that are not waiting for a person, collapse into one summary line. The summary names the verb and how many calls it covers, for example "Read 6 files" or "Ran 3 commands". It does not add those calls' `+N -M` figures into a new total. Opening the summary shows the identity lines in their original order. A call that is still running, a call that failed, and a call that is waiting for approval or a typed answer each stay on their own line and are not folded into a summary. Closing the summary does not discard the calls.

The first opening of an identity line shows the plain result: the path, the command, the output, or the short description of the change. The internal tool name and the raw arguments stay on a further disclosure. They MUST NOT be the first thing that opening shows.

While a call is unfinished and its body is open, that body follows the newest line until the person scrolls inside it. The open body shows the full text produced so far. Every line stays reachable by scrolling, and copy copies that full text. The product MUST NOT drop earlier text to keep the view small. Completed file content SHALL remain readable with its original line breaks; raw arguments remain available separately.

Choosing a file identity line opens the dock on that change, or on the file when no change record exists. Choosing a summary line does not open the dock. The choice MUST NOT send a chat message or call the model. Approvals and typed questions keep their existing cards. The activity line MUST NOT offer a second set of approval buttons.

#### Scenario: Todo list updates in place

- **WHEN** the agent writes a todo list and later marks an item complete
- **THEN** one checklist shows the latest successful items and statuses
- **AND** detailed streams being off does not hide it.

#### Scenario: Checklist status stays off the sentence

- **WHEN** a checklist item is pending and its content is "Fix the frame step"
- **THEN** the row shows that content as the sentence and shows pending as a separate mark
- **AND** the sentence does not begin with the word pending.

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

### Requirement: API-028 - Confirm before swapping the loaded model

Changing or unloading a model SHALL require explicit reviewed confirmation. An explicit Apply & reload or Unload action on that reviewed state SHALL count as confirmation. The confirmation names the conversation that will be kept and any work that must finish or be stopped. It MUST NOT unload a model as a side effect of choosing a different row. After confirmation, the conversation, its draft, and its history remain. The screen shows waiting, loading, or the failure, and the draft is still there if loading fails.

#### Scenario: Swap during a quiet chat

- **WHEN** a person chooses another model and confirms
- **THEN** the same conversation stays open
- **AND** the previous model is not unloaded until that confirmation.

#### Scenario: Swap while work is running

- **WHEN** a reply or a Lab run is still using the model
- **THEN** the confirmation names that work and does not unload it silently.

## ADDED Requirements

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

The transcript SHALL be able to scroll so the last line of the conversation sits clear of the composer. Model settings, the approval menu, and the context readout SHALL open without covering that last line. When there is not room below the composer control, the menu opens above it inside the conversation column. The shield's visible label SHALL be the same words as the menu: Ask, Approve for me, or Full access.

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

Each model chooser SHALL show one row per selectable model configuration or connected endpoint, rather than duplicate historical runtime instances. Two rows MUST NOT share the same visible label. A repeated file name gains the fact that distinguishes it, such as ready or stopped, context, or size. An internal prefix such as `managed:` MUST NOT appear in the label. Meaningfully distinct configurations SHALL remain selectable; equivalent duplicate runtime records SHALL not become duplicate user choices.

In the library, rows that share a file name stay separate, and each row shows when it was added and where it belongs without opening the file.

#### Scenario: The sidebar matches the header

- **WHEN** a conversation's title changes from "New conversation" to a sentence
- **THEN** the sidebar row and the header both show that sentence
- **AND** a second conversation that is still untitled stays "New conversation".

#### Scenario: Repeated model files stay distinguishable

- **WHEN** two selectable setups use the same file name and one is ready
- **THEN** each row has its own visible label
- **AND** neither label begins with an internal prefix.

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

Settings SHALL remain one destination in the sidebar. Within it, the person SHALL be able to open Appearance, Notifications, Defaults, Connections, Permissions, and Backup directly. Appearance SHALL show compact basic controls and explicitly opened advanced customization, preserving every existing shared control, slider and typeable value, Apply, Cancel, and per-row Reset within bounded responsive columns. Help for Apply, Cancel, and Reset SHALL open on hover or keyboard focus. It MUST NOT be a standing paragraph above the controls.

The separate preview window SHALL show a small conversation of the draft: sidebar, a short transcript with one tool line and one answer, the composer, and one card. Spacing guides SHALL start off and remain available. Pointing at a control, or changing it, still marks the parts that control changes. The preview MUST NOT replace the open Settings page.

#### Scenario: Backup is reachable without the colour list

- **WHEN** a person opens Settings and chooses Backup
- **THEN** backup and restore are shown
- **AND** the appearance controls are not required to scroll past first.

#### Scenario: The sample looks like the conversation

- **WHEN** a person opens the appearance preview
- **THEN** the sample shows a sidebar, a short transcript, a composer, and a card using the draft
- **AND** spacing guides are off until the person turns them on.

### Requirement: API-036 - Group one file's edits without losing an edit

On the Changes page, for the selected turn, consecutive recorded edits of the same file SHALL be grouped under that file. Each recorded edit remains selectable. Selecting one opens that edit's stored before and after text in the shipped diff editor, as API-024 requires. Reverse still confirms and applies to the selected edit only. The group MUST NOT invent a difference that combines several edits into one unrecorded result. When the editor assets cannot load, the page says the difference is unavailable and why. It does not stay on an endless opening state.

#### Scenario: Repeated edits of one file

- **WHEN** a turn edited `style.css` five times
- **THEN** Changes shows those edits grouped under `style.css`
- **AND** each edit can still be opened on its own stored difference.

#### Scenario: The editor fails to load

- **WHEN** the diff editor's assets cannot be loaded
- **THEN** the page says the difference is unavailable and why
- **AND** it does not remain on an opening message.

### Requirement: API-037 - Say when a saved permission let the tool proceed

When the chat is on Ask, and a tool that would have paused proceeds because a saved grant allows it, that call's activity line SHALL say a saved permission was used. The line names the grant in plain words. The full grant remains available on the further disclosure and in Settings, where it can still be revoked. Saved grants remain explicit exceptions to the access rules, are attributed by the backend, and MUST NOT override Plan mode or enable a disabled tool.

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
