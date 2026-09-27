# Spec Delta

## MODIFIED Requirements

### Requirement: MOD-017 - Budget real context and preflight continued conversations

The initialized model SHALL expose usable input capacity from available runtime observations, explicit output reservation and a disclosed counting margin. Include instructions, history, tool schemas and applicable media overhead without double subtraction. Training metadata, cloud aliases and library defaults MUST NOT become verified running capacity. Counts and unknown capacity SHALL be labelled.

Use one existing Deep Agents context/summarisation path; both normal and summarisation requests SHALL fit or fail actionably. Housekeeping remains available with tools off and internal summaries are not user answers. Before reconfiguration, retained content SHALL receive known message, tool and image compatibility checks. Before native dispatch on a continuing thread, validate actual pending content against observed context and message/tool/image/structured-output constraints. A context reduction SHALL NOT be refused merely because retained history exists; the existing native compaction owner SHALL reduce the active prompt or fail actionably at dispatch without rewriting canonical checkpoint history. Do not silently remove attachments, instructions or tool-result pairs. Offer a compatible setup, fitting compaction or deliberate fresh/supported branch outcome. Publish capacity, input estimate/usage, counting method, reservation and compaction events to shared inspectors.

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


The product SHALL offer explicit Balanced (medium effort, 2048 thinking tokens, 8192 total output tokens) and Deep (extra-high effort, 8192 thinking tokens, 16384 total output tokens) presets separate from publisher recipes. Balanced SHALL remain an available explicit model-configuration choice. Ordinary new Chat use SHALL start from its selected model's saved defaults rather than silently replacing them with a response preset. Unsupported independent thinking limits SHALL be labelled as response-limit-only; startup settings and saved publisher recipes SHALL remain distinct.

#### Scenario: Duplicate reasoning representation
- **WHEN** one reasoning string exists in both native content and additional metadata
- **THEN** context accounting SHALL count only the outbound representation and SHALL NOT trigger compaction due to duplicate storage.

#### Scenario: Response limit interrupts tool input
- **WHEN** generation reaches its configured limit during tool arguments
- **THEN** partial arguments SHALL remain inert and the chat SHALL offer an actionable continuation instead of becoming permanently blocked.

### Requirement: MOD-008 - Import Hugging Face bundles by explicit selection

Guided Hugging Face imports SHALL read repository metadata before weight transfer, present GGUF variants with disk size and all shards, require explicit projector or text-only choice when projectors exist, resolve an immutable commit internally, and preserve relative paths and hashes. Ambiguous weights, ambiguous projectors, incomplete shards, and mixed shards MUST fail explicitly.

#### Scenario: Ambiguous projector

- WHEN a repository contains more than one plausible projector
- THEN import or deployment MUST require an explicit selection or text-only choice
- AND legacy ambiguous projector records MUST fail at deployment start rather than guessing.

The guided import SHALL present Find, Choose and Review/download stages. Find SHALL support repository search and exact supported Hugging Face links; Choose SHALL preserve complete primary/projector selections and offer the advisory hardware estimate; Review SHALL show exact selection and initial configuration before explicit Download. Back SHALL preserve selections and draft settings. Advanced metadata SHALL remain expandable. Selected context, supported KV precision and placement SHALL become the initial saved configuration rather than display-only suggestions; publisher recipe selection and native metadata provenance SHALL remain explicit and intact.

Automatic context, f16 key/value cache and GPU KV SHALL be the fresh import defaults. Import-created recipe configurations SHALL inherit the selected job's startup in their own stable identities; retry/recovery SHALL NOT overwrite prior or deliberately edited configurations. Ordinary repeated model-card recipe creation SHALL preserve existing editable recipe identities.

#### Scenario: Review and revise import options

- **WHEN** a person selects a complete quantization, context and KV options, opens Review then goes Back
- **THEN** the exact selections remain, and explicit Download retains the chosen initial settings alongside the immutable revision, file membership and projector/text-only choice.

#### Scenario: Exact linked primary file

- **WHEN** Find receives a supported exact primary GGUF file link
- **THEN** the staged flow retains that exact variant and required shards rather than switching to another quantization.

### Requirement: MOD-022 - Apply managed configuration changes safely

Idle managed configurations SHALL support validated reconfiguration with expected-version and retained-history compatibility checks. Startup edits SHALL preserve the current launch snapshot until an explicit safe reload; active, queued, waiting, cancelling, Lab and helper consumers SHALL block a configuration binding change with named reasons. An explicit response-only configuration switch MAY update the existing deployment binding without reloading only when the selected configuration and requested operation match its frozen launch identity, the owned process still matches and fresh runtime observations confirm health. Automatic listen ports SHALL use the established configuration identity normalization; the actual frozen startup and process identity SHALL remain unchanged. Saved publisher recipes SHALL not be repurposed as product presets.

