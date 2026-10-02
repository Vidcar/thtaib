# Spec Delta

## ADDED Requirements

### Requirement: AGT-039 - Show accepted tools by call name and screen label

When a chat or helper turn has an input policy, admission SHALL generate a capability index from the accepted tools and append it beside the existing discovery sentence. The index SHALL use each tool's call name and screen label, grouped by the catalogue group in the catalogue's group order. A group with no accepted tool SHALL be omitted. A tool with no screen presentation SHALL be omitted. The index SHALL NOT include parameter manuals or tool-schema handbooks. It SHALL be included whenever at least one presented accepted tool has a screen label, including when every such tool is already pinned and the discovery sentence is empty. It SHALL NOT be added when the turn has no input policy. The index SHALL NOT be stored as agent instructions or on the agent record. Agent instructions SHALL remain the job. The Deep Agents profile prompt SHALL stay empty for this model. Workbench core SHALL stay the short operating text and SHALL NOT list tools. Saved model setup prompts SHALL stay empty. The Inputs preview of that same next message SHALL show this index when the model would receive it, and opening the preview MUST NOT call the model. A helper SHALL receive the index for its own accepted tools. A helper SHALL NOT receive `task` only because the parent has helpers. Who may call a tool, when-needed bootstrap, pins, and the automatic addition of `find_tools`, `read_reference`, or `task` SHALL stay unchanged.

#### Scenario: Accepted names and labels are indexed

- **WHEN** an input-policy turn accepts `ls` and `edit_file` and does not accept another project tool
- **THEN** the model request contains the selected-tools heading, `ls`, `edit_file`, the screen labels List files and Edit files, and the line that says to call `find_tools` with the label or the call name
- **AND** the index does not contain the parameter handbook for those tools, and a tool that was not accepted does not appear.

#### Scenario: Pinned tools still get an index

- **WHEN** every accepted tool is already pinned and the discovery sentence is empty
- **THEN** the capability index is still included beside where that sentence would be.

#### Scenario: The preview matches the next message

- **WHEN** a person opens Inputs for a next message that would include the index
- **THEN** the preview shows that index
- **AND** opening it does not call the model, and the index is not written into the agent instructions.

#### Scenario: A helper reference is on the parent preview

- **WHEN** a helper has a memory or a skill and the parent does not
- **THEN** the Inputs preview index matches the index on the admitted parent prompt
- **AND** that index names `read_reference` and does not name a tool only the helper selected.

#### Scenario: A project memory merged onto a helper is indexed

- **WHEN** a helper saved no memory or skill and the chat project includes a memory or skill set to always or off
- **THEN** the Inputs preview index matches the index on the admitted parent prompt
- **AND** that index names `read_reference`

#### Scenario: A helper does not inherit task

- **WHEN** a parent has helpers and a helper's accepted tools are a smaller list
- **THEN** the helper index names the helper's tools
- **AND** it does not add `task` only because the parent has helpers.

#### Scenario: Operating text stays short

- **WHEN** the next message is prepared for this model
- **THEN** Workbench core remains the short operating text and does not list tools
- **AND** the Deep Agents profile prompt stays empty, and agent instructions remain the job.

#### Scenario: No index without an input policy

- **WHEN** a turn has no input policy
- **THEN** the capability index is not added.

## MODIFIED Requirements

### Requirement: AGT-035 - Offer explicit conditional runtime workflows

The product SHALL offer an opt-in versioned library of project-change, failure-diagnosis, Windows-execution, delivery-verification, browser-validation, desktop-validation, evidence-research, delegate-review and memory-curation skills. Installation, selection, metadata discovery and body/resource reading SHALL remain distinct. Setup templates SHALL use real saved selections and disclose Chat-owned access/mode requirements without granting them. No template or skill SHALL silently enable capabilities, save durable memory, grant project/window/shell access or import repository development skills into ordinary Chat. Starter drafts other than Trusted project builder MUST NOT select project-change, windows-execution, verify-delivery, failure-diagnosis, browser-validation, desktop-validation, evidence-research, memory-curation, or delegate-review. Their suggested Chat access SHALL stay Ask. Trusted project builder SHALL keep its Full-access suggestion. The General starter SHALL leave helper ids empty. The General job SHALL state that a send needs the bound project folder. The evidence-researcher template SHALL be usable for attached documents and retained results without a bound project. It SHALL select those read-only file tools plus `browser_navigate`, `browser_snapshot`, and `browser_find`, SHALL NOT pin those browser tools, and SHALL NOT select writes or shell. Project discovery in that template SHALL remain available only when a project is bound and SHALL NOT be required for a projectless run. The definition-loading preference SHALL NOT decide whether unpinned project reads can exist. A projectless run SHALL omit unpinned `glob` and `grep` under both Always include all and When needed. Unpinned `ls` and `read_file` SHALL NOT be project readers on that run: they are omitted unless a selected knowledge or capture route keeps them for its virtual paths, and that schema SHALL name those paths and SHALL NOT describe a project root. The saved tool list SHALL NOT be rewritten. Pinned project reads, skill-required project or shell tools, eager file mutations, and eager shell or preview SHALL still fail when no project is bound. New stock templates that consume retained evidence SHALL select the retained-result reader. Applying a template SHALL NOT rewrite an existing saved setup.

#### Scenario: Install without applying

- **WHEN** a person installs the bundled skills or chooses an agent template
- **THEN** the existing selected agent, conversation permissions and knowledge versions are preserved until explicitly edited and submitted.

#### Scenario: Conditional activation and exclusion

- **WHEN** a meaningful project change or unrelated simple answer is requested
- **THEN** the relevant selected workflow can be loaded progressively while unrelated bodies remain deferred
- **AND** deselection and interrupt/resume retain the existing immutable version rules.

#### Scenario: Projectless document research

- **WHEN** the evidence-researcher template is saved and admitted with an attached document and no project, with or without the research skill, under When needed, or under Always while Plan has removed the unpinned browser tools
- **THEN** admission accepts the run and the document and retained-result readers are available
- **AND** the saved tool list is unchanged, the three browser tools stay selected and unpinned, project discovery is not authorized, and no public-web connection is created. With the research skill, a project path read is refused and any virtual skill reader names `/skills/` without describing a project root.

#### Scenario: Work and Always include needs the browser worker

- **WHEN** the evidence-researcher template is admitted in Work with Always include and the browser worker is not installed
- **THEN** admission requires the browser worker
- **AND** the page tools do not run.

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

#### Scenario: Starter drafts stay the job

- **WHEN** a person applies a starter draft other than Trusted project builder
- **THEN** the instruction body is the job, suggested Chat access stays Ask, and the nine repository-development skills are not selected
- **AND** General does not name saved helper ids and states that a send needs the bound project folder.
