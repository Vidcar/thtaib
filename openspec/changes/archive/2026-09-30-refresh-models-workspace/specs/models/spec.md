# Spec Delta

## MODIFIED Requirements

### Requirement: MOD-003 - Preserve profile fidelity

Each model SHALL allow zero or more named saved configurations, shared by Chat, Lab and Workflows, with an optional preferred configuration. A model without usable selected card recipes SHALL have no automatically created setup; the user SHALL save a named setup before loading it. Empty native setting bags SHALL be valid when recorded model artifacts and runtime requirements suffice. The first manually saved setup SHALL become preferred. Deleting the last or preferred setup SHALL be allowed subject to active-use protection and SHALL clear the preferred pointer when needed. Missing setup references SHALL remain actionable without silently selecting another setup. Configurations SHALL separate startup and per-request inference settings; agents and project/chat setup SHALL own behaviour, tools and knowledge. An optional saved model instruction block SHALL be visible, editable and explicitly resettable in its owning Models setup and shared input inspection. Omitting this block while saving other configuration fields SHALL preserve it; resetting it SHALL clear only this optional guidance. A model configuration MUST reject a different bundle or agent capability/access fields. Historical snapshots preserve their original distinct settings bags. Selecting a profile SHALL pass its identity and resolved bags to the backend. Each deployment SHALL freeze its launch inputs; profile edits affect future work and show pending startup differences rather than rewriting an active deployment.

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

### Requirement: MOD-008 - Import Hugging Face bundles by explicit selection

Guided Hugging Face imports SHALL read repository metadata before weight transfer, present GGUF variants with disk size and all shards, require explicit projector or text-only choice when projectors exist, resolve an immutable commit internally, and preserve relative paths and hashes. Ambiguous weights, ambiguous projectors, incomplete shards, and mixed shards MUST fail explicitly.

#### Scenario: Ambiguous projector

- WHEN a repository contains more than one plausible projector
- THEN import or deployment MUST require an explicit selection or text-only choice
- AND legacy ambiguous projector records MUST fail at deployment start rather than guessing.

The guided import SHALL present Find and Choose with an explicit Download/Add action on Choose and no separate Review stage. Find SHALL support repository search, exact supported Hugging Face links and native local browsing. Choose SHALL preserve one complete primary/shard selection, explicit projector or text-only choice, immutable revision and checked usable card recipes. Back and failed requests SHALL preserve choices. Card recipes SHALL create only the selected named configurations. Without selected recipes, import SHALL create no setup. Untouched native settings SHALL remain omitted. Memory preview controls SHALL remain advisory and MUST NOT become saved startup overrides. Retry/recovery SHALL NOT overwrite prior or deliberately edited configurations. Repeated card creation SHALL preserve editable recipe identities.

#### Scenario: Choose and install
- **WHEN** a person selects a complete quantization, an explicit projector or text-only choice and two offered recipes, then chooses Download
- **THEN** the exact selection is installed and only those two named setups are created, without another review step or implicit Default setup.

#### Scenario: Advisory preview is not a setup
- **WHEN** a person explores context, placement or cache values on Choose and downloads without selecting card recipes
- **THEN** no setup is created and the preview settings are not stored as native overrides.

#### Scenario: Review and revise import options
- **WHEN** a person chooses complete files/projector on Choose, explores the advisory settings, then goes Back
- **THEN** the exact selections remain and Download is available directly from Choose without a separate Review stage.

#### Scenario: Untouched loading settings stay omitted
- **WHEN** a person downloads without selecting any recipes or authoring a named setup
- **THEN** optional native tuning stays omitted and no generic setup is created.

#### Scenario: Exact linked primary file
- **WHEN** Find receives a supported exact primary GGUF file link
- **THEN** Choose retains that exact variant and required shards rather than switching quantization.


### Requirement: MOD-019 - Keep capability probes specific to the tested setup

Reusable probes SHALL exercise shared-adapter streaming, a harmless real tool round trip, structured output and suitable reasoning/image support. Records SHALL retain test inputs/outcomes, runtime/deployment/bundle, template/projector and effective response/Thinking/history settings. Behavioral evidence SHALL persist in user data and be reusable across replacement deployments with matching artifacts/runtime/template/projector/response semantics. Mutable labels, revision-only changes, process IDs and endpoint changes SHALL NOT invalidate managed proof. A changed effective response/Thinking/history setting SHALL have its own tested scope. Proof follows the weight files, projector, template and runtime. Changing context, key or value cache precision, cache location, GPU layers, flash attention or MTP on the same weights and projector SHALL NOT discard that proof. Changing the weight files, projector, template or runtime SHALL. Publisher guidance, recommendations, user opt-outs, tested adjustments, failed, untested and inconclusive outcomes remain distinct. A failed probe MUST NOT establish universal model incompatibility or prevent explicitly unverified ordinary use.

