# Spec Delta

## MODIFIED Requirements

### Requirement: AGT-034 - Preserve executable tool contracts and complete discovery

Cold input inspection and actual model requests SHALL preserve tool-schema semantics, including property names, nested alternatives, references and literal defaults/examples. Model-facing arguments SHALL state enforced types, bounds, units and mutually exclusive modes. Bounded tool discovery SHALL make every accepted selected match reachable through query/selection-bound continuation, with human-readable aliases, grouping and exact lookup. Discovery SHALL retain new-turn reset and resume behavior and MUST NOT enable excluded tools or trust external annotations as authority. Plan SHALL permit only selected built-in public-web search/page-reading capabilities through trusted connection identity. When tools are not off, admission SHALL include the trusted search and page-reading operations of an already selected built-in public-web connection without requiring each remote name in the saved tool list and without adding any other connection operation. An explicit empty tool selection SHALL add none.

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

#### Scenario: Selected connection without naming each remote tool
- **WHEN** a saved selection names the tested built-in public-web connection and does not turn tools off
- **THEN** only that connection's trusted search and page-reading operations are added
- **AND** an explicit empty selection adds no connection operation.

### Requirement: AGT-035 - Offer explicit conditional runtime workflows

The product SHALL offer an opt-in versioned library of project-change, failure-diagnosis, Windows-execution, delivery-verification, browser-validation, desktop-validation, evidence-research, delegate-review and memory-curation skills. Installation, selection, metadata discovery and body/resource reading SHALL remain distinct. Setup templates SHALL use real saved selections and disclose Chat-owned access/mode requirements without granting them. No template or skill SHALL silently enable capabilities, save durable memory, grant project/window/shell access or import repository development skills into ordinary Chat. The evidence-researcher template SHALL be usable for attached documents and retained results without a bound project. Project discovery in that template SHALL remain available only when a project is bound and SHALL NOT be required for a projectless run. New stock templates that consume retained evidence SHALL select the retained-result reader. Applying a template SHALL NOT rewrite an existing saved setup.

#### Scenario: Install without applying
- **WHEN** a person installs the bundled skills or chooses an agent template
- **THEN** the existing selected agent, conversation permissions and knowledge versions are preserved until explicitly edited and submitted.

#### Scenario: Conditional activation and exclusion
- **WHEN** a meaningful project change or unrelated simple answer is requested
- **THEN** the relevant selected workflow can be loaded progressively while unrelated bodies remain deferred
- **AND** deselection and interrupt/resume retain the existing immutable version rules.

#### Scenario: Projectless document research
- **WHEN** the evidence-researcher template is saved and admitted with an attached document and no project
- **THEN** admission accepts the run and the document and retained-result readers are available
- **AND** project discovery is not authorized and no public-web connection is created.

#### Scenario: Project-bound research keeps project reading
- **WHEN** the same template is admitted with a bound project
- **THEN** the project reading operations in the template remain available with the source readers.

#### Scenario: New template can read retained evidence
- **WHEN** a new stock template that consumes retained evidence is saved and compiled
- **THEN** its accepted selection includes the retained-result reader
- **AND** an existing saved setup is left unchanged.
