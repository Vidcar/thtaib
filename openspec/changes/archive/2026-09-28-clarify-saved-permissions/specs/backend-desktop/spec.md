## ADDED Requirements

### Requirement: Chat permission controls explain remembered approvals

The Chat access menu SHALL keep its help icon inline with a named row and explain future-message access and Plan restrictions concisely. Its Saved permissions shortcut SHALL appear only after existing remembered approvals are confirmed, with their presence refreshed on opening. Settings SHALL always offer permission management and explain creating remembered approvals from an Ask-mode action card, their exact action/input/project scope, and revocation. Empty-state copy SHALL NOT imply that Full access pauses for approval or creates saved permissions.

#### Scenario: No remembered approvals

- **WHEN** no remembered approvals exist and the person opens Chat access
- **THEN** the empty shortcut is absent and the help icon shares the Access heading's row
- **AND** Settings explains Allow for this session and Always allow, without promising pauses under Full access.

#### Scenario: Permissions are saved or revoked

- **WHEN** a remembered approval is created or the last one is revoked
- **THEN** reopening Chat access reflects the current presence of saved permissions.

### Requirement: Chat model choices show a compact hierarchy

Chat SHALL present each installed model with a readable model name and visible quantization, with named configurations directly available as indented secondary choices. Full weight filenames SHALL be available through search and tooltips rather than repeated beside configuration names. Small expand arrows SHALL be absent. Distinct installed choices SHALL remain distinguishable, and selection, readiness, compatibility, loading and keyboard navigation SHALL retain their existing guarantees.

#### Scenario: Choosing a named configuration

- **WHEN** Chat's model picker opens for a model with several configurations
- **THEN** the model name and quantization head a group of immediately available named settings
- **AND** choosing a setting uses its exact saved configuration without displaying a repeated weight filename.

#### Scenario: Searching by the original filename

- **WHEN** the person searches for an installed model's original weight filename
- **THEN** the correct compact model group remains discoverable and selectable.
