# Spec Delta

## ADDED Requirements

### Requirement: STATE-023 - Retain scoped visual captures and session truth

Successful browser and window captures SHALL use the existing retained asset authority with their source conversation, run, tool, time, target identity, content type, size and hash. The Chat result and Library SHALL refer to the same authorized asset. Raw image bytes MUST NOT be embedded in durable public event streams merely to display a capture. Reset, cancellation and restart SHALL distinguish retained captures from live browser, preview and window access; unacknowledged external actions MUST NOT be replayed.

#### Scenario: Reopen a conversation after restart
- **WHEN** a conversation with a captured screenshot is reopened after its worker session ended
- **THEN** the capture remains available under its access scope, while the browser or window session is shown as closed or lost rather than resumed from a screenshot.
