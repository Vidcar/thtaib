# Tasks

## 1. Configuration and runtime

- [x] 1.1 Reproduce known default, inheritance, duplicate configuration and port-conflict defects with production boundaries; retain the failing cases as regression evidence.
- [ ] 1.2 Implement versioned model defaults/variants using existing storage and an idempotent quiet migration; verify exact effective settings, instructions, historical snapshots, weights and ScratchArea records survive.
- [ ] 1.3 Extend the shared setup resolver with source/default/support/reset/reload facts; verify all controls display the same values the run and captured request use, including explicit empty/default/reset and stale responses.
- [ ] 1.4 Add coordinated reconfiguration and launch-time port allocation/preflight; verify idle continued Chat, expected revisions, history fit, all durable consumers, ownership, failure restoration and restart reconciliation.
- [ ] 1.5 Replace primary preset/deployment controls with canonical model configurations in Models, Chat, Agents, project/application defaults, Lab and Workflows; verify Save changes, Save as variant, local Apply and Save to model are distinct and non-duplicating.

## 2. Access and agent capabilities

- [x] 2.1 Implement Ask/Approve for me/Full access semantics and truthful inherited access; prove receiver-side mutations, recovery coverage, saved-grant attribution and disabled-tool enforcement.
- [x] 2.2 Implement frozen Work/Plan mode and backend read-only enforcement across ordinary/restored/child calls; prove prohibited actions have zero effects even under Full access, while authorized reads/questions/planning work.
- [x] 2.3 Implement selected frozen named helper versions through shared enforcement and upstream delegation; verify authority intersection, no recursive/general helper, named streaming/approvals, shared cancellation and model resource admission.
- [x] 2.4 Implement opt-in read-only rubric review with visible criteria and at most two revisions; verify no reviewer call when off, no reviewer side effects, genuine distinct judgement and visible limit reached.
- [x] 2.5 Enforce explicit atomic shared tool-call budgets and remove accepted-but-unused review semantics; verify concurrent child calls cannot overspend and unset limits remain unset.

## 3. Stable conversation and shared controls

- [ ] 3.1 Reproduce and remove composer/menu/telemetry jumps using stable overlays, reserved measurement width and compact attachments; verify rendered geometry, scroll position, Escape/focus and long labels.
- [x] 3.2 Restore conversation, draft, attachments and reading position across destinations; verify explicit New chat alone resets state and sidebar/header titles agree.
- [ ] 3.3 Implement truthful thinking toggle/effort/context controls and local apply/reload; verify actual supported defaults, unavailable reasons and dispatched settings.
- [ ] 3.4 Expose Work/Plan, selected helpers and optional review without a wall of switches; verify next-turn scope and immutable submitted/queued settings.
- [ ] 3.5 Group adjacent finished successful activity while preserving every identity; verify live/failed/waiting separation, result-first disclosure, checklist marks, incoming turn and saved permissions.
- [x] 3.6 Group a file's changes without merging recorded differences and make editor failures actionable; verify actual packaged editor/worker loading and selecting/reversing the exact edit.

## 4. Existing surfaces

- [ ] 4.1 Move project settings/files/lifecycle into rail context and remove redundant destination; verify removal versus deletion, file ownership and context navigation.
- [ ] 4.2 Use compact Models/Agents list-detail editors with useful descriptions, sources and actionable disabled controls; verify create/edit/save/apply/reopen and failure paths.
- [ ] 4.3 Make Knowledge, Library/files and Attention dense and purposeful; verify versions/proposals/skills, source previews/reuse/deletion and correctly owned attention actions.
- [x] 4.4 Organize Settings by direct categories, compact basics and deliberate advanced appearance/preview; verify saved customization, Apply/Cancel/Reset and preview with guides initially off.
- [ ] 4.5 Repair current Lab and Workflows actions using shared settings/access/results; verify each existing visible action and failure/retry without claiming the deferred suite/canvas complete.
- [ ] 4.6 Verify responsive bounded layouts, both themes, narrow/full/ultrawide windows, Windows scaling, keyboard access and no horizontal overflow or layout shift across all surfaces.

