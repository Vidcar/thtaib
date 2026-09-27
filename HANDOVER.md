# Current handover

Updated 2026-09-27. Chrome Browser rail implementation is validated on `codex/embed-chrome-browser-in-chat`, worktree `C:\Users\Dave_\.codex\worktrees\chrome-chat-browser\thtaib`. [Delivery checklist](openspec/changes/embed-chrome-browser-in-chat/tasks.md) has only Git/local refresh/archive outstanding.

Implemented: actual background Chrome shared by official MCPAdapter and typed rail controls; per-chat sign-ins, confined uploads/retained downloads, confirmed owned-process lifecycle; private authenticated management and bounded live frames; native whole-task/helper takeover, stale-action rejection, approvals and Stop; interactive Browser rail with viewport, scaled input and sign-in-preserving lost-session Close; sensitive-profile backup opt-in. Main capability specs are synchronized.

Validation passed: backend default 977 (one existing skip), integration 206, final focused backup/browser 20; thirteen native graph handoff checks; real Chrome forms, scrolling, drag, popup/duplicate tabs, dialogs, files, cookie isolation/persistence and process cleanup; final desktop build including mounted/native Electron checks; shared-contract freshness; OpenSpec 14 items; whitespace. Three uninterrupted loaded-model turns and separate generation Take/Return passed. Full production App in native Electron verified 390×844 layout, scaled click, Take/Return, rail reconnect and identical six-message/three-run API/rendered transcript hashes after reopening. Owned Chrome had zero visible desktop windows.

Next: confirm isolated UAT cleanup, commit/push/PR/merge, refresh the established application and optional worker, verify installed real Chrome, then archive and finish delivery notes. Evidence: `.scratch/chrome-chat-validation`; refresh: `.scratch/refresh-chrome-chat.py`. Preserve saved chats/drafts, weights, model settings/residency/PIDs and previews.

[PR176](https://github.com/Vidcar/thtaib/pull/176) file reading remains delivered. Preserve unrelated Lab/archive files and prior worktree `C:\Users\Dave_\.codex\worktrees\reliable-chat\thtaib`.
