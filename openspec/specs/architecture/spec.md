# Architecture

## Purpose

Define the Local AI Workbench ownership boundaries: one local backend coordinates records and execution, one desktop presents and edits, upstream engines own inference and agent/workflow loops, and shared records keep Models, Chat, Lab, and Workflows aligned.

## Requirements

### Requirement: ARCH-001 - One modular backend

The application SHALL keep coordination responsibilities in one Python FastAPI backend bound to loopback. The desktop SHALL edit definitions and call the backend for execution. The backend MAY manage external child processes such as `llama-server`; Docker Compose MAY manage container services, but it MUST NOT become a competing application job scheduler.

#### Scenario: Desktop action reaches backend execution

- WHEN the desktop starts a task or workflow action
- THEN the action MUST route through the backend-owned execution path
- AND any external process split MUST remain separately managed and recorded as a reviewed decision.

### Requirement: ARCH-002 - One owner for execution

The application SHALL use llama.cpp for supported inference, Deep Agents for each agent loop, LangGraph for runtime checkpoints and outer workflows, and LangChain for model, message, tool and frontend interaction interfaces. Generic frontend message assembly, tool-call presentation state, subscriptions, interrupt projections and scoped selectors SHALL use compatible upstream interaction libraries. The application MUST own model installation/loading/settings, effective configuration, project/session identity, permissions, resource admission, durable application records, confirmed outcomes, retained files and local evaluation. Frontend projections MUST NOT become execution, authorization, scheduling or checkpoint authority. The application MUST NOT implement a second model/tool loop or workflow runtime.

The text editor and file-tree widget SHALL be loaded presentation libraries. They are not execution engines. The application owns the dock and the records those views read. It MUST NOT implement its own syntax highlighter, file-tree widget, agent loop, checkpointer, or MCP host.

#### Scenario: Execution owner trace

- WHEN a model call, tool execution, and workflow step are traced
- THEN each MUST reach its designated upstream owner
- AND a second application-written agent loop MUST be rejected.

#### Scenario: Multiple observers

- WHEN multiple frontend selectors or subscriptions observe one thread
- THEN they MUST observe the same backend-owned run without another graph invocation
- AND their loading or disconnected state MUST NOT establish a durable run outcome.

#### Scenario: Review uses the loaded editor

- **WHEN** a person reads a permitted project file in the dock
- **THEN** the loaded editor shows the live file's text
- **AND** opening that view MUST NOT call the model or create another file authority.

### Requirement: ARCH-003 - Shared records across surfaces

Models, Lab, Chat, and Workflows SHALL share configurations, deployments, runs, artifacts, and effective setup records. A surface MUST NOT substitute a hidden profile or report equivalence solely from a shared profile name. Selected values MUST remain distinct from loaded and applied values.

#### Scenario: Profile carried between surfaces

- WHEN a profile is used from more than one surface
- THEN the deployment, environment, and applied settings MUST be comparable from recorded state
- AND visible differences MUST be reported rather than hidden.

### Requirement: ARCH-004 - Expose capability without pretending certainty

The product SHALL simplify guidance without silently removing supported model or agent capabilities. Unknown and unverified model capabilities SHALL remain usable and distinguishable from known incompatibility. Testing SHOULD inform use, but MUST NOT be a prerequisite to using a model.

#### Scenario: Compatibility states

- WHEN known-compatible, known-incompatible, and unverified configurations are inspected
- THEN supported advanced controls MUST remain available
- AND unsupported, overridden, or unverified settings MUST be explained.

### Requirement: ARCH-005 - One access and event model

All invocation paths SHALL share the selected access policy and common run hierarchy. Permissions and approvals MUST be enforced in tools and workers, not solely in prompts. Autonomy and access SHALL remain independent choices.

#### Scenario: Same action through multiple paths

- WHEN an action is attempted through an agent tool, workflow adapter, and another enabled invocation path
- THEN approval behavior and parent/child run attribution MUST be equivalent for the same policy.

### Requirement: ARCH-006 - Extend through the registry

New supported integrations SHALL register definitions, capabilities, configuration, execution behavior, and presentation integration with the application-owned versioned registry. React Flow, LangChain, and LangGraph SHALL consume that registry; none SHALL define an independent integration authority.

#### Scenario: Representative adapter registration

