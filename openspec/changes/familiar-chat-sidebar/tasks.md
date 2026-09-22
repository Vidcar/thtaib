# Tasks

## 1. Shared sidebar

- [x] 1.1 Replace the chat-only rail and the page rail with one sidebar that shows destinations, project folders with their chats, and pinned no-project chats. Verify Chat and another page share that rail, and selecting a chat opens it.
- [x] 1.2 Add a name-and-one-folder create dialog and open it from the sidebar, empty chat, and Projects page. Verify a created project appears in the sidebar and does not start a chat.

## 2. Answer actions and copy

- [x] 2.1 Show Copy, Regenerate, and Branch on saved assistant answers in both chat render paths, and remove those two actions from the header menu. Verify a streaming answer has no row, an unavailable action stays disabled with its reason, and Retry still asks before it runs.
- [x] 2.2 Use one copy icon on chat code blocks, tool input and output, and file differences. Verify the word Copy is gone from code blocks and suggested-memory text has no copy icon.

## 3. Check

- [x] 3.1 Rebuild the desktop and exercise the running app at full and half height, including a collapsed sidebar. Verify the layout, create dialog, copy icon, and answer actions on disposable chats. Do not treat existing green tests as acceptance.
- [x] 3.2 Align Packet 03's unarchived API-016 and API-018 text with this change and validate OpenSpec. Verify `openspec validate --all` passes and Packet 03 is not archived.
