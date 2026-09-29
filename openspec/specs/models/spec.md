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

The guided import SHALL present Find, Choose and Review/download stages. Find SHALL support repository search and exact supported Hugging Face links; Choose SHALL preserve complete primary/projector selections and offer the advisory hardware estimate; Review SHALL show exact selection and initial configuration before explicit Download. Back SHALL preserve selections and draft settings. Advanced metadata SHALL remain expandable. Selected context, supported KV precision and placement SHALL become the initial saved configuration rather than display-only suggestions; publisher recipe selection and native metadata provenance SHALL remain explicit and intact.

A 32,768-token context (or a smaller verified model maximum), f16 key/value cache, automatic GPU layers and native GPU KV SHALL be the fresh import defaults. The shared slider SHALL increment by 1,024 tokens and display the resolved value directly. Import-created recipe configurations SHALL inherit the selected job's startup in their own stable identities; retry/recovery SHALL NOT overwrite prior or deliberately edited configurations. Ordinary repeated model-card recipe creation SHALL preserve existing editable recipe identities.

#### Scenario: Review and revise import options

- **WHEN** a person selects a complete quantization, context and KV options, opens Review then goes Back
- **THEN** the exact selections remain, and explicit Download retains the chosen initial settings alongside the immutable revision, file membership and projector/text-only choice.

#### Scenario: Exact linked primary file

- **WHEN** Find receives a supported exact primary GGUF file link
- **THEN** the staged flow retains that exact variant and required shards rather than switching to another quantization.

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

Validate fields/types and distinguish missing/invalid results from schema-permitted empty values. Invalid structured output SHALL fail clearly with its validation reason and MUST NOT trigger an extra formatting or effectful tool turn. JSON-looking answer text alone is not the structured result, and schema validity is not factual correctness.

#### Scenario: Tools-off formatting

- **WHEN** structured output is selected while tools are explicitly off
- **THEN** supported native formatting runs without tools, or the combination is reported unavailable.

#### Scenario: Invalid result

- **WHEN** formatting fails after a task action
- **THEN** the run fails with inspectable structured validation, without repeating the action or starting a formatting-repair turn.

### Requirement: MOD-017 - Budget real context and preflight continued conversations

The initialized model SHALL expose full per-request context capacity from available runtime observations. Upstream context management SHALL own output reservations and headroom once; the application MUST NOT reduce the advertised profile by its own output allowance or percentage margin. Include instructions, history, tool schemas and applicable media overhead without double subtraction. Training metadata, cloud aliases and library defaults MUST NOT become verified running capacity. Counts and unknown capacity SHALL be labelled.

Use one existing Deep Agents context/summarisation path; both normal and summarisation requests SHALL fit or fail actionably. Housekeeping remains available with tools off and internal summaries are not user answers. Before reconfiguration, retained content SHALL receive known message, tool and image compatibility checks. Before native dispatch on a continuing thread, validate actual pending content against observed context and message/tool/image/structured-output constraints. A context reduction SHALL NOT be refused merely because retained history exists; the existing native compaction owner SHALL reduce the active prompt or fail actionably at dispatch without rewriting canonical checkpoint history. Do not silently remove attachments, instructions or tool-result pairs. Offer a compatible setup, fitting compaction or deliberate fresh/supported branch outcome. Publish full capacity, input estimate/usage, counting basis, configured output and compaction events to shared inspectors. Approximate application observations MUST NOT independently reject a request or establish a hidden early compaction limit.

#### Scenario: Small context

- **WHEN** a continued request or its compaction request exceeds usable capacity
- **THEN** the supported fitting path is used or an actionable capacity error appears without silent truncation.

#### Scenario: Model switch

- **WHEN** a user selects a known-incompatible model for retained messages or media
- **THEN** dispatch is blocked with the specific constraint; unknown capability remains labelled unknown.

Accounting SHALL use the same outbound representation as dispatch and count each reasoning, content, tool argument and schema once. Native reduction SHALL run before rejecting reducible history. Work and summarization measurements SHALL remain separately attributable, including the evidence responsible for an overflow.

Reasoning replay capability SHALL be distinct from preservation of earlier user turns. A replay-capable template with history preservation disabled SHALL still receive the current tool cycle's reasoning. Explicit full-history preservation SHALL retain earlier reasoning; unsupported replay SHALL send none. Thinking generation on/off SHALL remain a separate setting. The same pure projection SHALL supply transport, preflight and compaction counting without changing checkpoints or the selected runtime settings. Application-supplied tool images SHALL remain tool-response context rather than becoming a new user-query boundary in templates that distinguish that boundary.

#### Scenario: History preservation disabled during a tool cycle
- **WHEN** a replay-capable model has completed an earlier user turn and is continuing the current turn after tools return
- **THEN** current-cycle reasoning SHALL remain in the outbound request and earlier-turn reasoning SHALL follow the selected native history policy
- **AND** tool-image projection SHALL preserve that distinction, while estimates SHALL count exactly the transmitted representation once.

#### Scenario: Thinking generation switched off
- **WHEN** the user disables new thinking generation on a replay-capable setup
- **THEN** that setting SHALL NOT erase reasoning needed to continue the current tool cycle or silently change its history-preservation policy.


