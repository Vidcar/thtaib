# Models

## Purpose

Specify how Local AI Workbench imports, describes, configures, starts, observes, and reports local and connected models so every surface can use the same bundle, profile, deployment, compatibility, and applied-setting records.

## Requirements

### Requirement: MOD-001 - Record complete bundles

Model bundle records SHALL preserve quantization, shards, companion files, immutable repository revisions, hashes, relative paths, and local locations. Managed downloads SHALL use `huggingface_hub` with revision-pinned selections, and the model manager SHALL pass resolved local files to llama.cpp. The product MUST NOT silently choose ambiguous projectors or flatten copied filenames so identity is lost.

#### Scenario: Import with companions

- WHEN a GGUF variant with shards and companion projector files is imported
- THEN the recorded manifest MUST include revision, selected variant, shards, projector choice, relative paths, hashes, and skipped alternatives
- AND repeated imports from existing files MUST reuse the canonical record format.

### Requirement: MOD-002 - Inspect, do not edit GGUF metadata

The model manager SHALL use llama.cpp `gguf-py` for metadata and tensor inspection feeding compatibility assessment. Normal import, inspection, and compatibility paths MUST NOT modify original model metadata.

#### Scenario: Metadata inspection

- WHEN representative GGUF metadata is inspected
- THEN provenance MUST be retained
- AND the source model file MUST remain unchanged.

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

### Requirement: MOD-004 - Track real deployments

A deployment SHALL identify its live managed process or connected endpoint, ownership, URL, immutable startup configuration, health, available server properties and resource observations. The model manager SHALL own managed start, stop and reconciliation. An authorised request for a selected installed model SHALL load it on demand with visible waiting/loading/readiness and no silent model, quantisation, device or settings substitution. Unload SHALL confirm owned process exit while retaining weights, profiles and the configuration needed to restart. Readiness and actual generation success SHALL be separate observations.

Saved profiles alone MUST NOT be treated as running deployments. Connected endpoints SHALL preserve observed identity and explicitly unknown properties; connection does not grant start, stop, kill or unload authority. Disconnect removes future selection/binding, not remote work. On restart, the manager SHALL verify ownership/process identity and reconcile missing/crashed processes before reporting them healthy. Hardware/build failures, setup dependencies, logs and corrective actions SHALL be visible through the existing first-use interface.

#### Scenario: Managed and connected deployment

- **WHEN** a managed deployment is started/stopped and an external endpoint is connected
- **THEN** managed process identity, health, launch settings and logs are recorded; destructive stop verifies ownership; connected start/stop/kill is refused.

#### Scenario: Load unload and generate

- **WHEN** an authorised turn selects an installed inactive managed model
- **THEN** the same selected setup loads, real generation is separately verified, and a later safe unload retains the installation without inventing freed-memory measurements.

#### Scenario: Exit cannot be confirmed

- **WHEN** termination, kill, or failed-start cleanup cannot confirm exit
- **THEN** the operation reports failure, retains process identity and blocks destructive lifecycle operations until exit or loss of ownership is established.

#### Scenario: Interrupted start without recorded identity

- **WHEN** startup recovery finds a starting deployment with neither PID nor identity
- **THEN** it exposes an actionable interrupted-start failure with saved configuration retained, without killing an unknown process or leaving indefinite loading.

#### Scenario: Disconnect during health observation

- **WHEN** an endpoint is disconnected while a health observation is in progress
- **THEN** the observation and disconnect are serialized so the old response cannot recreate the deleted connection.

#### Scenario: Repeated turn on a ready model

- **WHEN** another turn selects an unchanged ready managed deployment
- **THEN** readiness does not rescan the entire weight files; full integrity verification remains required at installation, repair and launch boundaries.

### Requirement: MOD-005 - Keep the model adapter narrow and faithful

The model adapter SHALL supply Deep Agents with an initialized LangChain model for the selected deployment's actual OpenAI-compatible chat endpoint and model identifier. It SHALL send the resolved per-request bag and preserve supported tool calls, multimodal user input and runtime-specific controls. It MUST NOT load weights, start engines, tokenize or render templates as a replacement inference owner, or silently change generation settings during compaction.

The shared input contract SHALL retain string tasks and accept validated current-user content blocks without string-flattening. It MUST reject arbitrary caller-supplied system messages, tool results and replacement history. Authorized image fixtures SHALL carry actual supported image bytes/content, not an attachment ID or host path. Capability/context constraints SHALL come from the selected deployment and evidence.

#### Scenario: Adapter trace

