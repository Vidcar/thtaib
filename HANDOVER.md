# Current handover

Updated 2026-09-27. Chrome Browser rail is complete, merged in [PR177](https://github.com/Vidcar/thtaib/pull/177), and refreshed in the established application. [Archived change](openspec/changes/archive/2026-09-27-embed-chrome-browser-in-chat/tasks.md) and affected main specs contain the completed contract. No feature work remains.

Browser access now uses actual background Chrome shared by official MCPAdapter and the interactive Chat rail. Start/first browser action launches it; each chat retains its own sign-ins. Close preserves them, confirmed Reset clears them, and chat deletion confirms termination before profile removal. Take control pauses root/helpers; Return refreshes page evidence and rejects stale actions while preserving approvals and Stop. Viewport presets/custom sizing, scaled input, tabs, dialogs, confined uploads and retained Library downloads are available. Sensitive-profile backup is explicit.

Validation: backend default 977 tests OK (one existing skip), integration 206 OK, final focused backup/browser 20 OK; desktop build and mounted/native checks passed; shared contracts fresh; OpenSpec and whitespace passed. Actual Chrome tested forms, scrolling, drag, popups/duplicate tabs, dialogs, files, isolated persistent cookies and cleanup. Three uninterrupted loaded-model turns and separate generation takeover passed. Full native production App verified phone layout, scaled click, reconnect and equivalent API/rendered transcript after reopening. Owned Chrome had zero visible Windows windows.

Normal backend refreshed to PID34828 using existing shortcut recovery; desktop/model/router process identities, settings, residency and saved chat/draft/run hashes were preserved. Installed worker/Chrome readiness and real phone layout/live frame/cleanup passed. Isolated UAT's thirteen owned processes stopped. Evidence is under `.scratch/chrome-chat-validation` and `.scratch/chrome-chat-refresh` in worktree `C:\Users\Dave_\.codex\worktrees\chrome-chat-browser\thtaib`.

Preserve unrelated Lab/archive files and prior `reliable-chat` worktree. [PR176](https://github.com/Vidcar/thtaib/pull/176) file reading remains delivered.
