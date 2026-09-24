# Spec Delta

## MODIFIED Requirements

### Requirement: STATE-005 - Version durable knowledge and enforce its write policy

Durable knowledge SHALL preserve user, agent, and project scopes; `memory`, `skill`, and `protected_instruction` kinds; provenance; append-only versions; and reversible edits through new versions. Writes SHALL name an expected base version and report conflicts. Protected instructions SHALL reject agent-origin writes. Skill creation, edit, and import SHALL require valid native `SKILL.md` content with a matching name and nonempty description; the body SHALL be materialized unchanged. A starter template MAY assist creation. Package name collisions SHALL be explicit, and an imported script MUST NOT execute during import. Context-capture retention and redaction SHALL be local configuration and SHALL govern persisted diagnostic copies of model requests.

#### Scenario: Knowledge write policy

- WHEN memory is edited, reverted, concurrently updated, or a protected instruction is overwritten by an agent
- THEN version history, conflict behavior, and protected-instruction rejection MUST be enforced
- AND configured context-retention and redaction behavior MUST be applied.

#### Scenario: Native skill validation

- **WHEN** a person creates, edits or imports a skill package
- **THEN** invalid `SKILL.md` name/description or a name collision is rejected before materialization
- **AND** a valid body is stored unchanged without running bundled scripts or converting freeform notes.

## REMOVED Requirements

### Requirement: STATE-017 - Render file changes from the stored images

**Reason**: Per-edit file images, line counts, diff view, and single-file reverse are retired.

**Migration**: Use current-file inspection through the Files page; project snapshots remain a separate recovery mechanism and do not promise undo.