- **WHEN** a supported tool call and multimodal request cross the adapter
- **THEN** no inference process is launched; selected request settings and actual image content reach the endpoint, and unsupported features, context limits and compatibility constraints are surfaced from recorded deployment and compatibility data.

#### Scenario: User input boundary

- **WHEN** a caller submits content that impersonates system or tool history
- **THEN** validation rejects it rather than replacing the saved conversation state.

### Requirement: MOD-006 - Separate evidence from recommendations

Compatibility records SHALL be versioned and SHALL keep publisher guidance, inspected metadata, tested adjustments, observed probe outcomes, shared provenance keys, recommendations, and user opt-outs separate. Unfamiliar models MUST remain usable when unverified. Known incompatibility MUST be distinguishable from unknown or inconclusive support.

#### Scenario: Compatibility record categories

- WHEN a compatibility record includes publisher guidance, probe evidence, and a user opt-out
- THEN each category MUST remain distinct
- AND an unverified model MUST not be excluded merely because no probe has passed.

### Requirement: MOD-007 - Pin and observe managed runtime honestly

Managed runtime installation SHALL use the supported pinned llama.cpp runtime and verify matching archives before reuse. NVIDIA absence on the supported Windows CUDA path SHALL be a clear error, not a silent CPU fallback. Runtime flags SHALL be produced through pin-aware settings mapping; there MUST be no raw command-string escape hatch.

#### Scenario: Runtime pin and settings preview

- WHEN startup controls are previewed and a managed server is started
- THEN invalid, retired, or unknown controls MUST fail before spawn
- AND requested launch settings MUST remain distinguishable from observed server context and generation defaults.

### Requirement: MOD-008 - Import Hugging Face bundles by explicit selection

Guided Hugging Face imports SHALL read repository metadata before weight transfer, present GGUF variants with disk size and all shards, require explicit projector or text-only choice when projectors exist, resolve an immutable commit internally, and preserve relative paths and hashes. Ambiguous weights, ambiguous projectors, incomplete shards, and mixed shards MUST fail explicitly.

#### Scenario: Ambiguous projector

- WHEN a repository contains more than one plausible projector
- THEN import or deployment MUST require an explicit selection or text-only choice
- AND legacy ambiguous projector records MUST fail at deployment start rather than guessing.

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

### Requirement: MOD-013 - Verify transmitted settings and supplied usage

The adapter SHALL preserve supported temperature, top-p, output limit, penalties, seed, stop, top-k, min-p, typical-p and repeat-penalty controls in their intended scope. Evidence SHALL record actual wire keys/values rather than infer them from constructor arguments. Dropped/rejected fields MUST NOT appear applied. Supplied usage SHALL be preserved, with streamed usage requested and tested where supported. Missing usage is unavailable, never zero; chunks are not tokens. Transmission does not prove the model/template honoured a setting.

#### Scenario: Wire fidelity

- **WHEN** a configured ordinary or streaming request is sent
- **THEN** its actual JSON and supplied usage agree with the recorded settings; unavailable observations remain unknown.

### Requirement: MOD-014 - Preserve messages and complete tool calls across client modes

Synchronous/asynchronous ordinary invocation and incremental streaming SHALL use equivalent settings and conversion. Answers, supplied identities, finish reasons and partial output SHALL survive conversion. A tools-only assistant message is not an empty final success. Tool names, arguments, call IDs and tool-result linkage SHALL remain intact; streamed indexed fragments SHALL assemble before execution eligibility. Malformed/incomplete calls remain invalid, and prose MUST NOT manufacture a tool call. Multiple/parallel-call support SHALL remain model/template-specific.

#### Scenario: Fragmented calls

- **WHEN** two indexed calls arrive in interleaved fragments
- **THEN** arguments assemble under the correct IDs before execution and results return through their matching tool-call IDs.

#### Scenario: Invalid and tools-only messages

- **WHEN** an endpoint returns malformed arguments or only a valid tool call
- **THEN** malformed data stays an explicit error; the valid call is preserved without inventing a final answer.

### Requirement: MOD-015 - Keep returned reasoning distinct from thinking controls

Returned reasoning SHALL be preserved separately from answer text for ordinary responses and streamed deltas; outbound replay SHALL use only the representation supported/required by the selected template. Logging alone is insufficient and absent reasoning MUST NOT be fabricated. Configuration SHALL distinguish request effort, response parsing format, template-specific inputs, startup reasoning budget and history-preservation support. Raw/no-parsing format MUST NOT be called thinking off. Supported effort values and template behaviour SHALL be evidence-based; startup changes follow managed lifecycle controls.

#### Scenario: Reasoning round trip