Capacity-driven eviction of an idle model instance MAY occur between calls, including during an alternate-model helper handoff, provided no in-flight inference request is interrupted and the next call can reload its exact selected configuration. Adding a separately frozen queued preset SHALL NOT be treated as an edit to an unchanged existing preset merely because a section separator moved; an actual edit to a referenced preset SHALL retain its active/queued-consumer guard. Automatic child ports SHALL be allocated and checked at launch; fixed-port conflicts fail before spawn. Ownership and observed readiness SHALL precede committing loaded values. Failure SHALL preserve prior and attempted configurations, attempt at most one safe restoration and report truthful stopped/failed state; restart SHALL reconcile interrupted changes. Connected endpoints SHALL not grant reload authority.

#### Scenario: Response-only Balanced selection
- **WHEN** an idle healthy owned model selects a separate saved Balanced configuration with the same frozen launch identity
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

### Requirement: MOD-035 - Bound managed model residency

The application SHALL save one positive maximum-loaded-model count for managed llama.cpp configurations. A fresh installation SHALL default to one. Every loaded launch configuration SHALL consume one slot, even when two configurations use the same weights; the count SHALL remain distinct from each model's parallel request slots. Connected endpoints SHALL remain outside this owned count. A different or unloaded requested model SHALL load on explicit idle model/configuration selection, idle fixed-model agent selection, or the first accepted input that needs that selection. A selection made during active work SHALL stage the next submission and SHALL load only through that input's safe admission; it MUST NOT warm merely because a draft changed. Re-selecting the exact healthy loaded configuration SHALL not request another model start. Successive turns on an already loaded configuration SHALL avoid reading the complete weight file again while still checking its saved identity; an evicted configuration SHALL undergo full bundle verification before it loads again. Application launch, chat restoration, passive status reads and navigation SHALL NOT warm or load a model. Loading SHALL show pending, loaded or failed state, and MUST NOT silently substitute weights, quantization, device or settings.

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

## ADDED Requirements

### Requirement: MOD-036 - Estimate model hardware use without restricting user choice

Choose options and initial model configuration SHALL offer a condensed advisory hardware estimate driven by the complete selected model files and available metadata, supported KV precision/location, context and detected GPU/RAM memory. It SHALL show known model/disk size, hardware total/available memory and freshness, estimated weights, KV cache and runtime overhead, a qualified approximate context marker, and likely GPU/RAM placement where calculable. An upper-bound context marker that excludes unknown overhead SHALL NOT claim verified fit. Weight/layer offloading and KV-cache placement in RAM SHALL remain distinguishable. Unknown sizes, unsupported architecture calculations or unavailable hardware SHALL remain unknown with inspectable assumptions; filename quantization hints or disk size alone MUST NOT be reported as verified VRAM fit. Per-device memory SHALL NOT silently be treated as one pooled budget.

Estimates SHALL be labelled approximate and remain separate from observed native runtime memory, applied settings and actual admission/load outcomes. After download/loading, available verified metadata and runtime fit information SHALL refine the estimate without silently overwriting the chosen settings. Alternative contexts, quantizations or KV options SHALL be comparable but SHALL require deliberate selection. Chosen context, precision and placement SHALL use the same canonical configuration/launch contract as Models, preserving requested versus applied facts.

An estimated shortage or unknown fit MUST NOT disable saving, downloading or loading a supported valid configuration, and MUST NOT silently reduce context, precision or selected placement. Actual invalid file/configuration/permission conditions SHALL retain their established validation. Actual load failures SHALL identify the attempted configuration, preserve chosen settings and provide adjustment/recovery.

Before import, dense cache calculations SHALL use verified scalar architecture metadata and native quantization block sizes; unsupported hybrid/sliding-window/MoE/MLA/multimodal/layout components and compute overhead SHALL remain unknown. Explicit layer-count placement SHALL remain unknown without native tensor placement evidence and SHALL NOT supply a full-GPU context marker. Remote metadata inspection SHALL cap aggregate range bytes, requests and elapsed time and cache by immutable revision/file identity; ignored ranges SHALL fail before their body is consumed. After install, the pinned native no-model-allocation predictor SHALL be preferred independently of the bounded metadata result, with bounded process time/output/concurrency. Native Auto results SHALL be hypothetical evaluated values alongside unchanged selected values. When server automatic parallel slots are unresolved, the estimator SHALL explicitly record its evaluated one-slot setting, qualify full server allocation as unknown and suppress the native Auto context marker. Explicit parallel slots SHALL be passed through. Separate native device rows and actual loaded observations SHALL remain inspectable; excluded projector/draft/driver allocations SHALL be qualified. Cached predictions SHALL retain their original calculation time.

#### Scenario: Native helper defaults differ from automatic server slots
- **WHEN** a configuration leaves parallel slots Automatic and the native helper predicts one sequence
- **THEN** evaluated startup SHALL explicitly show one slot, requested startup SHALL stay unchanged and full server allocation SHALL remain unresolved
- **AND** that incomplete prediction SHALL NOT establish a native Auto context marker or an exact launch-memory match.

#### Scenario: Native prediction can inspect an unsupported dense estimate
- **WHEN** an installed model uses a hybrid architecture or has a directory exceeding the remote metadata budget, and the pinned native predictor is available
- **THEN** native prediction SHALL still be attempted without starting a deployment, hashing full weights or rewriting requested settings
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
