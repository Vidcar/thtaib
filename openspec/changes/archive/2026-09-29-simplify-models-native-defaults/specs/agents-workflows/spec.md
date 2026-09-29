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
