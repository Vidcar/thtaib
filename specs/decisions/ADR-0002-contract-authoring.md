# ADR-0002: Author shared types once and generate consumer contracts

**Decision status and approval:** see [the catalogue](../catalog.json). Initially a proposal.

## Context

Revision 0.5 selects Pydantic and JSON Schema and calls for versioned shared definitions. It does not specify exact wire fields or client-generation tooling. Independent handwritten backend, frontend and registry types would create multiple places to change the same contract.

## Proposed decision

Adopt [CTT-001](../contracts.md#ctt-001) and [CTT-002](../contracts.md#ctt-002): canonical Pydantic definitions, generated JSON Schema, and HTTP client/types generated from FastAPI OpenAPI. Define event/stream schemas explicitly from shared types; do not assume an HTTP generator covers the event protocol. Pin the generator/toolchain through OQ-001 and bind real locations before implementation.

Behavioural specifications remain necessary for policy, capabilities, lifecycle, effects and compatibility. A generated schema is not permission to execute an action and does not prove cancellation or recovery.

## Alternatives considered

Handwritten duplicate consumer types are easy initially but create drift risk. A schema-first pipeline could also be coherent, but the preceding planning discussion selected Pydantic as the authoring source to align with the backend foundation. This record does not select a particular TypeScript generator or invent API routes.

## Consequences and migration

Generated outputs are not manually edited. Generation must be deterministic under pinned tools and checked for changed, removed and new outputs. Existing types, if present, need an assessed transition; do not create a second concurrent contract source. Retain compatibility or provide explicit migration/rejection for stored/shared versions.

## Evidence and approval

Mechanism references are in [upstream links](../sources/upstream.md#contract-generation). Acceptance requires genuine human review recorded in the catalogue. Implementation verification requires real shared-type fixtures, generation/freshness checks and affected consumer tests. No schemas or client generator are shipped in this pack.
