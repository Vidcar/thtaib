# Proposal

## Why

The delivered local LangChain interaction migration has selection/command ownership races, an insufficient Electron requesting-document authorization boundary, and incorrect repeated-text legacy archive alignment. Repair these before Packet 03 while retaining the delivered architecture.

## What Changes

- Bind Chat selection, transport and pending commands atomically; guard delayed callbacks by selection generation and draft identity, including analogous Agent-run/Lab defects.
- Restrict Electron windows/navigation and authorize backend-token injection by exact requesting document/frame and owner; open validated HTTP(S) links in the system browser.
- Preserve repeated legacy chronology and safely repair provably affected existing projections without replaying execution or undoing display edits.
- Add deterministic component/backend reproductions, actual Windows Electron boundary checks and a real model desktop journey.
- Record the development data-retention rule and make this corrective delivery a Packet 03 prerequisite.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `backend-desktop`: API-008 selection/draft ownership and API-009 requesting-document trust.
- `state-recovery`: STATE-002 chronology and STATE-015 narrow idempotent display repair.
- `architecture`: precise local desktop document trust boundary.

## Impact

Chat and analogous interaction callbacks, Electron main link/request policy, interaction archive seeding/repair and focused tests. Existing Electron/React, FastAPI, stock LangChain SDK, Deep Agents/LangGraph, model manager, inference adapter and SQLite owners remain. No Packet 03 features or Packet 04 async migration; Packets 03–08 and completed archives remain intact. No new dependency is planned.
