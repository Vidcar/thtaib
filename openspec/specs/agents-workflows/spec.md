# Agents Workflows

## Purpose

Specify how Chat, Agent-run, and Workflows use the embedded Deep Agents harness and LangGraph runtime while keeping active context, displayed history, configuration links, workflow sequencing, and durable knowledge distinct.

## Requirements

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

### Requirement: WF-001 - Keep configuration links out of execution sequencing

Configuration connections SHALL supply model profile, tools, skills, memory, environment, access, and execution policy to the owning agent or step through explicit inheritance and overrides. Workflow connections SHALL define next steps and typed data or artifact handovers. Only workflow connections SHALL compile into workflow sequencing.

#### Scenario: Mixed definition compile

- WHEN a definition contains configuration links and workflow links for multiple owners
- THEN configuration links MUST affect only the intended owner setup
- AND they MUST NOT become executable steps or flatten every agent into one global setup.

### Requirement: WF-002 - Make delegation and cycle ownership explicit

Workflows SHALL invoke Deep Agents as named subgraphs with declared inputs and outputs. Subagents SHALL remain child runs within their owning step and MUST receive the intended model, tools, context policy, and access restrictions without escalation. Exactly one owner, either the outer LangGraph workflow or its agent step, SHALL control each review cycle. Planning through upstream middleware is allowed; general delegation and declared workflow cycles MUST remain explicit implementation capabilities, not assumed.

#### Scenario: Review loop ownership

- WHEN an outer review loop contains a delegating step
- THEN the run hierarchy MUST show which owner decides to repeat
- AND the same cycle MUST NOT be duplicated by both workflow and harness logic.

### Requirement: AGT-002 - Capture the actual model request

The product SHALL instrument the final model-adapter boundary after context middleware, including official memory, skills, retrieval, summaries, and offloaded content when applied. Captures SHALL link actual instructions, selected knowledge versions, available tools, usage, provenance, redaction, and capture gaps to each call. Captures MUST expose request visibility only and MUST NOT claim access to hidden model reasoning.

#### Scenario: Capture after context middleware

- WHEN a request is captured after compaction with memory or skills selected
- THEN the capture MUST match what the adapter sends, after configured redaction
- AND unread skill bodies MUST remain off the wire.

### Requirement: AGT-003 - Leave task budgets unset by default

The product SHALL NOT impose arbitrary task-level time, token, model/tool-call, reasoning-effort, or revision ceilings by default. Optional budgets SHALL be user-selected. Framework and middleware limits SHALL be explicitly configured and reported. Checkpointed continuation SHALL be supported when user budgets permit. A limit, cancellation request, or stalled-progress warning MUST NOT be reported as successful completion.

#### Scenario: Budget and stop reason

- WHEN a run continues beyond a framework boundary, is cancelled, completes, or hits a selected budget
- THEN the run MUST record the actual stop reason
- AND `cancel_requested` MUST remain live until the worker records confirmed `cancelled`.

### Requirement: AGT-004 - Separate active context from durable knowledge

The product SHALL use application-versioned user, agent, and project memory, skills, and protected instructions through configured backends. Selected versions SHALL be loaded as content before the run: memory through official `memory=`, skills through official `skills=`, and protected instructions through the composed system prompt. Automatic writes SHALL require explicit scope policy, provenance, and concurrent-write handling. Protected instructions MUST reject agent-origin writes.

#### Scenario: Versioned knowledge and fresh conversation

- WHEN a fresh conversation selects retained files and knowledge
- THEN durable knowledge and project files MUST be available without inheriting previous active context
- AND memory edit, revert, denied protected-instruction overwrite, and concurrent conflict MUST preserve version policy.

### Requirement: AGT-005 - Do not silently remove enabled tools

Tool-selection middleware MAY narrow tools presented for a call, but product discovery SHALL keep the current enabled catalogue visible and SHALL distinguish implemented planning from deferred delegation. Selection SHALL optimize context and MUST NOT become a new access-policy owner.

#### Scenario: Narrowed tool list

- WHEN a call receives a narrowed tool list
- THEN enabled tools outside the list MUST remain discoverable
- AND denied tools MUST remain denied while authorized tools are not permanently hidden.

### Requirement: AGT-006 - Keep completion evidence distinct from judgement

Tasks with definitions of done SHALL preserve executable checks, expected artifacts, and review criteria separately. Test outcomes SHALL remain distinct from model assessments. Rubric middleware MAY extend review, but MUST NOT be required for basic completion checking.

#### Scenario: Evidence report

- WHEN a task result is inspected
- THEN executable success or failure, expected artifacts, and model review MUST be reported separately
- AND removal of rubric integration MUST NOT remove basic acceptance checks.

### Requirement: AGT-007 - Preserve Chat continuity and restart truth

A Chat conversation SHALL link displayed history, deployment/profile/project binding, execution thread, and run ids. Continuing SHALL mean the same conversation and thread with a new run; fresh SHALL mean a new conversation and thread. Display-only history edits MUST NOT change project files, thread identity, or next harness context. Restart recovery SHALL reconcile durable conversation state and terminal runs before starting a next turn.

#### Scenario: Restart then continue

- WHEN the backend restarts with a persisted conversation and prior run linkage
- THEN continuation MUST use the persisted conversation, thread, and run records
- AND missing linkage MUST be reported as an explicit gap rather than silently starting a new thread as the same conversation.

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
