# Environments Tools

## Purpose

Specify how agent tools interact with real files, shell, browser, graphical, MCP, interpreter, and creative-job capabilities while preserving declared environments, permissions, approvals, cancellation, and side-effect truth.

MCP, public web search, host shell and visual browser/Windows tools have implementation paths. ComfyUI and speech connections and their user controls remain outstanding in [consolidate-product-contract](../../changes/consolidate-product-contract/tasks.md). Optional adapter requirements do not imply that an adapter is installed or available.

## Requirements

### Requirement: ENV-001 - Execute against the declared real environment

Filesystem tools SHALL target project storage. Shell, browser, and graphical tools SHALL require connected workers or declared adapters. The product SHALL explain execution location, exposed files, installation rights, and isolation. A working directory MUST NOT be described as a security boundary.

#### Scenario: Declared environment action

- WHEN a file is edited, a command runs, and a result is inspected
- THEN displayed paths and access MUST match the actual worker
- AND conversation-state files MUST NOT be substituted for the working project.

### Requirement: ENV-002 - Preserve policy across every invocation path

Autonomy and access SHALL remain separate. Selected permissions and approval rules SHALL be enforced in tools and workers for direct agent tools, workflow adapters, interpreter calls, interactive panels, and any implemented alternative invocation path. No path SHALL gain rights by bypassing visible Chat.

#### Scenario: Equivalent policy

- WHEN the same permitted and prohibited actions are attempted through each implemented path
- THEN outcomes, approvals, and child-run records MUST be equivalent under the same policy.

### Requirement: ENV-003 - Declare recoverability and cancellation truthfully

Adapters SHALL declare reconnect, resume, restart, cancellation, snapshot support, and external side-effect behavior. The product SHALL record unresolved side effects and MUST NOT silently replay work with an unknown outcome.

#### Scenario: Interrupted external job

- WHEN an external job is interrupted around its side-effect boundary and later reconnected or cancelled
- THEN confirmed, failed, and unknown outcomes MUST be distinguished
- AND no blind replay MUST occur.

### Requirement: ENV-004 - Reuse the creative job adapter

The ComfyUI adapter SHALL submit jobs, track progress, retrieve artifacts, and serve both agent tools and LangGraph nodes. The product MUST NOT implement two different job-control paths for the same creative capability.

#### Scenario: Creative job from two entry points

- WHEN a representative creative job is invoked through an agent tool and a LangGraph node
- THEN job ownership, progress, cancellation policy, and artifact references MUST match.

### Requirement: ENV-005 - Host interactive tools without desktop privilege bypass

MCP Apps and other interactive panels SHALL require application host support, sandboxed rendering, and permission-controlled tool messaging. Panels SHALL inherit run context and approvals. Ordinary MCP connectivity MUST NOT be treated as sufficient for interactive app hosting, and unavailable UI MUST preserve standard tool-result fallbacks.

#### Scenario: Panel permission

- WHEN a panel attempts allowed and denied tool actions
- THEN policy MUST be enforced through the inherited run context
- AND the panel MUST NOT obtain privileged desktop access directly.

### Requirement: ENV-006 - Keep interpreter orchestration separate from project shell

The beta Deep Agents interpreter integration SHALL be a separate optional tool-orchestration capability. Each underlying tool call SHALL retain permissions, approvals, cancellation, and child-run logging. Bulk code execution MUST NOT bypass project shell policy.

#### Scenario: Interpreter mixed operations

- WHEN a tool-composition program performs mixed allowed and denied operations and is cancelled
- THEN individual calls MUST remain attributable
- AND project shell policy MUST remain unchanged.

### Requirement: ENV-007 - Expand tools through registered MCP servers

The product SHALL discover and invoke tools from application-registered MCP servers through official `langchain.mcp.MCPAdapter`. It MUST NOT remake an MCP host or replace first-class tools. Selected server ids SHALL be distinct from connected adapters and applied tools. Disabled or omitted servers SHALL leave core Chat running. Missing records, connect or `list_tools` failures, missing stdio runtimes, missing secrets, and name collisions MUST fail closed for that run.

#### Scenario: MCP tools applied

- WHEN a registered MCP server is enabled for Chat
- THEN tools MUST arrive through `MCPAdapter.list_tools` into `create_deep_agent` with namespacing
- AND disabling or omitting the server MUST start no adapter while core Chat still runs.

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

### Requirement: ENV-009 - Route approval classes through one interrupt path

In Ask, every presented host-shell call and protected MCP write/destructive action SHALL pause through the shared interrupt path unless an explicitly saved action/resource grant matches. In Full access, selected enabled tools MAY skip approval; disabled tools and mandatory restrictions remain enforced. Grants SHALL follow AGT-008 and never enable an unselected tool. Host execution MUST NOT be described as sandboxed by its project directory. Typed MCP elicitation SHALL remain a typed response in the ordered interrupt batch, not an approve/reject payload. No command-prefix parser SHALL grant implicit shell approval.

