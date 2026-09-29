# Current handover

Updated 2026-09-29. Lean engineering implementation is complete on `codex/lean-engineering` (base `ada3476`); PR delivery is pending. The active tooling change is `openspec/changes/lean-engineering/`.

Installed: concise AGENTS routing, four portable development-only skills, and `scripts/verify.py` over the existing checks. Example from root: `uv run --project apps/backend python scripts/verify.py --tier acceptance --scope desktop`. Scopes are additive; default is all. Temporary reports and exercises stay under `.scratch/`.

Pilot: the shared model-tuning control now applies a successfully loaded candidate even if status refresh fails, and offers observation-only retry. Lab/Agent run have rejecting refresh callers; Chat catches refresh errors itself. Existing model-choice semantics remain distinct. Regression tests prove recovery and reject late results for another chat.

Validated: all-scope acceptance passed backend default (1,253 tests, one symlink-privilege skip), integration (213 tests, three missing Chrome-worker prerequisite skips), desktop build, shared contracts and OpenSpec. Four skills pass metadata validation. Fresh Codex root/backend/desktop and portable exercises covered discovery, explicit/natural selection, distinct semantics, false-green tests, old-build evidence and trivial editing. Fifteen deliberate runner/pilot violations were detected. Independent review passed, including the subsequently strengthened plan-only test; all 13 runner tests were rerun afterward. Evidence is under `.scratch/verification/` and `.scratch/engineering-skills/`.

No model load or application restart; the existing window is not live evidence for the new build. Broader stabilisation has not been completed. Preserve `consolidate-product-contract`, `lab-workbench`, `startup-catalogue`, weights and ScratchArea/ScratchProject chats. Older cleanup context remains in PRs #199–206/history, not this task's scope. Next: archive this completed tooling work and deliver the PR.
