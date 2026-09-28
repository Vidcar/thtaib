# Spec Delta

## MODIFIED Requirements

### Requirement: ENV-007 - Expand tools through registered MCP servers

The product SHALL discover and invoke tools from application-registered MCP servers through official `langchain.mcp.MCPAdapter`. It MUST NOT remake an MCP host or replace first-class tools. Selected server ids SHALL be distinct from connected adapters and applied tools. Disabled or omitted servers SHALL leave core Chat running. Missing records, connect or `list_tools` failures, missing stdio runtimes, missing secrets, and name collisions MUST fail closed for that run.

An enabled optional connection with deferred tools MAY remain Needs setup while ordinary chat proceeds. Its schemas and tool execution SHALL fail closed until the selected connection and its frozen allowed tool identities are ready. Discovering a connection MUST NOT widen access or silently accept changed tool identity.

#### Scenario: MCP tools applied

- WHEN a registered MCP server is enabled for Chat
- THEN tools MUST arrive through `MCPAdapter.list_tools` into `create_deep_agent` with namespacing
- AND disabling or omitting the server MUST start no adapter while core Chat still runs.

### Requirement: ENV-029 - Preflight conversation capability groups

Agents setup SHALL expose project files, host shell, browser and Windows control as understandable tool groups with individual choices, together with configured connection/tool dependencies. These choices SHALL be saved with the agent and resolved for new submissions; the composer `+` and Chat agent dropdown SHALL NOT duplicate them. Project file availability SHALL require the bound authorized project; selecting a group MUST NOT grant a broader window, file, network or approval scope. Chat SHALL own access/mode and live Windows target/grants, Browser its session controls and Settings installation/connections. The effective selected tools SHALL remain distinct from browser worker/session availability and live authority. Disabling Browser or Windows control in a saved agent MUST NOT leave a tool selected solely to read its captures. The backend SHALL validate the same effective selection and current authority at setup preview, admission, dispatch and restored/helper execution. A stale/missing window, absent broad grant, unavailable browser worker/session or unsupported mode SHALL yield a specific corrective action before affected tools are presented. Explicit agent requirements SHALL be checked before sending; unconfigured optional When needed features SHALL not block ordinary chat and SHALL pause with a focused setup action only when needed. Saved intention without a current grant MUST NOT be described as ready. Running/queued/paused setups retain their snapshots; future submissions use the latest saved agent.

#### Scenario: Stale selected window
- **WHEN** a conversation remembers Windows control but its selected window is gone
- **THEN** the interface asks for a current window and the backend does not present Windows tools as usable.

#### Scenario: Capability does not widen approval
- **WHEN** a person saves browser or host shell selection in an agent used by an Ask-access chat
- **THEN** applicable tool actions still use the existing approval path and helpers cannot exceed the parent's scope.

#### Scenario: Missing or lost browser worker

- **WHEN** Browser is selected but its worker is absent or its prior session was lost
- **THEN** readiness identifies installation or reset; deferred optional Browser permits ordinary model dispatch and pauses for setup before browser schemas or actions, while explicit agent requirements remain preflight checks.

#### Scenario: Turn Browser off

- **WHEN** Browser is turned off in the selected agent and a new submission is made in a projectless chat without an independent file-reading selection
- **THEN** the next-turn tool selection excludes browser tools and incidental capture reading.

#### Scenario: Cleaner Chat with missing dependencies

- **WHEN** an agent selects a tool whose connection or worker is unavailable
- **THEN** Chat shows a concise corrective route to the owning setup/connection screen without introducing tool toggles or granting access.

## ADDED Requirements

### Requirement: ENV-031 - Resolve deferred setup through existing access and interruption paths

When an enabled optional feature requires setup, the product SHALL pause its saved invocation with typed setup details and a corrective route to the owning screen. Repair SHALL resume the same frozen selection only after readiness and live authorization checks. Changing authorized tools or other frozen authored choices SHALL require a newly accepted input. Cancellation, rejection and restart SHALL preserve confirmed effects and MUST NOT replay uncertain actions. Credentials and live connection objects MUST NOT enter model context or checkpoints.

#### Scenario: Configure and resume
- **WHEN** discovery reaches an enabled unavailable feature
- **THEN** the user sees its specific setup action and ordinary unrelated messages need not configure it
- **AND** successful repair can resume the saved invocation without resending or repeating completed work.

#### Scenario: Deferred tool under Ask and Plan
- **WHEN** a deferred tool becomes ready in Ask or Plan mode
- **THEN** it enters the same approval and backend dispatch checks before exposure and execution
- **AND** discovery or setup cannot authorize effects or broaden selected-window access.

#### Scenario: Setup changes tool identity
- **WHEN** connection repair changes the originally authorized tool identities or schemas incompatibly
- **THEN** execution rejects that mismatch and requires a newly accepted selection
- **AND** it does not silently enlarge the frozen run.
