## MODIFIED Requirements

### Requirement: MOD-027 - Expose model controls and clear terminal downloads

The Models workspace SHALL provide My models, Add models and Downloads tabs. My models SHALL use a compact, searchable and keyboard-accessible model and configuration picker above a responsive editor, rather than reserving a full-height sidebar for installed models. Long names SHALL remain available in full in the picker. Unsaved edits SHALL remain available when switching between models or configurations and SHALL be marked visibly.

The selected model SHALL show common startup, response and thinking controls directly, including context, GPU layers, memory fitting, flash attention, key and value cache precision, supported speculative mode and draft tokens, thinking and supported thinking effort, thinking history, reply limit, temperature, top P, top K, min P, presence penalty, repetition penalty and frequency penalty. Context SHALL support direct numeric entry and an empty value SHALL restore Automatic. GPU layers SHALL offer Automatic, All, CPU and an exact count. MTP SHALL appear only when supported by inspected metadata. Less common controls, diagnostics, logs and file details SHALL live together in one secondary area.

Controls SHALL show effective value and source beside the label without repeated default rows or separate default buttons for binary settings. Binary settings SHALL use accessible round switches. Inherited three-state settings SHALL expose Default and both explicit states with a keyboard-operable control. A separate Loaded value SHALL appear only for a meaningful difference reported by the running engine. Unknown defaults SHALL remain unknown. Saving SHALL update the selected model configuration for future Chat, Lab and Workflows turns; startup application SHALL follow managed reload safety. Save changes, Save as variant and Load or Apply & reload SHALL remain visible.

Discard SHALL safely remove an eligible stopped, failed, interrupted or previously discarded import's owned unreferenced temporary content and clear its terminal job record. It MUST reject active and completed jobs. Shared or installed content SHALL remain protected, and cleanup failure SHALL leave the job actionable. Clearing history MUST NOT claim to free bytes it did not measure.

#### Scenario: Edit and apply model settings
- **WHEN** a person edits a model's response and startup settings, switches to another model, then returns
- **THEN** the unsaved draft remains visible and requested values and inherited defaults are distinguishable
- **AND** saving changes future model use while applying the startup change requires a safe managed reload.

#### Scenario: Clear an old discarded import
- **WHEN** a previously discarded job shares staging with a completed installation
- **THEN** clearing removes the discarded job record while retaining the shared staging and installed model
- **AND** active and completed jobs cannot be cleared through discard.

## ADDED Requirements

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
