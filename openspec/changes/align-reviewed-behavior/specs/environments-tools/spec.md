# Spec Delta

## MODIFIED Requirements

### Requirement: ENV-008 - Attach host shell only when execute is presented

This computer SHALL be the host command shell: run command, start job, stop job, and job status. These SHALL remain the existing host-shell and managed-command operations. The product MUST NOT add another shell. The shell is the Windows account that launched the app, not a project sandbox. The first worker environment SHALL be the Windows host shell through Deep Agents `LocalShellBackend`, approvals, and `interrupt_on`. The host shell SHALL attach only when `execute` is presented. It SHALL NOT require a bound project. A project-bound run that does not present `execute` SHALL use filesystem-only backend behavior.

When the chat has a project, commands SHALL start in that project folder. When it does not, commands SHALL start in the Windows user profile of the account that launched the app. The starting path SHALL be shown on the first confirmation and on every command the person reviews. That path is not a fence. A command MAY leave the folder. The catalogue text MUST say Windows-account authority and MUST NOT say the shell is sandboxed in the project folder. Standard agents SHALL leave This computer off.

File tools, preview, and skill scripts SHALL still fail without a project. Preview SHALL NOT turn the shell on. Skill scripts SHALL require This computer and a bound project. Unpinned `glob` and `grep` SHALL be omitted until a project is bound and SHALL NOT fail merely because definitions load eagerly. Unpinned `ls` and `read_file` follow that admission rule, except a selected knowledge or capture route may keep them for its virtual paths only. A project-free request for project preview, pinned project reads, or eager file mutations SHALL fail with an actionable error and SHALL NOT invent a project. Application lifecycle adapters SHALL own Windows shell descendants through command exit, cancellation and timeout without replacing the native tool or harness. A settled shell result SHALL mean that its process tree has stopped; unconfirmed termination SHALL retain uncertain-effect recovery. Long-running web servers SHALL use selected owned preview capabilities. Owning a shell process tree MUST NOT lock the project folder against another chat or helper.

#### Scenario: Shell availability

- **WHEN** a chat presents `execute` and runs a command
- **THEN** a project chat MUST start in the bound project folder, and a chat without a project MUST start in the Windows user profile of the account that launched the app
- **AND** the starting path MUST be shown on the first confirmation and on every command the person reviews
- **AND** the command MAY leave that folder
- **AND** the catalogue text MUST say Windows-account authority and MUST NOT say the shell is sandboxed in the project folder.

#### Scenario: Eager definitions do not require optional project reads

- **WHEN** a project-free selection includes unpinned project reads and definitions load eagerly
- **THEN** `glob` and `grep` are omitted and the run can continue
- **AND** `ls` and `read_file` are omitted unless a selected knowledge or capture route keeps them as virtual readers
- **AND** pinned reads, eager file mutations, and preview MUST still fail
- **AND** a presented host shell MUST NOT fail for lack of a project.

#### Scenario: A shell command spawns a detached child

- **WHEN** the command exits, reaches its timeout or is cancelled
- **THEN** the application SHALL stop and confirm the whole owned process tree before reporting a settled result or releasing a bound project from that command
- **AND** ordinary nonzero command exits SHALL remain tool failures; timeout or cancellation (native exit codes 124 or 130) and unconfirmed termination SHALL remain uncertain effects, even when process termination is confirmed, because partial file or external changes are not thereby established
- **AND** an uncertain command SHALL prevent further model/tool dispatch for that run until inspection and explicit acknowledgement, without replaying it; already dispatched siblings SHALL settle and retain their results
- **AND** confirming the process tree MUST NOT lock the project folder against another chat or helper.

#### Scenario: Preview and skill scripts stay separate

- **WHEN** preview is selected, or a skill script is requested without This computer or without a project
- **THEN** preview MUST NOT turn the host shell on
- **AND** the skill script MUST fail unless both This computer and a project are present
- **AND** file tools MUST still fail without a project.

#### Scenario: Standard agents leave This computer off

- **WHEN** a Standard agent is created
- **THEN** This computer MUST be off
- **AND** the person MUST tick it before the host shell is presented.

### Requirement: ENV-009 - Route approval classes through one interrupt path

