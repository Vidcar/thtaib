# Spec Delta

## ADDED Requirements

### Requirement: STATE-021 - Finalize runs and snapshots safely

Execution settlement SHALL be persisted before project capture, and restart recovery SHALL use that settlement without rerunning model or tool effects. Project capture SHALL run without holding the harness-wide lock, stage and verify its files before publishing a snapshot, and remove only incomplete owned staging after a failure. Capture failure SHALL leave the execution outcome intact and identify branching as unavailable. Final branch snapshots SHALL include safe project files created by the run.

#### Scenario: Concurrent run during capture

- **WHEN** one run is saving a large project snapshot while another run makes progress
- **THEN** the second run's observation and execution can progress
- **AND** the first run publishes one terminal outcome after capture settles.

#### Scenario: Restart or capture failure

- **WHEN** the application restarts or capture fails after execution settles
- **THEN** finalization uses the saved outcome without replaying effects
- **AND** a failed capture has no published partial snapshot and reports branching unavailable.

### Requirement: STATE-022 - Keep long interaction histories responsive

Routine live polling and append SHALL use durable scalar cursor and display-cutover metadata rather than decoding the full transcript. Replay and recovery work SHALL not block the HTTP event loop. In-progress message reconstruction SHALL happen once per subscriber join and then advance incrementally. Checkpoint linkage SHALL visit bounded history pages and stop at the saved prior boundary. While a run is active, its raw ordered interaction events SHALL remain available; after completion, token deltas MAY be compacted into ordered final message replay while retaining tool, lifecycle, and namespace identities. Only deliberate compaction gaps SHALL trigger a bridge.

#### Scenario: Long conversation with a late subscriber

- **WHEN** a long conversation is live and a subscriber joins for tool or nested detail
- **THEN** it receives available ordered matching activity without a full transcript decode on every poll
- **AND** unrelated event-loop work remains responsive.

#### Scenario: Completed replay after compaction

- **WHEN** a completed run's token deltas have been compacted
- **THEN** final message replay remains ordered with retained tool, lifecycle and namespace events
- **AND** a missing legacy detail is reported as unavailable.
