# Current handover

Last updated: 2026-09-20.

## Goal and state

Testing/CI simplification complete in [PR #105](https://github.com/Vidcar/thtaib/pull/105), `codex/test-suite-simplification`. No production application code changed. [Commands](specs/commands.md) and AGENTS now describe the tiers and isolation requirements.

## Changes and decisions

- Default: Models/Chat plus fast rules. Integration: cross-service harness/replay, real HTTP/SSE, host-shell and process checks. CI runs both on backend changes; no required coverage silently excluded.
- Scripted fixtures explicitly use an offline unhealthy probe instead of real closed-port waits. Reused application managers; consolidated polling helpers. Removed a duplicate lifecycle test and tautological catalogue assertion.
- Live SSE reconnect now observes a real loopback stream while the run remains live (0.8s versus 30s). Windows blocked transport uses event cleanup.
- Test bootstrap isolates the import-time app under `.scratch/`; early baseline imports could refresh everyday deployment metadata. No model weights/settings/conversations were used as test fixtures.
- Five workflows consolidated into one; three path-filter jobs become one; removed duplicate desktop typecheck and repeated post-merge real-model runs. Four required Linux check names preserved.

## Measured checks (Windows, installed dependencies)

Original: 304 tests, 833.17s wall, no failures; one desktop-dependency skip. Final: 213 default tests / 18.166s and 91 integration tests / 40.504s; all passed without skips. Real CUDA tiny-model smoke: four passed / 6.099s. Desktop: 4.540s before, 2.760s after. Spec checks, 57 tooling tests, contracts and actionlint pass.

Isolated Electron: real reply, transcript reopening and Models health passed. Wrong tiny-model follow-up despite intact request history; no capability claim. Test processes stopped. Raw logs: `.scratch/test-audit-measurements/`, `.scratch/test-audit-live/`.

## Delivery

All eight GitHub jobs passed, including both Windows jobs and real-model smoke. Final handover-only commit follows the same protected checks before merge. No GitHub settings changes needed. Testing/CI work is complete; resume product delivery using the [delivery map](docs/delivery-feature-map.md#next-path).
