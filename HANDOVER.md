# Current handover

Last updated: 2026-09-21.

## Goal and state

The two remaining baseline races are implemented and locally validated in [PR #108](https://github.com/Vidcar/thtaib/pull/108), `codex/fix-two-baseline-races`, based on `e33b2f0` (merged PR #107). Dave subsequently requested complete removal of GitHub CI and removed merge rules. Actions are disabled, workflow/path selection removed, and required status checks removed. Local validation remains mandatory; do not restore GitHub CI unless Dave asks.

OpenSpec CLI 1.13.1 is installed globally through npm and the repository is initialized for Codex. The tracked setup is `openspec/config.yaml` plus six generated skills under `.agents/skills/`; Codex uses skills, so zero command files is expected. Start planning with `$openspec-propose` and apply only in a later request with `$openspec-apply-change`.

## Changes and decisions

- Chat regression forces A to complete after initial reconciliation sees it running but before B's active-run check. It reproduced loss of assistant A directly in SQLite, without GET/SSE repair. Start now reloads durable conversation state and reconciles the observed terminal run before constructing B.
- Keep per-conversation admission and existing store completion writes. Never hold the store lock across harness calls (completion locks harness before store). Preserve display-only replacement and existing thread/configuration linkage.
- Approval reservations now release atomically with their consumed interrupt, after worker ownership is secured. Failed restart setup also cleans its reservation. Deep Agents interrupts, policy and single-worker ownership remain unchanged.

## Validation and next step

Both final regressions fail against original code and pass with the corrections. Approval A is persisted through the compiled agent/SQLite saver; its original worker is stopped without modifying the checkpoint before fresh-harness restoration. B approve/reject/cancel and duplicate races verify exact append counts. Chat uses events and inspects stored history without GET/SSE repair.

Windows backend delivery gate: all 341 tests passed; root specification check and all 59 checker tests passed after CI removal. No wire changes. Implementation and local validation are complete; PR #108 records merge status. Disposable data and scripted models only; no new real-model or desktop end-to-end claim.

OpenSpec initialization completed successfully from the repository root. No legacy OpenSpec command folders, marker blocks, or `~/.codex/prompts/opsx-*.md` files were present before initialization. Restart Codex before invoking the generated skills.

Launch: root `Launch Workbench.vbs`. Checks: [commands](specs/commands.md). Previous baseline live evidence remains in `.scratch/packet02-live/`; this task does not extend its claims.
