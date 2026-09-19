# Agents and workflows

[Specification index](../README.md) · [Status and evidence](../catalog.json)

## Ownership, scope and source

Deep Agents owns each agent's model/tool loop and active context. LangGraph owns its runtime and Builder's outer graph. LangChain supplies adapters and interfaces. Source: [revision 0.5, page 5](../sources/README.md#agents-and-workflows) and [the connection rules on page 7](../sources/README.md#integration-registry).

## Public contracts and collaboration

Consume a resolved agent setup, model adapter, enabled tool/file backends, selected memory/skill versions and task criteria. Emit events into the backend's run hierarchy and link checkpoints through [state and recovery](state-recovery.md). Builder supplies typed step inputs/outputs; Chat invokes the same harness without requiring an outer workflow.

Memory content/versioning is application-owned; consumption and active-context management are harness responsibilities. Retrieved documents are neither durable project memory nor model training. Retrieval/index storage selection remains open.

## Lifecycle and failure

The backend exposes start, progress, intervention, pause/cancel and recovery as supported by the integration. Exactly how interrupts, threads, checkpoints and continuation map to a pinned framework version must be tested before claiming resumability. A disconnected client is not evidence a run ended. Do not silently replay uncertain tool effects during recovery.

## Requirements and acceptance checks

<a id="agt-001"></a>
### AGT-001: Use the embedded harness

Run agent tasks with Deep Agents using LangChain components and LangGraph. Chat calls this harness directly; do not add an application-written model-and-tool loop.

**Acceptance:** Complete a real file-editing task through Chat and inspect the execution path to confirm that the harness owns the model/tool iteration.

<a id="wf-001"></a>
### WF-001: Keep configuration links out of execution sequencing

Configuration connections supply model profile, tools, skills, memory, environment, access and execution policy. Resolve one validated Deep Agents setup. Workflow connections define next steps and typed data/artifact handovers; only these compile into workflow sequencing.

**Acceptance:** Compile a mixed configuration/workflow definition and show that configuration links do not become executable workflow steps.

<a id="wf-002"></a>
### WF-002: Make delegation and cycle ownership explicit

Builder invokes Deep Agents as named subgraphs with declared inputs and outputs. Subagents remain child runs within their owning step. Expose delegation scope. General-purpose setups make supported planning and delegation available; specialist steps may explicitly narrow their role. Exactly one owner—the outer graph or agent step—controls each review cycle; do not silently duplicate workflow sequencing inside the harness.

**Acceptance:** Run an outer review loop with a delegating step and inspect the hierarchy. Demonstrate which owner decides to repeat and that the same cycle is not performed twice.

<a id="agt-002"></a>
### AGT-002: Capture the actual model request

Instrument the final model-adapter boundary after context middleware. Link actual instructions, memory/skill versions, retrieved material, available tools, summaries and offloaded content to each call. Expose capture gaps, usage and provenance with configurable local retention/redaction. This is request visibility, not access to hidden model reasoning.

**Acceptance:** Capture a request after compaction and compare it with what the adapter sends, accounting explicitly for redaction and any capture gap.

<a id="agt-003"></a>
### AGT-003: Leave task budgets unset by default

Do not impose arbitrary task-level time, token, model/tool-call, reasoning-effort or revision ceilings. Optional budgets are user-selected. Explicitly configure framework/middleware limits and timeouts, support checkpointed continuation, and distinguish actual boundaries from product budgets. A limit or stalled-progress warning is not successful completion; no uncertain action may be replayed silently.

**Acceptance:** Demonstrate work beyond the pinned framework's default limit without hidden quotas, duplicated effects or lost state. Separately exercise a selected budget, cancellation, completion and a real runtime boundary; each must have its actual stop reason.

<a id="agt-004"></a>
### AGT-004: Separate active context from durable knowledge

Use application-versioned user, agent and project memory/skills through configured backends. Automatic writes require explicit scope policy, provenance and concurrent-write handling; protected instructions must not be overwritten. Fresh conversations retain selected project files and durable knowledge without inheriting the previous active context. Background consolidation is a visible job under the same policy, not training.

**Acceptance:** Start a fresh conversation against retained files/knowledge, edit and revert a memory version, and exercise a denied or conflicting write. Verify protected instructions are unchanged.

<a id="agt-005"></a>
### AGT-005: Do not silently remove enabled tools

Tool-selection middleware may narrow tools presented for a call, while application discovery keeps the full enabled catalogue accessible. Show selections and allow overrides; selection is context optimisation, not a new access-policy owner.

**Acceptance:** Narrow a call's tool list, then discover an enabled tool outside that list. A denied tool remains denied; an authorised tool is not permanently hidden by the selection.

<a id="agt-006"></a>
### AGT-006: Keep completion evidence distinct from judgement

Attach executable checks, expected artifacts and review criteria where a task has a definition of done. Preserve evidence and distinguish test outcomes from model assessments. The source identifies rubric middleware as a beta extension, not a prerequisite for completion checking.

**Acceptance:** Report one executable success/failure, one expected artifact and one model review separately. Verify that removing rubric integration does not remove basic acceptance checks.

## Unresolved details

Resolve [OQ-004](../open-questions.md#oq-004) for state/continuation semantics and [OQ-006](../open-questions.md#oq-006) for knowledge policy/storage and RAG surface-versus-shared ([AGT-004](#agt-004)). [OQ-011](../open-questions.md#oq-011) covers the durable product Approvals inbox. [OQ-015](../open-questions.md#oq-015) covers workflow import/export. Evaluate optional middleware under [OQ-009](../open-questions.md#oq-009). Exact constructor arguments, graph APIs and middleware defaults are version-specific and are not prescribed here.