The product SHALL use compatible pinned-card recommendations and template-effective Thinking choices without invented response bundles. Explicit total-output limits SHALL remain exact; absent an explicit finite setting, native generation SHALL use Unlimited. Publisher metadata MUST NOT silently impose an output ceiling. Accepted exact settings SHALL remain frozen across queues, helpers, retries and resumes. Thinking on/off MUST NOT change advertised capacity or introduce an automatic fraction-based output reservation.

#### Scenario: Duplicate reasoning representation
- **WHEN** one reasoning string exists in both native content and additional metadata
- **THEN** context accounting SHALL count only the outbound representation and SHALL NOT trigger compaction due to duplicate storage.

#### Scenario: Response limit interrupts tool input
- **WHEN** generation reaches its configured limit during tool arguments
- **THEN** partial arguments SHALL remain inert and the chat SHALL offer an actionable continuation instead of becoming permanently blocked.

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

Model controls SHALL show the effective value and source when configuration, server properties or a recognized selected-template default establishes it. Omitted request values MUST remain omitted unless explicitly overridden or a frozen automatic output policy supplies its once-recorded allowance. Configured, transmitted, observed and template-derived facts MUST remain distinguishable. Unknown defaults remain unknown. Following a configuration default, using the model default and choosing explicit None SHALL remain distinct operations. Each available default-following action SHALL name its actual target and expose its known resolved value rather than saying Inherited.

#### Scenario: Known thinking default
- **WHEN** the selected template establishes Xhigh as the omitted effort default
- **THEN** the control shows Xhigh with its model-default source
- **AND** displaying that default does not manufacture an explicit request override.

#### Scenario: Uncertain default
- **WHEN** a default depends on an unresolved template condition or unavailable server information
- **THEN** the control reports the uncertainty rather than inventing an actual value.

### Requirement: MOD-022 - Apply managed configuration changes safely

Idle managed configurations SHALL support validated reconfiguration with expected-version and retained-history compatibility checks. Startup edits SHALL preserve the current launch snapshot until an explicit safe reload; active, queued, waiting, cancelling, Lab and helper consumers SHALL block a configuration binding change with named reasons. Response-only configuration selection SHALL reuse a compatible healthy child without rewriting its originating setup identity; each accepted request resolves its selected setup independently. Saving or preparing a startup draft SHALL remain possible during active work. Only loading/reloading changes require existing resource admission and consumer protections. Automatic listen ports SHALL use the established configuration identity normalization; the actual frozen startup and process identity SHALL remain unchanged. Saved publisher recipes SHALL not be repurposed as product presets.

Capacity-driven eviction of an idle model instance MAY occur between calls, including during an alternate-model helper handoff, provided no in-flight inference request is interrupted and the next call can reload its exact selected configuration. Adding a separately frozen queued preset SHALL NOT be treated as an edit to an unchanged existing preset merely because a section separator moved; a later save SHALL preserve existing accepted snapshots while future inputs resolve the new revision. Automatic child ports SHALL be allocated and checked at launch; fixed-port conflicts fail before spawn. Ownership and observed readiness SHALL precede committing loaded values. Failure SHALL preserve prior and attempted configurations, attempt at most one safe restoration and report truthful stopped/failed state; restart SHALL reconcile interrupted changes. Connected endpoints SHALL not grant reload authority.

#### Scenario: Response-only Balanced selection
- **WHEN** an idle healthy owned model selects a separate named saved configuration with the same frozen launch identity
- **THEN** the same deployment and process SHALL use that configuration's response values for the next request without stop or start
- **AND** actual startup, model files, publisher recipe configuration and its provenance SHALL remain unchanged.

#### Scenario: Idle conversation context change
- **WHEN** an idle conversation applies a valid context change
- **THEN** the owned model reloads and the same conversation continues with verified capacity
- **AND** its draft and history survive.

#### Scenario: Queued consumer blocks reload
- **WHEN** a queued or waiting turn depends on a configuration being edited
- **THEN** reconfiguration identifies that consumer without discarding its selected setup.

#### Scenario: Capacity handoff between calls
- **WHEN** one loaded slot is needed by a different-model helper after the parent's model call ends
- **THEN** the helper loads its exact configuration and the parent reloads its own configuration before its next call
- **AND** neither in-flight inference request is stopped.

#### Scenario: Conflicting or failed launch
- **WHEN** the requested configuration fails to become ready
- **THEN** no unrelated process is stopped or healthy foreign endpoint claimed
- **AND** prior selection and a usable recovery path remain.

Preparing chat-local model/agent/startup changes during active work SHALL save only next-message intent and SHALL NOT mutate a launch used by running, queued, waiting, paused or helper consumers. A later accepted input SHALL retain its own exact desired settings. Safe dispatch SHALL load/bind those settings through the existing shared admission owner, without editing a named configuration or replacing an earlier input's frozen launch. Live authority and compatibility SHALL be revalidated at that boundary. A staged failure SHALL retain input and attempted settings with paused progression and an actionable recovery path.

#### Scenario: Context changes while another message is queued

- **WHEN** a live turn and an already queued follow-up use context A, then the person applies context B and submits another message
- **THEN** the first two inputs keep context A, the later input freezes B and only its safe admission may load B
- **AND** no shared saved configuration or earlier launch is rewritten by the draft edit.

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

