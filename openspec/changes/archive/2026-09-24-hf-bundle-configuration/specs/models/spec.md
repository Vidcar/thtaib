# Spec Delta

## ADDED Requirements

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