The model header SHALL show the ten supported checks with accessible status/help and individual icon retests, plus Run all. Failure/inconclusive SHALL be normal evidence rather than an error banner. Audio/video automatic checks SHALL remain deferred with no verified claim from an indicator. After a healthy named-setup load, missing applicable checks SHALL run automatically through the backend without blocking ordinary text use; saved matching results SHALL prevent repeated testing on later loads. Passive reads/navigation SHALL NOT infer or load. Explicit retests SHALL replace only the requested check's evidence. Concurrent automatic, manual and dependent image checks SHALL share lifecycle protection and deduplication; cancelled unrun checks SHALL remain missing and retryable.

#### Scenario: Changed setup

- **WHEN** a previously tested template, projector, runtime or weight selection changes
- **THEN** old evidence remains attributable to its original setup and the new setup is not automatically labelled verified.

#### Scenario: Loading adjustments keep weight and projector proof

- **WHEN** context, cache precision, cache location, GPU layers, flash attention or MTP change on the same weights and projector
- **THEN** existing proof for those weights remains applicable.

#### Scenario: Reload reuses evidence
- **WHEN** a saved setup loads again after restart with unchanged behavioral inputs
- **THEN** its persisted pass, fail or inconclusive results are reused without running those checks again.

#### Scenario: Selected response recipe and manual retest
- **WHEN** two response recipes share one native child and a person retests one check for the selected saved setup
- **THEN** the saved setup identity/revision resolves its actual response values server-side and only that scope/check is updated.


### Requirement: MOD-025 - Organize model tasks without losing progress

The Models workspace SHALL provide My models and Add models tabs. Add models SHALL contain Find, Choose and ongoing import progress with Cancel/Retry and compact detailed recovery/cleanup actions. Progress and completion SHALL remain current while another tab/page is selected, survive restart through durable job records and never steal focus on completion. No separate Downloads page SHALL be required. Installation destination/storage cleanup SHALL be available in Settings.

#### Scenario: Leave a running download
- **WHEN** a person starts a download and switches to My models
- **THEN** Add models continues to report active work and the completed bundle becomes available without forcing a tab change.


### Requirement: MOD-027 - Expose model controls and clear terminal downloads

The Models workspace SHALL provide My models and Add models tabs. My models SHALL use a compact, searchable and keyboard-accessible catalogue beside a responsive editor when space permits, collapsing into an accessible model/configuration selector on narrower windows. Long names and filename-derived Standard, LOW-MTP or MTP variants SHALL remain distinguishable. Unsaved edits SHALL remain available when switching between models or configurations or navigating within the open app, and SHALL be marked visibly; reverting to saved values SHALL clear that mark.

The selected model SHALL present compact Generation and Loading columns with model-card/files/runtime maintenance in contextual disclosures. Common Context, GPU layers, independent K/V cache precision, Flash attention, Thinking, thinking history, maximum output tokens, MTP and all seven common sampling fields SHALL be visible in compact controls. Advanced SHALL retain memory fitting, specialist samplers, CPU/batch/parallel/offload/loading settings, thinking budget/format, speculative tuning and optional model instructions. Context SHALL use one 1,024-token slider and readout with verified bounds and the exact known maximum endpoint; display ranges MUST NOT become invented runtime bounds. Optional native overrides SHALL remain empty until set, with known defaults/effective values in brief contextual help; displaying a default SHALL NOT store it. GPU layers SHALL offer Auto, All, CPU and an exact count. Automatic SHALL pass llama.cpp's automatic value (`auto` or legacy `-1`); All SHALL pass its explicit `all` value. Displayed launch settings SHALL identify a requested mode without claiming actual GPU placement unless the engine reports it. MTP SHALL appear only when supported by inspected metadata. Diagnostics, logs, recipes, provenance and exact file membership SHALL remain accessible in their appropriate disclosures or tabs.

