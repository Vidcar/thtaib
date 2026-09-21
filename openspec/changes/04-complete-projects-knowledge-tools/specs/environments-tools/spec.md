# environments-tools delta

## MODIFIED Requirements

### Requirement: ENV-007 - Expand tools through registered MCP servers

The product SHALL discover/invoke selected registered MCP tools through the supported official `langchain.mcp.MCPAdapter`, passing namespaced tools into the same Deep Agents constructor rather than making an MCP host or agent loop. Selected server IDs, connected adapters and applied tools remain distinct. Discovery is not execution evidence: a real selected MCP tool SHALL return its actual result through a local model. Disabled/omitted servers start no adapter and leave core Chat usable.

Unknown records, connection/list-tools errors, unavailable stdio runtimes, missing credentials and name collisions SHALL fail closed for the selected run. Network URLs and explicitly authorized stdio process configuration SHALL be separate; entering a path in a URL field cannot launch a process. Only selected authorized actions become available. Remote tool errors, transport failures and unsupported conversions SHALL remain distinguishable; preserve model-visible/structured content and remote provenance. A remote URI is not a verified local artifact without deliberate retrieval/validation.

#### Scenario: MCP tools applied

- **WHEN** a registered MCP server is enabled and a selected tool is called
- **THEN** the official adapter supplies namespaced tools and the real result/call identity is retained; omission starts no adapter.

#### Scenario: Remote tool failure

- **WHEN** the server reports an error or returns an unsupported resource representation
- **THEN** the actual remote error/conversion limitation remains visible rather than an invented successful local file.

## ADDED Requirements

### Requirement: ENV-010 - Version shared tool connections and keep secrets backend-only

One shared catalogue SHALL retain stable integration/connection identity, configuration version, transport, credential reference, collision-safe discovered tool identity, schemas and known capabilities. Unknown output schemas stay unknown; remote names cannot inherit local authority through name matching. Persist selections and snapshot effective connections/tools in runs; revalidate selection/policy at dispatch/resume.

Provide connection add/edit/test/disconnect and credential replace/remove. Secrets remain backend-side, outside model descriptions, ordinary snapshots and exported diagnostics/backups by default. Removing local credentials is not provider revocation; disabling a connection prevents future use but does not undo/cancel remote work. Project/knowledge/setup/package/connection lifecycle SHALL extend shared dependency previews, retained versions, scope identity and manual backup without widening permissions. Existing Project, Knowledge and Chat configuration views SHALL expose these controls and missing dependencies rather than create parallel stores. Shared `@langchain/react` projections may present actual tool activity/results, while connection/setup selectors and policy remain application-owned.

#### Scenario: Connection removed

- **WHEN** a selected connection or credential disappears before another call
- **THEN** new execution detects the missing dependency, while retained evidence does not claim provider revocation or remote cancellation.

#### Scenario: Snapshot and export

- **WHEN** a run or backup captures connection configuration
- **THEN** version and credential binding are retained without exporting secret values or expanding scope.

### Requirement: ENV-011 - Read public web content through one concrete authorized integration

The product SHALL provide one concrete shared general-web search and public-page reader with documented provider, authentication, limits and failures. Search snippets and fetched page content SHALL remain distinct; retain URLs, titles, retrieval time and actual passages. A documentation MCP does not satisfy general web search. Text-only local Chat remains usable offline.

Content supplied to an authorized run MAY be used as needed through its already authorized tools/connections, including relevant excerpts in an external query, without a second document-sharing gate. Show the destination/query/content used. This MUST NOT grant tools, accounts, credentials, private/local-network access or automatic memory saving; linked/retrieved instructions remain untrusted data.

#### Scenario: Search then read

- **WHEN** the agent searches and fetches a selected public page
- **THEN** the result distinguishes snippets from actually read passages, with source/time and visible failures.

#### Scenario: Supplied document in query

- **WHEN** relevant supplied content is used through an already authorized external tool
- **THEN** no second sharing approval is demanded, but no new destination/access/credential authority is inferred.

### Requirement: ENV-012 - Run MCP and ordinary agents on one compatible async lifecycle

The common agent driver, model/tool middleware, saver/state access, approval resume, cancellation and recovery SHALL use a compatible async path for MCP and ordinary Chat/Lab. Preserve existing thread/branch/attachment/planning/interrupt records or report explicit incompatibility; do not delete history, edit private checkpoint tables or introduce another database. Long-lived clients, savers and owned tasks SHALL stay on their owning loop with explicit cleanup.

Session-dependent MCP operations SHALL retain the supported adapter session lifetime; per-call reconnection is allowed only where compatible. Timeouts/disconnects/cancellation MUST NOT blindly retry mutating calls or imply remote session survival. Supported elicitation SHALL use exact typed user-input identity and schema validation; unsupported elicitation is explicitly declined, never converted into approval or left hanging. Shutdown cleans owned resources and preserves unknown external outcomes.

#### Scenario: Shared async continuation

- **WHEN** MCP and non-MCP conversations continue/resume after migration or restart
- **THEN** compatible existing state uses the same driver and checkpointer, with correct loop/client ownership and explicit incompatibility where necessary.

#### Scenario: Elicitation and disconnect

- **WHEN** a session-dependent tool requests input or loses its connection
- **THEN** typed supported input resumes correctly or is explicitly declined; remote effects are not silently replayed.

### Requirement: ENV-013 - Keep optional selection and isolation inside real authority

Relevant-tool selection and isolated execution are optional, not prerequisites for the required catalogue. When implemented, selection SHALL be opt-in, operate only within the authorized catalogue, preserve tools-off/current dispatch policy and use the shared local adapter/capture/admission path without hidden tool-count quotas or cloud substitution. A selected user restriction remains explicit and removable.

An isolation option SHALL identify/test its actual environment, mounts, network, dependency setup, transfer, cleanup and recovery. Host cwd or virtual filesystem mode MUST NOT be labelled a sandbox, and no hosted execution environment may be substituted silently. Authorized host execution remains honestly labelled when isolation is absent.

#### Scenario: Optional extensions absent

- **WHEN** tool selection or isolated execution is not configured
- **THEN** ordinary authorized host/file/tool work remains available without false sandbox claims or extra prerequisites.