The Models workspace SHALL provide My models, Add models and Downloads tabs. My models SHALL use a compact, searchable and keyboard-accessible catalogue beside a responsive editor when space permits, collapsing into an accessible model/configuration selector on narrower windows. Long names and filename-derived Standard, LOW-MTP or MTP variants SHALL remain distinguishable. Unsaved edits SHALL remain available when switching between models or configurations or navigating within the open app, and SHALL be marked visibly; reverting to saved values SHALL clear that mark.

The selected model SHALL clearly separate Configuration, Model card and Files. Common Context, GPU layers, independent K/V cache precision, Flash attention, Thinking, thinking history, maximum output tokens, MTP and all seven common sampling fields SHALL be visible in compact controls. Advanced SHALL retain memory fitting, specialist samplers, CPU/batch/parallel/offload/loading settings, thinking budget/format, speculative tuning and optional model instructions. Context SHALL use one 1,024-token slider and readout with verified bounds and the exact known maximum endpoint; display ranges MUST NOT become invented runtime bounds. Known default values SHALL select their actual setting without a duplicate Default choice. GPU layers SHALL offer Auto, All, CPU and an exact count. Automatic SHALL pass llama.cpp's automatic value (`auto` or legacy `-1`); All SHALL pass its explicit `all` value. Displayed launch settings SHALL identify a requested mode without claiming actual GPU placement unless the engine reports it. MTP SHALL appear only when supported by inspected metadata. Diagnostics, logs, recipes, provenance and exact file membership SHALL remain accessible in their appropriate disclosures or tabs.

Controls SHALL make the backend-resolved effective value and source the main readout without storing a followed value as an explicit override. Known followed, edited, loaded and unknown values SHALL remain distinguishable; an unknown value SHALL say Not reported. Binary settings SHALL use accessible compact switches or labelled two-position controls. Keyboard-operable controls SHALL expose effective choices, retaining genuine Auto/Unlimited modes without redundant inheritance positions. Source, reset, exact native mapping and apply timing SHALL be available in contextual help. A separate Loaded value SHALL appear only for a meaningful difference reported by the running engine. Saving SHALL update the selected model configuration for future Chat, Lab and Workflows turns; startup application SHALL follow managed reload safety. Save changes, Save as configuration, default selection and Load or Apply configuration SHALL remain available with labels accurately describing saving and loading. Applying a loaded configuration SHALL not promise a restart when the existing frozen launch can be rebound without one; changed launch settings SHALL retain safe reload behaviour.

Discard SHALL safely remove an eligible stopped, failed, interrupted or previously discarded import's owned unreferenced temporary content and clear its terminal job record. It MUST reject active and completed jobs. Shared or installed content SHALL remain protected, and cleanup failure SHALL leave the job actionable. Clearing history MUST NOT claim to free bytes it did not measure.

#### Scenario: Edit and apply model settings
- **WHEN** a person edits a model's response and startup settings, switches to another model, then returns
- **THEN** the unsaved draft remains visible and requested values and resolved followed defaults are distinguishable
- **AND** saving changes future model use while applying the startup change requires a safe managed reload.

#### Scenario: Known and unknown inherited values
- **WHEN** a model reports a known default for one control but no known value for another
- **THEN** the editor shows the known value with its source and marks the other Not reported
- **AND** neither followed value is silently saved as an explicit setting.

#### Scenario: Clear an old discarded import
- **WHEN** a previously discarded job shares staging with a completed installation
- **THEN** clearing removes the discarded job record while retaining the shared staging and installed model
- **AND** active and completed jobs cannot be cleared through discard.

### Requirement: MOD-028 - Resolve thinking history consistently

When a model supports reasoning history, its configuration descriptor SHALL expose the capability and a verified template or runtime default for `reasoning_preserve`, or report the default as unknown. My models SHALL label the control Thinking history and offer Default, Keep and Drop, storing explicit settings under `reasoning_preserve`. The inference adapter and rendered template SHALL use the same resolved effective choice: Keep forwards earlier reasoning when supported; Drop omits it from later ordinary turns; unknown default SHALL not forward it by assumption. Unsupported models SHALL not offer the control. Model documentation may explain a choice but SHALL NOT silently save a recommendation.

#### Scenario: Known template default
- **WHEN** a supported template has a verified default of Keep and the user leaves Thinking history at Default
- **THEN** the editor reports that default and the adapter forwards earlier reasoning for later prompt rendering.

#### Scenario: Explicit Drop
- **WHEN** the user selects Drop for a supported template
- **THEN** later ordinary turns render without earlier reasoning.

#### Scenario: Unknown or unsupported default
- **WHEN** the template default cannot be established or the model lacks reasoning-history support
- **THEN** the editor does not claim a verified Keep default and the adapter does not forward earlier reasoning by assumption.

### Requirement: MOD-029 - Honor exact Hugging Face file links

Hugging Face inspection SHALL retain a valid file-specific link hint and compare it with the immutable repository listing. A hinted primary file SHALL be selected only when it belongs to a complete variant; an unavailable hint MUST be visible and MUST NOT silently select a different variant. Variants sharing a quantization label SHALL remain distinguishable by their filename-derived family and exact selected files before transfer. Filename-derived labels MUST NOT imply verified runtime capabilities.

#### Scenario: LOW-MTP link beside standard and MTP files
- **WHEN** a repository link hints at a LOW-MTP IQ4_XS file while standard IQ4_XS and MTP IQ4_XS files are also listed
- **THEN** the complete LOW-MTP variant is selected and its exact file is prominent before download
- **AND** the other variants remain separate choices.

