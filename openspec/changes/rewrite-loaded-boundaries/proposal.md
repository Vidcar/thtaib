# Proposal

## Why

The agent loop already runs through Deep Agents, but the original contract left room to rebuild file tools and a second planning list. Chat also painted Setup and conversation actions over the answer, and tool activity was a raw name plus JSON instead of the checklist and one-line rows people expect while work is happening. The later [Deep Agents simplification](../archive/2026-09-24-upgrade-deepagents-simplify-workbench/proposal.md) retired this change's custom file mutations and Changes view; the deltas here now match the current contract and cannot restore them.

## What Changes

- Name the Deep Agents, LangGraph, and LangChain calls the product loads. Ordinary Chat uses the native file tools and excludes the upstream general-purpose `task` and recursive `delete` tools through upstream configuration, including compiled children.
- Require one Deep Agents summarization middleware with its native model-aware trigger and retention defaults, adjusting only the usable input capacity to avoid double output reservation.
- Replace the covering right-hand cards with one docked column beside the conversation. Setup, Files, Library, and Actions are its pages. Widening the dock keeps the conversation visible, including in a narrow window.
- Browse the project tree and open a text file in Monaco's read-only editor. These are loaded presentation libraries. The app supplies the file read, confinement, and column.
- Show planning and native tool activity in the transcript as it happens: one checklist from `write_todos`, and one line per file, search, or shell call (`Read SKILL.md`, `Edited thistest.md`). A file line opens the current file in the dock without claiming an undoable difference.
- Keep model controls as compact popovers, Setup in the rail, and retry, export, and delete on the Actions page.
- **BREAKING** for presentation: a panel that covers the transcript, an expand mode that hides the conversation, and a raw `write_todos` dump as the only planning view no longer satisfy the desktop spec. Detailed tool JSON stays behind the existing detail toggle.

The completed implementation was later simplified by the linked change. Its current specification and remaining delivery checks are authoritative.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `architecture`: Loaded editor and tree widgets are presentation libraries. They are not a second agent or filesystem.
- `backend-desktop`: Docked Setup and Files pages, compact model controls, and the live checklist and activity lines.
- `agents-workflows`: Harness parameters that must be passed through, and the ordinary-Chat exclusions for `task` and recursive `delete`.
- `environments-tools`: The enabled native tool catalogue, with custom file mutations retired.

## Impact

Desktop presentation in `apps/desktop` and the file-read route the Files page needs. `monaco-editor`, `@monaco-editor/react`, and `react-arborist` ship inside the app with no CDN. Project file listing, tool-call projections, and `write_todos` arguments are the data. No second todo store, no Deep Agents CLI, and no change to llama.cpp, model install, or checkpoint ownership. The archived Deep Agents simplification controls where it supersedes this change.
