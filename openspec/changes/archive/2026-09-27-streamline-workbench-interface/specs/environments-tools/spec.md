# Spec Delta

## MODIFIED Requirements

### Requirement: ENV-029 - Preflight conversation capability groups

Agents setup SHALL expose project files, host shell, browser and Windows control as understandable tool groups with individual choices, together with configured connection/tool dependencies. These choices SHALL be saved with the agent and resolved for new submissions; the composer `+` and Chat agent dropdown SHALL NOT duplicate them. Project file availability SHALL require the bound authorized project; selecting a group MUST NOT grant a broader window, file, network or approval scope. Chat SHALL own access/mode and live Windows target/grants, Browser its session controls and Settings installation/connections. The effective selected tools SHALL remain distinct from browser worker/session availability and live authority. Disabling Browser or Windows control in a saved agent MUST NOT leave a tool selected solely to read its captures. The backend SHALL validate the same effective selection and current authority at setup preview, admission, dispatch and restored/helper execution. A stale/missing window, absent broad grant, unavailable browser worker/session or unsupported mode SHALL yield a specific corrective action before affected tools are presented. Saved intention without a current grant MUST NOT be described as ready. Running/queued/paused setups retain their snapshots; future submissions use the latest saved agent.

#### Scenario: Stale selected window
- **WHEN** a conversation remembers Windows control but its selected window is gone
- **THEN** the interface asks for a current window and the backend does not present Windows tools as usable.

#### Scenario: Capability does not widen approval
- **WHEN** a person saves browser or host shell selection in an agent used by an Ask-access chat
- **THEN** applicable tool actions still use the existing approval path and helpers cannot exceed the parent's scope.

#### Scenario: Missing or lost browser worker

- **WHEN** Browser is selected but its worker is absent or its prior session was lost
- **THEN** readiness and Send identify installation or reset before model or browser dispatch, while ordinary Chat remains available.

#### Scenario: Turn Browser off

- **WHEN** Browser is turned off in the selected agent and a new submission is made in a projectless chat without an independent file-reading selection
- **THEN** the next-turn tool selection excludes browser tools and incidental capture reading.

#### Scenario: Cleaner Chat with missing dependencies

- **WHEN** an agent selects a tool whose connection or worker is unavailable
- **THEN** Chat shows a concise corrective route to the owning setup/connection screen without introducing tool toggles or granting access.
