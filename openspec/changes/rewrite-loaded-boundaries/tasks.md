# Tasks

## 1. Harness catalogue

- [x] 1.1 Disable the general-purpose subagent for ordinary Chat through the upstream profile switch, and drop recursive `delete` through the upstream exclusion or filesystem tool list. Verify a compiled child cannot call `task` or `delete`, with a backend test that inspects the tools the model is offered.
- [x] 1.2 Keep exactly one summarization middleware on the configured usable input budget. Verify a long scripted turn compacts once and does not apply the default budget shrink on top.
- [x] 1.3 Confirm `rename_file` and single-file `delete_file` are the only custom file mutations and that `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep` are not re-registered. Verify with the existing catalogue test or a focused addition to it.

## 2. Project file read

- [x] 2.1 Add a read-only project-file read with the same confinement as the directory listing, published through the shared contract generator. Verify path escape, link, and framework-route cases are refused, and a normal text file returns its captured text without invoking the model.

## 3. Dock

- [x] 3.1 Replace the covering conversation-actions card and the in-transcript Setup card with the dock column, a compact setup popover, and a menu no larger than retry, edit-the-task, export, and delete. Verify in the desktop check that opening the dock narrows the transcript, the menu does not cover the answer, and widening the dock does not hide the conversation.
- [x] 3.2 Stack or close the dock when the conversation column is narrow. Verify the transcript and composer remain usable at the half-screen width without claiming the deferred half-screen review is accepted.

## 4. Monaco and the tree

- [x] 4.1 Add `monaco-editor`, `@monaco-editor/react`, and `react-arborist`, with Monaco's workers loaded from the desktop package. Verify the production build contains those assets and does not request a CDN.
- [x] 4.2 Build the Changes page from stored before/after text in the Monaco diff editor, side by side or inline with the dock width, read-only, with the existing reverse confirmation. Verify a text change renders both sides and a change with no text explains that the difference is unavailable.
- [x] 4.3 Build the Files page tree from the existing directory listing, a name filter, the read-only editor, the existing image preview, and labelled retained copies. Verify opening a text file does not call the model and a retained copy stays distinct from the live file.

## 5. Checklist and activity lines

- [x] 5.1 Render one `write_todos` checklist per turn from the latest successful tool-call arguments, visible with detailed streams off. Verify a second successful call replaces the list, a failed call keeps the previous list, and raw arguments stay behind expand.
- [x] 5.2 Render one activity line per file, search, shell, MCP, and memory call, with `+N -M` only from the observed difference for that call. Verify "Read SKILL.md" has no counts, a five-added four-removed edit shows `+5 -4`, and choosing the line opens that change in the dock without sending a message.

## 6. Checks

- [x] 6.1 Run `openspec validate --all` from the repository root and the desktop build from `apps/desktop`. Verify both pass.
- [x] 6.2 Run the focused backend harness and file-change tests from `apps/backend`. Verify the catalogue, summarizer, file-read confinement, and count behaviour they cover.
