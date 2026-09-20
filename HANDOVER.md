# Current handover

Last updated: 2026-09-20.

## Goal and state

Packet 02 baseline repairs are validated on `codex/repair-baseline`, based on `f50011b` (packet 01 / PR #106). The packet PR records CI and merge results. Scope stops at the seven supplied defects; the full vision is not delivered.

## Changes and decisions

- Shell approval uses conservative full argument forms; unknown options, quoting/expansion and mutations require approval. Existing Deep Agents interrupts remain the gate.
- Chat optional bindings distinguish omitted/unchanged, value/set and null/clear. Project clear detaches workspace and stale retrieval paths, without erasing checkpoint content or historical run setup.
- Scoped conversation admission and atomic store reconciliation preserve terminal replies without polling, including fast completion; stale hydration/cancel/resume cannot overwrite later turns. Transcript replacement stays display-only.
- Restart orphans fail with unresolved external effects; real checkpoint-backed approvals retain one continuation owner. Cancellation rejects a recovered pending command.
- Detached endpoints preserve history and require deliberate rebind. Observed health controls availability without granting process ownership.
- Unimplemented agent keys remain requested/unsupported. Failure diagnostics retain redacted prepared/attempt/response facts and retry evidence; original errors remain intact.

## Validation and use

Windows backend delivery gate: 339 tests passed. Desktop build (typecheck, SSE, null/omission serialization), generated-contract freshness and root spec check passed. An initial gate failure in a cancelling-worker fixture was corrected without weakening quiescence coverage.

Isolated Windows tiny-model checks passed: UI turns/reopening, independent clears, shell approve/reject/cancel, no-GET durable two-turn sequence, detach/rebind and preserved server health. Scripted tests separately cover races, restart approvals through the real saver/compiled agent, failure/retry/redaction and explicit budgets. Evidence remains in `.scratch/packet02-live/`; no downloads or everyday data/model changes. Tiny-model evidence proves plumbing, not capability.

Launch: root `Launch Workbench.vbs`. Checks: [commands](specs/commands.md). No feature-expansion work is authorized by this packet.
