## ADDED Requirements

### Requirement: STATE-016 - Immediate archive and complete chat deletion

Successful archive SHALL immediately remove the conversation from active history and active search while preserving access through archived history. Successful permanent chat deletion SHALL remove chat-owned readable history, drafts, queues, run records, interaction projections and execution checkpoints through their existing owners, including live in-memory read paths. Shared records and independent grants SHALL respect their existing ownership. Project-created files MUST remain unchanged. Destructive confirmation SHALL explain this distinction concisely, and active execution SHALL block deletion until safely stopped.

#### Scenario: Archive without navigation
- **WHEN** the user archives a conversation while viewing or searching active history
- **THEN** it immediately leaves that list without requiring a tab switch and can be reopened from archived history.

#### Scenario: Delete a project chat
- **WHEN** the user confirms deletion of an inactive project chat
- **THEN** its history cannot be fetched through conversation, run or interaction APIs before or after restart, and its project outputs remain byte-for-byte intact.
