# Current handover

Last updated: 2026-09-21.

## Active prerequisite migration

Work in progress on `codex/migrate-local-agent-interaction`, starting from verified clean main `98c77cc`. User authorized planning through implementation and delivery; stop before Packets 03–08. Active artifacts: `openspec/changes/migrate-local-agent-interaction`. Config and proposed packet plans now declare this prerequisite; no deferred feature is complete. Main specs and ordinary application behavior remain unchanged.

Baseline rerun: 315 default and 142 integration tests, desktop build/typecheck/SSE/settings and generated-contract freshness passed; strict OpenSpec 16/16 passed. Backend commands used `uv run --no-sync` because the running ordinary backend locks its executable. No ordinary process was stopped.

Published React SDK 1.1.1 / SDK 1.11.1 / protocol 0.0.19 inspected; core peer ^1.1.48. Installed Python LangGraph 1.2.11 public sync/async v3 state probes passed (experimental API). Real SDK/FastAPI/model proof remains pending. Prefer sync execution if proven; Packet 04 retains the full async transition unless the proof requires moving it coherently.

Next: finish native/SDK real-model streaming, tool, approval/denial, continuation and confirmed cancellation proof before replacing consumers. Helpers live under `.scratch/interaction-compat`, `interaction-native-proof`, `interaction-ui-proof`. Isolated model root `.scratch/interaction-model`, port 8127, startup in progress; stop only that owned model when finished. Ordinary backend :8000 untouched; no active ordinary runs observed. Preserve weights, real data, application/checkpoint ownership and Packet 02 guarantees.

## Completed baseline

Packet 02 is complete in [PR #113](https://github.com/Vidcar/thtaib/pull/113), branch `codex/packet-02-inference-adapter`, based on main after PR #112. Current model contracts are synced under `openspec/specs/models/spec.md`; the completed change is archived as `2026-09-21-02-complete-inference-adapter`. Packets 03–08 remain proposed.

Packet 02 setup-specific Qwen evidence and helpers remain under `.scratch/packet02-live/` and `.scratch/packet02_*.py`. Migration live checks must be rerun through the new path. No CI added.
