# Tasks

## 1. Setup ownership and admission snapshots

- [x] 1.1 Extend canonical saved agent/setup contracts and resolution for Use Chat model versus assigned model, grouped/individual tools, connections and knowledge identities; verify inherited/fixed agent resolution, explicit empty tools and project-only context with focused backend cases and regenerated shared contracts.
- [x] 1.2 Resolve the latest saved selected agent/skill/memory/protected-instruction records atomically at input admission and persist exact versions before queue acceptance; verify concurrent Save/admission, deselection, missing-record errors and unchanged running/queued/resumed content.
- [x] 1.3 Persist next-message intent separately from accepted snapshots and observed deployment bindings; route staged startup/model changes through shared safe admission rather than mutating active launch settings, and verify same/different configurations across queued turns, helper handoffs, failure/cancellation and restart.
- [x] 1.4 Preserve live permission checks, window grants, mode restrictions, helper intersections and resource/compatibility preflight under the new owners; verify a saved agent cannot grant access, a paused resume cannot refresh authored versions and staged failure retains exact input/settings without duplicate dispatch.

## 2. Basic shell and composer layout

- [x] 2.1 Split `WorkbenchSidebar`/shell into a persistent compact rail and independent resizable/collapsible project/chat list; verify global New chat versus project `+`, no-project grouping, draft restoration, archive/filter/history and existing initial-load recovery behaviour.
- [x] 2.2 Place small Search/Notifications icons at the rail top and Settings on the rail; use existing search/attention owners, remove duplicated chat-list controls and verify notification activation selects the correct existing conversation without replay, focus theft or new-chat creation.
- [x] 2.3 Arrange the composer footer in the agreed order and implement responsive secondary-column collapse using existing shared tokens; verify full/half-screen and actual Windows scaling, long labels, keyboard focus, preserved reading position and no dock/composer overlay.
- [x] 2.4 Exercise the basic shell/composer and Models-to-Chat path in the native desktop before adding remaining controls; record technical interaction evidence and Dave's early UX acceptance or explicit deferral separately in design/PR, without treating generated previews as acceptance.

## 3. Complete Chat controls and presentation

- [x] 3.1 Implement the bounded searchable one-row-per-model picker, multi-configuration expansion and observed exact-configuration status dots; verify expansion never loads, exact healthy reselection avoids start, idle explicit selection loads and passive restoration stays cold.
- [x] 3.2 Add the adjacent combined Thinking/effort/context editor with one Apply and per-model/chat override persistence; verify switching A→B→A, saved-base changes, supported/unknown controls, safe reload, connected-endpoint limits and preservation of input/attachments/history without adding response or thinking-token-limit controls.
- [x] 3.3 Connect agent/model/tuning selections during work to next-message intent with only a compact changed-state indicator; verify existing queued snapshots remain unchanged, fixed-model agent staging works, later input loads safely and a failure preserves exact attempted settings and recovery.
- [x] 3.4 Implement combined Send/Stop for the complete active turn with hover/focus feedback and Enter-to-queue; verify tool phases, approval/input waits, cancellation settlement, delayed admission, predecessor races, Shift+Enter and IME cannot send or queue duplicates.
- [x] 3.5 Implement shared `+`/`@`/`/` context/skill/action pickers, removable chips and active-only Plan pill; verify mouse/keyboard equivalence, Enter suggestion selection, Escape, admission-failure retention, next-message-only slash consumption and disabled tools remaining disabled.
- [x] 3.6 Consolidate dock pages into Files/Browser/Helpers using existing origins/previews and remove browser auto-open; verify click-only opening, indicators, retained width/tab/read position, same owned browser session and contextual live/upload/output/saved-copy authority without another catalogue.
- [x] 3.7 Style small right-aligned user bubbles and unboxed assistant answers and move export/delete to header and retry/edit beside messages; verify markdown/code/tables/diffs, independent reasoning/tool expansion, actionable errors/approvals and effect disclosures while preserving native stream identity, helpers and follow/scroll/selection behaviour.

## 4. Guided Agents and Knowledge

