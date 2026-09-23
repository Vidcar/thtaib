# Proposal

## Why

Overlapping settings and runtime records make the desktop misleading: inherited access can display Ask while granting Full access, known model defaults are hidden, saved deployments collide, and navigation and controls move unexpectedly. Repair the underlying behaviour and all existing surfaces together so the product is usable and trustworthy.

## What Changes

- **BREAKING**: one default model configuration plus optional named variants replaces the deployment/preset/no-preset selection combination. Model configurations own startup and response settings; agents own instructions, tools and knowledge; conversations retain explicit local overrides.
- The backend resolves the values, sources, defaults, support and pending reload state displayed by every surface. A one-time idempotent consolidation preserves meaningful configurations, instructions, weights and historical records.
- Managed reconfiguration supports context changes in idle conversations with consumer admission, launch-time port checks, ownership verification and recoverable failure.
- **BREAKING**: Ask pauses all mutations; Approve for me permits verified recoverable project edits; Full access skips approval for enabled tools. Explicit saved grants remain visible exceptions.
- Add backend-enforced Plan mode, explicitly selected named helpers and optional requested rubric review with up to two revisions. Enforce explicit shared tool-call budgets and distinguish review judgement from checks.
- Use stable compact controls and bounded responsive layouts throughout Chat, Models, Agents, contextual Projects, Knowledge, Library/files, current Lab/Workflows, Attention and Settings. Restore navigation state, group finished activity, keep real file differences and make failures actionable.
- Keep the future Lab suite, visual workflow canvas, media integrations, persistent goals and background agent servers outside this pass. Existing visible functions are repaired and verified, not replaced with placeholders.

## Capabilities

### New Capabilities

None; extend existing owners.

### Modified Capabilities

- `models`: canonical model configurations, truthful defaults and safe reconfiguration.
- `agents-workflows`: access semantics, Plan mode, named helpers, bounded requested review and enforced budgets.
- `architecture`: one effective setup and distinct configuration/runtime ownership.
- `backend-desktop`: compact stable controls, conversation continuity, contextual projects and all existing surface journeys.

## Impact

The existing backend, desktop, shared API contracts and their tests. Reuse profile storage and upstream Deep Agents/LangGraph mechanisms. No new application, registry, runtime loop, CI or hosted dependency. This change owns overlapping everyday-workspace and helper work formerly listed in `consolidate-product-contract`; its future Lab/canvas/media work stays deferred. Preserve the completed streaming/trust/ownership guarantees and ScratchArea records.
