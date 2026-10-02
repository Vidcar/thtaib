# Correct reviewed runtime boundaries

## Why

The current code review found seven defects that can lose an edited request, repeat queued work, bypass the first computer-use confirmation, hide uncertain command effects or preview cleanup, and misreport a model diagnostic or memory. Dave authorized building the current application, reproducing supported findings, running natural Qwen journeys, and fixing confirmed problems.

## What Changes

- Reset native summarization state when rewinding before a chat's first turn.
- Keep Queue input identity stable across a lost acknowledgement and reconcile the accepted item before retrying.
- Apply the same first-use confirmation to native commands, managed commands, and skill scripts.
- Block continued dispatch after a managed command times out or is cancelled with uncertain partial effects until inspection and acknowledgement.
- Keep preview ownership and chat records until process-tree shutdown is confirmed, with a retryable Stop control.
- Send smoke requests to the actual selected model, without implicitly loading another router model.
- Report per-model RAM as unavailable when only the shared router's memory is observed.
- Preserve the native helper identities and roles in compact tool descriptions, so discovery can select a capable helper without guessing.
- Exercise game creation, an interactive website, browser validation, research and helpers through the installed Qwen model using outcome-based prompts.

## Capabilities

No new or changed product requirements. This change restores the accepted contracts in architecture, agents-workflows, environments-tools, state-recovery, models and backend-desktop, including the completed align-reviewed-behavior deltas. `skip_specs: true` avoids inventing a new requirement for existing obligations. Historical main-spec snapshot/backup language remains owned by its existing pending reconciliation.

## Impact

Backend graph middleware, permission and execution recovery, managed process ownership, lifecycle deletion, model diagnostic/resource projection, desktop Queue and preview controls, and relevant regressions. No dependency replacement or second execution loop. Tests use disposable project/data roots; model weights and installed runtimes remain intact. This branch owns the fixes and delivery; other active work is preserved.
