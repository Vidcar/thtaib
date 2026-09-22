# Proposal

## Why

Chat draws a second sidebar and hides everyday answer actions inside a conversation menu. People expect one left rail, with projects as folders and copy, regenerate, and branch beside the answer they apply to.

## What Changes

- Use one collapsible sidebar on every page: destinations stay fully visible, then one list of named project folders with their chats, then chats that have no project.
- Add a project from that sidebar, an empty chat, or the Projects page with a name and one existing folder. Creating a project does not grant extra edit permission or choose memory.
- Show Copy, Regenerate, and Branch on each saved assistant answer. Leave Retry task, edit-the-task, export, and delete in the conversation menu, with confirmation before effectful retry.
- Use one small copy icon on chat code blocks, tool input and output, and file differences.
- This replaces the unarchived Packet 03 sidebar order that lists General chats above projects. It does not complete Packet 03 or Packet 04.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `backend-desktop`: API-016 sidebar order, single rail, and project creation; API-018 answer-action placement and chat copy controls.

## Impact

Desktop presentation in `apps/desktop` only. Existing project, branch, regenerate, and retry APIs stay in place. Chats remain permanently scoped to their original project or the non-project area. Packet 03 remains open.
