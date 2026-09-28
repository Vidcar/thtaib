## ADDED Requirements

### Requirement: MOD-043 - Keep Models editing stable and contextual

My models SHALL expose one saved-setup selector, explicit default marker and sticky Save, Load/Unload and Check settings actions. Pending edits SHALL label loading as Load saved. Controls SHALL use stable setting/control/value-source rows; ordinary edits, reset availability, background checks and memory recalculation SHALL NOT move subsequent rows by more than one CSS pixel at a fixed viewport. Controls, focus, drafts and scroll position SHALL remain available through checks. Explicit disclosures, panel opening and viewport changes MAY reflow.

The editor SHALL provide one contextual right panel for presets, checked settings, memory, runtime, card and files. The panel SHALL dock only when at least 720 CSS pixels remain for editing, otherwise overlay with keyboard containment, Escape dismissal and trigger focus restoration. Validation SHALL identify the exact candidate, include loading and response failures, and become stale after edits. Runtime details SHALL distinguish engine defaults from setup response settings. Response aliases SHALL have one canonical visible owner; bundle-level template/vision actions SHALL live in model information.

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
- **AND** existing setups are never automatically renamed or deleted.

### Requirement: MOD-044 - Apply and reversibly remove publisher presets

Publisher recommendations SHALL be applied from a contextual preset panel to the current response draft, changing only supplied response fields and explicitly stated Thinking mode. Applying/reapplying SHALL retain loading settings and unrelated response values, mark pending changes visibly and require Save to persist. Recorded ancestry SHALL remain read-only and SHALL NOT be inferred from names. Presets SHALL support persistent Remove from list and Restore presets from model card. Removal SHALL preserve underlying recommendations and saved origins. Restoration SHALL use the installed pinned card, clear hidden choices only after successful refresh, and SHALL NOT recreate deleted setups, overwrite saved configurations, change defaults or download weights.

#### Scenario: Apply non-thinking to an edited setup
- **WHEN** a person previews and applies a Non-thinking preset
- **THEN** the specified response fields and Thinking mode change in the draft, loading/unrelated settings remain intact and Save is required.

#### Scenario: Remove and restore a preset
- **WHEN** a person removes a preset, reopens the application and restores presets from the card
- **THEN** removal persists until restoration and existing saved setups/provenance remain usable throughout.

#### Scenario: Restore fails
- **WHEN** the pinned card cannot be verified or retrieved
- **THEN** the error is actionable and prior presets, visibility and saved setups remain unchanged.
