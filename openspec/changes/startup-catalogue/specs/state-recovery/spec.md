# Spec Delta

## MODIFIED Requirements

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

#### Scenario: Saved turn retains ordered completion without raw token history

- **WHEN** an unfinished turn settles and its terminal display projection is durably published
- **THEN** its finished token deltas MAY be compacted into ordered final message records, retaining tool, nested, lifecycle and partial outcomes, the latest display snapshot and execution checkpoint
- **AND** an active subscriber or prepared reconnect seed MUST NOT lose its visible answer during compaction.

#### Scenario: Catalogue-first token maintenance

- **WHEN** startup maintenance finds a substantial finished interaction log after the first catalogue request
- **THEN** it MAY compact settled message deltas and reclaim freed database space without deleting chats or loading a model
- **AND** archive or removing a project MUST NOT independently delete interaction records.
