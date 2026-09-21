# Current handover

Last updated: 2026-09-21.

## Goal and current state

Packet 01 implementation is complete in [PR #111](https://github.com/Vidcar/thtaib/pull/111), from `codex/packet-01-model-management`. The Models specification is synchronized; all ten tasks are archived at `openspec/changes/archive/2026-09-21-01-complete-model-management/`. Packets 02–08 remain planned and are not implemented.

## Delivered

Durable asynchronous imports with confirmed cancellation, retry/discard, revision-pinned repair and restart reconciliation; bounded Hub discovery; future install location and reference-aware storage cleanup; editable/duplicable profiles; coordinated deletion/load/unload/reload and Chat load on demand. Launch snapshots preserve actual startup settings after profile edits. Desktop controls and shared contracts are rebuilt.

## Verification and use

Final checks passed: 272 default backend tests; 118 integration tests; desktop typecheck/build/SSE regression; generated-contract check; strict OpenSpec validation (16 items after archive). Commands remain in `AGENTS.md`.

Real isolated Windows checks reused existing Qwen3.8-27B weights and llama.cpp by path: generated text, inspected actual startup evidence, confirmed process exits, and restarted with identical settings after editing the profile. A separate real Chat run loaded the stopped deployment and replied "Hello!". Changed desktop controls were rendered and inspected. Evidence remains under `.scratch/packet01-live/`; temporary UAT backend and Electron have stopped. Hub error/transfer edge tests use deterministic external-boundary fakes.

Launch normally with root `Launch Workbench.vbs`. User data and models are preserved. GitHub CI remains disabled; retain local gates. OpenSpec remains the only specification/change format. Preserve packet ordering and existing integration boundaries.

No Packet 01 implementation work remains. Check PR #111 for merge status; begin Packet 02 only when authorized.
