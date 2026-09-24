# Spec Delta

## ADDED Requirements

### Requirement: LAB-015 - Prune excluded project trees during capture

Project and Lab capture SHALL avoid descending into excluded directories. An explicitly empty Lab allowlist SHALL produce an empty file capture. Captured paths SHALL remain within the selected root, and changed files or symlinks that cannot be copied and verified safely SHALL fail capture without publishing a partial snapshot.

#### Scenario: Excluded large tree

- **WHEN** a project contains a large excluded dependency or environment directory
- **THEN** capture does not enumerate that directory's files
- **AND** its included files still restore byte for byte.

#### Scenario: Explicit empty capture and unsafe file

- **WHEN** a Lab capture explicitly selects no files
- **THEN** its file snapshot is empty
- **AND** an unsafe link or changing included file fails a separate capture without publishing partial data.
