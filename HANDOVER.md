# Current handover

Updated 2026-09-27. Windows Chat text-decoding repair is complete and locally delivered. [PR175](https://github.com/Vidcar/thtaib/pull/175) records branch `codex/fix-windows-chat-text-decoding`, implementation `75a09e4`, base `8ba971b`. Completed change: [fix-windows-chat-text-decoding](openspec/changes/archive/2026-09-27-fix-windows-chat-text-decoding/tasks.md).

The Windows shortcut and both backend entrypoints enable UTF-8 before application import. Native Deep Agents 0.7.19 searches are retained. Host commands retain Windows locale decoding. Only grep/read_file decoding failures become identity-preserving failed tool results that let Chat continue. No model, dependency, public API, schema or UI changes.

Checks passed: backend default 949 (one existing skip), integration 201, native Unicode searches through filesystem/shell/routed backends with exact characters and limits, real Windows entrypoints and Restart/Quit, synchronous/asynchronous tool recovery and retained sibling outcomes, OpenSpec and whitespace. Isolated actual Qwen Chat completed Unicode search and a failed read alongside a successful read; results survived backend reopening. The original read-only paint search returns four matches and its source is unchanged. Evidence: `.scratch/windows-text-decoding-validation/report.json`.

Normal shortcut recovery refreshed idle backend PID28644 to UTF-8 backend PID4916. Saved chats and draft content, original failed run, desktop/router/model processes, residency and model settings were preserved; no failed turn was replayed. Evidence: `.scratch/windows-text-decoding-refresh/after.json`. No outstanding implementation or local delivery work.

Previous performance delivery remains complete: [PR174](https://github.com/Vidcar/thtaib/pull/174), [archived tasks](openspec/changes/archive/2026-09-27-improve-agent-inference-performance/tasks.md). Existing profile uses q8 K/V, batch 2048, ubatch 1024, MTP draft max 2 and 98,304 context. Preserve unrelated untracked Lab/archive files and prior worktree `C:\Users\Dave_\.codex\worktrees\reliable-chat\thtaib`.
