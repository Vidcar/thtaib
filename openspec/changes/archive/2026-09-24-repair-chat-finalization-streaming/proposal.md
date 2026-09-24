# Proposal

## Why

A finished model request can leave Chat appearing to generate while project snapshot capture, interaction persistence, or replay work holds up completion. The current resume cursor also conflates reconnecting a hydrated view with opening a new filtered subscription, which can omit historical tool and nested activity.

## What Changes

- Persist a settled execution outcome and a visible project-saving phase before branch snapshot capture; finish the run exactly once after an atomic, verified capture outside the harness-wide lock.
- Decouple replaceable generation measurements from token delivery while keeping native execution and interaction records ordered and durable, with explicit persistence-failure reporting.
- Bound routine streaming, replay, and checkpoint-linkage work as conversations grow.
- Give hydrated views, new filtered subscriptions, and reconnecting stream handles separate replay positions. Retain identity-bearing events and compact completed token deltas into final message replay.
- Preserve existing chats and report unavailable historical detail where old compacted records cannot be reconstructed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `backend-desktop`: visible finalization and truthful cancellation, measurement isolation, durable and filtered interaction replay.
- `state-recovery`: atomic project snapshots, settled restart recovery, bounded checkpoint linkage, and truthful replay gaps.
- `lab-evaluation`: excluded-tree pruning and explicit empty allowlist capture semantics.

## Impact

The backend harness, Lab snapshot and state services, interaction SSE route/projection, inference adapter, SQLite migration, and desktop Chat/Agent run views change. The desktop carries a narrow patch for the pinned LangGraph SDK subscription implementation. The run contract gains optional finalization and settled-outcome fields; existing lifecycle status meanings remain.
