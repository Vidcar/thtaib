# Spec Delta

## MODIFIED Requirements

### Requirement: STATE-018 - Archive immediately and delete a chat without its project files

Archiving a conversation SHALL remove it from the active list and from active search at once. It remains available under archived conversations and can be reopened. Permanently deleting a chat SHALL remove that chat's history, drafts, queue, and its own run records after confirmation. The confirmation says project files and model files stay. Project files MUST remain byte for byte. Deletion waits until that chat's own work has stopped. Shared records another conversation still needs are kept, and the confirmation says so when that is the case.

#### Scenario: Archive from the active list

- **WHEN** a person archives the conversation they are reading
- **THEN** it leaves the active list immediately
- **AND** they can reopen it from archived conversations.

#### Scenario: Delete a project chat

- **WHEN** a person confirms deletion of a chat whose project contains files the agent wrote
- **THEN** the chat history is gone
- **AND** those project files are still in the project folder.

### Requirement: STATE-019 - Import a skill package without running it

A skill SHALL be importable as one native `SKILL.md` file or as a folder or archive that contains `SKILL.md` plus relative scripts, references, and assets. The entrypoint MUST have valid skill frontmatter, a lowercase name, and a nonempty description; it SHALL materialize under a skill folder matching that name. Name collisions SHALL be reported rather than silently replacing a skill. The import SHALL reject path traversal, links that escape the package, and Windows reserved names. Imported scripts MUST NOT run as part of import. The Knowledge screen lists the skill by name, shows the files it contains, and lets the person select or clear it for a later conversation. Selecting it uses the official skills path on the next new user turn, including after an edit or deselection. It does not execute the package or convert freeform notes into a skill.

#### Scenario: Import does not execute

- **WHEN** a person imports a skill package that contains a script
- **THEN** the skill appears in the list with its files
- **AND** the script has not been run.

#### Scenario: Invalid or conflicting package

- **WHEN** an imported skill has invalid `SKILL.md` frontmatter or an existing skill name
- **THEN** import fails with the reason and no existing skill body is overwritten.

### Requirement: STATE-020 - Extract supported documents without a source-inspection journey

A retained text, code, CSV, JSON, text-bearing PDF, or DOCX file SHALL be extractable locally. The result keeps the parser outcome: read, empty, encrypted, malformed, or unsupported. A scanned document without optical character recognition MUST NOT be described as understood. Extraction does not add a screen for inspecting a quote's source location. That journey stays out of this contract. The file itself remains openable in the Files dock when it is text or an image the dock already shows.

#### Scenario: Encrypted PDF

- **WHEN** a retained PDF is encrypted
- **THEN** the extraction says it could not be read
- **AND** the product does not present invented document text.
