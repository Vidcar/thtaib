# Proposal

## Why

The original catalogue and terminal-token improvements are implemented, but the initial-load failure path is incomplete: the sidebar stops after thirty failures and marks the failed lists loaded. It can then show an empty catalogue even though no successful read occurred.

## What Changes

- Retain the delivered independent small project/chat lists, saved-transcript opening, status dot and ordered terminal-token compaction.
- Finish initial-load recovery: retry until the first success, preserve a reading or unavailable state on failure, and never report a failed list as empty or ready.
- Retire the original automatic model-warming work. It was superseded by [the delivered model-residency change](../archive/2026-09-25-simplify-chat-model-agent-setup/tasks.md); launch, restoration and passive reads do not load a model.

## Capabilities

### Modified Capabilities

- `backend-desktop`: honest initial catalogue loading and recovery, retaining delivered launch and model-selection behaviour.
- `state-recovery`: ordered finished-message compaction after terminal projection, with live/reconnect and checkpoint guarantees intact.

## Impact

The remaining implementation is in sidebar list recovery and its desktop regression. Existing token-maintenance and backend read paths remain in place. No new model start, schema migration or product-data deletion is required.
