# Current handover

Last updated: 2026-09-21.

## Interaction prerequisite: validated, delivery in progress

Branch `codex/migrate-local-agent-interaction`, based on main `98c77cc` (PR #113). Implementation is complete and current specs synchronized across architecture, backend-desktop, shared-contracts, agents-workflows and state-recovery. Active change: `openspec/changes/migrate-local-agent-interaction`; final delivery task remains open until merge/local activation/archive. Packets 03–08 remain proposed; Packet 03 is next. Packet 04 retains the coherent async transition.

Chat, Agent-run and Lab share React SDK1.1.1 / stock HTTP adapter SDK1.11.1. Existing Python owner drives public synchronous native v3 once per run. Controlled durable projections reuse application.sqlite; checkpoints and permissions retain their existing owners. Custom browser SSE/parser/merger, old endpoints and envelope schemas are removed. Application metadata remains generated from canonical schemas. Native v3 is experimental and the tested dependencies are pinned.

Passed: 339 default and147 integration backend tests, generated-contract freshness, desktop build/typecheck and SDK/StrictMode/Markdown/interrupt/settings checks. Backend uses `uv run --no-sync python -m tests.run` (and integration tier) while ordinary backend locks its executable. Actual built Windows renderer with isolated Qwen3.8-27B passed incremental output, two turns, navigation/hydration, approval/denial/cancel. Real SDK reconnect/multiple observers, pending-approval backend restart, replay-gap recovery and strict structured results passed. Evidence and exact model scope in change design; vision capability is not claimed.

Next: final OpenSpec validation, commit/PR/merge, safely activate the rebuilt ordinary app, then archive and close delivery notes. Scratch helpers `.scratch/interaction-ui-proof`; owned model8127, proof backend8128, Vite5173 still need stopping. Ordinary data/weights are untouched. A read-only check of ordinary backend8000 is underway before activation.
