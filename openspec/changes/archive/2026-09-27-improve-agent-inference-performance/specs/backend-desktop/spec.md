## ADDED Requirements

### Requirement: API-047 - Explain model-call latency and cache reuse

Chat measurement details SHALL expose available prefill duration and first-output delay alongside cached and newly processed input counts, distinguishing them from decoding speed. A bounded call history SHALL retain request identity, purpose and completion status across model/tool boundaries and reopened runs. Measurement history SHALL update at call boundaries without copying or re-rendering the full transcript on every token. Unavailable measurements SHALL be labelled rather than invented.

#### Scenario: Inspect a completed tool continuation
- **WHEN** the next model request starts after a tool and resets current measurements
- **THEN** the previous call's cache and timing evidence remains inspectable and cannot be confused with the current call.

#### Scenario: Timing is unsupported
- **WHEN** an endpoint supplies no valid prefill measurement
- **THEN** Chat identifies prefill as unavailable while preserving whatever usage and generation measurements were actually supplied.
