# Design

## Context

See proposal.md. Chat's visible model IDs and the sparse setup override set can disagree. The readiness request accepts a broad setup shape, but its implementation constructs a stricter Chat send request. Opening a saved chat serially awaits fetch, interaction registration and setup resolution; the closed model picker previews all installed configurations.

## Goals / Non-Goals

**Goals:** Keep the displayed and submitted model identical; make readiness and Queue follow the run lifecycle; remove avoidable work from opening and sending while preserving backend admission and saved-chat recovery.

**Non-Goals:** Change model weights, saved conversation format, inference scheduling, or the Deep Agents/LangGraph interaction boundary.

## Decisions

1. **Conversation-owned model selection.** Treat the exact deployment/configuration pair as an explicit Chat choice when the picker shows one. Carry that choice into new-chat creation and future submissions across agent/project changes. A saved conversation restores its own pair. With no explicit choice, use only the sole healthy running chat deployment; multiple healthy choices remain unselected. This follows AGT-024 and avoids choosing an arbitrary model.
2. **Exact selection is a no-op.** A model row prefers the current named configuration for its bundle. If that exact managed deployment is already healthy, close the picker without preview or start. A different or unloaded configuration keeps the existing guarded load path. This avoids lifecycle work and accidental default-variant switches.
3. **Readiness remains a preview.** Project only fields accepted by Chat dispatch; retain nullable clears for those fields, omit null inheritance, and report unsupported non-null values as a structured client error. Keep the preview read-only and reuse its resolved setup rather than resolving the same candidate twice. Submission and Queue retain backend validation.
4. **Lifecycle owns action state.** Run occupancy determines Queue versus Send. Do not use an active-turn readiness result to gate Queue. Key preview ownership by selected conversation, exact candidate and run identity/status; ignore late results after a switch or terminal transition. Queue carries the known predecessor run ID when clicked during a run. If completion wins the admission race, the existing terminal coordinator collects output and advances or pauses the durable queue. Stale predecessor IDs fail without saving a turn, and ordinary idle Queue retains its explicit Resume behavior. A passive preview can explain a blocker but cannot by itself require waiting before Send when authoritative admission can load/check the model.
5. **Bind saved content before secondary work.** Show the fetched saved view, then complete registration and setup resolution concurrently with selection-generation checks. Keep Send unavailable until the current interaction binding is ready. Defer all-choice compatibility, model options and thinking previews until the picker opens; check a selected alternative before loading, and label failed checks unknown.
6. **Avoid repeated full weight scans on warm Send.** Verify the saved bundle identity for a healthy loaded preset without hashing every weight byte for each turn. A preset found evicted at admission must receive full verification before router loading. Explicit start, reload and reconfiguration keep their existing full verification.

## Risks / Trade-offs

- A saved transcript can appear briefly before live observation attaches. Show a connecting state and keep submissions disabled until its binding is current.
- A preview may become stale when runtime access changes. Backend admission remains authoritative, preserves the draft on rejection, and supplies an actionable error.
- Lazy compatibility checking moves some work to picker interaction. Unknown choices stay distinguishable, and the clicked choice is checked before loading.

## Migration Plan

No data migration. The change can roll back with the desktop/backend build; existing conversations and model deployments remain in place.
