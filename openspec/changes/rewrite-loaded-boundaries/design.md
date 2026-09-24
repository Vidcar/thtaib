# Design

## Context

This change originally established a loaded editor and tree, a docked Chat rail, native file tools, and projected planning and tool activity. It was drafted against Deep Agents 0.7.15. The later [Deep Agents simplification](../archive/2026-09-24-upgrade-deepagents-simplify-workbench/design.md) upgraded the integration to 0.7.18 and retired the Changes page, per-edit capture/reverse, custom rename/delete, and activity counts derived from file differences. The deltas in this active change now reflect that current contract.

## Goals and boundaries

- Keep one bounded rail beside the conversation and composer, including at half-screen width.
- Load the existing project listing through a tree widget and read permitted text files in the packaged Monaco editor without invoking the model.
- Render one `write_todos` checklist and one identity line per native tool call from projected stream data, visible even when detailed streams are hidden.
- Offer Deep Agents' selected built-in file tools while excluding the general-purpose `task` and recursive `delete` tools from ordinary Chat and compiled children.
- Keep one Deep Agents summarization middleware with native model-aware defaults, adjusting only its usable input capacity, without an application copy of the agent loop or todo state.

The rail pages are Setup, Files, Library, and Actions. Compact model controls remain near the composer. The rail does not overlay or hide the answer. File and tool rows open the current file when available; they do not claim a stored difference or an undo operation.

## Decisions

### File reading and presentation

The Files page uses `react-arborist` over the existing one-directory project listing. Selecting a text file uses a read-only project-file request with the same confinement as that listing: inside the project, no links, and no framework routes. The request does not call the model. `@monaco-editor/react` presents the text, with workers packaged inside the desktop app. Images keep the existing preview, and retained copies remain labelled separately from live files.

The dock owns layout only. Application services own project identity, path checks, file reads, and durable records. No renderer projection becomes an execution or filesystem authority.

### Activity from native tool calls

`write_todos` renders the latest successful parsed argument list for the turn. A later successful call replaces it; a failed call leaves it in place and shows the failure. Raw arguments remain behind a further disclosure. The product does not read private graph todo state or keep a second todo store.

Other filesystem, search, shell, MCP, and memory calls keep a line keyed by their actual call identity. Unfinished calls use present-tense verbs, finished calls use past tense, and failed or partial calls remain visibly distinct. Consecutive successful calls with the same verb may collapse into a summary that opens to the original calls. The first expansion shows the path, command, output, or short result; internal tool names and raw arguments stay on a further disclosure. File rows may open the Files page on the current file. Counts and differences are not inferred from tool prose or displayed without a record.

### Native tool catalogue

Deep Agents owns `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep`. Ordinary Chat excludes the general-purpose `task` and upstream recursive `delete` at the upstream profile or middleware catalogue, including a compiled child. Custom rename/delete are retired. `execute` is offered only when the selected host shell is attached. The application keeps actual path and access enforcement, not a duplicate filesystem tool implementation.

## Risks and verification

- Package Monaco workers and tree assets locally; the desktop build must not require a CDN.
- Show a checklist only after streamed `write_todos` arguments parse; partial input remains labelled partial.
- Verify a file read refuses paths outside the selected project, links, and framework routes.
- Inspect the tools offered to the model and compiled children, rather than relying on a parent-only hide.
- Verify one Deep Agents summarization middleware uses its native defaults with the configured input budget and no custom early trigger or additional shrink.

The original diff and reverse tasks were completed historically but superseded by the linked simplification. Current specs and its completed checks define the behavior to retain. The clean data reset requires no migration for discarded change records.
