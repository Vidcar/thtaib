# Current handover

Last updated: 2026-09-21.

## Current state

Packet 02 is complete in [PR #113](https://github.com/Vidcar/thtaib/pull/113), branch `codex/packet-02-inference-adapter`, based on main after PR #112. Current model contracts are synced under `openspec/specs/models/spec.md`; the completed change is archived as `2026-09-21-02-complete-inference-adapter`. Packets 03–08 remain proposed.

## Delivered

Shared adapter preserves actual model/settings, sync/async calls, streaming, reasoning and tool identities, with owned-client cleanup and bounded redacted diagnostics. Shared current-user blocks and versioned structured results enforce policy/capability gates and one effect-free repair. Observed context drives one upstream compaction path and saved-history preflight. Setup-specific probes persist in application SQLite. Chat cancellation durably pairs unanswered calls with explicit unconfirmed error results; no tool is replayed. Desktop details show context and validated results in a scrollable panel.

## Verification and local use

315 default and 142 integration tests passed; desktop build/typecheck/SSE/settings checks, generated contracts and strict OpenSpec validation passed. Real Qwen3.8-27B / b11045 CUDA checks passed for streaming, tool round trip, native/tool schema, combined tool-schema/executable tools, reasoning/replay, image recognition and tools-off compaction. Native schema plus executable tools was inconclusive on that setup; auto uses tested tool formatting. Counts are estimates; capability proof is setup-specific.

Rebuilt desktop is open, backend healthy on :8000 with the ordinary product data root. Isolated :8127 model stopped and verified closed. Weights preserved. Scratch evidence/helpers remain under `.scratch/packet02-live/` and `.scratch/packet02_*.py` (ignored). Packet 02 has no known outstanding defects or implementation tasks. No CI was added. Verify current Git/PR state before new work.