- **WHEN** a supported endpoint supplies separate reasoning and a later turn requires its representation
- **THEN** ordinary/streamed conversion and supported replay preserve it separately; unsupported controls are not described as effective.

### Requirement: MOD-016 - Produce validated structured results through the same agent

Runs SHALL support an optional versioned output schema using the existing agent constructor, retaining actual structured results, schema/strategy identity and validation status separately from display text and artifacts. Native versus tool-based strategy SHALL depend on verified setup capability and tool policy. Tools-off SHALL send no synthetic formatting tools; unsupported native formatting under tools-off SHALL be actionable unavailable. Formatting tools grant no other execution authority. Combined executable tools plus structured output require separate support evidence.

Validate fields/types and distinguish missing/invalid results from schema-permitted empty values. Bounded formatting recovery SHALL record attempts without replaying the whole task or mutating tools. JSON-looking answer text alone is not the structured result, and schema validity is not factual correctness.

#### Scenario: Tools-off formatting

- **WHEN** structured output is selected while tools are explicitly off
- **THEN** supported native formatting runs without tools, or the combination is reported unavailable.

#### Scenario: Invalid result

- **WHEN** formatting fails after a task action
- **THEN** bounded repair does not repeat the action; failure and actual structured validation remain inspectable.

### Requirement: MOD-017 - Budget real context and preflight continued conversations

The initialized model SHALL expose usable input capacity from available runtime observations, explicit output reservation and a disclosed counting margin. Include instructions, history, tool schemas and applicable media overhead without double subtraction. Training metadata, cloud aliases and library defaults MUST NOT become verified running capacity. Counts and unknown capacity SHALL be labelled.

Use one existing Deep Agents context/summarisation path; both normal and summarisation requests SHALL fit or fail actionably. Housekeeping remains available with tools off and internal summaries are not user answers. Before changing model/configuration on a continuing thread, validate actual pending content against known context, message, tool, image and structured-output constraints. Do not silently remove attachments, instructions or tool-result pairs. Offer a compatible setup, fitting compaction or deliberate fresh/supported branch outcome. Publish capacity, input estimate/usage, counting method, reservation and compaction events to shared inspectors.

#### Scenario: Small context

- **WHEN** a continued request or its compaction request exceeds usable capacity
- **THEN** the supported fitting path is used or an actionable capacity error appears without silent truncation.

#### Scenario: Model switch

- **WHEN** a user selects a known-incompatible model for retained messages or media
- **THEN** dispatch is blocked with the specific constraint; unknown capability remains labelled unknown.

### Requirement: MOD-018 - Bound diagnostics and clean up only owned requests

Bounded redacted evidence SHALL link transmitted requests and wire outcomes to converted messages/chunks, errors, partial output and retries without buffering the full stream before delivery. Credentials and embedded media MUST NOT be indiscriminately persisted. HTTP errors, timeouts, invalid responses and interrupted streams remain failures, not completion; partial delivery MUST NOT silently restart. Sync/async clients SHALL have explicit ownership, timeouts and cleanup. Cancellation stops further application work and owned resources, not a shared deployment or caller-owned client; runtime termination remains separately confirmed or unknown. Transport deadlines are not user task budgets.

#### Scenario: Interrupted stream

- **WHEN** a response fails after partial delivery or is cancelled
- **THEN** partial output and the real error remain, owned resources close, and neither the task nor another client is restarted/stopped.

### Requirement: MOD-019 - Keep capability probes specific to the tested setup

Reusable probes SHALL exercise shared-adapter streaming, a harmless real tool round trip, structured output and suitable reasoning/image support. Records SHALL retain test inputs/outcomes, runtime/deployment/bundle, template/projector and effective settings. A relevant setup change invalidates transferred proof. Publisher guidance, recommendations, user opt-outs, tested adjustments, failed, untested and inconclusive outcomes remain distinct. A failed probe MUST NOT establish universal model incompatibility or prevent explicitly unverified ordinary use.

#### Scenario: Changed setup

- **WHEN** a previously tested template, projector, runtime or relevant configuration changes
- **THEN** old evidence remains attributable to its original setup and the new setup is not automatically labelled verified.

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

### Requirement: MOD-024 - Apply verified Hugging Face bundle configuration

Hugging Face installation SHALL preserve the immutable revisions and verified contents of configuration files used with a selected GGUF bundle. A source-only repository SHALL lead to an explicit GGUF choice; publisher configuration from another repository MUST NOT be applied automatically unless the conversion's source identity and revision are verified. The bundle SHALL record the provenance and selection of its chat template and supported generation defaults, along with unsupported or conflicting source values. GGUF architecture, tokenizer and context metadata SHALL remain authoritative for the running GGUF.

