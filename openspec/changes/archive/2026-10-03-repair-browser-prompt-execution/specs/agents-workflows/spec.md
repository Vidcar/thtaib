## MODIFIED Requirements

### Requirement: AGT-001 - Use the embedded harness

Agent tasks SHALL run through `create_deep_agent` using LangChain components and LangGraph. Chat SHALL call the same harness with or without a bound project; the application MUST NOT add a model/tool loop. Each run executes once; native streaming, scoped selectors and audit projections observe that invocation while preserving message/block/tool and namespace identities. Without a project, project-filesystem and host-shell access SHALL be absent or rejected, not assigned an invented working directory. Explicitly supplied session attachments MAY be read through their authorized content/scoped backend without granting project or host access.

The harness SHALL receive the run's backend, filesystem permissions, `interrupt_on`, `memory`, and `skills` through those official parameters when the run uses them. Planning SHALL be the official `write_todos` tool when planning is selected. Exactly one Deep Agents summarization middleware SHALL run with its native model-aware trigger and retention defaults. It SHALL receive full observed per-request capacity and apply its native reservations/headroom once. Supported SDK configuration SHALL own token counting, retention, offloading, summary generation and overflow recovery; application budget overrides and extra percentage/output deductions MUST NOT alter those policies. The application MUST NOT set a separate early compaction threshold or stack another summarizer. Ordinary Chat SHALL disable the general-purpose subagent through the upstream profile switch, and SHALL NOT rely on a parent-only filter that a compiled child does not inherit. The product MUST NOT embed the Deep Agents CLI or a hosted agent runtime.

#### Scenario: Project-bound and project-free chat

- **WHEN** Chat performs a real project file task and then starts a non-project conversation
- **THEN** the shared harness owns iteration in both cases; non-project Chat has no project file/shell authority while authorized attachments remain usable.

#### Scenario: Native identity projection

- WHEN streamed content, a tool call and its result are observed by multiple scoped selectors
- THEN stable message/block/call and namespace identities MUST keep each result paired with its call without extra execution
- AND provider-reported reasoning, answer content and internal compaction output MUST remain distinct.

#### Scenario: Ordinary Chat has no general-purpose child

- **WHEN** ordinary Chat is compiled and a tool exclusion would matter
- **THEN** the general-purpose `task` tool is not offered, including to a child
- **AND** disabling it is the upstream profile switch rather than a filter only the parent runs.

#### Scenario: Summarize once

- **WHEN** a long turn is compacted
- **THEN** one Deep Agents summarizer applies its native model-aware compaction defaults against the full observed model capacity with the framework policy applied once
- **AND** no custom early threshold or second summarizer shrinks that budget again.

#### Scenario: Browser handoff context is delivered once

- **WHEN** a browser handoff or lifecycle change supplies a fresh observation
- **THEN** the next successful model request SHALL receive its marked, untrusted tool context once, with native checkpoint history and a delivery receipt
- **AND** counting, failed generation, cancellation or a resumed typed question SHALL NOT append repeated observation prompts or create a new real user-turn boundary
- **AND** a newer handoff revision SHALL remain deliverable even when its page text matches an earlier snapshot.

#### Scenario: A newer browser result supersedes handoff context

- **WHEN** a successful parent browser action after a handoff produces a newer result before the pending observation is dispatched
- **THEN** the observation SHALL identify its historical provenance and the newer result as superseding it
- **AND** failed calls and helper-local results SHALL NOT falsely establish a newer parent page
- **AND** token counting, outgoing request context and retained native history SHALL agree.


#### Scenario: Preserve native tool content and artifact separation

- **WHEN** the browser MCP adapter returns model content and a separate artifact
- **THEN** browser text projection SHALL preserve the native model content without stringifying absent artifacts or adding separate artifact metadata as response text
- **AND** permitted image acquisition, source identity, redaction and retained-result access SHALL remain usable.

#### Scenario: Execution platform is available before tool discovery

- **WHEN** a newly accepted task is composed for the local harness
- **THEN** its initial system context SHALL state the actual host operating system before platform-dependent work, independently of deferred tool-schema discovery
- **AND** input preview, accounting and root/helper composition SHALL use the same factual text without changing authored instructions, implying shell permissions or claiming installed dependencies
- **AND** the accepted prompt SHALL remain frozen for resume, without appending another environment prompt after ordinary answers or tool results.

### Requirement: AGT-005 - Do not silently remove enabled tools

Tool-selection middleware MAY narrow tools presented for a call, but product discovery SHALL keep the current enabled catalogue visible and SHALL distinguish implemented planning from deferred delegation. Selection SHALL optimize context and MUST NOT become a new access-policy owner.

Newly accepted inputs SHALL default enabled tools to When needed, with explicit Always include pins and an eager mode available. A compact discovery interface SHALL expose only the accepted enabled capability envelope and activate a small matching tool set without another selector model call. Active tool schemas SHALL be deterministic within a turn, persisted for resume and reset for the next newly accepted input except for pins. Disclosure MUST NOT grant permission, activate disabled tools or bypass context capacity.

#### Scenario: Narrowed tool list

- WHEN a call receives a narrowed tool list
- THEN enabled tools outside the list MUST remain discoverable
- AND denied tools MUST remain denied while authorized tools are not permanently hidden.

#### Scenario: Discover and pin
- **WHEN** an agent needs an enabled unpinned tool
- **THEN** discovery activates its applicable schema for subsequent model requests and execution retains the same access checks
- **AND** explicitly pinned tools are supplied initially while unrelated enabled definitions remain deferred.

#### Scenario: Advertised labels discover their accepted tools

- **WHEN** an agent looks up an exact advertised tool label or executable name within the accepted enabled catalogue
- **THEN** discovery SHALL recognize the corresponding tool, including actionable deferred setup, while retaining group, mode, exclusion and permission checks
- **AND** common browser URL and scrolling searches SHALL rank the corresponding accepted action meaningfully within the bounded result batch
- **AND** each successful result description SHALL be supplied once rather than repeated in an additional notice.
