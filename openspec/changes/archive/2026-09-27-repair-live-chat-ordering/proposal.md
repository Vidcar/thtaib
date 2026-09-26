# Proposal

## Why

Successive Chat replies misplace retained tool activity and remount earlier output while the conversation stays open. Refreshing repairs the visible transcript, so snapshot-only checks have repeatedly missed the live defects.

## What Changes

- Preserve stable turn/message identity and loaded historical run details across replies.
- Attribute native tools to their original run/turn, reconcile one visible call/result, and prevent retained SDK handles from becoming newest-turn activity.
- Keep verified history mounted during queued admission and sample coherent display state.
- Reset backend partial reconstruction at run boundaries before public metadata filtering.
- Require uninterrupted mounted SDK and native Windows acceptance, including chronology and layout rather than text presence alone.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `backend-desktop`: Stable chronological live Chat across repeated replies, truthful scoped tool ownership, and continuous transcript rendering during admission/reconstruction.

## Impact

Backend interaction projection/resume and typed Workbench metadata; desktop ChatPanel, InteractionStream and AgentMessageFeed; generated shared contracts; mounted SDK/backend and native Electron regression checks. No new runtime, transport or dependency. Isolated validation preserves everyday data, weights, unsaved edits and unrelated work.
