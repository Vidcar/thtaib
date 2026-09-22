## ADDED Requirements

### Requirement: MOD-020 - Reuse model inspection and expose supported controls

The model manager SHALL persist reusable inspection metadata associated with the current file identity and inspection schema, reusing it across repeated selection and backend restart. Changed or missing files, changed inspection schema and deliberate refresh SHALL invalidate affected evidence. Reusing metadata MUST NOT claim that runtime loading itself requires no weight reads or weaken explicit integrity verification.

Model configuration SHALL expose valid choices derived from the selected model family, metadata and supported runtime, with discoverable speculative decoding controls including supported MTP modes and numeric draft-token controls. Unsupported reasoning effort choices MUST NOT be offered as supported. Unknown capabilities SHALL remain explicit and users SHALL be able to refresh inspection and run relevant capability probes. Requested settings, actual launch settings and observed runtime values SHALL remain distinguishable and easily accessible.

#### Scenario: Repeat selection after restart
- **WHEN** the unchanged model is selected repeatedly and after a backend restart
- **THEN** stored inspection details are reused without reopening weight metadata unnecessarily; an explicit refresh or changed file obtains fresh evidence.

#### Scenario: Family-specific reasoning and MTP
- **WHEN** a model/runtime supports MTP and only particular reasoning controls
- **THEN** the normal configuration surface offers that mode and valid numeric options, hides unsupported effort levels, and displays the resulting applied configuration.

#### Scenario: Probe results
- **WHEN** the user probes a loaded setup
- **THEN** actual passed, failed, unavailable and untested outcomes are shown for that setup without treating metadata guesses as tested capability.
