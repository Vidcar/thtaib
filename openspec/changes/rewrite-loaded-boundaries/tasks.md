# Tasks

The completed work was reconciled with the later [Deep Agents simplification](../archive/2026-09-24-upgrade-deepagents-simplify-workbench/tasks.md). Custom rename/delete, the Changes page, and per-edit counts were subsequently retired; the checked tasks below describe the behavior that remains.

## 1. Harness catalogue

- [x] 1.1 Disable the general-purpose subagent for ordinary Chat through the upstream profile switch, and drop recursive `delete` through the upstream exclusion or filesystem tool list. Verify a compiled child cannot call `task` or `delete`, with a backend test that inspects the tools the model is offered.
- [x] 1.2 Keep one Deep Agents summarization middleware using native model-aware defaults, with only the narrow usable-input adjustment. Verify a long scripted turn does not stack another summarizer or a custom early trigger.
- [x] 1.3 Confirm the native `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep` tools are not re-registered and custom rename/delete are absent. Verify with the catalogue test.

## 2. Project file read

- [x] 2.1 Add a read-only project-file read with the same confinement as the directory listing, published through the shared contract generator. Verify path escape, link, and framework-route cases are refused, and a normal text file returns its captured text without invoking the model.

## 3. Dock

- [x] 3.1 Replace covering conversation cards with the dock column, its Setup and Actions pages, and compact model controls. Verify opening the dock narrows the transcript without covering or hiding the answer.
- [x] 3.2 Keep the dock beside the transcript and composer when the conversation column is narrow. Verify they remain usable at about half-screen width.

## 4. Monaco and the tree

- [x] 4.1 Add `monaco-editor`, `@monaco-editor/react`, and `react-arborist`, with Monaco's workers loaded from the desktop package. Verify the production build contains those assets and does not request a CDN.
- [x] 4.2 Retire the Changes page and reverse controls after the later simplification; keep the Files page's loaded editor. Verify the dock no longer presents an undoable difference.
- [x] 4.3 Build the Files page tree from the existing directory listing, a name filter, the read-only editor, the existing image preview, and labelled retained copies. Verify opening a text file does not call the model and a retained copy stays distinct from the live file.

## 5. Checklist and activity lines

- [x] 5.1 Render one `write_todos` checklist per turn from the latest successful tool-call arguments, visible with detailed streams off. Verify a second successful call replaces the list, a failed call keeps the previous list, and raw arguments stay behind expand.
- [x] 5.2 Render one activity line per native file, search, shell, MCP, and memory call without invented change counts. Verify "Read SKILL.md" and a completed edit have truthful labels, and choosing a file line opens the current file without sending a message.

## 6. Checks

- [x] 6.1 Run `openspec validate --all` from the repository root and the desktop build from `apps/desktop`. Verify both pass.
- [x] 6.2 Run the focused backend harness and file-confinement tests from `apps/backend`. Verify the catalogue, summarizer, and file-read confinement they cover.
