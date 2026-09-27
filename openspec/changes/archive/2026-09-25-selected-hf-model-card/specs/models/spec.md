# Spec Delta

## MODIFIED Requirements

### Requirement: MOD-030 - Offer model-card response recipes as explicit configurations

The product SHALL extract only unambiguous, supported response recommendations from a revision-pinned GGUF repository card and record their source repository, revision, card identity and section. Card recommendations SHALL remain separate from verified automatic generation defaults and MUST NOT affect requests until explicitly used in a saved configuration. Valid zero-valued samplers and supported presence and frequency penalties SHALL be retained. An unsupported, invalid or conflicting response recommendation SHALL not be offered as a selectable recipe.

The product SHALL support both explicitly named thinking and non-thinking recipes and a single clearly recommended set of response samplers without a thinking-mode instruction. The latter SHALL preserve the chosen configuration's existing thinking mode. Non-response guidance in the same recommendation section SHALL be clearly identified as not copied into the configuration and remain available in the full card.

During import or on an installed model, a user SHALL be able to select any offered recipes for creation as named model configurations and optionally choose one as the model default. A new configuration SHALL copy the then-current default configuration's requested launch settings, use the selected response recipe while retaining unrelated requested response settings, and remain independent of later default edits. Existing configurations and explicit overrides SHALL not be overwritten. Repeating a selected import or creation action SHALL not duplicate recipe-created configurations. Thinking mode SHALL be applied only when the selected model template supports the relevant toggle. Weight-install success and configuration-creation failure SHALL be reported separately.

#### Scenario: Three recommendations on one card
- **WHEN** the selected pinned model card clearly recommends general thinking, precise coding and non-thinking values
- **THEN** all three appear as separate response recipes with source attribution
- **AND** none becomes an active request default merely because the card was downloaded.

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
