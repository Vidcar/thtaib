# Shared contracts and compatibility

[Specification index](README.md) · [Status and evidence](catalog.json)

## Status and boundary

Revision 0.5 selects Pydantic plus JSON Schema for typed definitions and identifies the owned record families. [ADR-0002](decisions/ADR-0002-contract-authoring.md) is **accepted**: canonical Pydantic definitions generate JSON Schema and OpenAPI, and pinned OpenAPI→TS generation produces committed desktop consumer types.

The semantic records are specified in their owning modules: models/profiles/deployments/compatibility in [models](modules/models.md); resolved agent/workflow setup in [agents and workflows](modules/agents-workflows.md); definitions in [registry](modules/registry.md); run/checkpoint/snapshot/knowledge/artifact references in [state](modules/state-recovery.md); jobs/approvals/events in [backend](modules/backend-desktop.md); environments/tool invocation in [tools](modules/environments-tools.md); and captured cases/results in [Lab](modules/lab-evaluation.md). The shared selected ≠ loaded ≠ applied rule for that resolved setup is the [effective setup contract](architecture.md#effective-setup-contract) under [ARCH-003](architecture.md#arch-003). This file does not author a second bag schema.

## Authoritative paths

Bound locations for the Slice 1 shared-contract path are in [the repository map](repository-map.json): Python source, OpenAPI export, JSON Schema, generated desktop types, generator script and contract tests. Event/stream contracts, the remaining product HTTP route table, and import-boundary checks stay unbound until their `required_before` trigger. A linked module describes semantics, not a substitute handwritten JSON schema.

Upstream documentation pointers: [Pydantic schema generation and FastAPI client generation](sources/upstream.md#contract-generation). The selected TypeScript generator is pinned **openapi-typescript 7.13.0** in the desktop lockfile.

## Requirements and acceptance checks

<a id="ctt-001"></a>
### CTT-001: Author exact shared types once

Use canonical Pydantic definitions for shared backend data/configuration and generate JSON Schema. Generate HTTP client/types from the FastAPI OpenAPI description rather than maintain independent handwritten wire types. Choose and pin the generator at scaffolding. Streaming/event payloads need their own shared typed source and generation path; an HTTP client generator does not automatically specify a stream protocol.

**Acceptance:** Generate outputs reproducibly and compare with committed artifacts. Verify backend/frontend fixtures use the same field/enum definitions. Change a contract and demonstrate stale generated output causes a failed freshness check.

<a id="ctt-002"></a>
### CTT-002: Specify behaviour and compatibility before relying on a contract

For a shared boundary, define identity/version, ownership, required/optional values, capability/permission semantics, errors, lifecycle/cancellation/recovery and side effects in the owning specification. Specify supported historical versions and migration/rejection behaviour before storing durable data for reuse. New supported model-specific settings must remain representable rather than being silently discarded by a generic schema.

**Acceptance:** Check accepted and rejected fixtures, unsupported versions and migration/round-trip behaviour where relevant. Exercise cancellation/recovery at the real boundary; schema validation alone is insufficient.

## Generation maintenance

Generate from pinned tools using the registered commands in [commands](commands.md). Mark generated outputs and retain the generator input/configuration. Do not hand-edit generated clients or patch an exported schema to disagree with its source. The freshness check covers changed, removed and newly generated files, not merely tracked diffs that ignore untracked output.

The landed Slice 1 generator input is `create_shared_contract_app` in `apps/backend/src/workbench_backend/contracts`. It exports the shared session-trust header envelope (`X-Workbench-Local-Token`) and run/cancel lifecycle vocabulary (`cancel_requested`, `cancelled`, and the related queued/running/completed/failed names). It is not mounted on the product FastAPI app; product `/openapi.json` stays unpublished. Module-local Pydantic models for inference, harness, Lab and knowledge remain local and are not this generated path. [OQ-002](open-questions.md#oq-002), [OQ-004](open-questions.md#oq-004), [OQ-008](open-questions.md#oq-008) and remaining [OQ-010](open-questions.md#oq-010) gates stay open except for the registered advisory freshness job.
