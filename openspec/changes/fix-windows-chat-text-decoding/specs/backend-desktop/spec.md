# Spec Delta

## MODIFIED Requirements

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