#### Scenario: Read-only and destructive actions

- **WHEN** a read-only shell command or destructive MCP action is attempted in Ask
- **THEN** it pauses under its exact typed interrupt identity unless an explicit matching grant applies.

#### Scenario: Ambiguous read-only prefix

- **WHEN** a shell command begins with a familiar read-only name or includes quoting, expansion or composition
- **THEN** Ask applies the same approval check to the entire command; no prefix parser can authorize it.

### Requirement: ENV-020 - Use native file tools without duplicate mutations

Ordinary Chat SHALL offer Deep Agents built-in `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep` when project file access is selected. `execute` SHALL be offered only when ENV-008 attaches the host shell, and `write_todos` only when planning is selected. The product MUST NOT register another implementation of those tools or custom rename/delete tools. The upstream recursive `delete` and general-purpose `task` MUST NOT be offered in ordinary Chat, including compiled children; named helpers retain their selected invocation path. Application tools that are not file mutations remain `ask_user`, `propose_memory`, `read_attachment`, `echo`, and `time_now`; MCP tools remain supplied by ENV-007.

Selecting project file reading SHALL retain that access when knowledge search is also enabled. The reader description SHALL match its effective access. A reader supplied only for saved tool results, conversation history or retrieved evidence MUST remain restricted to those supplied routes and MUST NOT authorize project or knowledge file access.

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

#### Scenario: Native Unicode search on Windows

- **WHEN** Chat searches valid UTF-8 text containing Unicode characters or Unicode filenames through a project or framework file route on Windows
- **THEN** results SHALL preserve the exact matching text, paths, match limits and truncation status without a locale decoding failure
- **AND** the supported backend entrypoints and desktop shortcut SHALL provide the same behavior without changing host-command encoding or replacing the native tools.

#### Scenario: Project reads alongside knowledge search

- **WHEN** a project-bound Chat selects file reading and knowledge search
- **THEN** valid project files SHALL remain readable through returned virtual paths and project-relative filenames
- **AND** retrieved evidence, saved tool results and conversation history SHALL remain readable through their supplied routes.

#### Scenario: Result-only reader with project file access omitted

- **WHEN** Chat has active tools but has not selected file reading and receives an automatic reader for saved results or retrieved evidence
- **THEN** the reader SHALL permit only the supplied result routes and describe that restriction
- **AND** project and knowledge files, traversal and host-drive paths SHALL remain denied; tools-off SHALL execute no reader.

### Requirement: ENV-023 - Generate an image through a configured ComfyUI

Image generation SHALL call a ComfyUI address the person saved, using a workflow they already created there. The app MUST NOT ship ComfyUI or install its custom nodes. The composer SHALL offer Make an image only when an address is saved. Choosing it asks for the prompt, shows progress, and places the finished image in the reply and in the library. Failure names the address and the reason, and it does not invent an image. Text-only Chat hides the control when no address is saved.

A later image feature uses this same saved address. This contract does not include it, and it does not forbid it.

#### Scenario: Make an image

- **WHEN** a person has saved a ComfyUI address and asks for an image from the composer
- **THEN** progress is visible and the returned image appears in the reply
- **AND** the message is not sent to the language model as a substitute for the image.

#### Scenario: No ComfyUI configured

- **WHEN** no ComfyUI address is saved
- **THEN** the composer does not show a broken image action
- **AND** ordinary text chat is unchanged.

### Requirement: ENV-024 - Dictate and speak through a configured speech endpoint

Dictation and spoken replies SHALL use one OpenAI-compatible speech endpoint the person configures with an address, a model, and a voice. The app MUST NOT ship Whisper, Kokoro, Piper, or a voice model. Example local plugs are whisper.cpp or faster-whisper for dictation, Kokoro for a small natural voice, and Piper when the machine has no spare graphics processor. They are examples, not the only choices.

The settings screen SHALL say when the address is not on this machine. A cloud address is allowed only when the person saved it, and the screen says it is not local. The app MUST NOT send audio to an address the person did not save.

Dictation listens, then inserts editable text into the composer. It MUST NOT send the message. Spoken reply is a button on a finished answer and plays only that answer. Voice cloning, always-on listening, and a phone-call style conversation are not in this contract. A later version of those features uses this same endpoint. The contract does not forbid them.

#### Scenario: Dictate without sending

- **WHEN** a person dictates a sentence
- **THEN** the text lands in the composer for editing
- **AND** the conversation does not gain a user message until they send it.

#### Scenario: Speak one answer

- **WHEN** a person chooses Speak on a finished answer
- **THEN** that answer is spoken through the saved endpoint and voice
- **AND** other answers are not spoken on their own.

#### Scenario: Remote endpoint is labelled

