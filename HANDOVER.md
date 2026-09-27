# Current handover

Updated 2026-09-27. Chat reader repair is in progress on `codex/fix-chat-file-reader`, based on `57605cb`. Active change: [fix-chat-file-reader](openspec/changes/fix-chat-file-reader/tasks.md).

The harness now adds restricted framework paths only when `read_file` is not selected. Middleware uses the same distinction for authorization and the model-facing description, so knowledge search no longer narrows selected project reading. Native Deep Agents reading, project containment, projectless permissions and tools-off remain intact. No public API, schema, dependency, UI or model-setting changes.

Checks passed: backend default 954 (one existing skip), integration 203, seven focused reader/retrieval tests, OpenSpec and whitespace. An isolated Chat on the existing loaded Qwen completed two turns, including both JavaScript filename forms, project HTML and retrieved-evidence reads; all six calls succeeded and outcomes survived reopening. Model/router process identities, residency and settings were preserved. Evidence: `.scratch/chat-file-reader-validation/report.json`.

Next: complete Git/PR delivery, refresh only the idle established backend, verify saved chats/drafts and model state, then archive the focused change. Preserve unrelated work; do not replay failed production turns.

Previous deliveries remain complete: [PR175](https://github.com/Vidcar/thtaib/pull/175), Windows UTF-8 entrypoints and narrow grep/read decoding recovery; [PR174](https://github.com/Vidcar/thtaib/pull/174), prompt continuity and inference performance. Prior evidence: `.scratch/windows-text-decoding-validation/report.json` and `.scratch/windows-text-decoding-refresh/after.json`. Existing model profile uses q8 K/V, batch 2048, ubatch 1024, MTP draft max 2 and 98,304 context.

Preserve unrelated untracked Lab/archive files and prior worktree `C:\Users\Dave_\.codex\worktrees\reliable-chat\thtaib`.