In Ask, every presented host-shell call and protected action, including a protected MCP write or destructive action, SHALL pause through the shared interrupt path unless a matching exact grant applies. The first This-computer use in a chat SHALL be one card that shows the command and the resolved starting folder, in Ask and in Full access. A grant from another chat, including a matching Always allow, MUST NOT skip that first card. The stored grant SHALL apply only after this chat confirms. After that confirmation, Full access SHALL skip the approval pause for later enabled commands. Disabled tools and mandatory restrictions remain enforced. Grants SHALL follow AGT-008 and MUST NOT enable an unselected tool. A shell grant SHALL match only the exact command and the resolved starting folder. That folder SHALL be stored as the resolved path and MUST NOT be empty. Always allow SHALL store that exact command and that starting folder. Host execution MUST NOT be described as sandboxed by its project directory. Typed MCP elicitation SHALL remain a typed response in the ordered interrupt batch, not an approve/reject payload. No command-prefix parser SHALL grant implicit shell approval.

#### Scenario: Read-only and destructive actions

- **WHEN** a read-only shell command or destructive MCP action is attempted in Ask
- **THEN** it MUST pause under its exact typed interrupt identity unless a matching exact grant applies.

#### Scenario: Ambiguous read-only prefix

- **WHEN** a shell command begins with a familiar read-only name or includes quoting, expansion or composition
- **THEN** Ask MUST apply the same approval check to the entire command
- **AND** no prefix parser can authorize it.

#### Scenario: First This-computer use

- **WHEN** Ask uses This computer for the first time in a chat and the person chooses Always allow
- **THEN** one card MUST show the command and the starting folder
- **AND** the stored grant MUST be that exact command and that starting folder
- **AND** a different command or a different starting folder MUST pause again in Ask.

#### Scenario: Another chat does not skip the first This-computer card

- **WHEN** another chat has Always allow for the same command and the same resolved starting folder, and this chat uses This computer for the first time, in Ask or in Full access
- **THEN** one card MUST still show the command and the resolved starting folder
- **AND** that grant from the other chat MUST NOT skip the card, and the stored grant applies only after this chat confirms.

#### Scenario: Full access skips a later enabled command

- **WHEN** Full access has already confirmed This computer in that chat and then runs a later enabled host-shell command or another enabled tool
- **THEN** the approval pause MUST be skipped
- **AND** the first This-computer use MUST still show one card, and a tool that is not enabled MUST still be refused.

### Requirement: ENV-020 - Use native file tools without duplicate mutations

Ordinary Chat SHALL offer the Deep Agents filesystem tools when project file access is selected: `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep`. The existing exact multi-hunk tool SHALL remain beside `edit_file` and MUST NOT replace it. `execute` SHALL be offered only when ENV-008 attaches the host shell, and `write_todos` only when planning is selected. The product MUST NOT register another implementation of those tools, a new file editor, a second shell, or custom rename or delete tools. Delete SHALL be the upstream delete tool, offered only as a separate switch that a normal agent leaves off. Delete MUST NOT be included in the standing project-edit grant. It SHALL still refuse the project root, a link that leaves the project, and a tree too large to inspect. With Delete on, an approved card in Ask, or Full access with no card, Delete SHALL be allowed to delete `.git` or a secret file, including as part of a folder. The product MUST NOT offer undo for that delete. When Delete removes a file or a folder, a before-and-after record SHALL be kept. The product MUST NOT add a new screen for that record. Project file tools SHALL stay confined to the bound project, SHALL require a project, and MUST NOT run commands. General-purpose `task` MUST NOT be offered in ordinary Chat, including compiled children; named helpers retain their selected invocation path. Application tools that are not native file tools remain registered through their existing adapters; MCP tools remain supplied by ENV-007.

Selecting project file reading SHALL retain that access when knowledge search is also enabled. The reader description SHALL match its effective access. A reader supplied only for saved tool results, conversation history or retrieved evidence MUST remain restricted to those supplied routes and MUST NOT authorize project or knowledge file access.

A same-path conflict inside one tool batch, and across tasks, SHALL finish one write to that file, then run the next. This includes native writes, edits, deletions and structured applies. The product MUST NOT reject the second write as busy and MUST NOT lock the whole folder. A read of a file that is being written SHALL wait until that write finishes, then read the new contents. Other files SHALL continue. Several chats and helpers SHALL be permitted to use one folder. The app MUST NOT report that folder as busy. A read or later write that waits for a file MUST NOT occupy the worker required to finish the write to that file. Before the effect, the product SHALL recheck cancellation, run eligibility and the applicable approval or grant. Cancellation or resume SHALL NOT replay an effect or change the original tool-call identity. Different projects SHALL continue independently.

