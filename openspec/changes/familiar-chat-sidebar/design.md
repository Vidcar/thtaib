# Design

## Context

See proposal.md. Chat hides the application sidebar and draws a second rail in `ChatPanel`. Answer branching and regeneration live in the header menu beside effectful retry. Copy is a text button on markdown code only. Project creation is a form on the Projects page. Packet 03's unarchived API-016 lists non-project chats above projects; this change reverses that order and does not close Packet 03.

## Goals / Non-Goals

**Goals:**

- One shared sidebar component used on every page.
- One create-project dialog reused by the sidebar, empty chat, and Projects page.
- Answer actions and block copy use the existing branch and clipboard behaviour.

**Non-Goals:**

- Like, dislike, or share controls.
- Memory selection or extra edit grants in the create dialog.
- Copy icons outside Chat.
- Moving a chat between projects, or changing branch, regenerate, or retry semantics.

## Decisions

- Lift conversation listing into one sidebar rendered by the application shell. `ChatPanel` stops rendering brand, destinations, and service status. Selecting a chat from another page opens Chat and that conversation.
- Pin the no-project group and service status. The destination and project region scrolls. Collapsed mode stays icon-only.
- Create projects through the existing `workspaceApi.createProject` and folder picker. The dialog does not call chat creation.
- Put Copy, Regenerate, and Branch on the last saved assistant message of a run, in both the live feed and the plain transcript. Hide that row while the answer is streaming. Disabled actions keep the backend's unavailable reason. Remove those two actions from the header menu. Retry, edit-the-task, export, and delete stay there, and retry keeps its confirmation.
- One copy-icon button serves answer text, code blocks, tool input and output, and file differences including before and after. Suggested-memory text is unchanged.

Alternatives considered: restyling the chat-only sidebar, and putting Retry on the answer row. Both were rejected because the first leaves two rails and the second makes an effectful action look like an ordinary chat button.

## Risks / Trade-offs

- [Ten destinations crowd a half-height window] → Destinations stay fully visible, the one chat list scrolls, no-project chats stay last, and collapsed mode remains available. Live check covers half-height and collapsed layout.
- [API-016 existed only in unarchived Packet 03] → Packet 03 was archived on 2026-09-22 after Dave closed its final checkpoint. API-016 and API-018 are now current specs, and this change's delta modifies that text.
- [Answer rows on both render paths drift] → Both call the same action component and the same branch API.

## Migration Plan

Desktop-only. No data migration. Rollback is reverting the desktop presentation; stored chats and projects stay valid.

## Open Questions

None.
