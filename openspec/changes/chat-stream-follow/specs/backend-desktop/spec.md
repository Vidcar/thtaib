# Spec Delta

## MODIFIED Requirements

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

### Requirement: API-026 - Show planning and file activity as it happens

While an assistant turn runs, and when that turn is reopened, Chat SHALL show planning and tool activity from the projected tool calls. This is visible with detailed streams on or off.

`write_todos` SHALL appear as one checklist for that turn. Each item shows its content and its status: pending, in progress, or completed. The checklist is the arguments of the latest successful `write_todos` call. A later successful call replaces the list. A failed call leaves the previous list and shows the failure. The product MUST NOT keep a second todo list or read private graph state. Raw arguments remain available on expand. The checklist appears only once those arguments parse as the todo list.

Each other filesystem, search, shell, MCP, and memory tool SHALL appear as one line, one per call identity, in order, without a duplicate when live and retained records join:

- Reading or Read, plus the path. When the call includes an offset and limit, the line includes that line range.
- Creating or Created, Editing or Edited, Deleting or Deleted, Renaming or Renamed, using the recorded operation. A rename shows the source and destination.
- Listing or Listed, Finding or Found files matching, Searching or Searched for, Running or Ran, Calling or Called, Proposing or Proposed a memory.

The unfinished call uses the present-tense verb. The finished call uses the past tense. A failure shows on that line. `+N -M` SHALL appear only from the observed before/after difference for that same call, counting added and removed content lines and excluding diff headers. Missing text omits the counts. The product MUST NOT scrape a number out of tool prose or invent a count. A shell line shows the command truncated to one line; its full output stays on expand. The underlying tool name stays available on expand.

While a call is unfinished and its body is open, that body follows the newest line until the person scrolls inside it. The open body shows the full text produced so far. Every line stays reachable by scrolling, and copy copies that full text. The product MUST NOT drop earlier text to keep the view small.

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