#### Scenario: No custom file deletion

- **WHEN** a normal agent has not ticked Delete
- **THEN** native list, read, search, create, and edit SHALL be available as selected, while custom rename or delete tools and native `delete` are absent
- **AND** Delete MUST NOT inherit the standing project-edit grant.

#### Scenario: Authorized delete has no undo

- **WHEN** Delete is on and Ask has an approved card, or Full access is on and no card is shown
- **THEN** Delete SHALL be allowed to remove `.git` or a secret file, including as part of a folder inside the bound project
- **AND** the product MUST NOT offer undo
- **AND** file tools MUST still refuse a path outside the bound project and MUST NOT run a command.

#### Scenario: Delete keeps a before-and-after record

- **WHEN** Delete removes a file or a folder
- **THEN** a before-and-after record SHALL be kept
- **AND** the product MUST NOT add a new screen for that record.

#### Scenario: Concurrent same-file edits

- **WHEN** one assistant tool-call batch, or two tasks, request writes to the same path
- **THEN** one write to that file SHALL finish, and then the next write SHALL run
- **AND** the second write MUST NOT be rejected as busy
- **AND** sequential read-edit-test-edit across later batches remains permitted.

#### Scenario: No second reader

- **WHEN** the harness is assembled for a project
- **THEN** the file tools are the Deep Agents filesystem tools and the application registers no second tool with their names.

#### Scenario: Parallel creation of a missing Windows directory

- **WHEN** native tools concurrently write distinct files under a new shared directory
- **THEN** equivalent Windows path representations SHALL not cause false escape errors, and each call SHALL retain its own success or error result
- **AND** genuine traversal and junction escape SHALL remain rejected
- **AND** same-file writes SHALL be ordered and MUST NOT be rejected as busy or lock the folder.

#### Scenario: Native Unicode search on Windows

- **WHEN** Chat searches valid UTF-8 text containing Unicode characters or Unicode filenames through a project or framework file route on Windows
- **THEN** results SHALL preserve exact matching text, paths, match limits and truncation status without a locale decoding failure
- **AND** supported entrypoints and desktop shortcut SHALL provide the same behavior without changing host-command encoding or replacing native tools.

#### Scenario: Project reads alongside knowledge search

- **WHEN** a project-bound Chat selects file reading and knowledge search
- **THEN** valid project files SHALL remain readable through returned virtual paths and project-relative filenames
- **AND** retrieved evidence, saved tool results and conversation history SHALL remain readable through their supplied routes.

#### Scenario: Result-only reader with project file access omitted

- **WHEN** Chat has active tools but has not selected file reading and receives an automatic reader for saved results or retrieved evidence
- **THEN** the reader SHALL permit only supplied result routes and describe that restriction
- **AND** project and knowledge files, traversal and host-drive paths SHALL remain denied; tools-off SHALL execute no reader.

#### Scenario: Contended mutations of different files

- **WHEN** several chats or helpers write different files in one folder, including native edits and structured applies
- **THEN** those other files SHALL continue while a write to one file finishes
- **AND** the app MUST NOT report that folder as busy or lock the folder
- **AND** cancelling a queued write MUST NOT execute the cancelled call or stop another file's write.

#### Scenario: Read during a write

- **WHEN** a read targets a file that is being written
- **THEN** the read SHALL wait until that write finishes and then read the new contents
- **AND** reads and writes of other files SHALL continue.

### Requirement: ENV-028 - Control only the configured Windows window scope

Windows control SHALL be an agent choice named One window. It MUST NOT be a chat menu of Off, Selected, and All. There SHALL be no All-windows choice. One window SHALL be the window actions, and only for the window the chat picks when the agent tries to use it. The product SHALL recheck that window's identity. This one-window limit SHALL be real only while This computer is off. One window SHALL hide Local AI Workbench's own windows and MUST refuse them. Administrator or elevated windows SHALL be refused. Unavailable or stale targets SHALL fail visibly. Inspection, interaction and window or element capture SHALL pass through typed tools and the existing approval policy. Raw worker command execution MUST NOT become agent authority.

