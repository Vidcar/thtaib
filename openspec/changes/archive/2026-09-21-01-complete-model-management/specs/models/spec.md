# models delta

## MODIFIED Requirements

### Requirement: MOD-003 - Preserve profile fidelity

Profiles SHALL separate startup, per-request inference and agent settings, preserve supported controls and explicit overrides, and be shared by Chat, Lab and Workflows. A bundle-bound profile MUST reject a different bundle; an intentionally unbound profile MAY be reused. Selecting a profile SHALL pass its identity and resolved bags to the backend. Each deployment SHALL freeze its launch inputs; profile edits affect future work and show pending startup differences rather than rewriting an active deployment.

Requested, selected, transmitted, loaded, applied, overridden, unsupported and unverified values SHALL remain distinguishable. Startup controls include context, parallelism, GPU layers, KV-cache types, flash attention and supported loading modes; request controls include sampling and output limits; agent instructions use shared composition. Only startup changes require coordinated reload. Retired controls SHALL follow supported migration, not produce obsolete flags. Profiles SHALL support inspect, rename, duplicate and dependency-aware delete while retaining historical snapshots.

#### Scenario: Three settings bags

- **WHEN** startup, request and agent controls are exercised
- **THEN** each reaches only its intended consumer; actual transmitted values and unsupported/overridden/unverified outcomes remain visible.

#### Scenario: Bound profile and later edit

- **WHEN** a bound profile targets another bundle or an active profile is edited
- **THEN** the mismatched launch is rejected, and the active deployment keeps its original launch snapshot.

### Requirement: MOD-004 - Track real deployments

A deployment SHALL identify its live managed process or connected endpoint, ownership, URL, immutable startup configuration, health, available server properties and resource observations. The model manager SHALL own managed start, stop and reconciliation. An authorised request for a selected installed model SHALL load it on demand with visible waiting/loading/readiness and no silent model, quantisation, device or settings substitution. Unload SHALL confirm owned process exit while retaining weights, profiles and the configuration needed to restart. Readiness and actual generation success SHALL be separate observations.

Saved profiles alone MUST NOT be treated as running deployments. Connected endpoints SHALL preserve observed identity and explicitly unknown properties; connection does not grant start, stop, kill or unload authority. Disconnect removes future selection/binding, not remote work. On restart, the manager SHALL verify ownership/process identity and reconcile missing/crashed processes before reporting them healthy. Hardware/build failures, setup dependencies, logs and corrective actions SHALL be visible through the existing first-use interface.

#### Scenario: Managed and connected deployment

- **WHEN** a managed deployment is started/stopped and an external endpoint is connected
- **THEN** managed process identity, health, launch settings and logs are recorded; destructive stop verifies ownership; connected start/stop/kill is refused.

#### Scenario: Load unload and generate

- **WHEN** an authorised turn selects an installed inactive managed model
- **THEN** the same selected setup loads, real generation is separately verified, and a later safe unload retains the installation without inventing freed-memory measurements.

## ADDED Requirements

### Requirement: MOD-009 - Discover and install exact repository selections

The system SHALL provide bounded model/repository search and direct repository ID/URL entry through the existing Hugging Face path. Search SHALL distinguish offline, gated, inaccessible and authentication failures; credentials remain backend-only. Discovery grants neither download authority nor compatibility. Installation SHALL resolve an immutable revision, select one complete variant, preserve literal filenames/relative paths, and verify roles, sizes and hashes before marking ready. Missing/mixed shards, collisions and ambiguous weights SHALL fail explicitly. Projector candidates require explicit compatible/evidence-labelled or text-only selection; file completeness alone MUST NOT claim model/projector compatibility. User-owned imported originals SHALL retain that ownership.

#### Scenario: Selected bundle

- **WHEN** a repository selection proceeds to installation
- **THEN** the pinned complete variant and deliberate projector/text-only choice are preserved; corrupt or ambiguous content is not deployable.

#### Scenario: Search failure

- **WHEN** search cannot authenticate or reach a repository
- **THEN** the relevant error is visible and no alternate download or compatibility claim is invented.

### Requirement: MOD-010 - Recover installation jobs without changing their contents

A long import SHALL return a durable job ID before completion and expose resolving, downloading, verifying, recording and truthful terminal states. Progress SHALL use measured bytes or explicitly labelled file/stage counts. Reopening/restarting SHALL recover or reconcile jobs rather than leave abandoned workers running. Cancel download, Retry and Discard incomplete download SHALL be distinct. Cancellation requires owned-worker stop confirmation; discard removes only stopped owned staging. Retry and Verify/repair SHALL use the recorded revision and exact selection, repair only missing/corrupt owned content, and avoid duplicate completed bundles or silent upgrades.

#### Scenario: Interrupted download

- **WHEN** a download is cancelled or the backend restarts
- **THEN** worker state is reconciled, partial content remains non-ready, and retry preserves the original revision/selection.

#### Scenario: Repair

- **WHEN** verification finds a missing or corrupt selected file
- **THEN** only the affected owned installation is repaired and reverified without deleting healthy shared files or creating another bundle.

### Requirement: MOD-011 - Show storage and clean only owned unreferenced content

The system SHALL show the destination for new installs and distinguish managed files, staging, Hub cache and local download metadata. Required/reclaimable space SHALL be measured or labelled estimates including known extra copies; unproven deduplication MUST NOT be assumed. Changing the destination affects future installs only. Insufficient space SHALL be recoverable. Cache cleanup SHALL respect cache ownership and shared references. Relocation is optional; when offered, it SHALL require inactive owned files, verified copy/reference update/cleanup and a recoverable original on failure.

#### Scenario: Location and cleanup

- **WHEN** the destination changes or cache cleanup is requested
- **THEN** existing files are not reported moved; measured/estimated space and shared/user-owned exclusions remain explicit.

### Requirement: MOD-012 - Coordinate destructive model lifecycle operations

Stop, unload, replacement, model deletion and runtime repinning SHALL atomically check affected runs/sessions and prevent conflicting new starts. Initial implementation MAY reject active disruption with an actionable explanation; it MUST NOT bypass protection through another stop path. Deletion SHALL preview affected profiles, installations, selections, saved consumers and disk effects, then recheck ownership/references at execution. Only selected unreferenced application-owned content SHALL be removed; external originals/shared companions survive. Historical consumers retain configuration and explicit unavailable references rather than silently switching models.

#### Scenario: Concurrent start and delete

- **WHEN** new work races with deleting or repinning a used model
- **THEN** backend coordination admits only a safe outcome and preserves active/shared dependencies.

#### Scenario: Delete installation

- **WHEN** a confirmed deletion contains owned and externally shared files
- **THEN** only eligible selected content is removed; retained references and unavailable historical dependencies are accurately reported.
