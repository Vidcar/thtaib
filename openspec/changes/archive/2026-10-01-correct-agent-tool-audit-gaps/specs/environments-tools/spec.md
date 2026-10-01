# Spec Delta

## MODIFIED Requirements

### Requirement: ENV-020 - Use native file tools without duplicate mutations

Ordinary Chat SHALL offer Deep Agents built-in `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep` when project file access is selected. `execute` SHALL be offered only when ENV-008 attaches the host shell, and `write_todos` only when planning is selected. The product MUST NOT register another implementation of those tools or custom rename/delete tools. The upstream recursive `delete` SHALL be available only as an explicitly selected destructive operation with independent approval, confined whole-subtree validation, before/after evidence and cancellation handling; ordinary presets SHALL omit it. General-purpose `task` MUST NOT be offered in ordinary Chat, including compiled children; named helpers retain their selected invocation path. Application tools that are not native file tools remain registered through their existing adapters; MCP tools remain supplied by ENV-007.

Selecting project file reading SHALL retain that access when knowledge search is also enabled. The reader description SHALL match its effective access. A reader supplied only for saved tool results, conversation history or retrieved evidence MUST remain restricted to those supplied routes and MUST NOT authorize project or knowledge file access.

Native project writes, edits, deletions and structured applies for one project SHALL share one admission gate. Waiting asynchronous operations SHALL NOT occupy the blocking workers required to finish and release the active mutation. Different projects and ordinary reads SHALL continue independently. Same-path conflicts in one tool-call batch SHALL still be rejected. After admission and before the effect, the product SHALL recheck cancellation, run eligibility and the applicable approval or grant. Cancellation or resume SHALL NOT replay an effect or change the original tool-call identity.

#### Scenario: No custom file deletion
- **WHEN** ordinary Chat has not explicitly selected destructive deletion
- **THEN** native read/write/edit/list/search are available as selected while custom rename/delete and recursive `delete` are absent
- **AND** selecting native delete requires its independent destructive policy and cannot inherit a project-write grant.

#### Scenario: Concurrent same-file edits
- **WHEN** one assistant tool-call batch requests competing mutations to the same path
- **THEN** the native guard rejects the conflict before two writes can race
- **AND** sequential read-edit-test-edit across later batches remains permitted.

#### Scenario: No second reader
- **WHEN** the harness is assembled for a project
- **THEN** the file tools are Deep Agents built-ins and the application registers no second tool with their names.

#### Scenario: Parallel creation of a missing Windows directory
- **WHEN** native tools concurrently write distinct files under a new shared directory
- **THEN** equivalent Windows path representations SHALL not cause false escape errors, and each call SHALL retain its own success or error result
- **AND** genuine traversal, junction escape and same-file conflicts SHALL remain rejected.

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
- **WHEN** more project mutations are waiting than blocking workers are available, including native edits and structured applies to different files
- **THEN** the active mutation can finish and release admission, and a later mutation can acquire it
- **AND** cancelling a queued mutation does not release another operation's admission or execute the cancelled call.

### Requirement: ENV-029 - Preflight conversation capability groups

Agents setup SHALL expose project files, host shell, browser and Windows control as understandable tool groups with individual choices, together with configured connection/tool dependencies. Group membership, Standard membership and Plan eligibility SHALL come from the backend catalogue for the applicable project, knowledge, attachment and capture context. These choices SHALL be saved with the agent and resolved for new submissions; the composer `+` and Chat agent dropdown SHALL NOT duplicate them. Project file availability SHALL require the bound authorized project; selecting a group MUST NOT grant a broader window, file, network or approval scope. Chat SHALL own access/mode and live Windows target/grants, Browser its session controls and Settings installation/connections. The effective selected tools SHALL remain distinct from browser worker/session availability and live authority. Disabling Browser or Windows control in a saved agent MUST NOT leave a tool selected solely to read its captures. The backend SHALL validate the same effective selection and current authority at setup preview, admission, dispatch and restored/helper execution. A stale/missing window, absent broad grant, unavailable browser worker/session or unsupported mode SHALL yield a specific corrective action before affected tools are presented. Explicit agent requirements SHALL be checked before sending; unconfigured optional When needed features SHALL not block ordinary chat and SHALL pause with a focused setup action only when needed. Saved intention without a current grant MUST NOT be described as ready. Running/queued/paused setups retain their snapshots; future submissions use the latest saved agent.

Omission SHALL keep Standard resolution. An explicit empty selection SHALL stay empty. Changing one Standard choice SHALL save an explicit list that starts from the backend Standard selection for that context and SHALL NOT add an unselected opt-in operation. If the catalogue is unavailable, the editor SHALL NOT invent or persist a derived default. An existing explicit selection SHALL be reloaded unchanged. The Plan projection SHALL show only backend-eligible readers and trusted namespaced public-web operations.

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

