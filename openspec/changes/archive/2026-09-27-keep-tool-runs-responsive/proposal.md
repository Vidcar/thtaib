# Proposal

## Why

Browser and attention polling repeatedly load and redact all captured model requests, blocking both HTTP and execution event loops as tool runs grow. Live profiling confirmed a completed provider response reaching the native projection over three minutes late; existing browser tests omit the real store path.

## What Changes

- Separate typed, read-only operational run projections from diagnostic reads in the existing application store; use them throughout Browser, permissions, lifecycle, attention and routine desktop observation.
- Add capture-free `view=operational` run list/detail responses while retaining explicit diagnostic reads.
- Exclude diagnostic captures before interaction copies and serialization, including state and measurement publication.
- Enforce capture privacy incrementally using persisted content/policy/detector fingerprints, invalidated by changes and expiry, without duplicate whole-history processing under shared execution locks.
- Preserve native ordering, actual generation/tool status, tool permissions, approvals, cancellation and recovery.
- Validate substantial retained history and uninterrupted real-model tool runs with Browser viewing and attention polling active.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `state-recovery`: capture-free operational projections and incremental diagnostic privacy enforcement.
- `backend-desktop`: operational observation API and measurable long-run event/status responsiveness.
- `environments-tools`: Browser ownership recovery and viewing without diagnostic work or event-loop blocking.

## Impact

ApplicationStore, harness persistence/publication, diagnostic policy, Browser routes/service, desktop attention and routine run reads, generated shared contracts and mounted Chat tests. Reuses application.sqlite, existing execution owners and stream transport; Plan and Work retain current tool permissions. No new database, scheduler or framework is introduced.
