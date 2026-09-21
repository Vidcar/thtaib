# Proposal

## Why

Packet 02 completed the faithful local inference boundary, but the harness still streams completed updates and the desktop maintains custom subscription and projection machinery. Before Packets 03–08 expand that machinery, move generic interaction responsibilities to compatible published LangChain libraries while retaining the existing local execution and persistence owners.

## What Changes

- Gate replacement on published-version/source verification and a reversible real-model proof through the React SDK, existing FastAPI services and embedded Python agent.
- Use `@langchain/react` for shared message/tool/state projections, scoped subscriptions and interrupts; prefer its stock `HttpAgentServerAdapter` and public Python native event streaming.
- **BREAKING**: replace the custom `snapshot` / `run_event` / `stream_end` interaction contract only after every current Chat and live-run consumer is migrated. Remove superseded parser, merging, subscription and contract code.
- Keep backend-authoritative registration, identity mapping, settings, admission, approvals, confirmed cancellation, durable outcomes, replay/hydration and authenticated Electron-main requests.
- Preserve real conversation archives and checkpoint links, including history older than compacted execution context. Keep Packet 01/02 model and inference behavior intact.
- Align proposed Packets 03–08 with this prerequisite, preserving all unfinished features and a single owner for any required async foundation.
- Reuse suitable Agent Chat UI presentation selectively with revision/license attribution; do not adopt its old stream provider or whole application.

## Capabilities

### New Capabilities

None; this changes existing interaction boundaries.

### Modified Capabilities

- `architecture`: distinguish upstream frontend projections from application execution, persistence and permission authority.
- `backend-desktop`: versioned upstream interaction, truthful lifecycle, authenticated hydration/reconnect and thread isolation.
- `shared-contracts`: import upstream protocol definitions; generate and validate application-owned boundary schemas.
- `state-recovery`: durable thread identity, bounded replay/resynchronization and separate readable archive/checkpoint roles.
- `agents-workflows`: one native event-producing execution, scoped native identities and exact interrupt/run correlation.

## Impact

Backend harness, Chat, event transport, application records and contract generation; desktop Chat, Agent-run, progress/approval presentation, shared interaction consumers and regression checks; exact compatible dependencies and lockfiles; OpenSpec configuration and proposed packets. Preserve one Electron/React/Vite app, one loopback FastAPI backend, `WorkbenchChatOpenAI`, `application.sqlite` and the existing LangGraph saver. Use isolated `.scratch/` data and existing model weights for proof.

## Non-goals

Do not implement Packets 03–08, a JavaScript agent server, another loop/checkpoint owner, persistent queue, delegation/branching/workflow/media features, new hosting or CI. If the compatibility proof requires substantial replacement framework machinery or private APIs, keep the working app and this change active with the exact blocker and incomplete checks.
