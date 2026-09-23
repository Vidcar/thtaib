# Spec Delta

## MODIFIED Requirements

### Requirement: ARCH-008 - Resolve one effective setup before runs

Before Chat, Lab restore or rerun, Agent-run, or workflow execution starts, the backend SHALL resolve deployment, startup settings, per-request settings, agent settings, enabled tools and policy, selected knowledge, skill and protected-instruction versions, and selected MCP server slugs. Missing, unknown, or incompatible references MUST fail closed. Startup, per-request, and agent settings SHALL remain separate bags; values MUST NOT be moved between bags.

#### Scenario: Run-start validation

- WHEN a stored definition names settings, tools, knowledge, and deployment references
- THEN the backend MUST resolve and validate them immediately before execution
- AND the run record, inspector, and captured request MUST agree on selected, loaded, applied, unsupported, overridden, and unverified facts.

#### Scenario: Same setting displayed and dispatched
- **WHEN** Models, Agents, project/application defaults, Chat, Lab or Workflows display a setting
- **THEN** its effective value, named source, known default, support and reload state come from the shared backend resolution used at dispatch
- **AND** presentation does not implement another inheritance authority.