- **WHEN** the saved speech address is not on this machine
- **THEN** the settings screen says it is not local before the person uses it.

### Requirement: ENV-025 - Search the public web through one configured integration

The product SHALL offer one configured public web search and one public page reader. Search snippets and fetched page text stay distinct, and each keeps its address, title, and the time it was read. A documentation connection does not count as this search. When no search is configured, Chat still works offline and the tool is absent rather than failing closed after the model has called it. Secrets for the search stay in the backend.

The activity line for a search uses the same one-line pattern as other tools: the query, not a dump of the page.

#### Scenario: Search then open a page

- **WHEN** web search is configured and the agent searches and then reads one result
- **THEN** the snippet and the page text are separate retained results
- **AND** Chat without that configuration never offers the search tool.

### Requirement: ENV-026 - Keep connection secrets in the backend

Tool connections, including MCP, web search, ComfyUI, and speech, SHALL be one list in Settings. Each row shows the name, the kind, and whether it is ready. The address and options are editable. A secret can be replaced and cleared. It is never shown again after it is saved. Removing a connection asks for confirmation and does not delete chats that used it. A connection that fails to start shows the reason on the row and leaves Chat usable.

#### Scenario: Save a speech secret

- **WHEN** a person saves a speech endpoint with a secret and reopens Settings
- **THEN** the secret field is blank or marked as saved
- **AND** the secret is not present in the desktop's rendered page.

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

### Requirement: ENV-028 - Control only the configured Windows window scope

Work-mode Chat SHALL offer optional Windows window tools with Off, Selected window and All windows access. Selected window SHALL bind calls to an explicitly chosen live window and revalidate its identity. All windows SHALL require an explicit revocable conversation grant. Inspection, interaction and window or element capture SHALL pass through typed tools and the existing approval policy; raw worker command execution MUST NOT become agent authority. Unavailable, elevated or stale targets SHALL fail visibly.

#### Scenario: Selected window remains narrow
- **WHEN** a selected-window Chat requests inspection or input against a different or recycled window handle
- **THEN** the worker refuses the call without interacting with that window.

#### Scenario: Broader access is deliberate
- **WHEN** the person enables All windows for one conversation
- **THEN** its agent can list and target open windows until revocation or restart, while other conversations keep their own narrower access.

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

### Requirement: ENV-030 - Use one owned Chrome context for agents and browser viewing

Selected Browser access SHALL run actual Chrome without a visible operating-system browser window, with a dedicated persistent profile per conversation. Agent tools and the interactive Chat view SHALL use the same pages, tabs and viewport. Start and first browser actions SHALL launch it; close and expiry SHALL stop the owned process tree while retaining sign-ins. Reset SHALL clear the confirmed stopped profile after confirmation. Chrome availability SHALL be checked separately from worker installation. Structural and visual interaction, scrolling, dragging, page dialogs, permitted uploads and retained downloads SHALL use the existing access/effect rules. Unrestricted code, page-defined tools and the ordinary browser profile MUST NOT be exposed.

#### Scenario: Start and resize Chrome
- **WHEN** an authorized agent opens a page and changes its viewport
- **THEN** the live rail shows that same Chrome page and its actual dimensions without opening a desktop browser window
- **AND** rail resizing only changes display scale.

#### Scenario: Browser files remain scoped
- **WHEN** an agent uploads a project file or selected attachment and downloads a page file
- **THEN** the upload is resolved under current file authority and the completed download is retained with source attribution in the existing Library
- **AND** unrelated host files and arbitrary output destinations are refused.

#### Scenario: Page identity changes
- **WHEN** a popup opens, duplicate addresses exist, or a session is reset
- **THEN** the view follows the selected stable page identity and stale input/frames cannot target a different page.

#### Scenario: Lost worker
- **WHEN** the worker fails during an action
- **THEN** its live session is reported lost, the action outcome is preserved without replay, and retained sign-ins are distinct from the lost pages.

### Requirement: Browser observation retains scoped ownership without blocking execution
Browser viewing and action attribution SHALL use current operational ownership and permissions without inspecting diagnostics. Ownership recovery SHALL support agent and user control, invalidate cached ownership on run handoff, and preserve takeover/return rules. Each polling iteration SHALL resolve ownership once; blocking database/file work SHALL stay off HTTP and execution event loops.

#### Scenario: Agent ownership and handoff
- **WHEN** viewing continues across agent control, user takeover/return and a new current run
- **THEN** current ownership and permissions SHALL remain correct without repeated diagnostic normalization or stale control.

#### Scenario: Reconnect, restart and worker loss
- **WHEN** viewing reconnects, the backend restarts, the worker is lost or a run is cancelled
- **THEN** state SHALL remain truthful with no duplicate dispatch or replay of uncertain effects
- **AND** unrelated event delivery SHALL remain responsive.
