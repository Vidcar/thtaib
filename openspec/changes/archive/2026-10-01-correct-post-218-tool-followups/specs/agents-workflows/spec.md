# Spec Delta

## MODIFIED Requirements

### Requirement: AGT-035 - Offer explicit conditional runtime workflows

The product SHALL offer an opt-in versioned library of project-change, failure-diagnosis, Windows-execution, delivery-verification, browser-validation, desktop-validation, evidence-research, delegate-review and memory-curation skills. Installation, selection, metadata discovery and body/resource reading SHALL remain distinct. Setup templates SHALL use real saved selections and disclose Chat-owned access/mode requirements without granting them. No template or skill SHALL silently enable capabilities, save durable memory, grant project/window/shell access or import repository development skills into ordinary Chat. The evidence-researcher template SHALL be usable for attached documents and retained results without a bound project. Project discovery in that template SHALL remain available only when a project is bound and SHALL NOT be required for a projectless run. The definition-loading preference SHALL NOT decide whether unpinned project reads can exist. A projectless run SHALL omit unpinned `glob` and `grep` under both Always include all and When needed. Unpinned `ls` and `read_file` SHALL NOT be project readers on that run: they are omitted unless a selected knowledge or capture route keeps them for its virtual paths, and that schema SHALL name those paths and SHALL NOT describe a project root. The saved tool list SHALL NOT be rewritten. Pinned project reads, skill-required project or shell tools, eager file mutations, and eager shell or preview SHALL still fail when no project is bound. New stock templates that consume retained evidence SHALL select the retained-result reader. Applying a template SHALL NOT rewrite an existing saved setup.

#### Scenario: Install without applying
- **WHEN** a person installs the bundled skills or chooses an agent template
- **THEN** the existing selected agent, conversation permissions and knowledge versions are preserved until explicitly edited and submitted.

#### Scenario: Conditional activation and exclusion
- **WHEN** a meaningful project change or unrelated simple answer is requested
- **THEN** the relevant selected workflow can be loaded progressively while unrelated bodies remain deferred
- **AND** deselection and interrupt/resume retain the existing immutable version rules.

#### Scenario: Projectless document research
- **WHEN** the evidence-researcher template is saved and admitted with an attached document and no project, with or without the research skill, under either definition-loading preference
- **THEN** admission accepts the run and the document and retained-result readers are available
- **AND** the saved tool list is unchanged, project discovery is not authorized, and no public-web connection is created. With the research skill, a project path read is refused and any virtual skill reader names `/skills/` without describing a project root.

#### Scenario: Projectless eager mutation, shell, or pinned project read
- **WHEN** a projectless run keeps an eager file mutation, eager shell or preview, or a pinned project read
- **THEN** admission fails with an actionable project requirement and the tool is not executed.

#### Scenario: Project-bound research keeps project reading
- **WHEN** the same template is admitted with a bound project
- **THEN** the project reading operations in the template remain available with the source readers.

#### Scenario: New template can read retained evidence
- **WHEN** a new stock template that consumes retained evidence is saved and compiled
- **THEN** its accepted selection includes the retained-result reader
- **AND** an existing saved setup is left unchanged.
