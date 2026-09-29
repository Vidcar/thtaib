# Proposal

## Why

The current application passes its existing gates, but failure/race reproductions expose mismatches between accepted work, saved settings, uncertain effects and desktop projections. Correct those existing behaviours before later Lab and workflow feature work; the historical audit is a lead, not the acceptance evidence.

## What Changes

- Acknowledge queued Chat submissions without inventing a run, settle queued-only cancellation, and wake the existing coordinator when a project reservation becomes available.
- Keep post-dispatch desktop uncertainty in the existing uncertain-effect recovery path rather than converting it into a correctable tool failure.
- Invalidate Chat previews when the selected saved configuration revision changes; retain the original base revision of dirty Models drafts and complete accepted model-picker actions reliably.
- Recover Chat's independent startup reads without false empty states or stale errors, retain accepted Lab run ownership through failed observation, and reject obsolete Browser/attention observations.
- Add regressions through the existing production boundaries, challenge them against isolated original behaviour, independently review the changes and validate the actual built Windows application with isolated data and an installed model.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `backend-desktop`: clarify accepted-action versus observation failure, read recovery and ordering, and queued submission display.
- `models`: include saved revisions in preview identity and preserve dirty draft revision conflicts.
- `state-recovery`: clarify progress after reservation release, queued-only cancellation settlement, and post-dispatch desktop uncertainty.

## Impact

Existing React owners and mounted checks, interaction/Chat/project-admission services, desktop automation adaptation and their existing backend tests. No dependency upgrade, new execution loop, storage authority or queue. GitHub CI and the delivered lean engineering workflow remain unchanged. `lab-workbench` and `consolidate-product-contract` remain later feature work. Product weights, protected chats and unrelated work are preserved; validation data lives under `.scratch/`.
