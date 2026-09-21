# Registry

## Purpose

Specify one application-owned, versioned integration model for supported model, agent, tool, environment, adapter, and presentation definitions consumed by React Flow, LangChain, and LangGraph.

## Requirements

### Requirement: REG-001 - Define identity, capabilities and execution together

A registry definition SHALL include stable identity, version, supported dependency versions, connection kinds, configuration schema and defaults, applied values, capabilities, policy, environment, execution state, evidence, reuse, errors, cancellation, recovery, snapshot behavior, context, provenance, and presentation information. Experimental status SHALL be explicit. A registry declaration alone MUST NOT imply implemented behavior.

#### Scenario: Representative definitions

- WHEN representative model, agent, and tool definitions are registered
- THEN required metadata MUST validate
- AND incomplete configuration MUST be explained without pretending the integrations are ready.

### Requirement: REG-002 - Validate wiring and effective execution policy

The backend SHALL use types, required capabilities, configuration completeness, access, and execution policy to reject known-incompatible connections. Configuration links SHALL remain distinct from workflow, data, and artifact links. Backend validation SHALL repeat immediately before execution because deployment, environment, access, or configuration may have changed.

#### Scenario: Run-start restriction change

- WHEN an environment permission changes after a graph was edited
- THEN run-start validation MUST detect the new restriction
- AND compatible, incompatible, incomplete, and unverified connections MUST be distinguishable.

### Requirement: REG-003 - Keep a single integration authority

React Flow presentation, LangChain tool exposure, and LangGraph compilation SHALL consume the application registry. New integrations SHALL register there instead of defining disconnected copies throughout the application. Frontend connection rules MUST NOT be the sole execution validator.

#### Scenario: Definition change propagation

- WHEN a registered definition changes
- THEN all consumers MUST use the changed definition or report staleness
- AND backend validation MUST still protect execution when presentation is stale.

### Requirement: REG-004 - Unify run attribution and approvals

Agent, workflow, tool, interpreter, and interactive-panel events SHALL map into one run hierarchy. Approvals SHALL route through Deep Agents/LangGraph interrupts and the application interface. Embedded panels and tool-calling programs MUST NOT bypass access policy.

#### Scenario: Correlated paths

- WHEN one implemented path of each kind is inspected
- THEN parent run, progress, approval, and result attribution MUST correlate
- AND unsupported event or capture capabilities MUST be reported explicitly.

### Requirement: REG-005 - Expose effective controls and limits

Configuration SHALL include settings schemas, defaults, required fields, applied values, optional budgets, and effective technical limits. Supported controls SHALL be preserved. User-selected budgets SHALL be distinguished from runtime boundaries. Selected values MUST remain distinct from applied values.

#### Scenario: Runtime-specific settings

- WHEN a configuration contains runtime-specific settings and an unset budget
- THEN applied values and actual limiting boundaries MUST be visible
- AND the unset user budget MUST NOT be converted into a hidden product quota.

### Requirement: REG-006 - Keep registry narrow and local

The registry SHALL be a product extension path for concrete integrations wired into controls, validation, and execution. It MUST NOT become a speculative generic plugin platform, hot-reload system, remote code loader, or second trust authority.

#### Scenario: Unimplemented integration

- WHEN an integration is only declared but has no adapter or contract tests
- THEN it MUST remain unavailable for execution
- AND the registry MUST not load remote code to make it appear supported.