This computer MAY still affect the app, because those commands run as the Windows account. While This computer is on, the screen MUST NOT describe that agent as limited to one window or to the project folder. A normal message SHALL still send when no window is selected. The chat SHALL ask when the agent tries to use the window. The product MUST NOT take over a window automatically. The person presses Stop to stop window control. The isolated Chrome browser SHALL keep its own takeover.

#### Scenario: Selected window remains narrow

- **WHEN** One window is used while This computer is off and a call targets a different or recycled window
- **THEN** the worker MUST refuse the call without interacting with that window
- **AND** the identity of the picked window MUST be rechecked
- **AND** Local AI Workbench's own windows MUST be hidden and refused
- **AND** administrator or elevated windows MUST be refused.

#### Scenario: Broader access is deliberate

- **WHEN** the person configures Windows control for an agent
- **THEN** the choice SHALL be named One window
- **AND** Chat MUST NOT offer Off, Selected, and All
- **AND** there MUST be no All-windows grant.

#### Scenario: A message sends before a window is picked

- **WHEN** no window is selected and the person sends a normal message
- **THEN** the message MUST still send
- **AND** the chat MUST ask when the agent tries to use the window
- **AND** the product MUST NOT take over a window automatically
- **AND** the person MUST be able to press Stop
- **AND** the isolated Chrome browser MUST keep its own takeover.

#### Scenario: This computer is not described as one window

- **WHEN** This computer is on
- **THEN** the screen MUST NOT describe that agent as limited to one window or to the project folder
- **AND** host commands run as the Windows account and MAY affect the app
- **AND** One window tools MUST still refuse the app's own windows and administrator or elevated windows.

### Requirement: ENV-029 - Preflight conversation capability groups

Agents setup SHALL expose project files, This computer, browser, and One window as understandable tool groups with individual choices, together with configured connection/tool dependencies. This computer is the host shell. One window is Windows control. There SHALL be no All-windows choice. Group membership, Standard membership and Plan eligibility SHALL come from the backend catalogue for the applicable project, knowledge, attachment and capture context. These choices SHALL be saved with the agent and resolved for new submissions; the composer `+` and Chat agent dropdown SHALL NOT duplicate them. Project file availability SHALL require the bound authorized project. Selecting a group MUST NOT grant a broader window, file, network or approval scope, and a group MUST NOT widen the parent's ticks. Chat SHALL own access/mode and the window the chat picks when the agent tries to use One window. Browser SHALL keep its session controls, and Settings SHALL keep installation and connections. The effective selected tools SHALL remain distinct from browser worker/session availability and live authority. Disabling Browser or One window in a saved agent MUST NOT leave a tool selected solely to read its captures. The backend SHALL validate the same effective selection and current authority at setup preview, admission, dispatch and restored/helper execution. A missing window grant or a missing picked window MUST NOT block send. Windows checks SHALL run when a Windows tool is about to be used. An unavailable browser worker or session, or an unsupported mode, SHALL yield a specific corrective action before the affected browser tools are presented. Explicit agent requirements SHALL be checked before sending. Unconfigured optional features SHALL NOT block ordinary chat and SHALL pause with a focused setup action only when needed. Saved intention without a current grant MUST NOT be described as ready. Running, queued, and paused setups SHALL retain their snapshots; future submissions SHALL use the latest saved agent.

Omission SHALL keep Standard resolution. Standard resolution SHALL leave This computer and Delete off. An explicit empty selection SHALL stay empty. Changing one Standard choice SHALL save an explicit list that starts from the backend Standard selection for that context and SHALL NOT add an unselected opt-in operation. If the catalogue is unavailable, the editor SHALL NOT invent or persist a derived default. An existing explicit selection SHALL be reloaded unchanged. The Plan projection SHALL show only backend-eligible readers and trusted namespaced public-web operations.

#### Scenario: Stale selected window

- **WHEN** a conversation has One window but its selected window is missing or gone, and the person sends an ordinary message
- **THEN** the message MUST still send
- **AND** a missing window grant MUST NOT block send
- **AND** Windows checks MUST run when a Windows tool is about to be used, and the chat MUST ask for a window then.

#### Scenario: Capability does not widen approval

