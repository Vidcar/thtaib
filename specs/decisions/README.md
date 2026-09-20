# Architecture Decision Records

Status and approval of each record live in [the catalogue](../catalog.json). Records explain rationale and scope; current behaviour lives in [architecture](../architecture.md) and the module specifications. Smaller dated decisions are in the [changelog](changelog.md).

| Record | Status | Purpose |
| --- | --- | --- |
| [ADR-0001](ADR-0001-adopt-specification-pack.md) | superseded | Original proposal to adopt the specification pack |
| [ADR-0002](ADR-0002-contract-authoring.md) | accepted | Canonical Pydantic → OpenAPI → TypeScript contract authoring (Issue #41) |
| [ADR-0003](ADR-0003-builder-v1-chrome.md) | draft | Builder v1 canvas chrome locks (Issue #29); Builder is not shipped |
| [ADR-0004](ADR-0004-slim-specification-pack.md) | accepted | Slim the pack and adopt it (product owner, 2026-09-19) |
| [ADR-0005](ADR-0005-application-record-storage.md) | accepted | Reuse application SQLite for new records; staged migration of existing JSON |

Use ADRs for consequential rationale that future agents need, not as mandatory approval paperwork. Technical decisions within the authorized scope are agent-owned under [AGENTS.md](../../AGENTS.md); record the real decision authority and ask Dave only for material unresolved choices. Historical approval language does not override the current working process.

Write a new record from the [decision template](../templates/decision.md) with the next unused number. Never renumber. A replacement record names what it supersedes and updates the affected specifications in the same change. Revision 0.5 is the evidence for the original stack selections; do not invent an approval trail for them.
