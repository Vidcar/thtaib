# ADR-0002: Author shared types once and generate consumer contracts

**Decision status and approval:** accepted in [the catalogue](../catalog.json). Maintainer review reference: [GitHub Issue #41](https://github.com/Vidcar/thtaib/issues/41) (David / Vidcar, 2026-09-19), the Slice 1 contracts issue that authorises this path.

## Context

Revision 0.5 selects Pydantic and JSON Schema and calls for versioned shared definitions. It does not specify exact wire fields or client-generation tooling. Independent handwritten backend, frontend and registry types would create multiple places to change the same contract.

## Decision

Adopt [CTT-001](../contracts.md#ctt-001) and [CTT-002](../contracts.md#ctt-002): canonical Pydantic definitions, generated JSON Schema, and HTTP types generated from a FastAPI OpenAPI description.

The landed Slice 1 path is:

- Canonical Pydantic source: `apps/backend/src/workbench_backend/contracts`.
- Generator input is a dedicated FastAPI **schema app** built from those models (`create_shared_contract_app`). It is not a second backend and is not mounted on the product HTTP app.
- Product `/openapi.json` / `/docs` stay unpublished ([OQ-002](../open-questions.md#oq-002) covers the remaining trust questions).
- OpenAPI export and JSON Schema are committed under `apps/backend/contracts/`.
- Desktop consumer types are generated with pinned **openapi-typescript 7.13.0** (`apps/desktop/package.json` / `pnpm-lock.yaml`) into `apps/desktop/src/generated/shared-contracts/`.
- Generation and freshness commands are registered in [commands](../commands.md). The freshness check fails on changed, removed, or newly generated files versus the committed tree.
- Slice 1 shared types include the local-trust header envelope (`X-Workbench-Local-Token`) and run/cancel lifecycle names (`cancel_requested`, `cancelled`, plus the existing queued/running/completed/failed names). Electron secret I/O and harness cancel semantics are out of scope here ([#40](https://github.com/Vidcar/thtaib/issues/40), [#42](https://github.com/Vidcar/thtaib/issues/42)).

Event/stream schemas still need their own shared typed source when a streaming consumer is added. An HTTP type generator does not automatically specify an event protocol.

Behavioural specifications remain necessary for policy, capabilities, lifecycle, effects and compatibility. A generated schema is not permission to execute an action and does not prove cancellation or recovery.

## Alternatives considered

Handwritten duplicate consumer types are easy initially but create drift risk. A schema-first pipeline could also be coherent, but the preceding planning discussion selected Pydantic as the authoring source to align with the backend foundation.

For OpenAPI→TS, `openapi-typescript` was selected over a Java OpenAPI Generator SDK and over generating the entire unpublished product route table. Slice 1 needs committed, freshness-gated consumer **types** for the shared envelope, not a sprawling unused client. The product app's runtime OpenAPI remains disabled so generation does not require opening a privileged HTTP docs surface.

## Consequences and migration

Generated outputs are not manually edited. Generation must be deterministic under pinned tools and checked for changed, removed and new outputs. Existing module-local Pydantic models (inference, harness, Lab, knowledge) remain local until those routes are moved onto this path; they are not a second shared-contract source for the Slice 1 types. Desktop `src/renderer/types.ts` handwritten shapes are not replaced in this change. #42 must consume the shared lifecycle names rather than invent a parallel enum.

## Evidence and approval

Mechanism references are in [upstream links](../sources/upstream.md#contract-generation). Human approval is Issue #41, recorded in the catalogue. Generation, committed artifacts and the Linux freshness job exist and `shared-contract-freshness (ubuntu-latest)` remains a required check on `main` (2026-09-20 CI slim: no second Windows freshness job; generation is OS-independent); the CTT-001 row in the catalogue records the current status.