- **WHEN** a person saves browser or This computer in an agent used by an Ask-access chat, or a helper runs under that parent
- **THEN** applicable tool actions MUST still use the existing approval path
- **AND** a group MUST NOT widen the parent's ticks or exceed the parent's scope.

#### Scenario: Missing or lost browser worker

- **WHEN** Browser is selected but its worker is absent or its prior session was lost
- **THEN** readiness identifies installation or reset; deferred optional Browser permits ordinary model dispatch and pauses for setup before browser schemas or actions, while explicit agent requirements remain preflight checks.

#### Scenario: Turn Browser off

- **WHEN** Browser is turned off in the selected agent and a new submission is made in a projectless chat without an independent file-reading selection
- **THEN** the next-turn tool selection excludes browser tools and incidental capture reading.

#### Scenario: Cleaner Chat with missing dependencies

- **WHEN** an agent selects a tool whose connection or worker is unavailable
- **THEN** Chat shows a concise corrective route to the owning setup/connection screen without introducing tool toggles or granting access.

#### Scenario: One Standard change does not add opt-in tools

- **WHEN** a new agent using Standard tools changes one non-opt-in choice and is saved, reloaded and admitted
- **THEN** the explicit selection matches the backend Standard set for that project or projectless context except the changed choice
- **AND** destructive, host, resource and diagnostic opt-in operations stay unselected, including This computer and Delete, in projectless and project-bound contexts.

#### Scenario: Catalogue failure does not invent a selection

- **WHEN** the tool catalogue cannot be loaded
- **THEN** the editor does not persist a locally invented default list.

#### Scenario: Optional Windows setup does not block chat

- **WHEN** an optional One window choice has no picked window and the person sends an ordinary message
- **THEN** ordinary chat MUST NOT be blocked
- **AND** the Windows check MUST wait until a Windows tool is about to be used.

### Requirement: ENV-030 - Use one owned Chrome context for agents and browser viewing

Selected Browser access SHALL run one owned Chrome per conversation, without a visible operating-system browser window, with a dedicated persistent profile for that conversation. It MUST NOT use the person's ordinary browser profile. Agent tools and the interactive Chat view SHALL use the same pages, tabs and viewport. Start and first browser actions SHALL launch it. Closing the rail SHALL stop viewing and MUST NOT stop the session. Close and expiry SHALL stop the owned process tree while retaining sign-ins in that profile. Reset SHALL clear the stopped profile after confirmation. Retained sign-ins MUST NOT be copied into an application backup. There is no application backup. Chrome availability SHALL be checked separately from worker installation. Structural and visual interaction, scrolling, dragging, page dialogs, permitted uploads and retained downloads SHALL use the existing access/effect rules. Unrestricted code, page-defined tools and the ordinary browser profile MUST NOT be exposed.

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

#### Scenario: Closing the rail keeps the session

- **WHEN** the person closes the browser rail
- **THEN** viewing MUST stop and the owned Chrome session MUST keep running
- **AND** sign-ins MUST remain in that conversation's dedicated profile
- **AND** those sign-ins MUST NOT be placed in an application backup.

#### Scenario: Close or expiry retains sign-ins without a backup

- **WHEN** the owned browser is closed or expires, or the stopped profile is reset after confirmation
- **THEN** close or expiry MUST stop the owned process tree and retain sign-ins until a confirmed reset clears the stopped profile
- **AND** the product MUST NOT copy those sign-ins into an application backup, because there is no application backup.

#### Scenario: First navigation with concurrent viewing
- **WHEN** the first authorized browser action launches Chrome while the live view or status monitor observes its startup
- **THEN** observation waits for coherent initialized page state and the action continues in the same owned context
- **AND** partially initialized state MUST NOT establish browser loss or cause a healthy browser to be terminated.

#### Scenario: Recover a lost browser without clearing sign-ins
- **WHEN** a lost session is closed and a fresh session is started
- **THEN** the existing Close/start path retains the conversation profile and recovery guidance identifies it distinctly from Reset
- **AND** neither recovery path automatically repeats completed or uncertain actions.

#### Scenario: Background live-view failure
- **WHEN** background frame capture fails while a foreground browser action succeeds
- **THEN** the live-view error remains observable without changing that action's successful result
- **AND** actual foreground action failures, directly requested frame failures and genuine worker loss retain their existing error and recovery boundaries.
