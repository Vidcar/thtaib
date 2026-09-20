# Current handover

Last updated: 2026-09-20.

## Goal and state

Packet 01 is complete in [PR #106](https://github.com/Vidcar/thtaib/pull/106), `codex/repository-cleanup`, based on `46157ed` (PR #105). The PR records protected CI and merge results. Packet 02 behavioral repairs are not part of this change.

## Changes and decisions

- [David's exact vision](thtaib-vision.md) is canonical product intent. README/spec index provide the short reading path; Workflows is the intended area, Agent run / Builder legacy/UI terminology. Revision 0.5 stays historical.
- Documentation is about 24% smaller including the new vision. Current decisions live in owning contracts; unique rationale/evidence remains linked. All 53 requirement IDs and 22 evidence rows remain, without status promotion.
- Removed the empty Compose stub, unused reserved-prefix wrapper, duplicate replay wrappers and unused React Flow package/transitive dependencies. React Flow remains the intended workflow-canvas integration. Replay middleware retains fixture matching, reconstruction and no live dispatch.
- Checker covers maintained docs, vision and handover without requiring obsolete ancillary files. Existing run/Chat startup migration is bound; remaining metadata migration stays separate. CI and branch protection are unchanged.

## Validation and next step

Windows: 213 default backend tests, 92 integration tests, 41 focused replay/shell/memory tests and 62 checker/tooling tests passed. Desktop build passed (includes typecheck and SSE regression). Spec checker passed, including requirement preservation against the base commit. Live protection query confirmed the four required Ubuntu checks with strict protection.

Launch remains root `Launch Workbench.vbs`; actual checks are in [commands](specs/commands.md). No cleanup implementation remains. Next product work is the separately scoped packet 02 baseline repairs when supplied, rather than feature expansion. No user/model data changed.
