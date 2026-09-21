# Current handover

Last updated: 2026-09-21.

## Approved shared UX specification

Specification-only update complete on `codex/lock-shared-ux-spec`. Dave approved the conversation-led layout and shared UX decisions. Packet 03's [design](openspec/changes/03-complete-shared-chat/design.md#shared-ux-contract) owns the contract: grouped General/project chats, compact model/reasoning/context/tok/s controls, always-streamed answers with remembered optional detail streams, Queue/Stop, scoped approvals, background attention, on-demand Files/activity, Library and system/light/dark themes. Packets 04-08 extend that contract and retain their original sequence; 04 owns Agents/connections and the async transition. Packet 07 must implement a new React Flow editor within the existing desktop and preserve Agent run history.

No application code or current capability specs changed. UX acceptance remains pending until Dave reviews the built journeys or explicitly defers review. Early Chat review and approved Lab/Workflows layout checkpoints are required. Cross-packet review and `openspec validate --all` passed (15/15); no runtime tests were needed for these document changes. Delivery is awaiting PR/merge. Packet 03 implementation is the next separately authorized goal; do not start automatically.

## Existing implementation baseline

Interaction repairs are complete in [PR #116](https://github.com/Vidcar/thtaib/pull/116); details/evidence remain in `openspec/changes/archive/2026-09-21-repair-local-interaction-boundaries`. Preserve selection/draft ownership, Electron document trust, legacy chronology and durable stream reconciliation. Prior checks passed: 351 default/147 integration backend tests, desktop build and actual Windows Chat/Electron checks, contracts and OpenSpec 15/15. These are prior repair evidence, not validation of the proposed UX.

Ordinary backend/desktop were restored by that delivery; this specification update does not change runtime state or model weights. GitHub CI remains disabled. Use repository `AGENTS.md` for implementation checks and isolated `.scratch/` data roots.