#### Scenario: Linked file is unavailable
- **WHEN** the hinted file is absent or does not belong to a complete primary variant at the resolved revision
- **THEN** the user sees that mismatch and no other variant is silently preselected.

### Requirement: MOD-030 - Offer model-card response recipes as explicit configurations

The product SHALL extract only unambiguous, supported response recommendations from a revision-pinned GGUF repository card and record their source repository, revision, card identity and section. Card recommendations SHALL remain separately attributed from verified automatic generation defaults. A new model default SHALL initialise from an unambiguous compatible recommendation matching native Thinking; ambiguous or unsupported choices SHALL fall back to native/template settings and remain explicitly selectable. Valid zero-valued samplers and supported presence and frequency penalties SHALL be retained. An unsupported, invalid or conflicting response recommendation SHALL not be offered as a selectable recipe.

The product SHALL support both explicitly named thinking and non-thinking recipes and a single clearly recommended set of response samplers without a thinking-mode instruction. The latter SHALL preserve the chosen configuration's existing thinking mode. Non-response guidance in the same recommendation section SHALL be clearly identified as not copied into the configuration and remain available in the full card.

During import or on an installed model, a user SHALL be able to select any offered recipes for creation as named model configurations and optionally choose one as the model default. A new configuration SHALL copy the then-current default configuration's requested launch settings, use the selected response recipe while retaining unrelated requested response settings, and remain independent of later default edits. Existing configurations and explicit overrides SHALL not be overwritten by metadata refresh or later card changes. Repeating a selected import or creation action SHALL not duplicate recipe-created configurations. Thinking mode SHALL be applied only when the selected model template supports the relevant toggle. Weight-install success and configuration-creation failure SHALL be reported separately.

#### Scenario: Three recommendations on one card
- **WHEN** the selected pinned model card clearly recommends general thinking, precise coding and non-thinking values
- **THEN** all three appear as separate response recipes with source attribution
- **AND** only an unambiguous compatible initial recommendation matching native Thinking may initialise a new default; other recipes require explicit selection.

#### Scenario: Single recommended response set
- **WHEN** the selected pinned card clearly recommends one valid set of response samplers without specifying a thinking mode
- **THEN** the supported values appear as one selectable recipe with source attribution
- **AND** creating its configuration preserves the current default's requested thinking mode.

#### Scenario: Mixed response and other guidance
- **WHEN** a card recommends valid response samplers alongside prompt or launch guidance
- **THEN** the selectable recipe identifies the guidance it will not copy
- **AND** conflicting, invalid or unsupported response values prevent that recipe from being offered.

#### Scenario: Create three configurations and select a default
- **WHEN** a user selects all three recipes and chooses General thinking as the default
- **THEN** three distinct named configurations are saved once, copied launch settings remain independent, and the default points to General thinking
- **AND** an unrelated existing configuration remains intact.

#### Scenario: Incompatible thinking template or setup failure
- **WHEN** the selected GGUF cannot verify a recipe's thinking mode, or configuration creation fails after weights install
- **THEN** the mode is not claimed as configured and the installed weights remain available with an actionable setup error.

### Requirement: MOD-031 - Refresh pinned card metadata without downloading weights

An installed Hugging Face bundle SHALL present the full root model card for the model selected in My models, identified by that bundle's repository, immutable installed revision and card checksum. The card SHALL be read from a size- and hash-verified saved copy or fetched from that same repository and revision if the saved copy cannot be used. A missing, unreadable or mismatched card SHALL produce a clear error; content from another model or an unverified revision MUST NOT be displayed. Card display SHALL keep markup inert and SHALL not download weights, change saved configurations or defaults, or rewrite live deployment snapshots.

An installed Hugging Face bundle SHALL support an explicit response-recipe refresh from its hash-verified saved card or that same repository's immutable revision. Refresh SHALL not download model weights, change saved configurations or defaults, or rewrite live deployment snapshots. Card candidates and effective settings SHALL refresh in the UI without presenting stale values from a previously selected model.

#### Scenario: View the selected model card
- **WHEN** the user selects an installed Hugging Face model in My models and opens its card
- **THEN** the full pinned card and its repository and revision are displayed for that model
- **AND** switching models while a card is loading cannot display the prior model's card.

#### Scenario: Refresh an older installation
- **WHEN** an installed revision-pinned bundle has no imported response recipes and the user refreshes its card metadata
- **THEN** any valid pinned-card recipes become available for explicit configuration creation without another weight download
- **AND** its existing configurations, default and deployments remain unchanged.

#### Scenario: Card is unavailable or ambiguous
- **WHEN** the saved card cannot be verified and the pinned card cannot be fetched, or the card has conflicting recipes
- **THEN** no recommendation becomes active or silently changes an existing configuration.

### Requirement: MOD-032 - Distinguish user-image and tool-image support

The active deployment's capability record SHALL distinguish accepted user images from image content returned by a tool. The model adapter SHALL preserve tool-call pairing, bounded image bytes and selected request settings when a supported tool image is sent to the endpoint. Failed, untested and inconclusive tool-image support MUST NOT be displayed as verified visual inspection. An untested tool-image check MAY run once when a screenshot is taken on a vision setup. Until it passes, the product SHALL NOT send the image and SHALL keep the page text available. Other model uses SHALL remain available under their existing compatibility rules.

