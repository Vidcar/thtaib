# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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

### Requirement: API-019 - Present queued work and scoped attention clearly

During active work Enter queues the draft. The send control stays the send arrow, with a separate Stop control. A compact row inside the composer SHALL expose each queued message with edit and remove. Stop SHALL cancel the active turn separately; cancelling leaves the queue paused until deliberate continuation. A queued message sends itself when the turn finishes successfully. AGT-010 SHALL govern persistence, dispatch and progression: only success advances automatically, failure/cancellation pauses, and approval/input waits do not advance. Header setting changes MUST NOT silently mutate queued items.

Inline approval cards SHALL show exact action/resource scope and the four AGT-008 choices, explaining broader grant scope before selection. Saved grants SHALL remain inspectable/revocable in Settings. Sidebar badges and a compact attention list SHALL identify conversations waiting for approval/input or needing failure recovery. The count is the same small circle on the bell in the expanded and collapsed navigation. A notice can be dismissed. Opening a notice selects its existing conversation and dismisses that notice. If that conversation is gone, the notice is dismissed and a new chat is not created. Deleting a conversation dismisses notices for runs that leave with it, and the bell count updates immediately. A dismissed notice does not return. The list finds the conversation that contains the run, including when that run is no longer the latest turn. Windows notifications SHALL default on for those events while the application is backgrounded, subject to OS/user settings; successful completion notifications SHALL default off. Notifications MUST NOT steal focus, auto-switch conversation or answer interruptions. User activation SHALL navigate to the corresponding current conversation/attention state without replaying work; in-app attention SHALL remain usable when OS notifications are unavailable.

#### Scenario: Queue with independent configuration

- **WHEN** a user queues a follow-up, changes the selected model and then the active turn fails
- **THEN** the queue pauses with its original intended model/setup visible and editable, and Stop/Queue remain distinct from approval actions.

#### Scenario: Background approval and notification navigation

- **WHEN** another conversation requests approval while the app is backgrounded
- **THEN** its badge/attention entry and allowed Windows notification identify it without moving focus, and opening it presents the current interruption rather than accepting a stale decision.

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

## REMOVED Requirements

### Requirement: API-024 - Review changes in the loaded diff editor

**Reason**: Per-edit capture, reverse, and the Changes page are retired.

**Migration**: Use the Files page to inspect current project files; ordinary file edits remain available through native tools.

### Requirement: API-036 - Group one file's edits without losing an edit

**Reason**: The Changes page and its grouping/reverse behavior are retired.

**Migration**: Use the Files page to inspect current project files.

### Requirement: API-026 - Show planning and file activity as it happens

**Reason**: Per-edit difference and line-count presentation is retired while native tool activity remains.

**Migration**: Use the new API-026 activity contract, which shows actual tool calls without an undoable difference claim.
