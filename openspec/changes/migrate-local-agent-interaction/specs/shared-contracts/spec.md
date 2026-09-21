## MODIFIED Requirements

### Requirement: CTT-001 - Author exact shared types once

Application-owned shared backend data, metadata, command extensions and configuration shapes SHALL be authored as canonical Pydantic definitions. JSON Schema and OpenAPI SHALL be generated from a dedicated schema app, and desktop TypeScript SHALL be generated with the pinned generator. Generated artifacts MUST NOT be manually edited. Upstream-owned interaction definitions SHALL be imported from compatible published upstream sources rather than copied into a competing protocol. Serialization and runtime validation SHALL explicitly bridge those definitions and application-owned schemas; type declarations alone MUST NOT be treated as validation.

#### Scenario: Contract generation freshness

- WHEN shared contract outputs are regenerated
- THEN committed application-owned JSON Schema, OpenAPI and desktop TypeScript MUST match reproducibly
- AND changed, removed or new output MUST fail freshness checks until committed, while upstream protocol definitions MUST remain owned by their pinned packages.

### Requirement: CTT-002 - Specify behaviour and compatibility before relying on a contract

For each shared boundary, the owning specification SHALL define identity, version, ownership, required and optional values, capability and permission semantics, errors, lifecycle, cancellation, recovery, side effects and supported historical-version behavior before durable reuse. The interaction boundary SHALL record and validate its exact compatible package/protocol versions and allowed serialized fields. Schema validity alone MUST NOT authorize actions or prove cancellation, recovery, compatibility or operational support. New supported model-specific settings MUST remain representable rather than silently discarded by a generic schema.

#### Scenario: Boundary behavior validation

- WHEN accepted, rejected, unsupported-version and migration fixtures are exercised at a shared boundary
- THEN runtime validation MUST be paired with checks for permission, lifecycle, cancellation, recovery and side effects
- AND incompatible or unsupported values MUST fail explicitly without starting execution.

### Requirement: CTT-003 - Keep shared-contract scope explicit

The application header envelope, lifecycle names, application audit events, interaction metadata/extensions and exported Hugging Face repository/variant records SHALL follow the application generation path once bound. The upstream interaction protocol SHALL follow its own compatible package definitions. Superseded custom run-stream envelopes SHALL be removed after all consumers migrate. Module-local route shapes MAY remain module-local until migrated but MUST NOT be described as generated shared contracts.

#### Scenario: Module-local route shape

- WHEN a route still uses module-local Pydantic models mirrored by hand in the desktop
- THEN its behavior MUST be governed by the owning module specification
- AND it MUST NOT be treated as freshness-gated shared output until moved onto the generation path.

### Requirement: CTT-004 - Use a schema app, not product OpenAPI publication

The application shared OpenAPI export SHALL come from a dedicated schema app created for contract generation. That schema app MUST NOT become a second backend or duplicate upstream protocol ownership. Product OpenAPI/docs publication MUST remain a separate trust decision. Protocol and application payloads SHALL be serialized and validated at the authenticated product boundary, independently of documentation publication.

#### Scenario: Generate without product docs

- WHEN shared OpenAPI is exported
- THEN generation MUST use the schema app
- AND privileged product HTTP documentation MUST remain unpublished unless separately authorized.
