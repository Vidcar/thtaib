# Spec Delta

## MODIFIED Requirements

### Requirement: MOD-003 - Preserve profile fidelity

Each model SHALL have one saved default configuration and optional named variants, shared by Chat, Lab and Workflows. Configurations SHALL separate startup and per-request inference settings; agents and project/chat setup SHALL own instructions, tools and knowledge. A model configuration MUST reject a different bundle. Historical snapshots preserve their original distinct settings bags. Selecting a profile SHALL pass its identity and resolved bags to the backend. Each deployment SHALL freeze its launch inputs; profile edits affect future work and show pending startup differences rather than rewriting an active deployment.

Requested, selected, transmitted, loaded, applied, overridden, unsupported and unverified values SHALL remain distinguishable. Startup controls include context, parallelism, GPU layers, KV-cache types, flash attention and supported loading modes; request controls include sampling and output limits; agent instructions use shared composition. Only startup changes require coordinated reload. Retired controls SHALL follow supported migration, not produce obsolete flags. Profiles SHALL support inspect, rename, duplicate and dependency-aware delete while retaining historical snapshots.

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
- **THEN** its response defaults and explicit conversation overrides resolve through the shared backend with instruction composition from the agent/project/chat owners
- **AND** Apply remains local, Save to model explicitly updates the configuration, and neither action rewrites a queued turn or historical loaded snapshot.

## ADDED Requirements

### Requirement: MOD-021 - Report known defaults and their source

Model controls SHALL show the effective value and source when configuration, server properties or a recognized selected-template default establishes it. Omitted request values MUST remain omitted unless explicitly overridden. Configured, transmitted, observed and template-derived facts MUST remain distinguishable. Unknown defaults remain unknown. Use inherited value, Use model default and explicit None SHALL be distinct operations.

#### Scenario: Known thinking default
- **WHEN** the selected template establishes Xhigh as the omitted effort default
- **THEN** the control shows Xhigh with its model-default source
- **AND** displaying that default does not manufacture an explicit request override.

#### Scenario: Uncertain default
- **WHEN** a default depends on an unresolved template condition or unavailable server information
- **THEN** the control reports the uncertainty rather than inventing an actual value.

### Requirement: MOD-022 - Apply managed configuration changes safely

Idle managed deployments SHALL support validated reconfiguration with expected-version checking and retained-history compatibility. Active, queued, waiting, cancelling, Lab and helper consumers SHALL block disruption with named reasons. Automatic ports SHALL be allocated and checked at launch; fixed-port conflicts fail before spawn. Ownership and observed readiness SHALL precede committing loaded values. Failure SHALL preserve prior and attempted configurations, attempt at most one safe restoration and report truthful stopped/failed state; restart SHALL reconcile interrupted changes. Connected endpoints SHALL not grant reload authority.

#### Scenario: Idle conversation context change
- **WHEN** an idle conversation applies a valid context change
- **THEN** the owned model reloads and the same conversation continues with verified capacity
- **AND** its draft and history survive.

#### Scenario: Queued consumer blocks reload
- **WHEN** a queued or waiting turn depends on the model being changed
- **THEN** reconfiguration identifies that consumer without stopping its model.

#### Scenario: Conflicting or failed launch
- **WHEN** a fixed port is occupied or the requested configuration fails to become ready
- **THEN** no unrelated process is stopped and no healthy foreign endpoint is claimed
- **AND** prior settings and a usable recovery path remain.

### Requirement: MOD-023 - Consolidate saved configuration without changing meaning

Ordinary saving SHALL update the selected configuration with stale-edit protection; creating a variant SHALL be explicit. A quiet idempotent migration SHALL merge equivalent legacy configuration duplicates, retain meaningful referenced variants and preserve instructions, historical runtime snapshots, model weights and conversation records. Explicitly created named variants SHALL remain distinct even while their settings are equal. Runtime instances MUST NOT appear as indistinguishable saved presets.

#### Scenario: Intentional equal variant
- **WHEN** a user chooses Save as variant without changing the selected configuration's settings
- **THEN** the new named variant remains selectable after reload and restart, without creating another deployment or changing the model default

#### Scenario: Repeat save and migration
- **WHEN** a configuration is saved twice and consolidation is rerun
- **THEN** no duplicate user configuration is created and effective settings remain unchanged
- **AND** distinct referenced settings and historical evidence survive.
