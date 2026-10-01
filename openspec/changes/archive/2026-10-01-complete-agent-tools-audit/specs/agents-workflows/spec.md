## ADDED Requirements

### Requirement: AGT-034 - Preserve executable tool contracts and complete discovery

Cold input inspection and actual model requests SHALL preserve tool-schema semantics, including property names, nested alternatives, references and literal defaults/examples. Model-facing arguments SHALL state enforced types, bounds, units and mutually exclusive modes. Bounded tool discovery SHALL make every accepted selected match reachable through query/selection-bound continuation, with human-readable aliases, grouping and exact lookup. Discovery SHALL retain new-turn reset and resume behavior and MUST NOT enable excluded tools or trust external annotations as authority. Plan SHALL permit only selected built-in public-web search/page-reading capabilities through trusted connection identity.

#### Scenario: Title is an argument or literal data
- **WHEN** a selected tool includes required or nested title fields and title-bearing default data
- **THEN** inspection and compiled projection retain those fields and runtime validation accepts the same conforming arguments.

#### Scenario: Sixth selected match and changed selection
- **WHEN** a search has more matches than one result batch
- **THEN** continuation can reach the remainder without repeating the first batch
- **AND** a changed selection or query rejects an obsolete continuation.

#### Scenario: Read-only public research
- **WHEN** Plan selects the tested built-in public-web connection
- **THEN** its search/page tools remain usable while arbitrary external tools and browser mutations remain unavailable.

### Requirement: AGT-035 - Offer explicit conditional runtime workflows

The product SHALL offer an opt-in versioned library of project-change, failure-diagnosis, Windows-execution, delivery-verification, browser-validation, desktop-validation, evidence-research, delegate-review and memory-curation skills. Installation, selection, metadata discovery and body/resource reading SHALL remain distinct. Setup templates SHALL use real saved selections and disclose Chat-owned access/mode requirements without granting them. No template or skill SHALL silently enable capabilities, save durable memory, grant project/window/shell access or import repository development skills into ordinary Chat.

#### Scenario: Install without applying
- **WHEN** a person installs the bundled skills or chooses an agent template
- **THEN** the existing selected agent, conversation permissions and knowledge versions are preserved until explicitly edited and submitted.

#### Scenario: Conditional activation and exclusion
- **WHEN** a meaningful project change or unrelated simple answer is requested
- **THEN** the relevant selected workflow can be loaded progressively while unrelated bodies remain deferred
- **AND** deselection and interrupt/resume retain the existing immutable version rules.

### Requirement: AGT-036 - Approve project file changes without widening exact grants

The product SHALL offer a separately approved, inspectable and revocable project file-change grant bound to the concrete selected project and explicit operation set. It SHALL retain path exclusions and reject traversal, symbolic-link/junction escapes, managed knowledge routes and operations outside the granted set. Existing exact-argument session/persistent grants SHALL keep their original meaning. All dispatch and resume paths SHALL recheck current selection, project identity and grant revocation. File-change authority MUST NOT imply deletion, shell, browser, external connection, protected instruction or durable memory authority.

#### Scenario: Two different edits within approved project scope
- **WHEN** a person deliberately grants selected project file changes with exclusions
- **THEN** distinct eligible edits can proceed under Ask while excluded paths and other effect classes still require their own authorization.

#### Scenario: Revoke between approval and dispatch
- **WHEN** the grant is revoked or the selected project identity changes before an action dispatches
- **THEN** the stale grant does not authorize that action or a helper.

## MODIFIED Requirements

### Requirement: AGT-020 - Enforce explicit Plan mode

Work SHALL be the default mode. Explicit Plan mode SHALL present only authorized non-mutating project/context reading, questions, checklist and discovery capabilities, and selected trusted built-in public-web search/page reading. It SHALL reject shell execution, file mutation/deletion, durable memory changes, browser/desktop interaction and effectful or unclassified external operations under every approval level and invocation path. External read-only annotations or names SHALL NOT establish Plan eligibility. Internal checkpoints/context housekeeping SHALL remain available. The mode SHALL be frozen with queued turns and enforced for restored calls and helpers. Full access MUST NOT override it; returning to Work SHALL require explicit user selection and a new submission.

#### Scenario: Plan with Full access
- **WHEN** a Plan-mode run attempts an effectful tool call
- **THEN** the call is rejected before execution regardless of Full access or saved grants.

#### Scenario: Trusted web tools with arbitrary MCP selection
- **WHEN** Plan includes selected built-in public-web tools and an unrelated MCP tool claiming read-only behavior
- **THEN** only the trusted search/page reader can be disclosed and dispatched.
