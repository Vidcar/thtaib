# Environments Tools

## Purpose

Specify how agent tools interact with real files, shell, browser, graphical, MCP, interpreter, and creative-job capabilities while preserving declared environments, permissions, approvals, cancellation, and side-effect truth.

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

The first worker environment SHALL be the Windows host shell through Deep Agents `LocalShellBackend`, approvals, and `interrupt_on`. The host shell SHALL attach only when a project is bound and `execute` is presented. Project-bound runs without `execute` SHALL use filesystem-only backend behavior. A project-free request for project file or shell tools SHALL fail with an actionable error, not invent a home-directory cwd.

#### Scenario: Shell availability

- WHEN a project-free Chat requests shell access
- THEN `execute` MUST be absent or rejected with a project-required error
- AND when a project-bound run does not present `execute`, no live host shell MUST be attached.

### Requirement: ENV-009 - Route approval classes through one interrupt path

Automatic host-shell allowance SHALL be limited to the configured small read-only prefix set without shell metacharacters, or an explicitly saved matching action/resource grant. Other protected shell and MCP write/destructive actions SHALL pause through the shared interrupt path and record approval class. Grants SHALL follow AGT-008 and never enable an unselected tool or weaken mandatory restrictions. Host execution MUST NOT be described as sandboxed by its project directory. MCP elicitation SHALL remain a distinct typed input/resume operation, not an approve/reject command payload.

The read-only policy SHALL preserve validation against the actual `LocalShellBackend` shell execution semantics. A matching command prefix alone is insufficient: quoted, expanded, compound, redirected, unknown-option and ambiguous forms MUST NOT inherit automatic read-only approval. An explicit grant must match the actual action/resource under AGT-008 rather than reuse a misleading prefix parse.

#### Scenario: Read-only and destructive actions

- **WHEN** read-only shell and destructive MCP actions are attempted
- **THEN** only actions permitted by the current read-only policy or explicit matching grant proceed; other protected calls pause under their own typed interrupt identity.

#### Scenario: Ambiguous read-only prefix

- **WHEN** a command begins with a read-only name but includes quoting, expansion, an unrecognised option or shell composition
- **THEN** it requires approval unless an explicit valid grant matches the actual action and resource; prefix matching does not bypass the existing shell safeguards.

### Requirement: ENV-020 - Offer built-in file tools and only two custom file mutations

Ordinary Chat's file tools SHALL be the Deep Agents built-ins `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep`. `execute` SHALL be offered only when ENV-008 attaches the host shell. `write_todos` SHALL be offered only when planning is selected. The only custom file mutations SHALL be `rename_file`, which renames one regular file without overwriting a destination, and `delete_file`, which deletes one regular file. The product MUST NOT register a second copy of the built-in filesystem tools.

The upstream recursive `delete` tool and the general-purpose `task` tool MUST NOT be offered in ordinary Chat. Extra tools passed into the harness are additive and MUST NOT be treated as removing a built-in. Removal SHALL use the upstream exclusion or the filesystem middleware tool list, including for a compiled child. Application tools that are not file mutations remain `ask_user`, `propose_memory`, `read_attachment`, `echo`, and `time_now`. MCP tools remain those supplied by ENV-007.

#### Scenario: Model sees one delete

- **WHEN** ordinary Chat with a project presents file tools
- **THEN** `delete_file` is the delete the model can call
- **AND** the recursive `delete` tool and `task` are not offered, including to a child.

#### Scenario: No second reader

- **WHEN** the harness is assembled for a project
- **THEN** `read_file`, `write_file`, `edit_file`, `ls`, `glob`, and `grep` are the built-in tools
- **AND** the application does not register another tool of the same name.

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