- WHEN a representative adapter is introduced
- THEN presentation, validation, and execution MUST consume the registry definition
- AND no alternative integration authority MAY be introduced.

### Requirement: ARCH-007 - Optional extensions stay optional

Optional extensions, including background consolidation, beta rubric or interpreter integrations, MCP Apps, voice, ordinary MCP server connectivity, and other future adapters, SHALL extend the same contracts. They MUST NOT become prerequisites for the core local model and agent experience. MCP SHALL be optional extra tools, not the default tool bus.

#### Scenario: Core path without extensions

- WHEN optional extensions are disabled or absent
- THEN core inference and agent runs MUST still start
- AND unavailable optional capabilities MUST be reported without failing core startup.

### Requirement: ARCH-008 - Resolve one effective setup before runs

Before Chat, Lab restore or rerun, Agent-run, or workflow execution starts, the backend SHALL resolve deployment, startup settings, per-request settings, agent settings, enabled tools and policy, selected knowledge, skill and protected-instruction versions, and selected MCP server slugs. Missing, unknown, or incompatible references MUST fail closed. Startup, per-request, and agent settings SHALL remain separate bags; values MUST NOT be moved between bags.

#### Scenario: Run-start validation

- WHEN a stored definition names settings, tools, knowledge, and deployment references
- THEN the backend MUST resolve and validate them immediately before execution
- AND the run record, inspector, and captured request MUST agree on selected, loaded, applied, unsupported, overridden, and unverified facts.

#### Scenario: Same setting displayed and dispatched
- **WHEN** Models, Agents, project/application defaults, Chat, Lab or Workflows display a setting
- **THEN** its effective value, named source, known default, support and reload state come from the shared backend resolution used at dispatch
- **AND** presentation does not implement another inheritance authority.

### Requirement: ARCH-009 - Preserve local persistence boundaries

Product data SHALL live under the configured product data root, with files for weights, runtimes, project workspaces, knowledge bodies, snapshots, artifacts, and logs. New mutable application records SHALL use `application.sqlite`; LangGraph checkpoints SHALL remain in `checkpoints.sqlite`; the application SHALL store checkpoint identifiers and MUST NOT read or write checkpointer tables directly.

#### Scenario: Persisted run after restart

- WHEN the backend restarts and follows a persisted run
- THEN application records MUST locate related files and checkpoint identifiers
- AND checkpoint bytes MUST remain owned by the LangGraph checkpointer.

### Requirement: ARCH-010 - Protect same-machine trust

Privileged `/v1` routes SHALL require the shared secret header. Missing tokens MUST return 401 and wrong tokens MUST return 403. `GET /health` MAY be public. CORS MUST NOT be treated as authorization, and unsupported remote backend access MUST NOT be enabled silently.

Desktop-granted backend authorization SHALL be restricted to the verified application requesting document/frame and owning WebContents at the exact loopback destination. Same-session untrusted content SHALL NOT inherit that authority. Electron main SHALL own validated HTTP(S) external-link opening and denial of untrusted windows/navigation, including redirects, while keeping sandboxing, context isolation and CSP intact.

#### Scenario: Privileged request authentication

- WHEN `/v1` is called without the header or with the wrong token
- THEN the backend MUST reject it with the corresponding authentication failure
- AND the renderer MUST NOT receive or store the shared secret.

#### Scenario: Desktop document replacement

- WHEN untrusted content attempts to open within or replace a trusted desktop document
- THEN navigation/window policy MUST deny it and backend credential injection MUST independently reject untrusted requesting frames
- AND an allowed window ID or null origin alone MUST NOT authorize backend access.

### Requirement: ARCH-011 - Leave a door for a later feature

A capability this contract does not include SHALL be described as not in this contract. It MUST NOT be described as forbidden unless it would break a safety rule, such as running arbitrary code from an imported graph or sending audio to an unsaved address. A later image, voice, schedule, evaluation, or helper feature SHALL extend the existing endpoint, workflow step, Lab catalogue, or saved agent. It MUST NOT add a second agent loop, a second workflow engine, or a second media store.

#### Scenario: Voice cloning is later

- **WHEN** a later change adds voice cloning
- **THEN** it uses the saved speech endpoint or another application the person configures
- **AND** the current dictation and spoken-reply controls remain the way speech is used until that change exists.
