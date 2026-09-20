# Shared contracts

[Architecture](architecture.md) · [Status and evidence](catalog.json) · [ADR-0002](decisions/ADR-0002-contract-authoring.md)

## Purpose and boundary

Shared types are written once as Pydantic models and generated outward: JSON Schema and OpenAPI from a dedicated schema app, TypeScript for the desktop through pinned `openapi-typescript` 7.13.0. Record semantics live in the owning module specification; this file governs how exact shapes are authored and kept fresh.

## Paths and commands

Canonical source `apps/backend/src/workbench_backend/contracts`; generated `apps/backend/contracts/` (OpenAPI, JSON Schema) and `apps/desktop/src/generated/shared-contracts/`; generator `scripts/generate_shared_contracts.py`; tests `apps/backend/tests/contracts` ([repository map](repository-map.json), [commands](commands.md)). Generated files are never hand-edited; the freshness check fails on changed, removed or newly generated output.

## Current scope

Slice 1 covers the `X-Workbench-Local-Token` header envelope and the run-lifecycle names (`queued`, `running`, `cancel_requested`, `cancelled`, `completed`, `failed`). The run-stream envelope (`RunStreamEnvelope`: `snapshot`, `run_event`, `stream_end`, plus the shared `AgentEvent` `{at, kind, detail}` item) is the first event-contract slice; `snapshot` still embeds the module-local GET record until those routes move onto the generated path. Hugging Face repository discovery now also exports its canonical `HubRepository` and variant records from `inference/schemas.py` through the same schema app; Models consumes the generated TypeScript shape. Remaining route shapes are module-local Pydantic models mirrored by hand in `apps/desktop/src/renderer/types.ts`. Product `/openapi.json` stays unpublished. Event contracts are bound (`shared-event-contracts`).

## Requirements

<a id="ctt-001"></a>
### CTT-001: Author exact shared types once

Use canonical Pydantic definitions for shared backend data/configuration and generate JSON Schema. Generate HTTP client/types from the FastAPI OpenAPI description rather than maintain independent handwritten wire types. Choose and pin the generator at scaffolding. Streaming/event payloads need their own shared typed source and generation path; an HTTP client generator does not automatically specify a stream protocol.

**Acceptance:** Generate outputs reproducibly and compare with committed artifacts. Verify backend/frontend fixtures use the same field/enum definitions. Change a contract and demonstrate stale generated output causes a failed freshness check.

<a id="ctt-002"></a>
### CTT-002: Specify behaviour and compatibility before relying on a contract

For a shared boundary, define identity/version, ownership, required/optional values, capability/permission semantics, errors, lifecycle/cancellation/recovery and side effects in the owning specification. Specify supported historical versions and migration/rejection behaviour before storing durable data for reuse. New supported model-specific settings must remain representable rather than being silently discarded by a generic schema.

**Acceptance:** Check accepted and rejected fixtures, unsupported versions and migration/round-trip behaviour where relevant. Exercise cancellation/recovery at the real boundary; schema validation alone is insufficient.

## Open questions

[OQ-002](open-questions.md#oq-002) event transport; [OQ-004](open-questions.md#oq-004) event envelopes; [OQ-008](open-questions.md#oq-008) registry schemas; [OQ-017](open-questions.md#oq-017) record persistence and migrations.