Controls SHALL make the backend-resolved effective value and source the main readout without storing a followed value as an explicit override. Known followed, edited, loaded and unknown values SHALL remain distinguishable; an unknown value SHALL say Not reported. Binary settings SHALL use accessible compact switches or labelled two-position controls. Keyboard-operable controls SHALL expose effective choices, retaining genuine Auto/Unlimited modes without redundant inheritance positions. Source, reset, exact native mapping and apply timing SHALL be available in contextual help. A separate Loaded value SHALL appear only for a meaningful difference reported by the running engine. Saving SHALL update the selected model configuration for future Chat, Lab and Workflows turns; startup application SHALL follow managed reload safety. Create and Delete SHALL be compact primary setup actions; rename, copy, preferred selection and revert SHALL be available in a small menu. Save and Load SHALL remain distinct with accurate labels. Applying a loaded configuration SHALL not promise a restart when the existing frozen launch can be rebound without one; changed launch settings SHALL retain safe reload behaviour.

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

The product SHALL extract only unambiguous, supported response recommendations from a revision-pinned GGUF repository card and record their source repository, revision, card identity and section. Card recommendations SHALL remain separately attributed from verified automatic generation defaults. Only explicitly selected card recipes SHALL be adopted as saved setups. Empty/manual setups SHALL use native/template and verified publisher generation defaults without implicitly adopting a card recipe. Valid zero-valued samplers and supported presence and frequency penalties SHALL be retained. An unsupported, invalid or conflicting response recommendation SHALL not be offered as a selectable recipe.

The product SHALL support both explicitly named thinking and non-thinking recipes and a single clearly recommended set of response samplers without a thinking-mode instruction. The latter SHALL preserve the chosen configuration's existing thinking mode. Non-response guidance in the same recommendation section SHALL be clearly identified as not copied into the configuration and remain available in the full card.

During import or on an installed model, a user SHALL be able to select any offered recipes for creation as named model configurations and optionally choose one as the model default. A new configuration SHALL be created directly from required verified bundle/template defaults and the selected response recipe without requiring or cloning a generic default setup. Checked usable recipes SHALL be selected initially in stable card order; the user SHALL be able to uncheck any/all recipes. Only checked recipes SHALL create named setups, with the first selected recipe preferred unless explicitly chosen otherwise. Existing configurations and explicit overrides SHALL not be overwritten by metadata refresh or later card changes. Repeating a selected import or creation action SHALL not duplicate recipe-created configurations. Thinking mode SHALL be applied only when the selected model template supports the relevant toggle. Weight-install success and configuration-creation failure SHALL be reported separately.

#### Scenario: Three recommendations on one card
- **WHEN** the selected pinned model card clearly recommends general thinking, precise coding and non-thinking values
- **THEN** all three appear as separate response recipes with source attribution
- **AND** only checked recipes create named setups; unchecking all leaves the model without a saved setup.

#### Scenario: Single recommended response set
- **WHEN** the selected pinned card clearly recommends one valid set of response samplers without specifying a thinking mode
- **THEN** the supported values appear as one selectable recipe with source attribution
- **AND** creating its configuration preserves native/template Thinking when the recipe does not specify it.

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

Choose, Models and Chat context candidates SHALL consume the shared non-disruptive hardware preview. Choose selects quantization, projector or text-only, and the publisher generation recipe. Ordinary installed-model preview SHALL use fast cached metadata/tensor calculations. A deliberate native check SHALL use a bounded subprocess compiled against the exact pinned llama.cpp native APIs. Both methods SHALL account for the selected server parallel slots, unified context, embeddings and speculation; measure target, selected projector and draft/MTP together; and count shared MTP weights once. A built-in draft head is a tensor whose name ends in `nextn.eh_proj.weight`, for every architecture. A separate draft file counts only after that file's own header contains a NextN tensor. MTP memory is included only when draft-mtp is selected. MTP off excludes embedded next-token tensors from the estimate; those tensors remain in the downloaded file. A built-in head counts shared weights once and adds the head cache. A separate draft adds that file and does not recount the target's embedded tensors. The helper protocol, digest and native compatibility SHALL be recorded in the runtime manifest. It SHALL NOT start or stop a deployment or replace the running inference process. The estimate SHALL NOT block Download.

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
- **WHEN** the person adjusts the context slider or chooses supported CPU KV placement on Choose
- **THEN** the estimate updates its cache and GPU/RAM breakdown without saving those advisory values into an initial configuration.

#### Scenario: Draft head is offered only from tensor evidence
- **WHEN** a repository GGUF header contains a `nextn.eh_proj` tensor, or a separate MTP-named file's header contains a NextN tensor
- **THEN** Choose offers MTP and includes its memory only after the person turns that head on
- **AND** a filename alone, including an imatrix file, does not offer MTP.

