## ADDED Requirements

### Requirement: Browser observation retains scoped ownership without blocking execution
Browser viewing and action attribution SHALL use current operational ownership and permissions without inspecting diagnostics. Ownership recovery SHALL support agent and user control, invalidate cached ownership on run handoff, and preserve takeover/return rules. Each polling iteration SHALL resolve ownership once; blocking database/file work SHALL stay off HTTP and execution event loops.

#### Scenario: Agent ownership and handoff
- **WHEN** viewing continues across agent control, user takeover/return and a new current run
- **THEN** current ownership and permissions SHALL remain correct without repeated diagnostic normalization or stale control.

#### Scenario: Reconnect, restart and worker loss
- **WHEN** viewing reconnects, the backend restarts, the worker is lost or a run is cancelled
- **THEN** state SHALL remain truthful with no duplicate dispatch or replay of uncertain effects
- **AND** unrelated event delivery SHALL remain responsive.
