# Versioned integration registry

[Architecture](../architecture.md) · [Status and evidence](../catalog.json) · [Decisions](../decisions/changelog.md)

## Purpose

One application-owned, versioned description of every model, agent, tool, environment and adapter integration, consumed by React Flow for presentation, LangChain for tool exposure and LangGraph for compilation, so that no consumer keeps its own copy of the integration model.

## Boundaries and ownership

The application owns the integration model and its validation. React Flow, LangChain tools and LangGraph consume it. Adapters and their contract tests prove that a registered behaviour is actually implemented; a registry entry only declares it. Source: [Revision 0.5, page 7](../sources/README.md#integration-registry).

## Interfaces and contracts

A definition carries stable identity and version with dependency support; typed inputs and outputs with connection kind (configuration or workflow); configuration schema, defaults and applied values; capabilities and discovery; environment, access, approval and memory scope; progress, results, errors and cancellation; run, checkpoint, effect, recovery and snapshot behaviour; context, evidence and provenance; presentation controls, renderers and MCP Apps permissions. This is a semantic inventory; the exact schema is authored once at the contract boundary ([contracts](../contracts.md)). Nothing is implemented yet (`integration-definitions` is unbound in [the repository map](../repository-map.json)).

## Behaviour

Definitions are registered, validated and resolved before execution; a stored graph names the definitions it uses. Invalid wiring is rejected with an explanation; an unverified capability is never promoted to supported. The backend repeats validation at run start because deployment, environment, access or configuration may have changed since editing; that is the same resolve-before-run step as the [effective setup](../architecture.md#effective-setup). Effective controls are the applied bag plus the actual runtime limits; user-selected budgets are distinguished from runtime boundaries. The registry does not imply dynamic code loading, remote plugin execution or hot reload.

## Requirements

<a id="reg-001"></a>
### REG-001: Define identity, capabilities and execution together

A node/adapter definition includes the identity, connections, configuration, capability/policy, execution/state, evidence/reuse and presentation information specified above. Experimental status and supported dependency versions are explicit.

**Acceptance:** Register a representative model, agent and tool definition; validate their required metadata and explain incomplete configuration without pretending the integrations are ready.

<a id="reg-002"></a>
### REG-002: Validate wiring and effective execution policy

Use types, required capabilities, configuration completeness and execution policy to reject known-incompatible connections. Distinguish configuration links from workflow/data/artifact links. Repeat backend validation immediately before execution and enforce policy in the executing tools/workers.

**Acceptance:** Try compatible, incompatible, incomplete and unverified connections. Change an environment permission after editing and confirm run-start validation detects the new restriction.

<a id="reg-003"></a>
### REG-003: Keep a single integration authority

React Flow presentation, LangChain tool exposure and LangGraph compilation consume the application registry. New integrations register there instead of establishing disconnected copies of the integration model throughout the application.

**Acceptance:** Trace a definition change to all consumers and detect a stale/incompatible consumer. Demonstrate that frontend connection rules are not the sole execution validator.

<a id="reg-004"></a>
### REG-004: Unify run attribution and approvals

Map agent, workflow, tool, interpreter and interactive-panel events to one run hierarchy. Route approvals through Deep Agents/LangGraph interrupts and the application interface. Embedded panels and tool-calling programs cannot bypass access policy.

**Acceptance:** Inspect one implemented path of each kind, correlating its parent run, progress, approval and result. Report unsupported event/capture capabilities explicitly.

<a id="reg-005"></a>
### REG-005: Expose effective controls and limits

Configuration includes settings schemas, defaults, required fields, applied values, optional budgets and effective technical limits. Preserve supported controls and distinguish user-selected budgets from runtime boundaries. Selected ≠ applied.

**Acceptance:** Render and resolve a configuration containing runtime-specific settings and an unset budget. Verify the applied values and any actual limiting boundary are visible.

## Status and evidence

Rows REG-001…005 in [the catalogue](../catalog.json). No registry exists on `main`.

## Open questions

[OQ-008](../open-questions.md#oq-008) schemas, compatibility, discovery and extension trust; [OQ-004](../open-questions.md#oq-004) shared identities and events; [OQ-015](../open-questions.md#oq-015) workflow import/export.
