# Shared Contracts

## Purpose

Specify how shared backend, desktop, and event data shapes are authored once, generated outward, kept fresh, and paired with behavioral contracts before they are relied on for durable records or execution.

## Requirements

### Requirement: CTT-001 - Author exact shared types once

Shared backend data and configuration shapes SHALL be authored as canonical Pydantic definitions. JSON Schema and OpenAPI SHALL be generated from a dedicated schema app, and desktop TypeScript SHALL be generated from that OpenAPI description with the pinned generator. Generated artifacts MUST NOT be manually edited. Streaming and event payloads SHALL have a shared typed source; an HTTP client generator alone MUST NOT be treated as specifying a stream protocol.

#### Scenario: Contract generation freshness

- WHEN shared contract outputs are regenerated
- THEN committed JSON Schema, OpenAPI, and desktop TypeScript MUST match reproducibly
- AND changed, removed, or newly generated output MUST cause the freshness check to fail until committed.

### Requirement: CTT-002 - Specify behaviour and compatibility before relying on a contract

For each shared boundary, the owning specification SHALL define identity, version, ownership, required and optional values, capability and permission semantics, errors, lifecycle, cancellation, recovery, side effects, and supported historical-version behavior before durable reuse. Schema validity alone MUST NOT authorize actions or prove cancellation, recovery, compatibility, or operational support. New supported model-specific settings MUST remain representable rather than silently discarded by a generic schema.

#### Scenario: Boundary behavior validation

- WHEN accepted, rejected, unsupported-version, and migration fixtures are exercised at a shared boundary
- THEN schema validation MUST be paired with behavioral checks for permissions, lifecycle, cancellation, recovery, and side effects
- AND incompatible or unsupported values MUST be rejected or reported explicitly.

### Requirement: CTT-003 - Keep shared-contract scope explicit

The header envelope, run lifecycle names, run-stream envelope, shared `AgentEvent`, and exported Hugging Face repository and variant records SHALL follow the shared generation path once bound. Remaining module-local route shapes MAY stay module-local until migrated, but they MUST NOT be described as generated shared contracts.

#### Scenario: Module-local route shape

- WHEN a route still uses module-local Pydantic models mirrored by hand in the desktop
- THEN its behavior MUST be governed by the owning module specification
- AND it MUST NOT be treated as freshness-gated shared output until moved onto the generation path.

### Requirement: CTT-004 - Use a schema app, not product OpenAPI publication

The shared OpenAPI export SHALL come from a dedicated schema app created for contract generation. That schema app MUST NOT be mounted as a second backend, and product `/openapi.json` or docs publication MUST remain a separate trust decision.

#### Scenario: Generate without product docs

- WHEN shared OpenAPI is exported
- THEN generation MUST use the schema app
- AND privileged product HTTP documentation MUST remain unpublished unless separately authorized.
