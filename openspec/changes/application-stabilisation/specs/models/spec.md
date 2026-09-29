## MODIFIED Requirements

### Requirement: MOD-037 - Preview the selected model candidate faithfully

Models readouts SHALL resolve the selected model, configuration and unsaved draft through the existing model-capable resolver boundary. Application-default editing SHALL remain access-only. Chat context preview and Apply this chat's settings SHALL use the same candidate, including removed overrides, and default labels SHALL use the correct parent/model value and source. Editing SHALL remain available during validation, while Apply this chat's settings SHALL require the latest matching valid result. Readiness SHALL use the resolver's exact selected live configuration identity and distinguish quantization/configuration labels.

#### Scenario: Preview advanced startup edits
- **WHEN** the selected configuration requests All GPU layers, memory fitting Off and q4_0 key precision, then edits and resets them
- **THEN** requested and effective readouts agree with the real resolver for that candidate and the reset target value is correct.

#### Scenario: Preview completes out of order
- **WHEN** typing changes the candidate while an earlier check completes
- **THEN** editing stays uninterrupted and that earlier result cannot enable Apply this chat's settings for the newer candidate.

#### Scenario: Saved setup changes while Chat stays mounted
- **WHEN** a selected saved configuration gains a new revision while Chat remains mounted
- **THEN** its readiness, Thinking and context preview SHALL be reverified for that revision without passively loading a model
- **AND** explicitly selecting the changed saved startup SHALL apply that exact selection rather than treat an older running configuration as current.

#### Scenario: Model and agent preparation share setup ownership
- **WHEN** an explicit model or main-agent choice is still preparing its resolved setup
- **THEN** shared setup controls SHALL remain visibly busy until that owned action settles, so a competing choice cannot be silently discarded by its later callback
- **AND** disposal or replacement of the selection owner SHALL release its UI gate without allowing obsolete completion to overwrite the replacement.

### Requirement: MOD-043 - Keep Models editing stable and contextual

My models SHALL expose a saved-setup selector only when multiple setups exist, one Model card entry point, and compact Save, Load or Load saved, plus Reload only when a managed deployment exists for the selected setup. Load and Load saved SHALL post the saved profile to managed start with an empty startup object and SHALL ignore unsaved edits. Reload SHALL be the only control labelled Reload and SHALL post `POST /v1/deployments/{id}/reload` for that same record. Load snapshot SHALL remain the start of a stopped record. Metadata/files/refresh/setup management and optional native checking SHALL live in contextual details. Generation/Sampling and Loading/Memory SHALL form two compact columns when at least 840 CSS pixels are available, stacking below that width. Common controls SHALL remain immediately visible and show resolved values without repeated Saved/default/provenance paragraphs. Pending startup changes SHALL require explicit loading. Controls SHALL use stable compact geometry; ordinary edits, reset availability, background checks and memory recalculation SHALL NOT move subsequent rows by more than one CSS pixel at a fixed viewport. Controls, focus, drafts and scroll position SHALL remain available through checks. Explicit disclosures, panel opening and viewport changes MAY reflow.

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
