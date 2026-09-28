## ADDED Requirements

### Requirement: ARCH-012 - Distinguish authored acceptance from applied runtime binding

Accepted work SHALL freeze authored model/setup revisions, response choices, automatic-budget policy/source/version and helper setups before queue acceptance. Runtime-dependent numeric allowances SHALL be recorded once per accepted execution role at its first exact native binding and before model execution. These applied facts SHALL extend existing run/effective-setup records without replacing authored snapshots or creating a second state authority. Concurrent first-binding attempts SHALL observe one result. Subsequent calls/recovery SHALL retain that result and reject incompatible capacity rather than refresh authored versions or silently recompute limits.

#### Scenario: Author edits while a cold request waits
- **WHEN** a saved setup changes after acceptance but before its cold native model binds
- **THEN** binding consumes the original frozen authored policy and persists one numeric result from the exact loaded model.

#### Scenario: Concurrent binding and resume
- **WHEN** parallel calls race to bind the same role or a paused role resumes
- **THEN** they consume the same recorded allowance and provenance through existing application records.

## MODIFIED Requirements

### Requirement: ARCH-008 - Resolve one effective setup before runs

Before Chat, Lab restore or rerun, Agent-run, or workflow execution starts, the backend SHALL resolve deployment, startup settings, per-request settings, agent settings, enabled tools and policy, selected knowledge, skill and protected-instruction versions, and selected MCP server slugs. Missing, unknown, or incompatible references MUST fail closed. Startup, per-request, and agent settings SHALL remain separate bags; each control SHALL reach its current owner, with a narrow cutover moving proven native request-capable defaults from legacy startup into the request bag while preserving effective saved values and historical snapshots.

For each newly accepted Chat input, the backend SHALL atomically resolve selected saved agent and knowledge record identities into their latest saved exact versions, including helper setups, model configuration settings, explicit deselection, tools, context references, policy and selected versioned shortcut prompts. It SHALL persist that immutable snapshot before execution or queue acceptance. Unsaved editor drafts SHALL NOT participate. Authored capture SHALL use Knowledge → Application → Model configuration lock order without holding those locks across model loading or execution.

Dispatch, queued recovery, helper execution and approval/question resumes SHALL consume the accepted snapshot and recheck live authorization, resource availability, model/history compatibility and shared admission. These checks SHALL NOT refresh frozen authored versions or settings from current records. A text-only queue revision SHALL retain its frozen setup; an explicit revision-checked setup edit SHALL resolve and freeze a new snapshot. Accepted input identity SHALL remain stable, with identical retries reusing the corresponding snapshot and conflicting edits or obsolete revisions rejected. Draft intent, accepted execution and observed model binding SHALL remain distinguishable. No renderer or duplicate runtime SHALL become an alternative resolution authority.

#### Scenario: Run-start validation

- **WHEN** a stored definition names settings, tools, knowledge and deployment references
- **THEN** the backend resolves and validates them before accepting execution, and immediately before dispatch checks current authority, resource availability and compatibility against that resolved selection
- **AND** the run record, inspector and captured request agree on selected, loaded, applied, unsupported, overridden and unverified facts.

#### Scenario: Same setting displayed and dispatched

- **WHEN** Models, Agents, project/application defaults, Chat, Lab or Workflows display a setting
- **THEN** its effective value, named source, known default, support and reload state come from shared backend resolution and observed runtime facts
- **AND** Chat distinguishes an editable candidate from the exact accepted snapshot used at dispatch rather than implementing another inheritance authority.

#### Scenario: Save races a newly accepted input

- **WHEN** a selected agent, knowledge record or model configuration is saved concurrently with Chat admission
- **THEN** one consistent exact snapshot is persisted, including main and helper selections and settings
- **AND** dispatch and request inspection use that snapshot, while the next new input can resolve the newer saved records.

#### Scenario: Saved edits and revoked authority after queue acceptance

- **WHEN** authored records change or a live grant is revoked after an input was queued
- **THEN** dispatch retains that input's exact authored versions and settings while rejecting unavailable or unauthorized resources and actions
- **AND** failure or pause preserves its attempted setup for deliberate recovery without substituting a model or refreshing authored content.
