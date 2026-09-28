## ADDED Requirements

### Requirement: AGT-032 - Preserve omitted capture policy settings

Updates to context-capture policy SHALL merge only fields explicitly provided into the current saved settings under the existing service concurrency boundary. Omitted retention or redaction settings SHALL remain unchanged; an explicitly provided null SHALL retain its supported clearing semantics. Independent Knowledge catalogue, configuration and proposal failures SHALL not make otherwise available editing unusable.

#### Scenario: Change redaction alone
- **WHEN** a person updates capture redaction without specifying retention
- **THEN** the saved retention policy remains unchanged.

#### Scenario: Change or clear retention
- **WHEN** a person updates retention alone or explicitly clears a nullable retention value
- **THEN** redaction remains unchanged and the provided retention change is applied.
