# agents-workflows delta

## MODIFIED Requirements

### Requirement: AGT-004 - Separate active context from durable knowledge

The product SHALL use application-versioned user, agent and project memory, skills and protected instructions with actual scope identities. Selected immutable versions SHALL load through official `memory=` and `skills=` integration and protected instructions through the composed system prompt, not labels alone. Durable writes obey STATE-005, including explicit automatic-save scope, provenance and conflicts; agents cannot write protected instructions. Fresh conversations may select retained files/knowledge without inheriting earlier active context.

At next-turn boundaries, changed/deselected versions SHALL refresh supported derived loading state and resources without changing session thread/history. Obsolete skill resources must not remain discoverable; cleanup must not delete framework history or tool-result offloads. Deselection stops future loading but does not claim erasure of content already in active context. Actual subsequent requests/reads SHALL reflect the selected versions.

#### Scenario: Versioned knowledge and fresh conversation

- **WHEN** a fresh conversation selects retained files/knowledge, or a continued thread changes selected versions
- **THEN** fresh context and durable content remain distinct; continued loading refreshes without replacing the thread, and version/conflict/protected-write guarantees remain enforced.

#### Scenario: Deselected skill

- **WHEN** a selected skill package is replaced or disabled before the next turn
- **THEN** obsolete derived resources are removed from discovery without deleting conversation history or sibling scratch.

## ADDED Requirements

### Requirement: AGT-014 - Resolve reusable setups and composed instruction layers

Reusable agent setups SHALL have stable identity/version, name/role, model/deployment/profile references, instructions, selected tools/connections/knowledge and workspace/access requirements. They SHALL be inspectable, selectable, renamable, duplicable and removable with retained historical versions and explicit missing dependencies through the shared **Agents** destination and compact conversation setup controls. Primary Chat, children and workflow nodes use the same records and shared application-owned selection controls. SDK projections display selected tools and their actual call/results; they do not own setup state or authorization.

Resolve application defaults, selected project defaults, selected agent setup and explicit turn/node overrides in that order. Scalar values use precedence; ordinary instruction text composes as named inspectable layers, with later ordinary instructions resolving conflicts rather than erasing all earlier text. Protected instructions/mandatory restrictions remain separate and cannot be weakened. Preserve omitted versus explicitly empty selections. Document/skill/tool text cannot grant access.

#### Scenario: Layered setup

- **WHEN** a project, agent setup and turn provide different ordinary settings/instructions
- **THEN** the resolved setup shows each layer and precedence, preserves protected restrictions and does not silently replace missing dependencies.

#### Scenario: Agents destination selection

- **WHEN** a user opens Agents, edits a reusable setup and selects it from a conversation
- **THEN** the same versioned setup identity is visible in the compact conversation controls and future submissions use the new selection without rewriting live or historical invocations.
