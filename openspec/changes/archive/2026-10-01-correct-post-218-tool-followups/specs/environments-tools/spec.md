# Spec Delta

## MODIFIED Requirements

### Requirement: ENV-008 - Attach host shell only when execute is presented

The first worker environment SHALL be the Windows host shell through Deep Agents `LocalShellBackend`, approvals, and `interrupt_on`. The host shell SHALL attach only when a project is bound and `execute` is presented. Project-bound runs without `execute` SHALL use filesystem-only backend behavior. A project-free request for host shell, project preview, pinned project reads, or eager file mutations SHALL fail with an actionable error and SHALL NOT invent a home-directory cwd. Unpinned `glob` and `grep` SHALL be omitted until a project is bound and SHALL NOT fail merely because definitions load eagerly. Unpinned `ls` and `read_file` follow that admission rule, except a selected knowledge or capture route may keep them for its virtual paths only. Application lifecycle adapters SHALL own Windows shell descendants through command exit, cancellation and timeout without replacing the native tool or harness. A settled shell result SHALL mean that its process tree has stopped; unconfirmed termination SHALL retain uncertain-effect recovery and project ownership. Long-running web servers SHALL use selected owned preview capabilities.

#### Scenario: Shell availability

- **WHEN** a project-free Chat requests shell access
- **THEN** `execute` MUST be absent or rejected with a project-required error
- **AND** when a project-bound run does not present `execute`, no live host shell MUST be attached.

#### Scenario: Eager definitions do not require optional project reads

- **WHEN** a project-free selection includes unpinned project reads and definitions load eagerly
- **THEN** `glob` and `grep` are omitted and the run can continue
- **AND** `ls` and `read_file` are omitted unless a selected knowledge or capture route keeps them as virtual readers
- **AND** pinned reads, eager mutations, and eager shell or preview still fail.

#### Scenario: A shell command spawns a detached child

- **WHEN** the command exits, reaches its timeout or is cancelled
- **THEN** the application SHALL stop and confirm the whole owned process tree before reporting a settled result or releasing the project
- **AND** ordinary nonzero command exits SHALL remain tool failures; timeout or cancellation (native exit codes 124 or 130) and unconfirmed termination SHALL remain uncertain effects, even when process termination is confirmed, because partial file or external changes are not thereby established.
- **AND** an uncertain command SHALL prevent further model/tool dispatch and project admission until inspection and explicit acknowledgement, without replaying it; already dispatched siblings SHALL settle and retain their results.

### Requirement: ENV-032 - Retain acquired evidence before bounded presentation

Browser snapshots, acquired public-page text, command output and preview logs SHALL retain complete permitted acquired content before generating a bounded preview. Results SHALL identify source, acquisition coverage, byte/character units and an authorized bounded range/search continuation that can recover late errors and long single lines. Continuation guidance SHALL use the same effective reader resolution as model dispatch, including an automatic framework-only `read_file` limited to framework paths, explicit reader exclusions, and Tools off. The notice SHALL name that reader and its path limits when it is already available and no explicit reader is selected. It SHALL NOT grant a project reader or change the saved selection. When no reader is accepted, including when tools are off or the framework reader is excluded, the notice SHALL state that limitation and SHALL NOT imply that discovery can grant access. The stored notice is retention provenance. A later read SHALL report current availability separately and SHALL NOT rewrite that provenance. Retention SHALL use existing result/asset owners and MUST NOT grant access to another conversation, excluded project file, credential or arbitrary host path. Transfer/disk acquisition limits SHALL be explicit; omitted bytes MUST NOT be called complete. Reading retained evidence SHALL NOT execute the original producer again.

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

#### Scenario: Browser-only setup already has the framework reader
- **WHEN** a saved browser-only setup with tools enabled and no explicit file reader produces a large retained result
- **THEN** the notice names the already available framework-only line reader and its path limits
- **AND** an explicit reader exclusion or Tools off is not given that reader
- **AND** a later read under another selection reports current availability without rewriting the stored notice.

### Requirement: ENV-034 - Own extended operation lifecycles

Explicitly selected extensions SHALL support one structured exact multi-edit mechanism with original-byte identity, prevalidation, overlap rejection and one atomic file replacement; managed command launch/status/output/stop with stable owned identities; bounded selected MCP resource listing/reading; and selected immutable skill-script execution. These operations SHALL use existing execution, permission, result, connection and process owners. Skill scripts SHALL verify frozen version/resource hashes, materialize only into an owned execution directory, require independently selected host-command authority and retain truthful output/exit/cancellation. Resource text SHALL remain untrusted reference data. Lost acknowledgements and restart SHALL preserve uncertainty without replaying effects; cancellation SHALL settle owned processes.

A connection SHALL be ready for the protocol capabilities confirmed by its last successful test. A connection test SHALL inspect negotiated server capabilities. It SHALL list tools only when tools are advertised and SHALL validate resources independently when resources are advertised. A server that advertises resources and does not implement tools/list SHALL complete a successful resources-only test with an empty tool list and no fabricated tools. An empty tool list on an advertised tools capability SHALL remain tools support. Method-not-found on a capability that was not advertised SHALL be an unsupported optional method. Method-not-found, transport, or authentication failure on an advertised capability SHALL fail the test. Arbitrary error text SHALL NOT be capability evidence. A successful empty tool manifest SHALL NOT by itself make a tested resource-capable connection unready, and a successful tool manifest SHALL NOT make unsupported resources appear supported. Failed tests, disabled connections, missing credentials and changed versions SHALL remain unready or rejected. Resource operations SHALL stay unavailable when the tested server does not support them. Neither readiness nor resource reading SHALL fabricate tools.

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

#### Scenario: Resources without a tools endpoint
- **WHEN** a server advertises resources and no tools capability, and implements no tools/list handler
- **THEN** testing, saving, and admission in both loading modes succeed, and listing and reading its resources succeed
- **AND** the tool list stays empty
- **AND** a tools-only server and an empty tool manifest on an advertised tools capability stay distinct.
