# Tasks

## 1. Adopt the native Deep Agents behavior

- [x] 1.1 Raise the Deep Agents minimum and refresh `uv.lock` to 0.7.18 after checking the release notes and installed source; verify the resolved version and backend import.
- [x] 1.2 Remove custom Knowledge refresh; set native skill reload state on new user turns only, including deselection, and verify changed skills load while approval resumes keep their checkpoint state.
- [x] 1.3 Freeze exact memory versions at the first conversation turn or branch checkpoint, refuse later changes before dispatch (including queued turns), and show pinned versions; verify a new chat sees an edited version.
- [x] 1.4 Require valid native `SKILL.md` on create, edit and import, provide a starter template, reject mismatched name/description and collisions, and preserve package content without running scripts; verify focused Knowledge tests.

## 2. Simplify execution and interruptions

- [x] 2.1 Remove Workbench's structured-output repair call and attempt field while retaining strategy selection and final schema validation; verify invalid output fails without a second model/tool turn.
- [x] 2.2 Unify typed `ask_user` and protected tool actions into one native ordered HITL decision batch; verify valid/invalid/stale mixed responses, saved grants, cancellation and restart.
- [x] 2.3 Remove Approve for me and the unused read-only shell/parser and placeholder permission rules; verify Ask pauses all ungranted shell/effectful actions, Full applies only to enabled tools, and Plan mode still blocks effects.
- [x] 2.4 Remove custom rename/delete tools and retain native file tools, project confinement and actual skill write protection; verify same-path concurrent edits are rejected and malformed named-helper `task` arguments fail.
- [x] 2.5 Remove the custom early summarization threshold and use Deep Agents' native model-aware trigger and retention defaults, retaining only the input-budget adjustment; verify the resolved summarizer settings and compaction behavior.

## 3. Retire fragile UI and change capture

- [x] 3.1 Remove per-edit file-change capture/reverse and its endpoints without touching project snapshots or durable run outcomes; verify file tools, branching and recovery use their remaining owners.
- [x] 3.2 Remove Changes dock/routes, reverse controls and file-difference/count claims; keep Files and ordinary tool activity, and verify the desktop build and narrow Chat layout.
- [x] 3.3 Remove Steer while keeping separate Stop and queue behavior; verify success advances the queue, cancellation/failure pauses it, and navigation does not submit or retarget a draft.

## 4. Contracts, reset and delivery

- [x] 4.1 Prepare the affected OpenSpec deltas for current-spec sync at archive, update the overlapping `consolidate-product-contract` skill-import task, and refresh README and pinned upstream references; verify `openspec validate --all`.
- [x] 4.2 Verify each authorized deletion target and link, stop the established app, clean-reset disposable app data and the six approved linked project folders while retaining weights/staging/cache/runtimes, then register a fresh Qwen3.8 setup; verify a clean first launch.
- [x] 4.3 Run the full backend and integration suites, contract freshness check and desktop build; verify clipped-result notices, supported attachment MIME and UTF-8 byte sizes without an unplanned compatibility path.
- [x] 4.4 Run a real Windows Qwen3.8 model/tool turn and desktop mixed question/approval flow; verify skill reload, fixed memory, invalid structured output, Ask/Full and Stop/queue behavior with focused Windows integration tests.
- [ ] 4.5 Refresh the handover, review the complete diff, prepare Git delivery and update the local app; verify the resulting installation is usable.