For managed inference, the selected compatible standalone chat template SHALL be passed to the runtime. A conflicting GGUF embedded template SHALL remain selected by default; choosing the publisher template SHALL require a compatibility check. Runtime failure MUST NOT silently substitute a different template. Supported generation defaults SHALL reach requests across Chat, Lab and Workflows through shared backend resolution, with explicit saved or conversation overrides taking precedence. The product SHALL distinguish downloaded, selected, transmitted and observed values.

#### Scenario: Source-only link and verified conversion
- **WHEN** a person enters a publisher repository with no GGUF weights and selects a linked GGUF conversion
- **THEN** the app shows the complete variant and its source verification status before download
- **AND** only configuration from a verified immutable source revision can become automatic publisher defaults.

#### Scenario: Template selection and launch
- **WHEN** the publisher template differs from the selected GGUF embedded template
- **THEN** the GGUF template is selected by default and the difference is visible
- **AND** a compatible publisher choice is retained through launch and restart without silent fallback.

#### Scenario: Generation settings in a real request
- **WHEN** a verified downloaded bundle has supported generation settings and no explicit override
- **THEN** those settings are transmitted in the actual model request and remain visible with their source
- **AND** an explicit saved or conversation setting overrides only its matching default.

#### Scenario: Unsupported or incompatible configuration
- **WHEN** a publisher field has no safe runtime equivalent, token identity cannot be verified, or a template fails compatibility
- **THEN** the field or template is reported as not applied with a reason
- **AND** no successful application is claimed from download, file presence or request construction alone.

### Requirement: MOD-025 - Organize model tasks without losing progress

The Models workspace SHALL separate installed models, adding models and downloads into distinct accessible tabs. Import progress and completion SHALL remain current while another Models tab is selected. Starting an import SHALL expose its progress in Downloads; completion SHALL refresh the library without taking focus from the person. Storage controls SHALL be available with Downloads.

#### Scenario: Leave a running download
- **WHEN** a person starts a download and switches to My models or Add models
- **THEN** the Downloads tab continues to report active work
- **AND** the completed bundle becomes available in My models without forcing a tab change.

### Requirement: MOD-026 - Compare complete primary GGUF variants

Repository inspection SHALL present complete primary variants with exact file membership, known disk size, file count and a clearly identified filename-derived quantization and nominal bit-family hint. Unknown labels or sizes SHALL remain unknown; the bit family and disk size MUST NOT be represented as verified effective precision or memory fit. Incomplete selections SHALL explain why they cannot be downloaded. Obvious auxiliary MTP and imatrix GGUF files SHALL be reported separately and MUST NOT be accepted as the primary model selection. Projector or text-only choice and immutable revision SHALL remain explicit before transfer.

#### Scenario: Mixed repository contents
- **WHEN** a repository lists Q4 and BF16 primary weights, split shards and an `MTP/mtp-*` file
- **THEN** primary rows show the respective nominal families, exact quantization hints, aggregate disk sizes and shard completeness
- **AND** the MTP file appears as auxiliary rather than a selectable primary weight.

#### Scenario: Unrecognized or incomplete variant
- **WHEN** a filename does not declare a recognized quantization or a shard is missing
- **THEN** the label remains unknown or the selection remains unavailable with a reason
- **AND** the app does not invent a quality, compatibility or memory-fitting claim.

### Requirement: MOD-027 - Expose model controls and clear terminal downloads

The selected model SHALL show common startup, response and thinking controls directly, including context, GPU layers, memory fitting, flash attention, speculative decoding, thinking and supported thinking effort, temperature, top P, top K, min P, presence penalty, repetition penalty and reply limit. Values SHALL retain their effective source and saved-versus-loaded distinction. Saving SHALL update the selected model configuration for future work; startup application SHALL follow managed reload safety.

Discard SHALL safely remove an eligible stopped, failed, interrupted or previously discarded import's owned unreferenced temporary content and clear its terminal job record. It MUST reject active and completed jobs. Shared or installed content SHALL remain protected, and cleanup failure SHALL leave the job actionable. Clearing history MUST NOT claim to free bytes it did not measure.

#### Scenario: Edit and apply model settings
- **WHEN** a person edits a model's sampling settings and a startup setting
- **THEN** the requested values and inherited defaults are distinguishable
- **AND** saving changes future model use while applying the startup change requires a safe managed reload.

#### Scenario: Clear an old discarded import
- **WHEN** a previously discarded job shares staging with a completed installation
- **THEN** clearing removes the discarded job record while retaining the shared staging and installed model
- **AND** active and completed jobs cannot be cleared through discard.
