# Current handover

Last updated: 2026-09-21.

## Completed interaction boundary repairs

Corrective change: `openspec/changes/archive/2026-09-21-repair-local-interaction-boundaries`. Delivery branch `codex/repair-local-interaction-boundaries` targets main from `87e0f507`. Current contracts are synchronized. The completed local LangChain migration remains intact. Packet 03 is the next separate goal; do not start automatically. Packets 03-08 remain proposed and Packet 04 owns the full async transition.

Chat now keeps selection, transport, pending commands and drafts under coherent generation/identity ownership; Agent-run/Lab callbacks have corresponding guards. Electron main validates document/frame ownership before adding the backend token and denies untrusted windows/navigation while opening validated HTTP(S) links externally. Legacy history retains chronology; existing projections repair only with exact old-seed provenance, preserving later output and display edits.

Passed: 351 default and 147 integration backend tests; 23 focused recovery/display tests; shared-contract freshness; desktop build including 12 actual Chat component cases, Agent-run ownership and actual Windows Electron receiver fixtures. Reviewed baseline fails 10 Chat cases. Final built desktop/Qwen27B journey passed incremental output, navigation, cancel, partial revisit and same-thread continuation: exactly two runs, answer AZALEA, no renderer errors. Evidence and limitations are in the archived design; fixtures remain under `.scratch/`.

Validation: backend `uv run --no-sync python -m tests.run` and integration tier while executable is locked (installed dependencies checked); desktop `pnpm run build`; root `openspec validate --all`. Model weights and existing Qwen8080 are preserved. Ordinary backend8000 restored and desktop rebuilt. AGENTS.md records disposable development chats/memories/skills and authorized computer/process use. GitHub CI stays disabled.

No feature work remains in this repair; finish its Git delivery before beginning any separately authorized packet.
