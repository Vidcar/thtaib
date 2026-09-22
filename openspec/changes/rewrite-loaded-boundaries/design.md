# Design

## Context

See proposal.md for why. Chat already streams tool calls through `@langchain/react`. `write_todos` puts the whole list on the tool-call arguments (`content`, `status` of `pending`, `in_progress`, or `completed`). File mutations already store before/after text on a record keyed by the tool-call id. The Files column is a real grid track, Setup is a card inside the conversation, and conversation actions are an absolutely positioned card that paints over both.

Deep Agents 0.7.15, as installed, treats extra `tools=` as additive. Built-ins are removed only with a harness profile exclusion or a filesystem middleware tool list. An empty `subagents` list still compiles the general-purpose subagent, and that child does not inherit the parent catalogue gate. Upstream `delete` is recursive. There is no upstream rename.

## Goals / Non-Goals

**Goals:**

- One dock column, one page at a time, conversation still readable.
- Monaco for the diff and for reading a text file. A loaded tree widget for the project listing that already exists.
- A checklist and one-line activity rows from data the stream and the file-change record already have.
- Ordinary Chat offers the built-in filesystem tools, and does not offer `task` or recursive `delete`.

**Non-Goals:**

- Implementing the dock, the editor, or the harness change in this change. This change is the contract.
- A Monaco editor on every transcript row. The row is one line. The dock is the editor.
- Per-hunk accept, git status letters, a PDF viewer, or the Deep Agents CLI.
- A second todo store, or projecting private graph state into the renderer.
- Subagent cards. Ordinary Chat keeps `task` disabled. Declared workflow delegation stays with its own change.
- The deferred journeys: memory-proposal review, document-source inspection, the skill journey, and half-screen acceptance. A memory tool may show "Proposed a memory". That does not build the review journey.
- Re-planning open changes `04` through `08`, `compact-workbench-experience`, or `familiar-chat-sidebar`.

## Decisions

### Dock, not another card

The right side is one column beside the transcript. Opening it narrows the conversation. Closing it gives the width back. A splitter resizes it. Widening it keeps a readable conversation; the current expand path that hides the conversation is retired. Under about 900px of conversation width the dock stacks with a bounded height or closes. Setup stays a popover that does not consume transcript height and closes when the dock or another menu opens. Retry, edit-the-task, export, and delete stay a menu no larger than those actions, and that menu must not cover the dock.

Alternative considered: making Setup a dock page. Rejected. The existing model controls are compact popovers, and Setup is the same kind of control. The dock starts as Changes and Files so later pages have one place to land.

### Monaco for review and reading, a tree widget for navigation

Changes: `monaco-editor`'s diff editor through `@monaco-editor/react`, original and modified taken from the stored before/after text. Side by side when the dock is wide, inline when it is narrow. Read-only. Theme follows the app. Workers and grammars ship inside the desktop package.

Files: `react-arborist` over the existing one-directory project listing. A filter box filters names already loaded. Selecting a text file uses a new read-only project-file read with the same path confinement as that listing. The read does not call the model. Images keep the current image preview. Anything else says it cannot be shown. Retained copies stay in the same page and stay labelled as retained copies.

The unified-diff string may remain copy text. It is not the view. Reverse stays the existing confirmed reverse.

Alternative considered: CodeMirror or a static diff renderer. Rejected. They would mean building the review interaction Monaco already has. Building a custom tree was rejected for the same reason.

Git status letters like a Cursor tree are a later decoration on this same tree. The spec does not require git to open a file.

### Activity from the stream, counts from the observed diff

`write_todos` renders as one checklist per assistant turn, replaced by the latest successful call. A failed call leaves the previous list. The checklist is visible with detailed streams off. Raw arguments stay behind expand. Do not parse the tool's prose reply and do not read graph todo state.

Every other filesystem, search, shell, MCP, and memory tool renders as one line, joined to retained history by the existing call identity:

- `Read SKILL.md`, and `lines 10–40` when the call's offset and limit say so
- `Edited thistest.md +5 -4` only after the observed before/after difference can be counted
- `Created`, `Deleted`, and `Renamed from → to` from the file-change operation
- `Listed`, `Found files matching`, `Searched for`, `Ran`, `Called`, `Proposed a memory`

While the call is unfinished the verb is present tense (`Reading`, `Editing`). A failure shows on that line and does not keep success counts. Counts are added and removed content lines in the observed difference, excluding diff headers. Missing text omits the counts. Do not scrape a number out of tool prose.

Choosing a file line opens the dock on that change, or on the file when there is no change record. It does not send a chat message. Approvals and typed questions keep their existing cards. The line is not a second set of approval buttons.

`compact-workbench-experience` requirement API-022 asks the row to identify the actual tool name. This contract leads with the human action. The tool name remains on expand, on the same call. Where those two changes disagree, this one is the label rule.

### Harness exclusions go through upstream, once

Ordinary Chat disables the general-purpose subagent with the upstream profile switch, and drops recursive `delete` with the upstream exclusion or filesystem tool list. A parent middleware hide is not sufficient, because the compiled child does not inherit it. `delete_file` remains the one-file delete. `rename_file` remains the only rename. `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep` stay the built-ins. Exactly one summarization middleware runs, and it uses the configured usable input budget rather than stacking the default on top.

Do not adopt the Deep Agents CLI, Managed Deep Agents, `StoreBackend` for knowledge, or a second shell tool.

## Risks / Trade-offs

- [Monaco's weight and worker loading in Vite] → Ship the assets inside the desktop package and load them from there. No CDN.
- [`write_todos` arguments arrive as a partial stream] → Show the checklist only once the arguments parse as the todo list. Until then show the pending line, not a broken list.
- [Line counts lag the tool call] → Show the path immediately. Add `+N -M` when the file-change record has both texts. Never invent a count.
- [Upstream still registers `delete` and `task` today] → The implementation must turn them off through the upstream switch and prove the model cannot call them, including through a child.
- [A second summarizer double-shrinks the budget] → One middleware, name-replaced, with a check that compaction runs once.
- [New file read could escape the project] → Same confinement as the directory listing: inside the project, no links, no framework routes.

## Migration Plan

Sync these deltas into `openspec/specs/` on this branch. No product-data migration. Existing file-change records stay as they are; counts are derived when presenting them. Implementation is a later apply. Rollback is reverting the spec commit.

## Open Questions

None that change this contract. Git decorations on the tree can be added later without a new panel.
