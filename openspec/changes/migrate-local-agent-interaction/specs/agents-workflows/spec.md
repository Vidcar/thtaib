## MODIFIED Requirements

### Requirement: AGT-001 - Use the embedded harness

Agent tasks SHALL run through Deep Agents using LangChain components and LangGraph. Chat SHALL call this harness directly with or without a bound project folder. Each run SHALL execute once through the existing owner; native streaming, UI selectors and application audit records SHALL observe that same invocation. Public message/content-block, tool-call/result, namespace and parent/child identities SHALL survive controlled interaction projection. The application MUST NOT add a second model/tool loop, checkpoint owner or inference client to satisfy a frontend integration.

#### Scenario: Project-bound and project-free chat

- WHEN Chat completes a real file-editing task with a project bound
- THEN the harness MUST own model/tool iteration and the completed faithful inference adapter MUST remain in use
- AND when Chat starts without a project, filesystem and shell tools MUST be absent and reported as unavailable.

#### Scenario: Native identity projection

- WHEN streamed content, a tool call and its result are observed by multiple scoped selectors
- THEN stable message/block/call and namespace identities MUST keep each result paired with its call without extra execution
- AND provider-reported reasoning, answer content and internal compaction output MUST remain distinct.

### Requirement: AGT-008 - Use framework interrupts for approvals

Host-shell and MCP approvals SHALL use Deep Agents interrupt decisions and LangGraph resume on the same checkpointer thread. A pending interrupt SHALL keep the application run running with recorded details and MUST NOT create a separate lifecycle status or imply completion. Decisions SHALL identify the application thread/run, interrupt and namespace; stale, duplicate and wrong-run decisions MUST be rejected. Cancel while interrupted SHALL reject-resume the pending command and finish as cancelled only after worker confirmation. Privileged tools MUST remain behind backend policy and MUST NOT become automatically resolved browser tools.

#### Scenario: Approve deny cancel

- WHEN a dangerous command pauses on an interrupt
- THEN Approve or Deny MUST resume through the installed framework decision format using the correct identities
- AND Cancel MUST resolve the pending command without replaying or claiming stopped external work before confirmation.

#### Scenario: Cross-run or duplicate decision

- WHEN an old approval is submitted twice or against another run, thread or namespace
- THEN it MUST fail without executing the action or reserving another continuation
- AND the current pending approval MUST retain its authoritative identity and state.
