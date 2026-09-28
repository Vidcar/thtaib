# Proposal

## Why

Models mixes saved configurations, publisher recipes and runtime diagnostics, and background checks repeatedly change the editor's geometry. The approved design gives each action one home and keeps continuously edited rows stable.

## What Changes

- One saved-setup selector and sticky Save/Load toolbar; publisher presets apply to the current draft from a contextual side panel.
- Persistent reversible preset removal and restoration from the installed pinned card, without changing saved setups.
- Stable three-column settings, reserved reset/status/custom-entry space and mounted controls during checks.
- Contextual checks, memory, runtime, card and files panels; consolidate response aliases and place bundle-level vision/template actions in model information.
- Expose existing guarded setup deletion and mark checks stale after any draft/selection change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `models`: stable setup editing, contextual information and reversible publisher-preset visibility.

## Impact

Desktop Models/editor/shared controls and tests; existing model service/schema/routes gain preset visibility and an optional restoration flag. Generated shared contracts change. Existing setup meaning, native lifecycle, model weights, source revisions and other workspaces remain intact.
