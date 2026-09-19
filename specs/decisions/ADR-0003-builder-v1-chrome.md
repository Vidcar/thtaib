# ADR-0003: Lock Builder v1 canvas chrome

**Status:** draft; see [the catalogue](../catalog.json). Builder is not implemented.

## Context and current requirement

[OQ-016](../open-questions.md#oq-016) treated Builder look-and-feel and canvas chrome as fully unresolved. That blocked a later implementation Issue from having a maintainer-recorded chrome baseline. [Issue #29](https://github.com/Vidcar/thtaib/issues/29) supplies the seven **v1 chrome** locks. This record captures them. It does not implement a React Flow canvas.

Existing behaviour that this chrome must not reopen:

- [WF-001](../modules/agents-workflows.md#wf-001) — configuration links are not executable workflow steps.
- [ARCH-003](../architecture.md#arch-003) — Models, Lab, Chat and Builder share configurations; a surface must not hide its own profile.
- [API-002](../modules/backend-desktop.md#api-002) — React Flow edits definitions; the visual graph is not executable authority.
- [OQ-004](../open-questions.md#oq-004) — run-state, continuation and uncertain-effect semantics stay open.
- [OQ-011](../open-questions.md#oq-011) — the durable product Approvals inbox stays open.

Revision 0.5 already selects Electron / React / TypeScript / React Flow as the definition editor. This decision does not change that stack.

## Proposed decision

Lock **Builder v1 chrome** as follows. These are presentation locks for a later implementation Issue. They are not a claim that Builder exists, and they do not add an execution owner.

1. TooGraph-inspired cues, **original** layout (inspiration only — not a fork/pixel clone).
2. Grid, zoom, minimap, multi-select.
3. Icon rail + searchable node library.
4. Expanded nodes with inline prompt editor.
5. Run/Stop + canvas highlight + run inspector (**OQ-004 / OQ-011 stay open** for run semantics / Approvals inbox).
6. Colour+label **workflow** edges; config via node badge/popover **not** a canvas config edge (**WF-001 unchanged**).
7. Inherit workflow profile/deployment; explicit per-node override only (**ARCH-003 unchanged**).

Authoritative homes stay where they are. [OQ-016](../open-questions.md#oq-016) becomes **partially decided** for v1 chrome and remains open for the unfinished Builder surface. Do not rewrite [WF-001](../modules/agents-workflows.md#wf-001) or [ARCH-003](../architecture.md#arch-003) behaviour.

## Alternatives and rationale

Alternatives actually considered:

- Leave chrome fully unresolved. Rejected: the seven locks are already maintainer-stated; leaving them only in an issue invites silent invention at implementation time.
- Fork or pixel-clone TooGraph / CDF. Rejected: TooGraph is inspiration only. The layout must be original.
- Draw configuration as a canvas config edge. Rejected: that would present config as a workflow step and reopen [WF-001](../modules/agents-workflows.md#wf-001).
- Hide a per-node profile or default every slider on every node. Rejected: that would reopen [ARCH-003](../architecture.md#arch-003).
- Close [OQ-016](../open-questions.md#oq-016) or treat this record as Builder shipped. Rejected: chrome is not the surface.

## Consequences and compatibility

What changes: v1 chrome is recorded. Implementation may target these seven locks without inventing a different default look.

What does not change: workflow execution ownership, configuration-versus-workflow compilation ([WF-001](../modules/agents-workflows.md#wf-001)), shared profile/deployment records ([ARCH-003](../architecture.md#arch-003)), React Flow as definition editor ([API-002](../modules/backend-desktop.md#api-002)), run-state contracts ([OQ-004](../open-questions.md#oq-004)), or the Approvals inbox ([OQ-011](../open-questions.md#oq-011)). No public wire contract, persistence schema, permission model or process boundary is selected here.

Rollback is documentary: supersede this record and restore [OQ-016](../open-questions.md#oq-016) if maintainers reject a lock. There is no data migration.

Unresolved risk: a later implementation may ship a mock that resembles this chrome without backend execution. That remains a defect against [API-002](../modules/backend-desktop.md#api-002), not permission to call Builder finished.

## Verification

This record is documentation; pack integrity checks apply. Builder canvas implementation and product UAT belong to a later implementation issue. A screenshot or TooGraph resemblance is not that evidence.

## Review and supersession

No prior ADR is superseded. Record the real reviewer, reference and date in [the catalogue](../catalog.json) when the product owner accepts this decision.
