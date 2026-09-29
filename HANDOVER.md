# Current handover

Updated 2026-09-30. Application stabilisation is implemented and independently reviewed on `codex/application-stabilisation`, base `74f0e15` (PR #208). [Tasks](openspec/changes/application-stabilisation/tasks.md) and [design/evidence](openspec/changes/application-stabilisation/design.md) hold the current scope. Later `lab-workbench` and `consolidate-product-contract` remain unchanged.

Repairs cover queue acknowledgement/cancellation/progress, desktop uncertainty, model revision previews and retained draft conflicts, model/agent selection ownership, independent Chat reads, and Lab/Browser/attention observation races. Native validation additionally exposed initial Models hydration discarding accepted edits and claiming Not loaded before observation. That repair now establishes saved authoring readiness separately from engine checks; five mounted cases, negative controls and fresh-context review are clear. Final focused reports: `20260929T235650Z-5f2fe8e1`, `20260929T235544Z-7a7a83f6`.

Backend default 1,266 tests (one symlink skip), integration 213 (three Chrome-worker skips), contracts/specs passed in `20260929T232443Z-ca98eec5`. A premature test action was repaired without production change; desktop/spec passed in `20260929T234105Z-0a322898`. The later Models repair requires a replacement desktop/spec acceptance build.

Pre-repair built native cold/outage/restore, full/half/125% geometry, Electron keyboard events and installed 4B CPU tools/multi-turn/queue/cancel passed. OS/Sky input verification is unavailable because desktop composition/coordinate capture fails. Failed Models evidence remains under `.scratch/stabilisation/native/final-20260930-002455/`; successful Chat/keyboard evidence under `final-electron-keyboard-1790725927726/`. Owned test processes are cleaned up. Root owns final rebuild, native rerun, PR/merge, local delivery and archive; no source writers remain.

Preserve product processes, weights and protected chats. CI and PR #207 workflow remain unchanged. Three untracked `.vite/` cache files remain after automatic cleanup rejection. `startup-catalogue` was delivered/archived in PR #208. Human UX acceptance is not claimed.
