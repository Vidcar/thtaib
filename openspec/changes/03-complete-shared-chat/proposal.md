# Complete persistent shared-agent Chat

## Why

Chat must reliably retain conversation state, expose real agent work and make approvals, files, recovery and deletion understandable.

## What Changes

Complete fixed session scope, turn/queue continuity, streamed presentation, tools-off, scoped approvals and typed input, explicit branching, retained files, manual backup and background lifecycle.

## Capabilities

### Modified Capabilities

- `agents-workflows`: Complete Chat continuity, tool selection, approvals, branches and user-input behaviour.
- `environments-tools`: Allow explicitly scoped reusable grants without weakening tool policy.
- `state-recovery`: Add retained-file, deletion and manual backup/restore contracts.
- `backend-desktop`: Complete existing Chat presentation and tray/quit behaviour.

## Impact

Work order **03 of 08**. Both change 02 and `migrate-local-agent-interaction` must be implemented and verified before this change starts. Consume the prerequisite's supported `@langchain/react` interaction boundary for messages, tool/state projections, scoped subscriptions and interrupts; do not extend the superseded custom snapshot/event transport. SDK integration is a prerequisite only: every feature and acceptance task below remains required and unchecked until its own evidence exists. Reuse existing services and current contracts; an existing passing implementation satisfies a task without being rebuilt. The deltas specify the required end state, not a claim that every listed behaviour is absent.

## Non-goals

No session moves, transcript-based agent reconstruction, second Chat settings store, automatic backups or claim of rollback/secure erasure.
