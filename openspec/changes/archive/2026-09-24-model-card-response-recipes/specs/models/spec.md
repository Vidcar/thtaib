# Spec Delta

## ADDED Requirements

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

The product SHALL extract only unambiguous, supported response recommendations from a revision-pinned GGUF repository card and record their source repository, revision, card identity and section. Card recommendations SHALL remain separate from verified automatic generation defaults and MUST NOT affect requests until explicitly used in a saved configuration. Valid zero-valued samplers and supported presence and frequency penalties SHALL be retained. An unsupported or conflicting recommendation SHALL not be offered as a complete recipe.

During import or on an installed model, a user SHALL be able to select any offered recipes for creation as named model configurations and optionally choose one as the model default. A new configuration SHALL copy the then-current default configuration's requested launch settings, use the selected response recipe while retaining unrelated requested response settings, and remain independent of later default edits. Existing configurations and explicit overrides SHALL not be overwritten. Repeating a selected import or creation action SHALL not duplicate recipe-created configurations. Thinking mode SHALL be applied only when the selected model template supports the relevant toggle. Weight-install success and configuration-creation failure SHALL be reported separately.

#### Scenario: Three recommendations on one card
- **WHEN** the selected pinned model card clearly recommends general thinking, precise coding and non-thinking values
- **THEN** all three appear as separate response recipes with source attribution
- **AND** none becomes an active request default merely because the card was downloaded.

#### Scenario: Create three configurations and select a default
- **WHEN** a user selects all three recipes and chooses General thinking as the default
- **THEN** three distinct named configurations are saved once, copied launch settings remain independent, and the default points to General thinking
- **AND** an unrelated existing configuration remains intact.

#### Scenario: Incompatible thinking template or setup failure
- **WHEN** the selected GGUF cannot verify a recipe's thinking mode, or configuration creation fails after weights install
- **THEN** the mode is not claimed as configured and the installed weights remain available with an actionable setup error.

### Requirement: MOD-031 - Refresh pinned card metadata without downloading weights

An installed Hugging Face bundle SHALL support an explicit response-recipe refresh from its hash-verified saved card or that same repository's immutable revision. Refresh SHALL not download model weights, change saved configurations or defaults, or rewrite live deployment snapshots. Card candidates and effective settings SHALL refresh in the UI without presenting stale values from a previously selected model.

#### Scenario: Refresh an older installation
- **WHEN** an installed revision-pinned bundle has no imported response recipes and the user refreshes its card metadata
- **THEN** any valid pinned-card recipes become available for explicit configuration creation without another weight download
- **AND** its existing configurations, default and deployments remain unchanged.

#### Scenario: Card is unavailable or ambiguous
- **WHEN** the saved card cannot be verified and the pinned card cannot be fetched, or the card has conflicting recipes
- **THEN** no recommendation becomes active or silently changes an existing configuration.

## MODIFIED Requirements

### Requirement: MOD-027 - Expose model controls and clear terminal downloads

The Models workspace SHALL provide My models, Add models and Downloads tabs. My models SHALL use a compact, searchable and keyboard-accessible model and configuration picker above a responsive editor, rather than reserving a full-height sidebar for installed models. Long names and filename-derived Standard, LOW-MTP or MTP variants SHALL remain distinguishable in the picker. Unsaved edits SHALL remain available when switching between models or configurations and SHALL be marked visibly.

The selected model SHALL show common startup, response and thinking controls directly, including context, GPU layers, memory fitting, flash attention, key and value cache precision, supported speculative mode and draft tokens, thinking and supported thinking effort, thinking history, reply limit, temperature, top P, top K, min P, presence penalty, repetition penalty and frequency penalty. Context SHALL support direct numeric entry and an empty control SHALL restore inheritance. GPU layers SHALL offer inherited, Automatic, All, CPU and an exact count. MTP SHALL appear only when supported by inspected metadata. Less common controls, diagnostics, logs and file details SHALL live together in one secondary area.

Controls SHALL make the backend-resolved effective value and source the main readout without storing an inherited value as an explicit override. Known inherited, edited, loaded and unknown values SHALL remain distinguishable; an unknown value SHALL say it was not reported. Binary settings SHALL use accessible round switches. Inherited three-state settings SHALL expose the inherited choice and both explicit states with a keyboard-operable control. A separate Loaded value SHALL appear only for a meaningful difference reported by the running engine. Saving SHALL update the selected model configuration for future Chat, Lab and Workflows turns; startup application SHALL follow managed reload safety. Save changes, Save as configuration and Load or Apply & reload SHALL remain visible.

Discard SHALL safely remove an eligible stopped, failed, interrupted or previously discarded import's owned unreferenced temporary content and clear its terminal job record. It MUST reject active and completed jobs. Shared or installed content SHALL remain protected, and cleanup failure SHALL leave the job actionable. Clearing history MUST NOT claim to free bytes it did not measure.

#### Scenario: Edit and apply model settings
- **WHEN** a person edits a model's response and startup settings, switches to another model, then returns
- **THEN** the unsaved draft remains visible and requested values and inherited effective values are distinguishable
- **AND** saving changes future model use while applying the startup change requires a safe managed reload.

#### Scenario: Known and unknown inherited values
- **WHEN** a model reports a known default for one control but no known value for another
- **THEN** the editor shows the known value with its source and marks the other Not reported
- **AND** neither inherited value is silently saved as an explicit setting.

#### Scenario: Clear an old discarded import
- **WHEN** a previously discarded job shares staging with a completed installation
- **THEN** clearing removes the discarded job record while retaining the shared staging and installed model
- **AND** active and completed jobs cannot be cleared through discard.
