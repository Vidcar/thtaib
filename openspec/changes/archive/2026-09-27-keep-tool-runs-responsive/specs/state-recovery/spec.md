## ADDED Requirements

### Requirement: Operational observation excludes diagnostic capture processing
Routine ownership, permission, lifecycle, attention and run observation SHALL read capture-free projections from the existing application records. These reads SHALL neither load captured model history into application objects nor normalize/redact it. An operational projection SHALL be read-only and SHALL NOT be persisted as a complete run or erase saved diagnostics. Diagnostic inspection SHALL remain available separately.

#### Scenario: Substantial retained diagnostic history
- **WHEN** repeated Browser, status and attention reads observe a stored run with at least 50 captures and 10 MB of diagnostic content
- **THEN** those reads SHALL perform zero diagnostic normalization and retain saved diagnostic content unchanged.

### Requirement: Incremental diagnostic privacy enforcement
Persisted captures SHALL carry a fingerprint covering capture content, detector version and configured retention/redaction policy. Unchanged unexpired captures SHALL skip repeated redaction; new or changed content, policy or detector changes and expiry SHALL invalidate that result. Discard/expiry SHALL retain safe provenance. Diagnostic work SHALL NOT hold shared execution locks, and routine publication SHALL exclude captures before copying or serialization.

#### Scenario: Fingerprint invalidation
- **WHEN** captured content, settings or the detector version changes, or a capture expires
- **THEN** the shared privacy policy SHALL be enforced again before diagnostic exposure/persistence
- **AND** unchanged captures SHALL avoid repeated redaction.

#### Scenario: Operational update
- **WHEN** a lifecycle or measurement update is persisted or published
- **THEN** saved diagnostics SHALL survive and no captured request SHALL cross the interaction boundary.
