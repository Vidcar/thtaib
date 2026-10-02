# Tasks

## 1. Remove retired copies and stores

- [x] 1.1 Remove Lab case capture, restore, and recorded-tool replay routes and the unused case screen, and verify a backend test shows those routes are gone while Performance, Memory, and Challenges still load.
- [x] 1.2 Remove the project-tree copy taken before and after a run, and verify a backend test starts a second chat in the same folder without waiting for a copy and without the app creating a git branch or worktree to separate the second chat.
- [x] 1.3 Remove application backup and restore, including the Settings Backup section and any option to include browser sign-ins, and verify the Settings test shows Appearance, Notifications, Defaults, Connections, and Permissions, and no Backup section.
- [x] 1.4 Remove stored copies of the model request, the redaction setting, and the paste-a-capture box, and verify a backend test sends a chat turn without writing a request body while the partial output and error of a failed stream remain.
- [x] 1.5 Leave Deep Agents compaction scratch and large tool results under the product data root, and verify a test shows that scratch is not in the project folder and is not served as a request inspector.

## 2. Keep the existing engines

- [x] 2.1 Keep one Deep Agents agent and one summarization middleware with its own trigger and keep fractions, fed the live context size, and verify a test does not add a second summarizer or an earlier size rejection.
- [x] 2.2 Map the Deep Agents context-overflow error to the existing capacity failure, with the chat left in place and no branch offered, and verify that test.
- [x] 2.3 Keep project file tools as the Deep Agents filesystem tools, keep the exact multi-hunk tool beside edit, and keep delete as the upstream delete tool, and verify a harness test registers no second tool of the same name.
- [x] 2.4 Keep the shell as LocalShellBackend, with the existing job tools beside it, and verify a project-free This-computer command starts in the resolved user profile and a skill script without a project fails.
- [x] 2.5 Keep the thin middleware and shell subclasses under their library names, and verify the harness test still sees FilesystemMiddleware, MemoryMiddleware, SkillsMiddleware, and LocalShellBackend rather than a second copy.
- [x] 2.6 Send Thinking and sampling through the existing llama.cpp request fields, and verify a chat Thinking change does not reload the model or change the saved setup.

## 3. Permissions, windows, and file order

- [ ] 3.1 Show one card the first time This computer is used in a chat, including Full access, store the resolved starting folder, and verify an Ask test pauses later commands unless the exact command and folder match, that another chat's Always allow does not skip that first card, and that Reject does not confirm This computer.
- [ ] 3.2 Keep the standing project-edit grant until revoked, always excluding `.git`, starting with secret files excluded, and excluding delete, and verify an excluded-file card can allow that one edit without growing the grant, and that Approve once, Allow for this session, and Always allow each allow only that edit so a later identical edit pauses again.
- [ ] 3.3 Let Delete, when switched on, remove `.git` or a secret file with no card in Full access, still refusing the project root, an escaping link, and a tree too large to inspect, and verify that test.
- [ ] 3.4 Replace the project-wide file lock with per-file order, and verify two writes to different files proceed while a second write to the same file waits, and the waiter does not block the writer.
- [ ] 3.5 Hide and refuse the app's own windows and elevated windows for One window, and verify a message still sends before a window is picked.
- [ ] 3.6 Keep helpers to the shared ticks, the parent's window, and the same starting folder, and verify a test that a helper cannot turn on a tool the parent does not have.

## 4. Rewind, transcript, and memory

- [ ] 4.1 Remove Regenerate and Branch, and implement Retry and Edit as a public checkpoint rewind on the same chat, and verify a test that an accepted edit removes later messages and waiting follow-ups without creating a second chat or restoring files.
- [ ] 4.2 Leave messages in place when the rewind cannot start, and verify a running turn disables Retry and Edit with the reason on hover.
- [ ] 4.3 Download a Markdown transcript of messages, one shown activity line per tool, and retained file names, and verify the file has no thinking text, no full tool output, and a line that it is not a restore, and that advanced JSON export is not offered.
- [ ] 4.4 Make every memory suggestion wait for Accept or Reject, and verify Full access and an approval card do not write a memory, while an accepted memory still loads through the official memory parameter.

## 5. Screens

- [x] 5.1 Use one model menu on Chat and the one-task page, with the model's Thinking levels and a context slider, and verify the desktop check shows no tuning icon and no Apply or Stage button.
- [x] 5.2 Show a known quantization token even when a dot precedes it, and verify `Qwen3.5-0.8B.Q4_K_M.gguf` displays that token and an unknown name stays unknown.
- [x] 5.3 Keep the ten named checks, retest only the clicked check, and leave all ten results in place when sampling or answer length changes, and verify a saved Thinking change drops only Thinking and Thinking history.
- [x] 5.4 Say a resources-only connection is ready and has no tools, and verify the connections screen does not say "0 tools ready".
- [x] 5.5 Apply the short label-and-value rule on the changed screens, with explanation on hover or focus, and verify Chat, the one-task page, Settings, and the project-edit screen in the desktop check.
- [x] 5.6 Keep Lab and Workflows on the primary sidebar, do not name Lab Measurements or a future suite, and verify the desktop check shows that.

## 6. Delivery check

- [ ] 6.1 Run the affected backend tests and the desktop build through the repository verifier for the scopes this change touches, and record the command and result. Do not treat that run as live desktop acceptance.
