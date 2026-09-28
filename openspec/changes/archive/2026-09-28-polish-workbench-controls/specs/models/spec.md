## MODIFIED Requirements

### Requirement: MOD-021 - Report known defaults and their source

Model controls SHALL show the effective value and source when configuration, server properties or a recognized selected-template default establishes it. Omitted request values MUST remain omitted unless explicitly overridden. Configured, transmitted, observed and template-derived facts MUST remain distinguishable. Unknown defaults remain unknown. Following a configuration default, using the model default and choosing explicit None SHALL remain distinct operations. Each available default-following action SHALL name its actual target and expose its known resolved value rather than saying Inherited.

#### Scenario: Known thinking default
- **WHEN** the selected template establishes Xhigh as the omitted effort default
- **THEN** the control shows Xhigh with its model-default source
- **AND** displaying that default does not manufacture an explicit request override.

#### Scenario: Uncertain default
- **WHEN** a default depends on an unresolved template condition or unavailable server information
- **THEN** the control reports the uncertainty rather than inventing an actual value.

### Requirement: MOD-027 - Expose model controls and clear terminal downloads

The Models workspace SHALL provide My models, Add models and Downloads tabs. My models SHALL use a compact, searchable and keyboard-accessible catalogue beside a responsive editor when space permits, collapsing into an accessible model/configuration selector on narrower windows. Long names and filename-derived Standard, LOW-MTP or MTP variants SHALL remain distinguishable. Unsaved edits SHALL remain available when switching between models or configurations or navigating within the open app, and SHALL be marked visibly; reverting to saved values SHALL clear that mark.

The selected model SHALL clearly separate Configuration, Model card and Files. Common context, GPU offloading, cache, thinking, thinking history, reply and sampling controls SHALL be visible; advanced settings SHALL retain memory fitting, flash attention, independent key and value cache precision, supported speculative mode/draft tokens and all existing sampler controls without removing capability-dependent choices. Context SHALL support direct numeric entry and an empty requested control SHALL restore default-following behaviour. GPU layers SHALL offer following the resolved default, Automatic, All, CPU and an exact count. Automatic SHALL pass llama.cpp's automatic value (`auto` or legacy `-1`); All SHALL pass its explicit `all` value. Displayed launch settings SHALL identify a requested mode without claiming actual GPU placement unless the engine reports it. MTP SHALL appear only when supported by inspected metadata. Diagnostics, logs, recipes, provenance and exact file membership SHALL remain accessible in their appropriate disclosures or tabs.

Controls SHALL make the backend-resolved effective value and source the main readout without storing a followed value as an explicit override. Known followed, edited, loaded and unknown values SHALL remain distinguishable; an unknown value SHALL say Not reported. Binary settings SHALL use accessible round switches. Three-state settings SHALL expose the resolved default choice and both explicit states with a keyboard-operable control. A separate Loaded value SHALL appear only for a meaningful difference reported by the running engine. Saving SHALL update the selected model configuration for future Chat, Lab and Workflows turns; startup application SHALL follow managed reload safety. Save changes, Save as configuration, default selection and Load or Apply configuration SHALL remain available with labels accurately describing saving and loading. Applying a loaded configuration SHALL not promise a restart when the existing frozen launch can be rebound without one; changed launch settings SHALL retain safe reload behaviour.

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

## ADDED Requirements

### Requirement: MOD-037 - Preview the selected model candidate faithfully

Models readouts SHALL resolve the selected model, configuration and unsaved draft through the existing model-capable resolver boundary. Application-default editing SHALL remain access-only. Chat tuning preview and Apply SHALL use the same candidate, including removed overrides, and default labels SHALL use the correct parent/model value and source. Editing SHALL remain available during validation, while Apply SHALL require the latest matching valid result. Readiness SHALL use the resolver's exact selected live configuration identity and distinguish quantization/configuration labels.

#### Scenario: Preview advanced startup edits
- **WHEN** the selected configuration requests All GPU layers, memory fitting Off and q4_0 key precision, then edits and resets them
- **THEN** requested and effective readouts agree with the real resolver for that candidate and the reset target value is correct.

#### Scenario: Preview completes out of order
- **WHEN** typing changes the candidate while an earlier check completes
- **THEN** editing stays uninterrupted and that earlier result cannot enable Apply for the newer candidate.

### Requirement: MOD-038 - Keep import choices and estimates truthful

Model import SHALL retain Find, Choose and Review/download stages; Back and failed requests SHALL preserve choices. Selected context and independent K/V settings SHALL become the initial configuration while exact shards, projectors, capabilities and import defaults remain authoritative. Slider fill SHALL reflect the actual displayed value; an automatic setting SHALL not imply a fixed value. Hardware presentation SHALL expose real GPU/RAM availability and qualified weights/cache/overhead estimates, with unknown components and device boundaries explicit. Estimates SHALL never block valid choices or silently reduce settings. A manual Refresh SHALL bypass estimate caching only for that request.

#### Scenario: Review then go Back
- **WHEN** a person chooses files, context and cache precision, advances to Review, then goes Back
- **THEN** those exact choices remain selected and become the installed initial configuration on download.

#### Scenario: Incomplete estimate
- **WHEN** device availability or overhead is unknown
- **THEN** the estimate describes the unknown component without claiming a verified fit or blocking a valid download.