- [x] 4.1 Build guided new-agent creation followed by the grouped saved-agent editor; keep Chat's agent dropdown selection-only, and verify grouped/individual tools, Use Chat model/fixed assignment, dependencies, helpers, review/save and immutable history through mounted UI interactions. Native Windows layout and failure/recovery acceptance remain in 6.3.
- [x] 4.2 Retain the Knowledge list/editor while adding guided skill fields and Source tab backed by one draft; verify imported metadata/frontmatter/resources round-trip, source validation, native slug uniqueness and no saved version from invalid or unsaved source.
- [x] 4.3 Connect saved agent/knowledge edits to the backend's admission resolver rather than cached frontend version IDs; verify a newly submitted message uses saved edits, an already queued input does not, and historical setup labels identify their actual frozen versions.
- [x] 4.4 Place browser lifecycle controls in Browser, installation/connections in Settings and live Windows grants under Chat access; group existing operational settings without changing their policies, and verify missing worker/connection/grant recovery remains available before a model is selected and cannot grant agent authority implicitly.

## 5. Guided model import and advisory hardware estimate

- [x] 5.1 Reorganize `HuggingFaceImport` into Find→Choose→Review/download using its current inspection/job owner; verify exact file links, complete shards, explicit projector/text-only choice, immutable revisions, Back preserving choices and no transfer before explicit Download.
- [x] 5.2 Extend bounded backend GPU/RAM memory observation and estimate contracts with source/freshness/unknown fields; verify per-device budgets, unavailable telemetry and no silent pooled-GPU or filename-only verified-fit claim.
- [x] 5.3 Implement metadata-based weights/cache/overhead estimates and approximate GPU-context/RAM placement with qualified unsupported-architecture results; verify representative supported metadata calculations, shards/projectors, CPU KV placement, uncertain architecture/overhead and changed hardware budgets without downloading full weights for estimation.
- [x] 5.4 Verify KV placement/precision/context mapping against the pinned llama.cpp runtime, extend canonical descriptors/validation/launch settings and connect the compact quant/KV/context-slider estimate; verify actual launch/requested-versus-applied facts and distinguish CPU KV placement from model-layer offloading.
- [x] 5.5 Carry explicit estimator choices into the initial saved model configuration alongside publisher recipes/provenance; verify review/back/download/install preserves them, estimated shortages or unknown fit do not block Save/Download/Load, and actual failed loads preserve the attempted settings with adjustment/recovery.

## 6. Cross-screen wording and integrated validation

- [x] 6.1 Apply short labels and on-demand supporting detail across Chat, Models, Agents, Knowledge and Settings; verify routine staged changes have no repeated 'for next message' paragraphs while accessible names, actual failures, estimated/unknown facts and approval/effect disclosures remain available.
- [x] 6.2 Run a continuously mounted multi-turn native Chat journey covering reasoning→tools→answer, delayed metadata, queue handoff, helper activity, partial cancellation, warm versus reopened chronology and changing selections; verify no flicker, stale attribution, duplicated input, lost draft or measurement-driven scroll changes.
- [x] 6.3 Exercise guided Agents/Knowledge/Models and Files/Browser/Helpers in full and half-screen Windows layouts with actual scaling, keyboard-only use and at least one failure/recovery per affected owner; record technical results and Dave's major-surface UX acceptance or explicit deferral separately.
- [x] 6.4 Run relevant backend checks from `apps/backend` using `uv run python -m tests.run` and `uv run python -m tests.run --tier integration --durations 10`, desktop `pnpm run build`, affected shared-contract freshness, `openspec.cmd validate --all` and `git diff --check`; verify passing results or fix remaining failures without weakening contracts.

## 7. Reconcile and deliver

- [x] 7.1 Reconcile the affected OpenSpec requirements with current main specs and active-change boundaries, then archive only the implemented/verified change; verify `startup-catalogue`, `lab-workbench` and Workflows/media tasks remain intact and generated previews are not reported as native acceptance.
- [x] 7.2 Complete the scoped Git/PR/local delivery workflow after applicable checks and review status are recorded; verify only intended files are delivered, weights/unrelated work are preserved and the established desktop works without test records in everyday product data.
- [x] 7.3 Refresh the concise root handover with the delivered state, actual checks and any remaining next step; verify Dave receives a usable result and honest remaining limitations without needing to operate development tools.
