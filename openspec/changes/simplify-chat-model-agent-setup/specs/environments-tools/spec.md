# Spec Delta

## ADDED Requirements

### Requirement: ENV-029 - Preflight conversation capability groups

Chat SHALL expose project files, host shell, browser and Windows control as understandable capability groups. Project files SHALL follow the bound project folder without an additional tool list choice. Host shell, browser and Windows control SHALL require explicit enablement for that conversation; enabling a group MUST NOT itself grant a broader window, file, network or approval scope. The backend SHALL validate the same effective group and live authority at setup preview, turn dispatch and restored or helper tool execution. A missing or stale selected window, absent All windows grant, unavailable worker or unsupported mode SHALL yield a specific unavailable reason and a corrective action before affected tools are presented. A saved intention without a current grant MUST NOT be described as ready.

#### Scenario: Stale selected window
- **WHEN** a conversation remembers Windows control but its selected window is gone
- **THEN** the interface asks for a current window and the backend does not present Windows tools as usable.

#### Scenario: Capability does not widen approval
- **WHEN** a person enables browser or host shell under Ask access
- **THEN** applicable tool actions still use the existing approval path and helpers cannot exceed the parent's scope.
