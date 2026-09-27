## ADDED Requirements

### Requirement: MOD-033 - Prepare visual capability before dependent inference

An admitted run with screenshot access on an untested vision setup SHALL complete necessary image capability checks before its main model/tool conversation begins. Matching setup evidence SHALL be reused. Check activity SHALL be visible without publishing internal probe output. Failure SHALL preserve text use and truthful visual fallback. Necessary checks SHALL NOT be interleaved with a warm main conversation solely because its first screenshot arrives. Passive status reads SHALL NOT start capability inference or load a model.

#### Scenario: First visual run on an untested setup
- **WHEN** a submitted run enables capture access and its loaded setup has no matching image evidence
- **THEN** checks finish before the first main model request, and the actual retained screenshot uses that evidence without additional capability calls in the tool continuation.

### Requirement: MOD-034 - Preserve prompt and generation timing evidence

For supported timing streams, inference SHALL retain actual cached and newly processed input token counts, reported prefill duration and locally observed time to the first substantive output delta under their request identity and purpose. Missing or invalid measurements SHALL remain unavailable. Completed and interrupted model-call measurements SHALL survive the next request reset in a bounded history. Tool-call stream validation SHALL preserve complete and invalid call behavior without repeatedly accumulating answer or reasoning text solely for validation.

#### Scenario: Prefill precedes fast generation
- **WHEN** a request has a long reported prompt-processing interval and fast subsequent decoding
- **THEN** evidence distinguishes the prefill duration, first-output delay and decode rate rather than presenting decode speed as the whole request's performance.

#### Scenario: Large streamed tool arguments
- **WHEN** a valid large tool argument arrives in many fragments
- **THEN** deltas remain incremental and final validation preserves the complete tool call without repeatedly reparsing its growing arguments.
