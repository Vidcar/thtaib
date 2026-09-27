# Spec Delta

## MODIFIED Requirements

### Requirement: MOD-016 - Produce validated structured results through the same agent

Runs SHALL support an optional versioned output schema using the existing agent constructor, retaining actual structured results, schema/strategy identity and validation status separately from display text and artifacts. Native versus tool-based strategy SHALL depend on verified setup capability and tool policy. Tools-off SHALL send no synthetic formatting tools; unsupported native formatting under tools-off SHALL be actionable unavailable. Formatting tools grant no other execution authority. Combined executable tools plus structured output require separate support evidence.

Validate fields/types and distinguish missing/invalid results from schema-permitted empty values. Invalid structured output SHALL fail clearly with its validation reason and MUST NOT trigger an extra formatting or effectful tool turn. JSON-looking answer text alone is not the structured result, and schema validity is not factual correctness.

#### Scenario: Tools-off formatting

- **WHEN** structured output is selected while tools are explicitly off
- **THEN** supported native formatting runs without tools, or the combination is reported unavailable.

#### Scenario: Invalid result

- **WHEN** formatting fails after a task action
- **THEN** the run fails with inspectable structured validation, without repeating the action or starting a formatting-repair turn.