Automatic capability checks SHALL retain their outcomes as setup evidence without publishing their reasoning, answers or synthetic tool calls into the conversation display or execution history. When the active setup passes the required checks, the same screenshot's next model request SHALL use the newly verified image capabilities before unsupported-content filtering. The product MUST NOT substitute test images for the retained screenshot or change the selected model, request settings or context capacity to enable image delivery.

#### Scenario: Tool image reaches the model
- **WHEN** a vision deployment passes an actual tool-image probe and an authorized agent reads a screenshot
- **THEN** the outgoing endpoint request includes that image with the corresponding completed tool result and the response can refer to visible fixture details.

#### Scenario: User image alone has passed
- **WHEN** user-image input has passed but tool-image delivery has not
- **THEN** the product reports tool-image inspection as unverified while preserving ordinary text use.

#### Scenario: First screenshot verifies support
- **WHEN** an active vision setup has untested image capabilities and its automatic checks pass during screenshot handling
- **THEN** the next model request includes the actual retained screenshot and preserves the tool result, selected setup and context capacity
- **AND** the conversation contains no capability-test reasoning, colour replies or synthetic tool activity.

#### Scenario: Screenshot check cannot verify support
- **WHEN** either required image capability is failed or inconclusive
- **THEN** the image remains withheld and the page text remains available without presenting visual inspection as verified
- **AND** internal test output remains absent from the conversation.

### Requirement: MOD-035 - Bound managed model residency

The application SHALL save one positive maximum-loaded-model count for managed llama.cpp configurations. A fresh installation SHALL default to one. Each distinct loaded runtime/artifact/loading identity SHALL consume one residency slot; response-only saved setups sharing that identity SHALL reuse the child; the count SHALL remain distinct from each model's parallel request slots. Connected endpoints SHALL remain outside this owned count. A different or unloaded requested model SHALL load on explicit idle model/configuration selection, idle fixed-model agent selection, or the first accepted input that needs that selection. A selection made during active work SHALL stage the next submission and SHALL load only through that input's safe admission; it MUST NOT warm merely because a draft changed. Re-selecting the exact healthy loaded configuration SHALL not request another model start. Successive turns on an already loaded configuration SHALL avoid reading the complete weight file again while still checking its saved identity; an evicted configuration SHALL undergo full bundle verification before it loads again. Application launch, chat restoration, passive status reads and navigation SHALL NOT warm or load a model. Loading SHALL show pending, loaded or failed state, and MUST NOT silently substitute weights, quantization, device or settings.

#### Scenario: One-slot model switch
- **WHEN** the limit is one and a different configuration is explicitly selected while idle
- **THEN** the previous idle instance unloads and the requested one loads; during active work selection instead stages a later input, whose safe admission waits without interrupting earlier work.

#### Scenario: Two models remain ready
- **WHEN** the limit is two and two different installed configurations are selected
- **THEN** both can remain loaded and serve separate chats or parent/helper calls, subject to actual memory and each model's parallel request capacity.

#### Scenario: Cold launch and restored chat
- **WHEN** Workbench opens with a chat that remembers an unloaded model
- **THEN** no model starts until the person selects one or submits a turn, and that first turn loads then sends once ready.

#### Scenario: Failed load
- **WHEN** a pending model selection fails to load
- **THEN** the previous conversation binding and draft remain available and the failure names the attempted configuration.

#### Scenario: Exact healthy selection

- **WHEN** Chat selects the same healthy loaded named configuration again
- **THEN** the existing deployment remains selected without another model start request.

#### Scenario: Another turn on loaded weights

- **WHEN** a selected managed configuration is already loaded and healthy for another Chat turn
- **THEN** admission checks the saved bundle identity without hashing the entire weight file again
- **AND** a changed bundle or evicted preset must be fully verified before new weights are loaded.

### Requirement: MOD-033 - Prepare visual capability before dependent inference

An admitted run with screenshot access on an untested vision setup SHALL complete necessary image capability checks before its main model/tool conversation begins. Matching setup evidence SHALL be reused. Check activity SHALL be visible without publishing internal probe output. Failure SHALL preserve text use and truthful visual fallback. Necessary checks SHALL NOT be interleaved with a warm main conversation solely because its first screenshot arrives. Passive status reads SHALL NOT start capability inference or load a model.

#### Scenario: First visual run on an untested setup
- **WHEN** a submitted run enables capture access and its loaded setup has no matching image evidence
- **THEN** checks finish before the first main model request, and the actual retained screenshot uses that evidence without additional capability calls in the tool continuation.

### Requirement: MOD-034 - Preserve prompt and generation timing evidence

For supported timing streams, inference SHALL retain actual cached and newly processed input token counts, reported prefill duration and locally observed time to the first substantive output delta under their request identity and purpose. Missing or invalid measurements SHALL remain unavailable. Completed and interrupted model-call measurements SHALL survive the next request reset in a bounded history. Tool-call stream validation SHALL preserve complete and invalid call behavior without repeatedly accumulating answer or reasoning text solely for validation.

#### Scenario: Prefill precedes fast generation
- **WHEN** a request has a long reported prompt-processing interval and fast subsequent decoding
- **THEN** evidence distinguishes the prefill duration, first-output delay and decode rate rather than presenting decode speed as the whole request's performance.

