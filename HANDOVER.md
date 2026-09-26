# Current handover

Updated 2026-09-26. New chat scope fix is complete, locally built and delivered in [PR170](https://github.com/Vidcar/thtaib/pull/170), branch `codex/new-chat-no-project` in `D:\CodeProjects\thtaib`. Main New chat opens outside projects; project + opens its first composer; model/agent selection and departing drafts are retained. Full desktop build/regressions, OpenSpec14/14 and diff check pass. Native Windows check used the rebuilt renderer and live backend in a separate test window, verified both launch paths and retained model, and created no test records. The growing native-viewer suite's overall deadline is now60 seconds; its assertions are unchanged. Existing app window has unsaved MainAgent edits: preserve it; save/discard those edits and refresh with Ctrl+R to apply the rebuilt UI. No implementation work remains.

Prior Reliable Chat delivery is complete and deployed; [PR168](https://github.com/Vidcar/thtaib/pull/168) merged as `b38d847`, archive/handover [PR169](https://github.com/Vidcar/thtaib/pull/169) as `ac81727`. Acceptance details: [archived change](openspec/changes/archive/2026-09-26-reliable-chat-and-context/tasks.md). Managed worktree: `C:\Users\Dave_\.codex\worktrees\reliable-chat\thtaib`, branch `codex/reliable-chat`.

Prior validation: backend default918 tests (one symlink-privilege skip), integration194 passed; desktop/shared-contract checks passed. Live Windows acceptance covered writes/recovery, restart/queues/helpers, context, preview, documents and memory. Game/helper follow-up passed35 executable checks and full-route gameplay.

Normal app/backend8000 are running; Start Menu points to main. Balanced configuration `profile_51bc5a976fe8` is default: medium,2048 thinking,8192 output. Prior native response confirmed those limits. Original publisher Thinking revision3, weights and model processes remain untouched.

Limitations: one Qwen answer was stale despite correct context. Approval review blocked isolated `outline-probe/.git` cleanup; leave it. Prior evidence remains in worktree `.scratch/reliable-uat/`. Unrelated Lab proposal and archived model-spec files remain untracked and untouched.
