# Complete persistent shared-agent Chat

## Why

Chat must reliably retain conversation state, expose real agent work and make approvals, files, recovery and deletion understandable.

## What Changes

Complete fixed session scope, turn/queue continuity, streamed presentation, tools-off, scoped approvals and typed input, explicit branching, retained files, manual backup and background lifecycle.

Establish the shared conversation-led, clean and information-dense desktop UX: grouped project/chat navigation, compact model/reasoning/context/speed controls, remembered detailed-stream visibility, inline approvals, editable queue, background attention and on-demand file/activity panels. Add the initial scoped Library and Settings controls, and complete the installed-model start-from-Chat journey through the existing model manager. Preserve and review the existing Models experience. Later packets extend this shared shell as their destinations become functional; they do not duplicate it.

Add an early Chat layout checkpoint and separate built-Windows technical verification from Dave's UX acceptance. Approval of these specifications is not acceptance of an implemented interface.

## Capabilities

### Modified Capabilities

- `agents-workflows`: Complete Chat continuity, tool selection, approvals, branches and user-input behaviour.
- `environments-tools`: Allow explicitly scoped reusable grants without weakening tool policy.
- `state-recovery`: Add retained-file, scoped Library, deletion and manual backup/restore contracts.
- `backend-desktop`: Complete Chat presentation and tray/quit behaviour; define the shared UX contract, model-start journey, attention notifications and human acceptance protocol.

## Impact

`repair-local-interaction-boundaries` is an additional prerequisite and must be implemented and verified before this packet starts. Its delivery satisfies none of this packet's queue, upload, grant, branch, backup or tray feature work; retain its selection/draft, requesting-document trust and legacy chronology regression guarantees.

Work order **03 of 08**. Both change 02 and `migrate-local-agent-interaction` must be implemented and verified before this change starts. Consume the prerequisite's supported `@langchain/react` interaction boundary for messages, tool/state projections, scoped subscriptions and interrupts; do not extend the superseded custom snapshot/event transport. SDK integration is a prerequisite only: every feature and acceptance task below remains required and unchecked until its own evidence exists. Reuse existing services and current contracts; an existing passing implementation satisfies a task without being rebuilt. The deltas specify the required end state, not a claim that every listed behaviour is absent.

## Non-goals

No session moves, transcript-based agent reconstruction, second Chat settings store, automatic backups or claim of rollback/secure erasure.