#### Scenario: Large streamed tool arguments
- **WHEN** a valid large tool argument arrives in many fragments
- **THEN** deltas remain incremental and final validation preserves the complete tool call without repeatedly reparsing its growing arguments.

### Requirement: MOD-036 - Estimate model hardware use without restricting user choice

Choose, import review, Models and Chat context candidates SHALL consume the shared non-disruptive hardware preview. Ordinary installed-model preview SHALL use fast cached metadata/tensor calculations. A deliberate native check SHALL use a bounded subprocess compiled against the exact pinned llama.cpp native APIs. Both methods SHALL account for the selected server parallel slots, unified context, embeddings and speculation; measure target, selected projector and draft/MTP together; and count shared MTP weights once. The helper protocol, digest and native compatibility SHALL be recorded in the runtime manifest. It SHALL NOT start or stop a deployment or replace the running inference process.

Results SHALL expose per-device estimates, evaluated placement, shared context, per-request capacity, slots, plan identity, calculation time and complete/partial/unavailable status. Native context allocations SHALL be labelled Cache and model state; projector totals SHALL NOT invent an internal breakdown. Requested Auto values remain distinct from evaluated results. Dynamic driver, host cache and operating-system costs SHALL remain unknown or separately budgeted. Missing facts MUST NOT become zero or a green fits claim. Observed memory SHALL be labelled Observed, timestamped and associated only with the exact loaded identity; cached estimates retain their original time. Shared router process usage MUST NOT be presented as model process RAM.

Remote discovery SHALL retain bounded revision/file metadata estimates with exact shards/projector selection and explicit unknowns. Metadata preview SHALL account for dense/hybrid attention, recurrent state and shared MTP weights where known, retaining partial components and identifying unsupported allocations. Ignored byte ranges SHALL fail before body consumption. Predictions SHALL remain advisory, preserve settings and downloaded weights, and never block valid Save, Download or Load merely because estimated memory is insufficient.

#### Scenario: Native target, vision and speculation parity
- **WHEN** the selected plan includes a projector and shared MTP or a separate draft
- **THEN** the helper measures all selected components using native allocation APIs with server-equivalent preprocessing
- **AND** shared weights are counted once, the shared context pool is truthful and projector internals remain undisclosed.

#### Scenario: Unavailable or timed-out measurement
- **WHEN** helper compatibility, hardware facts or native measurement are unavailable or timeout
- **THEN** the result is explicitly partial or unavailable with missing components and an actionable reason
- **AND** existing inference continues without interruption and missing bytes do not establish a fit.

#### Scenario: Candidate differs from the loaded plan
- **WHEN** context, placement, artifacts or loading settings differ from the loaded identity
- **THEN** candidate estimates and loaded observations remain separately labelled with their identities and times
- **AND** stale observations cannot establish current candidate fit.

#### Scenario: Runtime contradicts prediction
- **WHEN** native loading reports a different actual allocation or fails
- **THEN** actual observations and failure are authoritative, with the attempted candidate retained for adjustment.

#### Scenario: Native helper defaults differ from automatic server slots
- **WHEN** a legacy helper cannot reproduce the selected native server slots and unified context
- **THEN** its prediction SHALL remain partial or unavailable and SHALL NOT establish an exact launch-memory match
- **AND** the pinned adapter SHALL evaluate server-equivalent slots and shared context before offering complete selected-component totals.

#### Scenario: Native prediction can inspect an unsupported dense estimate
- **WHEN** an installed model uses a hybrid architecture
- **THEN** ordinary preview SHALL calculate its known attention/recurrent components without starting a subprocess, and an explicit native check SHALL remain available without starting a deployment, hashing full weights or rewriting requested settings
- **AND** unknown/excluded allocations SHALL remain explicit alongside its predicted rows.

#### Scenario: Hardware observation fails after a successful observation
- **WHEN** telemetry refresh fails after prior per-device memory facts were observed
- **THEN** those prior facts MAY remain visibly stale with their original observation time
- **AND** stale budgets SHALL NOT establish a context marker or a current shortage comparison.

#### Scenario: User deliberately exceeds estimated GPU memory
- **WHEN** the chosen weights/cache/overhead exceed estimated available VRAM
- **THEN** the interface shows the approximate shortage and likely RAM use without blocking Save, Download or Load or silently reducing the settings.

#### Scenario: Unavailable hardware or unsupported architecture
- **WHEN** hardware telemetry or architecture-specific cache information is unavailable
- **THEN** known file sizes and settings remain usable, unavailable estimate components are explicit, and the app does not fabricate precise fit.

#### Scenario: Context and KV placement update together
- **WHEN** the person adjusts the context slider or chooses supported CPU KV placement
- **THEN** the estimate updates its cache and GPU/RAM breakdown and those same explicit choices carry into the initial saved configuration.

#### Scenario: Runtime contradicts the estimate
- **WHEN** the native engine reports a different actual allocation or fails to load the chosen setup
- **THEN** actual observations/failure remain authoritative and inspectable alongside the approximate estimate, and the user's attempted settings remain available for adjustment.

#### Scenario: Complete variant and projector sizing
- **WHEN** the selected model uses multiple shards or an explicitly selected projector
- **THEN** known selected-file sizes are included with clear components and unknown overhead remains qualified rather than omitting selected files.

