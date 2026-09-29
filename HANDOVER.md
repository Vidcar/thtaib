# Current handover

Updated 2026-09-30. Broader application stabilisation is implemented and independently reviewed; final acceptance and native delivery are next. Branch `codex/application-stabilisation`, base `74f0e15` (PR #208). [Tasks](openspec/changes/application-stabilisation/tasks.md) and [design/evidence](openspec/changes/application-stabilisation/design.md) are current. Later `lab-workbench` and `consolidate-product-contract` remain unchanged.

Repairs cover exact queued acknowledgements, cancellation/progress, desktop uncertain effects, saved-model revision previews, retained draft conflicts/previews, shared model/agent preparation ownership, independent Chat startup/defaults recovery, and Lab/Browser/attention observation races. Existing owners and framework boundaries are retained. All supported independent review findings are resolved; original-behaviour negative controls fail as intended under `.scratch/stabilisation/`, `.scratch/execution-recovery-audit/` and related evidence directories.

Unchanged-baseline acceptance passed at `74f0e15`: `.scratch/verification/20260929T220441Z-f3a9b4ef/` (1,253 default tests, one symlink skip; 213 integration tests, three Chrome-worker prerequisite skips; desktop build, contracts, OpenSpec). Latest focused reports: 54 backend controls `20260929T225442Z-f35af2b2`, startup reads `20260929T224142Z-0f25704d`, full Chat boundaries/model controls/typecheck `20260929T231921Z-afc655a8`. Final integrated gates are not yet claimed.

No active source writers remain. Root owns final gates/docs/Git; native validation uses isolated `.scratch/` data and the installed 4B model on CPU. Preparation passed real tools, multi-turn and queue/cancel checks; final built Windows validation remains pending.

Preserve live product backend `24156`, Electron `32744`, router `18688`, weights and protected chats; child `21996` exited independently and was never targeted. CI stays disabled; PR #207 workflow/exercises remain unchanged. Three untracked `.vite/` cache files remain after automatic cleanup rejection. `startup-catalogue` was delivered/archived in PR #208. Human UX acceptance is not claimed.
