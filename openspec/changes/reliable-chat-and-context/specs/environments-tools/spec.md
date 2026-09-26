## MODIFIED Requirements

### Requirement: ENV-008 - Attach host shell only when execute is presented

The first worker environment SHALL be the Windows host shell through Deep Agents `LocalShellBackend`, approvals, and `interrupt_on`. The host shell SHALL attach only when a project is bound and `execute` is presented. Project-bound runs without `execute` SHALL use filesystem-only backend behavior. A project-free request for project file or shell tools SHALL fail with an actionable error, not invent a home-directory cwd. Application lifecycle adapters SHALL own Windows shell descendants through command exit, cancellation and timeout without replacing the native tool or harness. A settled shell result SHALL mean that its process tree has stopped; unconfirmed termination SHALL retain uncertain-effect recovery and project ownership. Long-running web servers SHALL use selected owned preview capabilities.

#### Scenario: Shell availability

- **WHEN** a project-free Chat requests shell access
- **THEN** `execute` MUST be absent or rejected with a project-required error
- **AND** when a project-bound run does not present `execute`, no live host shell MUST be attached.

#### Scenario: A shell command spawns a detached child

- **WHEN** the command exits, reaches its timeout or is cancelled
- **THEN** the application SHALL stop and confirm the whole owned process tree before reporting a settled result or releasing the project
- **AND** ordinary nonzero command exits SHALL remain tool failures; timeout or cancellation (native exit codes 124 or 130) and unconfirmed termination SHALL remain uncertain effects, even when process termination is confirmed, because partial file or external changes are not thereby established.
- **AND** an uncertain command SHALL prevent further model/tool dispatch and project admission until inspection and explicit acknowledgement, without replaying it; already dispatched siblings SHALL settle and retain their results.

### Requirement: ENV-020 - Use native file tools without duplicate mutations

Ordinary Chat SHALL offer Deep Agents built-in `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep` when project file access is selected. `execute` SHALL be offered only when ENV-008 attaches the host shell, and `write_todos` only when planning is selected. The product MUST NOT register another implementation of those tools or custom rename/delete tools. The upstream recursive `delete` and general-purpose `task` MUST NOT be offered in ordinary Chat, including compiled children; named helpers retain their selected invocation path. Application tools that are not file mutations remain `ask_user`, `propose_memory`, `read_attachment`, `echo`, and `time_now`; MCP tools remain supplied by ENV-007.

#### Scenario: No custom file deletion

- **WHEN** ordinary Chat presents project file tools
- **THEN** native read/write/edit/list/search are available as selected while custom rename/delete and recursive `delete` are absent.

#### Scenario: Concurrent same-file edits

- **WHEN** one assistant response requests simultaneous edits to the same path
- **THEN** the built-in guard rejects the conflict before two writes can race.

#### Scenario: No second reader

- **WHEN** the harness is assembled for a project
- **THEN** the file tools are Deep Agents built-ins and the application registers no second tool with their names.

#### Scenario: Parallel creation of a missing Windows directory
- **WHEN** native tools concurrently write distinct files under a new shared directory
- **THEN** equivalent Windows path representations SHALL not cause false escape errors, and each call SHALL retain its own success or error result
- **AND** genuine traversal, junction escape and same-file conflicts SHALL remain rejected.

### Requirement: ENV-027 - Test web pages in an owned browser

Work-mode Chat with or without a project SHALL offer an optional, separately authorized browser through the registered tool integration. The browser SHALL use an isolated conversation session, expose page structure and bounded screenshots, and keep its state across turns until reset, close, expiry or worker loss. It SHALL permit local development URLs without changing the public page reader's private-address policy. The application SHALL report the browser's actual destination, access and session loss; it MUST NOT expose unrestricted worker code, page-defined tools, arbitrary capture paths or the person's ordinary browser profile through this capability. A project-bound preview process SHALL have owned start, health, logs and stop behavior under the existing Ask/Full access and exact-input permission policy. Selecting preview SHALL NOT implicitly enable host shell or browser access.

#### Scenario: Test a local page over several turns
- **WHEN** an authorized project Chat starts a preview and opens its local URL, then continues in another turn
- **THEN** the same browser session can inspect, interact and capture the page while the preview owner and destination remain visible.

#### Scenario: Browser worker is absent or lost
- **WHEN** the optional worker is unavailable or its process exits
- **THEN** ordinary Chat remains usable, the session reports unavailable or lost, and no browser action is silently replayed.

#### Scenario: Open generated local HTML
- **WHEN** an authorized project task opens a local HTML entry
- **THEN** the owned preview SHALL provide an HTTP loopback URL with visible Open, Stop and status controls
- **AND** an invalid browser address or expected preview error SHALL return a correctable tool error without terminating unrelated Chat work.

#### Scenario: Confined static entry and complete stop
- **WHEN** static preview is started for an existing project-relative HTML entry
- **THEN** its exact encoded loopback URL SHALL serve relative assets without directory listings or link escapes, and health SHALL identify the owned worker
- **AND** Stop SHALL wait for every owned Windows process to finish and release inherited log handles, including children of a launcher.

Model-facing descriptions SHALL accurately state allowed URL schemes, project-relative file paths and the actual host shell environment; they MUST NOT describe host execution as sandboxed.
