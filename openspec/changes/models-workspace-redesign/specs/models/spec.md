# Spec Delta

## ADDED Requirements

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
