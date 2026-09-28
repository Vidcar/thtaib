## MODIFIED Requirements

### Requirement: MOD-003 - Preserve profile fidelity

Each model SHALL have one saved default configuration and optional named variants, shared by Chat, Lab and Workflows. Configurations SHALL separate startup and per-request inference settings; agents and project/chat setup SHALL own behaviour, tools and knowledge. An optional saved model instruction block SHALL be visible, editable and explicitly resettable in its owning Models setup and shared input inspection. Omitting this block while saving other configuration fields SHALL preserve it; resetting it SHALL clear only this optional guidance. A model configuration MUST reject a different bundle or agent capability/access fields. Historical snapshots preserve their original distinct settings bags. Selecting a profile SHALL pass its identity and resolved bags to the backend. Each deployment SHALL freeze its launch inputs; profile edits affect future work and show pending startup differences rather than rewriting an active deployment.

Requested, selected, transmitted, loaded, applied, overridden, unsupported and unverified values SHALL remain distinguishable. Startup controls include context, parallelism, GPU layers, KV-cache types, flash attention and supported loading modes; request controls include sampling and output limits; optional model instructions use shared composition and source exclusion. Only startup changes require coordinated reload. Retired controls SHALL follow supported migration, not produce obsolete flags. Profiles SHALL support inspect, rename, duplicate and dependency-aware delete while retaining historical snapshots.

#### Scenario: Three settings bags

- **WHEN** startup, request and agent controls are exercised
- **THEN** each reaches only its intended consumer; actual transmitted values and unsupported/overridden/unverified outcomes remain visible.

#### Scenario: Bound profile and later edit

- **WHEN** a bound profile targets another bundle or an active profile is edited
- **THEN** the mismatched launch is rejected, and the active deployment keeps its original launch snapshot.

#### Scenario: Inherited values and explicit startup changes

- **WHEN** a preset is selected without editing its populated controls
- **THEN** the desktop sends its identity without turning inherited values into overrides; later preset edits remain detectable against the frozen launch snapshot.
- **AND** deliberately selecting automatic/default behavior clears that inherited key explicitly instead of silently restoring the preset value.

#### Scenario: Saved setup selected in Chat

- **WHEN** Chat selects a model configuration
- **THEN** its response defaults and explicit conversation overrides resolve through the shared backend with instruction composition from the model/agent/project/chat owners
- **AND** Thinking and context adjustments remain chat-local, only Models saves a named setup, and no adjustment rewrites a queued turn or historical loaded snapshot.

#### Scenario: Model guidance edited or reset

- **WHEN** a user edits optional model instructions or explicitly resets them
- **THEN** the full authored text or its explicit absence is saved for future selections without modifying startup settings, response settings or already accepted run snapshots
- **AND** a save that omits the agent instruction bag preserves its previous text.