#### Scenario: Runtime contradicts the estimate
- **WHEN** the native engine reports a different actual allocation or fails to load the chosen setup
- **THEN** actual observations/failure remain authoritative and inspectable alongside the approximate estimate, and the user's attempted settings remain available for adjustment.

#### Scenario: Complete variant and projector sizing
- **WHEN** the selected model uses multiple shards or an explicitly selected projector
- **THEN** known selected-file sizes are included with clear components and unknown overhead remains qualified rather than omitting selected files.

#### Scenario: Shared router process observation
- **WHEN** a managed deployment records router process usage without verified model-child usage
- **THEN** model process RAM remains unavailable with an explicit reason rather than displaying the router's resident memory as the model allocation.

#### Scenario: Total-capacity discovery preview
- **WHEN** a model selection is previewed on Choose while another model consumes memory
- **THEN** its advisory budget uses reported physical GPU/RAM totals with visible headroom rather than live availability; preview defaults use verified model bounds, highest supported cache precision and verified MTP where available
- **AND** live resource rings, admission and Chat capacity previews retain their available-memory semantics, with unknown allocation unable to establish a fit.

#### Scenario: Local metadata preview
- **WHEN** a local GGUF file/folder is opened on Choose
- **THEN** bounded read-only header inspection previews the exact complete selected model without importing, copying or loading weights.


### Requirement: MOD-038 - Keep import choices and estimates truthful

Model import SHALL retain Find and Choose with direct Download/Add; Back and failed requests SHALL preserve choices. Context, K/V precision and other memory preview controls SHALL be advisory and MUST NOT become saved setup overrides. Exact shards, projector/text-only, immutable revision, local copy/original ownership and checked card recipes SHALL remain authoritative. Slider fill SHALL reflect its displayed value and real model bounds; unknown bounds SHALL remain unknown. Hardware presentation SHALL expose reported total capacity and visible headroom for discovery, qualified component estimates and explicit unknown/device boundaries. Estimates SHALL never block valid choices or silently reduce settings. A manual Refresh SHALL bypass estimate caching only for that request. Search SHALL expose known complete-variant counts and advertised capability provenance; unknown counts/capabilities SHALL remain unknown without inferring Thinking from a recipe name or Image from a filename alone.

#### Scenario: Back retains choices
- **WHEN** a person chooses files, projector and card recipes, explores memory, then goes Back and returns
- **THEN** those choices remain and Download creates only checked card setups without copying memory-preview values.

#### Scenario: Review then go Back
- **WHEN** a person revises an import by returning from Choose to Find
- **THEN** exact file/projector/card choices remain available without a Review stage and advisory preview values remain unsaved.

#### Scenario: Incomplete estimate
- **WHEN** capacity or overhead is unknown
- **THEN** the estimate identifies unknown components without claiming verified fit or blocking a valid download.


### Requirement: MOD-043 - Keep Models editing stable and contextual

My models SHALL expose a saved-setup selector only when multiple setups exist, a single setup label when one exists, and an empty named setup editor when none exist. One Model card entry point and compact Save/Load SHALL remain. Create/Delete SHALL be visible beside setup management, with other setup actions in a small menu. Reload SHALL live in compact runtime details only when a managed deployment exists for the selected setup. Load and Load saved SHALL post the saved profile to managed start with an empty startup object and SHALL ignore unsaved edits. Reload SHALL be the only control labelled Reload and SHALL post `POST /v1/deployments/{id}/reload` for that same record. Load snapshot SHALL remain the start of a stopped record. Metadata/files/refresh/setup management and optional native checking SHALL live in contextual details. Generation/Sampling and Loading/Memory SHALL form two compact columns when at least 840 CSS pixels are available, stacking below that width. Common controls SHALL remain immediately visible and show resolved values without repeated Saved/default/provenance paragraphs. Pending startup changes SHALL require explicit loading. Controls SHALL use stable compact geometry; ordinary edits, reset availability, background checks and memory recalculation SHALL NOT move subsequent rows by more than one CSS pixel at a fixed viewport. Controls, focus, drafts and scroll position SHALL remain available through checks. Explicit disclosures, panel opening and viewport changes MAY reflow.

Infrequent presets, memory/native checking, runtime and files SHALL use compact contextual disclosures; header check icons SHALL be direct retest controls. Overlays SHALL retain keyboard containment, Escape dismissal and trigger focus restoration. Validation SHALL occur during Save for the exact candidate, include loading/response failures and retain edits on failure; no standalone Validate panel SHALL be required. Runtime details SHALL distinguish engine defaults from setup response settings. Response aliases SHALL have one canonical visible owner; bundle-level template/vision actions SHALL live in model information.

