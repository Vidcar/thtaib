# Spec Delta

## ADDED Requirements

### Requirement: AGT-025 - Retain correctly owned helper observations

Each named helper call SHALL have a durable parent call identity, frozen helper identity and request, and a child observation scope that cannot be confused with a parallel helper. Its waiting, working, approval, completed, failed, and cancelled states and public messages, tool calls, results, and errors SHALL remain inspectable during execution and after reconnect or reopen. Observation SHALL NOT execute a child twice or expand its permissions. An early failure before child admission SHALL still settle the visible parent call. Historical events that cannot be attributed to one child SHALL NOT be guessed into a transcript.

#### Scenario: Parallel helpers have separate output

- **WHEN** a parent starts two named helper calls that emit overlapping events
- **THEN** each event is visible only under its owning helper, and both remain distinguishable after reopening.

#### Scenario: Admission failure settles delegation

- **WHEN** a helper request fails before its child model is ready
- **THEN** the parent delegation shows the failure rather than remaining indefinitely queued.
