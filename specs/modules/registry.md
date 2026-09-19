# Versioned integration registry

[Specification index](../README.md) · [Status and evidence](../catalog.json)

## Ownership, scope and source

The application owns the integration model. React Flow, LangChain tools and LangGraph consume its contracts. Source: [revision 0.5, page 7](../sources/README.md#integration-registry).

## Definition content

A definition carries stable identity/version and dependency support; typed inputs/outputs and connection kind; configuration/defaults/applied values; capabilities and discovery; environment/access/approvals/memory scope; progress/results/errors/cancellation; run/checkpoint/effect/recovery/snapshot behaviour; context/evidence/provenance; and presentation controls/renderers/MCP Apps permissions.

This is a semantic inventory, not an approved JSON object schema. The exact model is created once at the contract boundary, under [contracts](../contracts.md), rather than independently in backend, desktop and plugins.

## Lifecycle and collaboration

Definitions are registered, validated and resolved before execution. A stored graph must identify the definitions it uses. Invalid wiring is rejected with an explanation; an unverified capability is not silently promoted to supported. The backend repeats validation at run start because deployment, environment, access or configuration may have changed since editing.

A registry entry declares behaviour; it does not prove the adapter implements it. Adapters and their contract tests supply that evidence.

## Requirements and acceptance checks

<a id="reg-001"></a>
### REG-001: Define identity, capabilities and execution together

A node/adapter definition includes the identity, connections, configuration, capability/policy, execution/state, evidence/reuse and presentation information specified above. Experimental status and supported dependency versions are explicit.

**Acceptance:** Register a representative model, agent and tool definition; validate their required metadata and explain incomplete configuration without pretending the integrations are ready.

<a id="reg-002"></a>
### REG-002: Validate wiring and effective execution policy

Use types, required capabilities, configuration completeness and execution policy to reject known-incompatible connections. Distinguish configuration links from workflow/data/artifact links. Repeat backend validation immediately before execution and enforce policy in the executing tools/workers.

**Acceptance:** Try compatible, incompatible, incomplete and unverified connections. Change an environment permission after editing and confirm run-start validation detects the new restriction.

Run-start validation is the same resolve-before-run rule as the [effective setup contract](../architecture.md#effective-setup-contract). A stored definition is not a resolved run.

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

Configuration includes settings schemas, defaults, required fields, applied values, optional budgets and effective technical limits. Preserve supported controls and distinguish user-selected budgets from runtime boundaries.

**Acceptance:** Render and resolve a configuration containing runtime-specific settings and an unset budget. Verify the applied values and any actual limiting boundary are visible.

Effective controls are the applied bag plus actual limits. Selected ≠ applied. The shared rule is [effective setup](../architecture.md#effective-setup-contract); this requirement remains the registry configuration home.

## Unresolved details

[OQ-008](../open-questions.md#oq-008) covers definition/version compatibility, plugin discovery/trust, invalidation and skills/plugins discovery UX. [OQ-004](../open-questions.md#oq-004) covers shared identities/events. [OQ-015](../open-questions.md#oq-015) covers workflow import/export; it is not a second registry or runtime. Do not add dynamic code loading, remote plugin execution or hot reload merely because the registry is extensible; those are separate decisions.

No application registry is implemented on main. A stored graph, third-party adapter or shared definition version still blocks on [OQ-008](../open-questions.md#oq-008). [Issue #53](https://github.com/Vidcar/thtaib/issues/53) records the shared [effective setup](../architecture.md#effective-setup-contract) that a future registry must resolve at run start; it does not implement this module or close [OQ-008](../open-questions.md#oq-008).