#### Scenario: Shared router process observation
- **WHEN** a managed deployment records router process usage without verified model-child usage
- **THEN** model process RAM remains unavailable with an explicit reason rather than displaying the router's resident memory as the model allocation.

### Requirement: MOD-037 - Preview the selected model candidate faithfully

Models readouts SHALL resolve the selected model, configuration and unsaved draft through the existing model-capable resolver boundary. Application-default editing SHALL remain access-only. Chat context preview and Reload SHALL use the same candidate, including removed overrides, and default labels SHALL use the correct parent/model value and source. Editing SHALL remain available during validation, while context Reload SHALL require the latest matching valid result. Readiness SHALL use the resolver's exact selected live configuration identity and distinguish quantization/configuration labels.

#### Scenario: Preview advanced startup edits
- **WHEN** the selected configuration requests All GPU layers, memory fitting Off and q4_0 key precision, then edits and resets them
- **THEN** requested and effective readouts agree with the real resolver for that candidate and the reset target value is correct.

#### Scenario: Preview completes out of order
- **WHEN** typing changes the candidate while an earlier check completes
- **THEN** editing stays uninterrupted and that earlier result cannot enable Reload for the newer candidate.

### Requirement: MOD-038 - Keep import choices and estimates truthful

Model import SHALL retain Find, Choose and Review/download stages; Back and failed requests SHALL preserve choices. Selected context and independent K/V settings SHALL become the initial configuration while exact shards, projectors, capabilities and import defaults remain authoritative. Slider fill SHALL reflect the actual displayed value; an automatic setting SHALL not imply a fixed value. Hardware presentation SHALL expose real GPU/RAM availability and qualified weights/cache/overhead estimates, with unknown components and device boundaries explicit. Estimates SHALL never block valid choices or silently reduce settings. A manual Refresh SHALL bypass estimate caching only for that request.

#### Scenario: Review then go Back
- **WHEN** a person chooses files, context and cache precision, advances to Review, then goes Back
- **THEN** those exact choices remain selected and become the installed initial configuration on download.

#### Scenario: Incomplete estimate
- **WHEN** device availability or overhead is unknown
- **THEN** the estimate describes the unknown component without claiming a verified fit or blocking a valid download.

### Requirement: MOD-039 - Share validated model controls and effective Thinking

Model import, save, preview and execution SHALL use one definition of supported control domains, units, dependencies, named defaults, provenance and apply timing. Numeric inputs SHALL reject nonfinite values and enforce whole counts where required. Slider spans SHALL remain distinguishable from actual supported bounds. Normal controls SHALL show actual resolved values and named native Auto/Off/Unlimited states, not raw sentinel numbers or redundant Default positions. Each help disclosure SHALL expose its actual native flag or request path, source and apply timing. Thinking SHALL offer only template-effective modes/levels and deduplicate aliases; unknown models SHALL remain usable with truthful unknown/default support. Invented generic Balanced/Deep response bundles SHALL be removed. Chat Thinking SHALL preserve explicit saved sampling choices; paired response recipes SHALL be deliberately selected in Models.

#### Scenario: Same choice across boundaries
- **WHEN** the same control is imported, saved, previewed and transmitted
- **THEN** its domain, source and effective setting agree and an invalid value fails before disruptive loading.

#### Scenario: Effective template levels
- **WHEN** a template supports binary Thinking or aliases High to Extra high
- **THEN** the normal control offers only effective distinct positions and no generic unsupported level.

### Requirement: MOD-040 - Reuse native instances independently from response choices

Native residency SHALL identify the exact runtime, weights, selected template/projector and normalized loading settings. Equivalent saved setups and response recipes SHALL reuse a compatible healthy instance; response defaults or setup ID SHALL NOT force another native child. Each accepted run SHALL resolve its own response values and SHALL NOT inherit another setup's response snapshot from that child. Save and record preparation SHALL remain possible while active work exists and SHALL NOT start or modify resident processes. Loading/replacement SHALL retain existing admission and ownership protections.

#### Scenario: Same loading plan and different response recipes
- **WHEN** two saved setups share one loading plan and differ in Thinking, sampling or output allowance
- **THEN** they reuse the child while each request transmits its own frozen settings.

#### Scenario: Prepare during generation
- **WHEN** a future setup is saved/prepared during active generation
- **THEN** preparation succeeds without replacing the active child's settings or process.

### Requirement: MOD-041 - Resolve model-aware response allowances once

Accepted explicit saved/chat total-output limits SHALL remain exact across calls, helpers, queues, retries and resumes. Absent an explicit finite setting, native generation SHALL use Unlimited and MUST NOT derive a hidden output ceiling from Thinking, publisher metadata or a fraction of context. The upstream context owner SHALL receive full observed per-request capacity, reserve a deliberate positive output limit using its own policy once, and perform reduction/overflow recovery. Default Thinking on/off SHALL leave capacity and compaction policy unchanged. No application budget binding or independent percentage safety margin SHALL shrink the framework profile.

#### Scenario: Cold helper with automatic allowance
- **WHEN** an accepted helper first binds to its exact cold model with no finite output override
- **THEN** generation remains Unlimited and its framework profile uses the full observed capacity, unchanged by Thinking.