## 5. Delivery gates

- [ ] 5.1 Run backend default and integration suites, desktop build, generated-contract freshness and strict OpenSpec validation; retain meaningful permission/process/recovery regressions and replace obsolete markup assertions.
- [ ] 5.2 Complete native file picker/Explorer drop, retained document/diff, real-model reasoning/tool/context, Plan/helper/review/cancellation and recovery journeys in isolated roots; record actual outcomes separately from mocks/builds.
- [ ] 5.3 Review every visible function against its real effects, repair discovered defects and reconcile all change artifacts; no checked task may represent partial/deferred work.
- [ ] 5.4 Deliver the validated branch/PR and established local desktop/backend, obtain remaining visual acceptance, then merge/archive only when gates pass; refresh HANDOVER.md with verified state and any concrete next step.

## Implementation evidence (acceptance still in progress)

- Reproductions: null inherited access displayed Ask while dispatch inherited Full; literal Qwen template default xhigh hidden; duplicate saved runtime records shared port8080; open composer details changed trigger geometry; leaving Chat cleared selection. Backend/component regressions now exercise these boundaries rather than obsolete markup.
- Backend default684 and integration166 pass on a1de934, including canonical origin/migration, interrupted-runtime recovery, immutable Lab/helper requirements and receiver-side access boundaries. Generated contracts match. Strict OpenSpec:14 passed,0 failed. Full desktop build passed before the latest acceptance fixes; final build pending.
- Real CPU Gemma: launch-time automatic port avoided occupied8080; owned4096 context became8192 in an idle continuing chat; next turn recalled earlier history; shrink2048, paused queue and waiting Lab refused without stopping the model. Failed real launch restored healthy8192 once. Evidence `.scratch/unified-runtime-live-20260923/evidence.json`.
- Real Qwen connected: Plan produced no prohibited effect; Ask rejection wrote nothing; Approve retained the project preimage; Full wrote once; selected Reader produced a durable child record; bounded review produced an independently captured review request and judgement. Evidence `.scratch/unified-workbench-uat/agent-smoke-results.jsonl`.
- Native Windows: file picker retained sample.txt; draft/attachment survived Settings navigation and desktop restart/reopening. Light/dark Settings and keyboard Escape/theme selection passed at actual Windows200% scaling. Attached text reached the real model (PINE-42). Retained Word preview showed CEDAR-58. Ask held a real write until one-time approval; packaged Monaco showed its exact diff and reversing it removed that file. Hidden Monaco paint leakage was reproduced and fixed without losing retained reading position.
- Twenty overlay/viewports at720/1280/1920/3440 measured zero composer movement and no horizontal overflow;342 real-stream samples verified stable composer/telemetry after reserving Stop space. Further native follow testing found a34px completion gap; the production rendered regression now reproduces/fixes late answer actions and approval arrival, with PageUp/Latest user intent. Final native retest pending.
- Native Models: clearing saved temperature previews unknown model default, Save changes preserves its canonical id with revision3 and no new deployment, and identical Save as variant remains a distinct named configuration. Evidence `.scratch/unified-workbench-uat/native-configuration-save.json`. Native project rail settings/files and new-project-chat action passed. Appearance13→14 preview/Cancel, Apply, individual Reset→13/Apply, and independent preview with spacing guides off passed.
- Real surface APIs verify original/project files survive link, Chat and retained-asset deletion, and Qwen Lab capture/restore/recorded+live replay/approval/cancellation preserve frozen configuration. Evidence `.scratch/unified-workbench-uat/surface-api-results.jsonl`.
- Native Explorer drag could not be executed because the computer-use helper rejects drag endpoints outside the source window. This is an unverified native gate, not a product pass. Final native follow/waiting, management responsive checks, action retry journeys, local upgrade and visual acceptance remain in progress. Unchecked tasks represent incomplete end-to-end acceptance even when implementation is present.
