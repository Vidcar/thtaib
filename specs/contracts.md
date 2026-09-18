# Shared contracts and compatibility

[Specification index](README.md) · [Status and evidence](catalog.json)

## Status and boundary

Revision 0.5 selects Pydantic plus JSON Schema for typed definitions and identifies the owned record families. It does **not** define final fields, routes, event envelopes or a client generator. This document proposes the authoring/maintenance convention discussed with the user; approve it through [ADR-0002](decisions/ADR-0002-contract-authoring.md).

The semantic records are specified in their owning modules: models/profiles/deployments/compatibility in [models](modules/models.md); resolved agent/workflow setup in [agents and workflows](modules/agents-workflows.md); definitions in [registry](modules/registry.md); run/checkpoint/snapshot/knowledge/artifact references in [state](modules/state-recovery.md); jobs/approvals/events in [backend](modules/backend-desktop.md); environments/tool invocation in [tools](modules/environments-tools.md); and captured cases/results in [Lab](modules/lab-evaluation.md).

## Authoritative paths

Actual locations for Python contracts, schema exports, OpenAPI, generated client/types, event definitions, migrations and generators are deliberately `unbound` in [the repository map](repository-map.json). Bind existing locations before creating replacements. A linked module describes semantics, not a substitute handwritten JSON schema.

Upstream documentation pointers: [Pydantic schema generation and FastAPI client generation](sources/upstream.md#contract-generation). Those references support the mechanism; the choice to use it here is the proposal.

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

Generate from pinned tools using a registered command. Mark generated outputs and retain the generator input/configuration. Do not hand-edit generated clients or patch an exported schema to disagree with its source. A freshness check must cover changed, removed and newly generated files, not merely compare tracked diffs while ignoring untracked output.

No generator or generated schema is shipped in this pack, so no generated-contract freshness gate is claimed to exist. Before the first shared API/registry contract is merged, create its actual source and generator, register paths/commands, and add that gate. Resolve [OQ-001](open-questions.md#oq-001), [OQ-002](open-questions.md#oq-002), [OQ-004](open-questions.md#oq-004) and [OQ-008](open-questions.md#oq-008) as applicable.
