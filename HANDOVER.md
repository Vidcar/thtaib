# Current handover

Last updated: 2026-09-21.

## Complete: local interaction prerequisite

Implementation merged in [PR #114](https://github.com/Vidcar/thtaib/pull/114), main `dc82f06`. All migration tasks are complete; current contracts synchronized. Evidence: `openspec/changes/archive/2026-09-21-migrate-local-agent-interaction`. Packets 03–08 remain proposed; Packet 03 is next. Packet 04 alone owns the coherent async transition. Do not automatically begin them.

Chat, Agent-run and Lab share React SDK1.1.1 / stock HTTP adapter SDK1.11.1. The existing Python owner drives synchronous native v3 once per run. Projections reuse application.sqlite; checkpoint/permission ownership is unchanged. Custom SSE/parser/merger, old endpoints and envelopes are removed. Application metadata retains generated contracts. Native v3 is experimental; tested dependencies are locked.

Passed: 339 default/147 integration backend tests, contract freshness, desktop build/typecheck and SDK/StrictMode/Markdown/interrupt/settings checks. Use backend `uv run --no-sync python -m tests.run` (plus integration tier) while the ordinary backend locks its executable; desktop `pnpm run build`; root `openspec validate --all` (15/15 after archive). Real isolated Qwen/Windows evidence covers incremental output, two turns, navigation, tools/approve/deny/cancel, reconnect/multiple observers, pending-approval restart, replay gaps, partial output and structured results. Exact model scope is in the archived design; no vision claim.

Ordinary backend8000 updated through `scripts/Launch-Workbench.ps1`; health/auth passed. All 12 tables match the online backup's full row hashes in `.scratch/interaction-delivery`; 6 runs/2 conversations/6 deployments preserved. Desktop rebuilt, ready through the usual launcher. Proof model8127/backend8128/Vite5173 stopped. Models/weights/content preserved; GitHub CI unchanged. No unfinished migration work.