#### Scenario: Explicit limit cannot fit
- **WHEN** a deliberate finite output setting cannot coexist with required input under the upstream policy
- **THEN** native reduction/recovery runs or an actionable capacity error is shown without silently changing that setting.

#### Scenario: Queued exact setting
- **WHEN** a saved response setting changes after an input was accepted
- **THEN** the accepted input retains its exact settings while future submissions use the changed default. No fraction-based output policy is rebound at dispatch.

### Requirement: MOD-042 - Preview complete selected native allocations

Installed-model preview SHALL default to fast metadata/tensor calculation without loading weights or disrupting inference. An explicit native check SHALL use the exact pinned runtime's allocation APIs. The request SHALL identify metadata or native method and results SHALL label their basis. It SHALL account for selected target, projector and draft/MTP allocations, including shared MTP weights once, server slot/pool preprocessing and per-device placement. The result SHALL identify the selected plan, evaluated settings, effective context/slots, timestamp and completeness. Dynamic driver/operating-system/host-cache overhead SHALL remain unknown or separately budgeted. A failed selected component SHALL remain unknown/partial, never zero or a verified fit. Actual loaded observations SHALL match the exact residency identity and remain separately authoritative. Missing/unsupported/crashed/timed-out helpers SHALL leave inference usable.

#### Scenario: Vision and MTP plan
- **WHEN** an explicit native check of an installed plan includes a projector and embedded MTP
- **THEN** the preview includes their native device allocations without counting shared weights twice.

#### Scenario: Concurrent context pool
- **WHEN** four requests share unified KV
- **THEN** the preview distinguishes the total pool and maximum per-chat capacity without promising four reserved full contexts.

#### Scenario: Predictor failure
- **WHEN** measurement fails or the adapter times out
- **THEN** the result is partial/unavailable with its reason and the existing model remains running.

### Requirement: MOD-043 - Keep Models editing stable and contextual

My models SHALL expose a saved-setup selector only when multiple setups exist, one Model card entry point and compact Save plus the appropriate Load/Reload action. Metadata/files/refresh/setup management and optional native checking SHALL live in contextual details. Generation/Sampling and Loading/Memory SHALL form two compact columns when at least 840 CSS pixels are available, stacking below that width. Common controls SHALL remain immediately visible and show resolved values without repeated Saved/default/provenance paragraphs. Pending startup changes SHALL require explicit loading. Controls SHALL use stable compact geometry; ordinary edits, reset availability, background checks and memory recalculation SHALL NOT move subsequent rows by more than one CSS pixel at a fixed viewport. Controls, focus, drafts and scroll position SHALL remain available through checks. Explicit disclosures, panel opening and viewport changes MAY reflow.

The editor SHALL provide one contextual right panel for presets, optional checks, memory, runtime, card and files. The panel SHALL dock only when at least 720 CSS pixels remain for editing, otherwise overlay with keyboard containment, Escape dismissal and trigger focus restoration. Validation SHALL identify the exact candidate, include loading and response failures, and become stale after edits. Runtime details SHALL distinguish engine defaults from setup response settings. Response aliases SHALL have one canonical visible owner; bundle-level template/vision actions SHALL live in model information.

#### Scenario: Continuous editing during checks
- **WHEN** a person types, resets or changes a control while descriptors, effective values or memory estimates update
- **THEN** subsequent rows remain within one CSS pixel and controls stay mounted with truthful pending/unknown state
- **AND** results from another selection cannot replace the current candidate's facts.

#### Scenario: Check then edit or switch setup
- **WHEN** a check completes and the person changes response/loading values or selects another setup
- **THEN** the panel identifies the old result as out of date and cannot claim it validates the new candidate.

#### Scenario: Manage saved setups
- **WHEN** a person requests deletion
- **THEN** existing lifecycle/reference protections remain and default/last-setup restrictions are explained before confirmation
- **AND** ordinary editing/refresh never automatically renames or deletes setups; an explicitly authorised development reset may discard obsolete setups without deleting weights.

### Requirement: MOD-044 - Apply and reversibly remove publisher presets

The main Model card button SHALL open a contextual preset panel; card reading, website links and refresh SHALL be secondary details within that panel. Publisher recommendations SHALL be applied from that panel to the current response draft, changing only supplied response fields and explicitly stated Thinking mode. Applying/reapplying SHALL retain loading settings and unrelated response values, mark pending changes visibly and require Save to persist. Recorded ancestry SHALL remain read-only and SHALL NOT be inferred from names. Presets SHALL support persistent Remove from list and Restore presets from model card. Removal SHALL preserve underlying recommendations and saved origins. Restoration SHALL use the installed pinned card, clear hidden choices only after successful refresh, and SHALL NOT recreate deleted setups, overwrite saved configurations, change defaults or download weights.

#### Scenario: Apply non-thinking to an edited setup
- **WHEN** a person previews and applies a Non-thinking preset
- **THEN** the specified response fields and Thinking mode change in the draft, loading/unrelated settings remain intact and Save is required.

#### Scenario: Remove and restore a preset
- **WHEN** a person removes a preset, reopens the application and restores presets from the card
- **THEN** removal persists until restoration and existing saved setups/provenance remain usable throughout.

#### Scenario: Restore fails
- **WHEN** the pinned card cannot be verified or retrieved
- **THEN** the error is actionable and prior presets, visibility and saved setups remain unchanged.
