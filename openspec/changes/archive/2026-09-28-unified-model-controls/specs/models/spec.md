## ADDED Requirements

### Requirement: MOD-039 - Share validated model controls and effective Thinking

Model import, save, preview and execution SHALL use one definition of supported control domains, units, dependencies, named defaults, provenance and apply timing. Numeric inputs SHALL reject nonfinite values and enforce whole counts where required. Slider spans SHALL remain distinguishable from actual supported bounds. Normal controls SHALL use named Auto/Off/inheritance states, not raw sentinel numbers. Thinking SHALL offer only template-effective modes/levels and deduplicate aliases; unknown models SHALL remain usable with truthful unknown/default support. Invented generic Balanced/Deep response bundles SHALL be removed. Chat Thinking SHALL preserve explicit saved sampling choices; paired response recipes SHALL be deliberately selected in Models.

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

Explicit saved/chat total-output allowances SHALL remain exact. Otherwise a compatible exact recipe/publisher total allowance SHALL be preferred; when absent, visible Workbench Auto SHALL select a finite allowance from the observed per-slot capacity and Thinking policy. Thinking and answer SHALL share this allowance; it SHALL NOT promise answer length or completion. Authored policy/source/version SHALL freeze at acceptance; each role SHALL atomically record its resulting numeric allowance and capacity provenance before its first model request, then reuse it for subsequent calls, retries and resumes. Wire limits, context guards and existing compaction SHALL agree without double reservation. Later incompatible capacity SHALL require recovery rather than recalculation or silent clamping.

#### Scenario: Cold helper with automatic allowance
- **WHEN** an accepted helper first binds to its exact cold model
- **THEN** its frozen policy resolves once against loaded capacity before the model call and survives later setup edits.

#### Scenario: Explicit limit cannot fit
- **WHEN** the selected explicit allowance cannot coexist with necessary input and safety margin
- **THEN** an actionable capacity/allowance conflict is shown without changing that explicit setting.

### Requirement: MOD-042 - Preview complete selected native allocations

Installed-model preview SHALL use the exact pinned runtime's native allocation APIs without loading model weights or disrupting inference. It SHALL account for selected target, projector and draft/MTP allocations, including shared MTP weights once, server slot/pool preprocessing and per-device placement. The result SHALL identify the selected plan, evaluated settings, effective context/slots, timestamp and completeness. Dynamic driver/operating-system/host-cache overhead SHALL remain unknown or separately budgeted. A failed selected component SHALL remain unknown/partial, never zero or a verified fit. Actual loaded observations SHALL match the exact residency identity and remain separately authoritative. Missing/unsupported/crashed/timed-out helpers SHALL leave inference usable.

#### Scenario: Vision and MTP plan
- **WHEN** an installed plan includes a projector and embedded MTP
- **THEN** the preview includes their native device allocations without counting shared weights twice.

#### Scenario: Concurrent context pool
- **WHEN** four requests share unified KV
- **THEN** the preview distinguishes the total pool and maximum per-chat capacity without promising four reserved full contexts.

#### Scenario: Predictor failure
- **WHEN** measurement fails or the adapter times out
- **THEN** the result is partial/unavailable with its reason and the existing model remains running.

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
- **AND** Thinking and context adjustments remain chat-local, only Models saves a named setup, and no adjustment rewrites a queued turn or historical loaded snapshot.

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


The product SHALL use compatible pinned-card recommendations and template-effective Thinking choices without invented response bundles. Explicit total-output limits remain unchanged; otherwise a compatible publisher total-output recommendation wins. Absent that, versioned Workbench Auto guidance reserves half the usable context when Thinking is enabled or unknown, or one quarter when disabled, after the existing eight-percent margin. The allowance includes Thinking plus answer and SHALL NOT promise an answer length. Admission freezes the policy, and each execution role records its numeric allowance once on binding to verified loaded capacity. Wire requests, replay and compaction use that recorded allowance; an incompatible later capacity requires deliberate recovery.

#### Scenario: Duplicate reasoning representation
- **WHEN** one reasoning string exists in both native content and additional metadata
- **THEN** context accounting SHALL count only the outbound representation and SHALL NOT trigger compaction due to duplicate storage.

#### Scenario: Response limit interrupts tool input
- **WHEN** generation reaches its configured limit during tool arguments
- **THEN** partial arguments SHALL remain inert and the chat SHALL offer an actionable continuation instead of becoming permanently blocked.

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

### Requirement: MOD-036 - Estimate model hardware use without restricting user choice

Choose, import review, Models and Chat context candidates SHALL consume the shared non-disruptive hardware preview. Installed-model allocation calculation SHALL use a bounded subprocess compiled against the exact pinned llama.cpp native APIs. It SHALL match server preprocessing for four default parallel slots, unified context, embeddings and speculation; measure target, selected projector and draft/MTP together; and count shared MTP weights once. The helper protocol, digest and native compatibility SHALL be recorded in the runtime manifest. It SHALL NOT start or stop a deployment or replace the running inference process.

Results SHALL expose per-device estimates, evaluated placement, shared context, per-request capacity, slots, plan identity, calculation time and complete/partial/unavailable status. Native context allocations SHALL be labelled Cache and model state; projector totals SHALL NOT invent an internal breakdown. Requested Auto values remain distinct from evaluated results. Dynamic driver, host cache and operating-system costs SHALL remain unknown or separately budgeted. Missing facts MUST NOT become zero or a green fits claim. Observed memory SHALL be labelled Observed, timestamped and associated only with the exact loaded identity; cached estimates retain their original time.

Remote discovery SHALL retain bounded revision/file metadata estimates with exact shards/projector selection and explicit unknowns until installed native measurement is available. Ignored byte ranges SHALL fail before body consumption. Predictions SHALL remain advisory, preserve settings and downloaded weights, and never block valid Save, Download or Load merely because estimated memory is insufficient.

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

### Requirement: MOD-037 - Preview the selected model candidate faithfully

Models readouts SHALL resolve the selected model, configuration and unsaved draft through the existing model-capable resolver boundary. Application-default editing SHALL remain access-only. Chat context preview and Reload SHALL use the same candidate, including removed overrides, and default labels SHALL use the correct parent/model value and source. Editing SHALL remain available during validation, while context Reload SHALL require the latest matching valid result. Readiness SHALL use the resolver's exact selected live configuration identity and distinguish quantization/configuration labels.

#### Scenario: Preview advanced startup edits
- **WHEN** the selected configuration requests All GPU layers, memory fitting Off and q4_0 key precision, then edits and resets them
- **THEN** requested and effective readouts agree with the real resolver for that candidate and the reset target value is correct.

#### Scenario: Preview completes out of order
- **WHEN** typing changes the candidate while an earlier check completes
- **THEN** editing stays uninterrupted and that earlier result cannot enable Reload for the newer candidate.