#### Scenario: One Standard change does not add opt-in tools
- **WHEN** a new agent using Standard tools changes one non-opt-in choice and is saved, reloaded and admitted
- **THEN** the explicit selection matches the backend Standard set for that project or projectless context except the changed choice
- **AND** destructive, host, resource and diagnostic opt-in operations stay unselected, including in projectless and project-bound contexts.

#### Scenario: Catalogue failure does not invent a selection
- **WHEN** the tool catalogue cannot be loaded
- **THEN** the editor does not persist a locally invented default list.

### Requirement: ENV-032 - Retain acquired evidence before bounded presentation

Browser snapshots, acquired public-page text, command output and preview logs SHALL retain complete permitted acquired content before generating a bounded preview. Results SHALL identify source, acquisition coverage, byte/character units and an authorized bounded range/search continuation that can recover late errors and long single lines. Continuation guidance SHALL name a reader that is accepted for that run, or the authorised line-oriented fallback when that is the only accepted reader. When no reader is accepted, including when tools are off, the notice SHALL state that limitation and SHALL NOT imply that discovery can grant access. Retention SHALL use existing result/asset owners and MUST NOT grant access to another conversation, excluded project file, credential or arbitrary host path. Transfer/disk acquisition limits SHALL be explicit; omitted bytes MUST NOT be called complete. Reading retained evidence SHALL NOT execute the original producer again.

#### Scenario: Late error outside the preview
- **WHEN** a long command or page contains relevant text outside its initial preview
- **THEN** the result supplies an authorized continuation that recovers that text with source identity and accurate coverage.

#### Scenario: Unauthorized retained result
- **WHEN** a different owner or revoked selection attempts to read the result
- **THEN** access is rejected without broadening framework or project access.

#### Scenario: Guidance matches the accepted reader
- **WHEN** retained output is presented to a run whose selection includes the retained-result reader, only the line-oriented file reader, or neither
- **THEN** the notice recommends the accepted reader, describes the line-oriented fallback, or states that no reader is accepted
- **AND** an explicit exclusion or tools-off selection is not given a reader by the notice.

### Requirement: ENV-034 - Own extended operation lifecycles

Explicitly selected extensions SHALL support one structured exact multi-edit mechanism with original-byte identity, prevalidation, overlap rejection and one atomic file replacement; managed command launch/status/output/stop with stable owned identities; bounded selected MCP resource listing/reading; and selected immutable skill-script execution. These operations SHALL use existing execution, permission, result, connection and process owners. Skill scripts SHALL verify frozen version/resource hashes, materialize only into an owned execution directory, require independently selected host-command authority and retain truthful output/exit/cancellation. Resource text SHALL remain untrusted reference data. Lost acknowledgements and restart SHALL preserve uncertainty without replaying effects; cancellation SHALL settle owned processes.

A connection SHALL be ready for the protocol capabilities confirmed by its last successful test. A successful empty tool manifest SHALL NOT by itself make a tested resource-capable connection unready, and a successful tool manifest SHALL NOT make unsupported resources appear supported. Failed tests, disabled connections, missing credentials and changed versions SHALL remain unready or rejected. Resource operations SHALL stay unavailable when the tested server does not support them. Neither readiness nor resource reading SHALL fabricate tools.

#### Scenario: Invalid or stale edit batch
- **WHEN** a structured edit has a stale original hash, overlapping replacements or an unmatched original string
- **THEN** no file bytes change and a correctable result identifies the invalid input.

#### Scenario: Cancel a managed job
- **WHEN** a running managed command is cancelled or explicitly stopped
- **THEN** the owned process tree settles before reporting stopped, and retained output remains readable.

#### Scenario: Frozen selected script
- **WHEN** a script-bearing selected skill runs after its saved source has changed
- **THEN** execution uses only the accepted frozen resource and hash
- **AND** missing independent command authority or a mismatched resource fails before materialization/execution.

#### Scenario: MCP resources are bounded selections
- **WHEN** a selected supported connection lists or reads a resource
- **THEN** connection/version authority and limits are rechecked, content is retained as reference data and no extra tool or account is enabled.

#### Scenario: Resource-only connection in either loading mode
- **WHEN** a tested resource-only connection is saved and a run is admitted with definitions loaded always or when needed
- **THEN** listing and reading its resources succeed and no tools are fabricated
- **AND** revocation or a changed version rejects later access, while a tools-only server does not gain resource access from an empty or successful tool manifest.
