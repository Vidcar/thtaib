# Proposal

## Why

The agent loop already runs through Deep Agents, but the specs still leave room to rebuild file tools, diff views, and a second planning list. Chat also paints Setup and conversation actions over the answer, and tool activity is a raw name plus JSON instead of the checklist and one-line file rows people expect while work is happening.

## What Changes

- Name the Deep Agents, LangGraph, and LangChain calls the product loads, and the two file mutations it still owns (`rename_file`, single-file `delete_file`). Ordinary Chat disables the upstream general-purpose `task` tool and the recursive `delete` tool through upstream configuration, not a parent-only hide.
- Require exactly one summarization middleware, using the model's configured usable input budget.
- Replace the covering right-hand cards with one docked column beside the conversation. First pages are Changes and Files. Widening the dock keeps the conversation visible. A narrow window stacks or closes the dock.
- Review recorded file changes in Microsoft Monaco's diff editor. Browse the project tree and open a text file in Monaco's read-only editor. Both are loaded libraries. The app supplies the records and the column.
- Show planning and file activity in the transcript as it happens: one checklist from `write_todos`, and one line per file, search, or shell tool (`Read SKILL.md`, `Edited thistest.md +5 -4`). Line counts come only from the observed before/after diff. Choosing a file line opens that file in the dock.
- Keep Setup as a compact popover that does not consume the transcript. Keep retry, export, and delete in a small header menu.
- **BREAKING** for presentation: a panel that covers the transcript, an expand mode that hides the conversation, and a raw `write_todos` dump as the only planning view no longer satisfy the desktop spec. Detailed tool JSON stays behind the existing detail toggle.

This change writes the contract. It does not implement the desktop or the harness.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `architecture`: Loaded editors and tree widgets are presentation libraries. They are not a second agent, filesystem, or diff engine.
- `backend-desktop`: Docked Changes and Files pages, compact Setup, and the live checklist and activity lines.
- `agents-workflows`: Harness parameters that must be passed through, and the ordinary-Chat exclusions for `task` and recursive `delete`.
- `environments-tools`: The enabled tool catalogue, including the only custom file mutations.
- `state-recovery`: Before/after images are the source for the Monaco diff and for `+N -M`. A pre-rendered diff string is copy text, not a second record.

## Impact

Desktop presentation in `apps/desktop` and the file-read route the Files page needs. New desktop dependencies when implemented: `monaco-editor`, `@monaco-editor/react`, and `react-arborist`, shipped inside the app with no CDN. Existing file-change records, project file listing, tool-call projections, and `write_todos` arguments are the data. No second todo store, no Deep Agents CLI, and no change to llama.cpp, model install, or checkpoint ownership. Open changes `04` through `08`, `compact-workbench-experience`, and `familiar-chat-sidebar` stay as the previous plan; this contract wins where they disagree.