#### Scenario: Continuous editing during checks
- **WHEN** a person types, resets or changes a control while descriptors, effective values or memory estimates update
- **THEN** subsequent rows remain within one CSS pixel and controls stay mounted with truthful pending/unknown state
- **AND** results from another selection cannot replace the current candidate's facts.

#### Scenario: Check then edit or switch setup
- **WHEN** a check completes and the person changes response/loading values or selects another setup
- **THEN** old evidence remains attributable and cannot claim it validates the new candidate.

#### Scenario: Manage saved setups
- **WHEN** a person requests deletion
- **THEN** active-use lifecycle protections remain, deleting the last/preferred setup is allowed and a deleted preferred pointer is cleared without remapping saved references
- **AND** ordinary editing/refresh never automatically renames or deletes setups; an explicitly authorised development reset may discard obsolete setups without deleting weights.

#### Scenario: Load the saved setup
- **WHEN** the person chooses Load or Load saved
- **THEN** the desktop posts the saved profile to managed start with an empty startup object and ignores unsaved edits
- **AND** that control does not say Reload.

#### Scenario: Reload the same record
- **WHEN** a managed deployment exists for the selected setup and the person chooses Reload
- **THEN** the desktop posts that deployment id to `POST /v1/deployments/{id}/reload`
- **AND** that is the only Models control whose label is Reload.

#### Scenario: Load a stopped snapshot
- **WHEN** the person chooses Load snapshot on a stopped managed record
- **THEN** the desktop posts `POST /v1/deployments/{id}/start` for that record.

#### Scenario: A dirty draft races another save
- **WHEN** a configuration changes after an editor draft was created, including while that draft is stashed during navigation
- **THEN** Save SHALL compare against the draft's original saved revision and report a conflict without overwriting the intervening change or discarding the local draft
- **AND** only an explicit revert or a confirmed save SHALL replace that draft's saved base; failed observation after a confirmed save SHALL not undo the save acknowledgement.
- **AND** displayed effective values, validation and memory estimates SHALL describe the retained draft that Save or Save a copy would submit, including settings removed or added by the intervening save.

#### Scenario: Initial saved setup and engine observations arrive independently
- **WHEN** Models opens while saved configurations or engine observations are still being read
- **THEN** the editor SHALL establish the selected saved authoring base before accepting edits, and an unverified model observation SHALL NOT claim that the model is unloaded
- **AND** once established, the editor SHALL remain usable through background checks and later observations SHALL NOT discard its accepted draft.

## REMOVED Requirements

### Requirement: MOD-044 - Apply and reversibly remove publisher presets

**Reason**: Persistent hide/restore preset management adds infrequent UI and is explicitly retired.

**Migration**: Remove hidden-choice metadata without shims; keep actual recipes, named setups and ancestry, and use explicit application/pinned refresh under MOD-046.


## ADDED Requirements

### Requirement: MOD-045 - Rename models without changing identity

An installed model SHALL allow a validated friendly-name change without changing bundle/setup IDs, source repository/revision, artifacts, engine aliases or compatibility/probe evidence. Current catalogue, Chat, Agent/project and Lab selectors SHALL refresh that name. Historical accepted/run snapshots SHALL retain their captured labels. Compatibility matching SHALL use stable source/artifact identity rather than mutable display names.

#### Scenario: Rename while other pages stay open
- **WHEN** a model is renamed from My models
- **THEN** mounted current selectors display its new name and continue using the same stable setup/model references without a reload or retest.


### Requirement: MOD-046 - Use publisher presets explicitly

The Model card entry point SHALL retain verified pinned reading, website links, refresh and compact explicit preset application/creation. Applying a publisher preset SHALL change only supplied response fields and explicitly supported Thinking mode in the current draft, retain loading/unrelated values, mark changes and require Save. Recorded ancestry SHALL remain read-only and MUST NOT be inferred from names. Persistent preset hide/remove/restore actions SHALL be removed; pinned refresh SHALL not recreate deleted setups, overwrite configurations, change preference or download weights.

#### Scenario: Apply non-thinking to an edited setup
- **WHEN** a person applies a supported Non-thinking preset
- **THEN** supplied response/Thinking fields change in the draft while loading/unrelated values remain, and Save is required.

#### Scenario: Refresh after setup deletion
- **WHEN** a person deletes a card-created setup and refreshes the pinned card
- **THEN** recipe metadata refreshes without recreating that setup or changing other saved setups.
