# Proposal

## Why

Real Windows Chat runs fail on concurrent nested file creation, lose successful sibling outcomes, hide the original cause and block continuation. Duplicate reasoning accounting also triggers false context failures; unbounded reasoning and poorly exposed document/memory capabilities make ordinary tasks unnecessarily slow and confusing.

## What Changes

- Repair Windows filesystem integration, recoverable tool errors and native terminal-history recovery without replaying effects.
- Count the actual serialized request once, use native compaction, separate housekeeping telemetry and provide bounded Balanced/Deep presets.
- **BREAKING** Serialize root task families using overlapping project folders; queue other chats through the existing durable coordinator.
- Show original failures, accurate tool outcomes, meaningful recovery and owned static previews.
- Add a bounded project outline, persistent conversation document selection, local text search, truthful citations/pagination and lazy nonduplicated similarity search.
- **BREAKING** Bind explicit memory versions per submitted turn rather than for the lifetime of a conversation.

## Capabilities

### New Capabilities

None; extend existing owners.

### Modified Capabilities

- `agents-workflows`: safe continuation, per-turn memory and bounded project context.
- `models`: canonical request accounting and bounded reasoning presets.
- `environments-tools`: Windows file correctness, tool errors and static preview.
- `state-recovery`: project-family admission, selected documents and derived retrieval.
- `backend-desktop`: durable failure/recovery, project waiting and source/context presentation.

## Impact

Backend harness/adapters, Chat coordinator, retained assets and search; shared run, queue, context and document contracts; desktop Chat, setup, measurements and preview. Preserve native Deep Agents/LangGraph ownership, model weights, existing runtime/startup configuration and the unrelated Lab proposal. Disposable development records do not require compatibility shims. Delivery includes local/default/integration checks, real Windows application workflows, Git merge and the established local deployment.
