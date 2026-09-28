# Proposal

## Why

Agent tool groups repeat their selected count and require a separate small disclosure row to reach individual tools. A single clickable group row makes the existing selection controls easier to scan and use.

## What Changes

- Present each tool group as a compact rounded row with its name, one selected/total count and its existing switch on the right.
- Expand individual tools by clicking the group row, without a group arrow or a separate "Individual tools" heading.
- Keep expansion independent of selection, preserve partial-group switch behaviour, and retain individual switches and information.
- Use the same keyboard-accessible controls for agent creation and editing, retaining bulk actions and existing loading/unavailable states.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `backend-desktop`: Refine the canonical agent tool picker with independent row expansion and group selection.

## Impact

The shared desktop setup editor, its styles and existing editor regressions. Agent tool selections continue through the existing configuration contract; disclosure is local UI state. Backend APIs, schemas, permission enforcement and saved data formats are unchanged.
