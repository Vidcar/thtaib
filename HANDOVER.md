# Current handover

Last updated: 2026-09-21.

## Current state

Packet 01 review repairs are complete on `codex/packet-01-review-fixes`, pending PR/merge. This corrects requirements already delivered in PR #111; packets 02–08 remain planned. The original packet remains archived under `openspec/changes/archive/2026-09-21-01-complete-model-management/`; clarified current behavior is in `openspec/specs/models/spec.md`.

## Repairs and decisions

Unconfirmed process exit retains ownership and blocks replacement, deletion and runtime repinning, including failed-start cleanup. Interrupted starts without recorded identity recover to actionable failure. Disconnect shares the health-update lock. The desktop submits only deliberate startup overrides; null explicitly clears an inherited startup key. Chat defaults to saved deployment settings (response and agent bags together), permits selecting a current preset or explicitly opting out, and preserves the immutable launch snapshot. Ready managed turns avoid full weight hashing; launch integrity checks remain. Deletion previews use current file sizes; first-use guidance includes on-demand loading.

## Verification and local use

All six findings were reproduced before correction. Final gates passed: 288 default backend tests, 120 integration tests, desktop typecheck/SSE/preset-payload regression/build, generated-contract check and 16 strict OpenSpec items. Targeted manager-restart regression also passed. Tests cover denied/unconfirmed exits, failed-start identity retention, delete/repin refusal, blocked health/disconnect ordering, saved prompt composition, sparse overrides and full-hash avoidance. Prompt inheritance uses scripted model execution; no new real-model capability claim.

The idle everyday backend was refreshed after checking zero active runs/imports/model processes. The rebuilt Windows Chat controls were inspected read-only; no synthetic records were added to everyday data. App is open, and normal launch is `Launch Workbench.vbs`. Preserve user models/data and disabled GitHub CI; commands remain in `AGENTS.md`.

Next: merge the validated repair PR; no later packet is authorized by this repair.
