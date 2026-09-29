## MODIFIED Requirements

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

### Requirement: MOD-039 - Share validated model controls and effective Thinking

Model import, save, preview and execution SHALL use one definition of supported control domains, units, dependencies, named defaults, provenance and apply timing. Numeric inputs SHALL reject nonfinite values and enforce whole counts where required. Slider spans SHALL remain distinguishable from actual supported bounds. Normal controls SHALL show actual resolved values and named native Auto/Off/Unlimited states, not raw sentinel numbers or redundant Default positions. Each help disclosure SHALL expose its actual native flag or request path, source and apply timing. Thinking SHALL offer only template-effective modes/levels and deduplicate aliases; unknown models SHALL remain usable with truthful unknown/default support. Invented generic Balanced/Deep response bundles SHALL be removed. Chat Thinking SHALL preserve explicit saved sampling choices; paired response recipes SHALL be deliberately selected in Models.

#### Scenario: Same choice across boundaries
- **WHEN** the same control is imported, saved, previewed and transmitted
- **THEN** its domain, source and effective setting agree and an invalid value fails before disruptive loading.

#### Scenario: Effective template levels
- **WHEN** a template supports binary Thinking or aliases High to Extra high
- **THEN** the normal control offers only effective distinct positions and no generic unsupported level.

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
