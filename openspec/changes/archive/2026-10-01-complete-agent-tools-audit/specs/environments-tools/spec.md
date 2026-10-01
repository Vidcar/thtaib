## ADDED Requirements

### Requirement: ENV-032 - Retain acquired evidence before bounded presentation

Browser snapshots, acquired public-page text, command output and preview logs SHALL retain complete permitted acquired content before generating a bounded preview. Results SHALL identify source, acquisition coverage, byte/character units and an authorized bounded range/search continuation that can recover late errors and long single lines. Retention SHALL use existing result/asset owners and MUST NOT grant access to another conversation, excluded project file, credential or arbitrary host path. Transfer/disk acquisition limits SHALL be explicit; omitted bytes MUST NOT be called complete.

#### Scenario: Late error outside the preview
- **WHEN** a long command or page contains relevant text outside its initial preview
- **THEN** the result supplies an authorized continuation that recovers that text with source identity and accurate coverage.

#### Scenario: Unauthorized retained result
- **WHEN** a different owner or revoked selection attempts to read the result
- **THEN** access is rejected without broadening framework or project access.

### Requirement: ENV-033 - Extend owned browser evidence and testing

Selected browser capabilities SHALL include the supported single-network-request companion and media emulation using the installed worker's executable schemas. Network evidence SHALL retain request identity, redact credential-bearing fields and provide bounded large-response continuation. Browser state changes SHALL retain current ownership, handoff invalidation, selected capability and approval checks. Desktop schemas SHALL expose the same enforced bounds/units used by execution. Stale observations and partial form effects SHALL remain explicit and MUST NOT trigger blind replay.

#### Scenario: Inspect an identified request
- **WHEN** a selected network-list result identifies a request
- **THEN** its supported detail operation can retrieve bounded permitted evidence without exposing credential headers.

#### Scenario: Theme and motion validation
- **WHEN** an authorized browser task changes supported color-scheme/reduced-motion emulation
- **THEN** the owned page uses those values and handoff/revocation rules still apply.

### Requirement: ENV-034 - Own extended operation lifecycles

Explicitly selected extensions SHALL support one structured exact multi-edit mechanism with original-byte identity, prevalidation, overlap rejection and one atomic file replacement; managed command launch/status/output/stop with stable owned identities; bounded selected MCP resource listing/reading; and selected immutable skill-script execution. These operations SHALL use existing execution, permission, result, connection and process owners. Skill scripts SHALL verify frozen version/resource hashes, materialize only into an owned execution directory, require independently selected host-command authority and retain truthful output/exit/cancellation. Resource text SHALL remain untrusted reference data. Lost acknowledgements and restart SHALL preserve uncertainty without replaying effects; cancellation SHALL settle owned processes.

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

## MODIFIED Requirements

### Requirement: ENV-020 - Use native file tools without duplicate mutations

Ordinary Chat SHALL offer Deep Agents built-in `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep` when project file access is selected. `execute` SHALL be offered only when ENV-008 attaches the host shell, and `write_todos` only when planning is selected. The product MUST NOT register another implementation of those tools or custom rename/delete tools. The upstream recursive `delete` SHALL be available only as an explicitly selected destructive operation with independent approval, confined whole-subtree validation, before/after evidence and cancellation handling; ordinary presets SHALL omit it. General-purpose `task` MUST NOT be offered in ordinary Chat, including compiled children; named helpers retain their selected invocation path. Application tools that are not native file tools remain registered through their existing adapters; MCP tools remain supplied by ENV-007.

Selecting project file reading SHALL retain that access when knowledge search is also enabled. The reader description SHALL match its effective access. A reader supplied only for saved tool results, conversation history or retrieved evidence MUST remain restricted to those supplied routes and MUST NOT authorize project or knowledge file access.

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
