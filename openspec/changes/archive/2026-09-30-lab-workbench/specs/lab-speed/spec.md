# Spec Delta

## Purpose

Specify Performance, the Lab view that measures prefill and generation speed for one loaded model or for concurrent serving, using the timings of the models that are actually loaded.

## ADDED Requirements

### Requirement: PERF-001 - Measure a single stream

Single stream SHALL measure one loaded model with one request at a time. The person SHALL choose an installed model and one of its saved configurations. The benchmark SHALL load that configuration through the same rules as the Models page, including the saved maximum-loaded-models limit. It MUST NOT load a second copy of those weights to produce the measurement. Prefill and generation speeds SHALL be the speeds that loaded model reports for the request.

#### Scenario: Single stream uses the loaded model

- **WHEN** a person runs Single stream for a saved configuration
- **THEN** the speeds come from that loaded model
- **AND** the benchmark does not start a separate bench process or a second copy of the weights

#### Scenario: Single stream respects the saved limit

- **WHEN** the saved maximum is one and another configuration is already loaded
- **THEN** Single stream waits for or replaces that load under the existing limit
- **AND** it does not raise the saved maximum

### Requirement: PERF-002 - Offer only legal Performance controls

Single stream SHALL expose context size, GPU layers, memory fitting, flash attention, key-cache precision, value-cache precision, speculative decoding, and draft tokens using the same choices the Models page offers for that model. A choice the model cannot accept MUST NOT be offered. Prompt lengths SHALL be switches from that model's legal size ladder. None SHALL start selected. A length past the model's maximum context, or past the context size selected for the benchmark, MUST NOT be offered. Generation length SHALL be a switch of 256, 512, and 1024 tokens and SHALL start at 512. The benchmark SHALL generate that many tokens even when the model would have stopped sooner. The model SHALL stay loaded across prompt lengths in one benchmark and SHALL reload only when a load setting changes.

#### Scenario: Illegal context is not offered

- **WHEN** a model's maximum context is 256 thousand tokens
- **THEN** Performance does not offer a context size or prompt length above that maximum
- **AND** prompt lengths above the context size selected for the benchmark are unavailable

#### Scenario: No prompt length selected

- **WHEN** no prompt length is switched on
- **THEN** the benchmark cannot start
- **AND** the screen says at least one prompt length is required

#### Scenario: Generation length is exact

- **WHEN** generation length is 512 and the model would otherwise stop after a short answer
- **THEN** the reported generation covers 512 generated tokens
- **AND** the generation speed is not taken from that short answer

### Requirement: PERF-003 - Chart prefill and generation as they finish

Performance SHALL show two charts. Prefill SHALL plot tokens per second against prompt length. Generation SHALL plot tokens per second against context length, meaning how full the context was for that measurement, not the configured context size. Each finished prompt length SHALL add its point to both charts immediately. Points SHALL use the prompt length and context length the model reported. When memory fitting changes the configured context size, the benchmark SHALL say so. A later benchmark with different settings SHALL appear as another series. A benchmark that has not finished SHALL show which prompt length is in progress.

#### Scenario: Points appear one length at a time

- **WHEN** prompt lengths of 1024 and 4096 are selected and the 1024 measurement finishes first
- **THEN** both charts show the 1024 point before the 4096 measurement finishes
- **AND** the 4096 point is absent until that measurement finishes

#### Scenario: Reported length wins

- **WHEN** the model reports a different prompt length or context length from the length that was requested
- **THEN** the charts use the reported lengths
- **AND** a context size changed by memory fitting is identified on the benchmark

### Requirement: PERF-004 - Measure concurrent serving

Concurrent serving SHALL let the person select more than one saved configuration, more than one concurrent request on a configuration, or both. Concurrent-request choices SHALL be the choices the Models page already offers. The benchmark MAY load more models than the saved maximum while it is running. Stopping the benchmark or leaving Lab SHALL unload every model loaded above that saved maximum and MUST NOT change the saved maximum. Concurrent serving SHALL use the same prompt-length switches, generation length, and charts as Single stream. Each configuration SHALL be its own series. The speeds SHALL be the speeds reported for those loaded models while the selected requests run together.

#### Scenario: Extra models are temporary

- **WHEN** the saved maximum is two and a concurrent benchmark loads a third configuration
- **THEN** that third configuration is loaded for the benchmark
- **AND** stopping or leaving Lab unloads it and leaves the saved maximum at two

#### Scenario: Concurrent requests share one model

- **WHEN** one configuration is set to four concurrent requests
- **THEN** the benchmark measures prefill and generation while those requests run together
- **AND** the interface calls that control concurrent requests
