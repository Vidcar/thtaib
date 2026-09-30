# Current handover

Updated 2026-09-30. Application stabilisation is on `codex/application-stabilisation`, base `74f0e15` (PR #208). [Tasks](openspec/changes/application-stabilisation/tasks.md) and [design/evidence](openspec/changes/application-stabilisation/design.md) hold scope and proof. Later `lab-workbench` and `consolidate-product-contract` remain unchanged.

Reviewed repairs cover queues, desktop uncertainty, model revisions/draft conflicts/initial hydration, selection ownership, independent Chat reads and Lab/Browser/attention ordering. Isolated negative controls detect the original defects. Built Windows testing found and drove the additional Models hydration and Quit repairs.

Quit now joins actual workers, passively reconciles terminal queues and stops owned engines through the existing lifecycle owner while preserving paused input/settings/tombstones/uncertainty. Ordinary stop/reload guards and connected engines remain protected. Seven new route cases and existing controls pass: final focused gate `20260930T001857Z-5c2d913b`, 83 tests. Fresh independent review is clear; exact hashes are in `.scratch/stabilisation/queue-review/shutdown-reviewed-hashes.json`. Backend writer is frozen.

Earlier full backend default 1,266 tests and integration213 passed with four environment skips; desktop/spec acceptance and actual Windows/model flows passed at `8da0236`, except native Quit409. That defect is fixed but replacement full shared/spec acceptance and actual native clean shutdown remain required. Root owns commit/freeze, gates, native rerun, PR/merge/local delivery and archive; no PR yet. Native helper requires normal200/no forced cleanup and exact retained records after exit.

Product processes/weights/protected chats remain preserved. OS/Sky input is unavailable due desktop composition; Electron keyboard events passed separately. CI and PR #207 workflow remain unchanged. Three untracked `.vite/` cache files remain after automatic cleanup rejection. `startup-catalogue` is delivered/archived in PR #208. Human UX acceptance is not claimed.
