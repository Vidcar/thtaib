# Agents and workflows

[Architecture](../architecture.md) · [Status and evidence](../catalog.json) · [Decisions](../decisions/changelog.md)

## Purpose

Run agent tasks through the embedded Deep Agents harness, keep Chat continuity honest, and compile Builder definitions so that configuration and workflow sequencing stay distinct.

## Boundaries and ownership

Deep Agents owns each agent's model/tool loop and active context. LangGraph owns the runtime, checkpoints and Builder's outer graph. LangChain supplies model, message and tool interfaces. The application owns the resolved setup, knowledge versions, run records, lifecycle visibility and cancellation semantics. Chat, Lab and Agent-run call the same harness; nothing in the application replays a transcript or loops over tools itself. Source: [Revision 0.5, page 5](../sources/README.md#agents-and-workflows) and [page 7](../sources/README.md#integration-registry).

## Interfaces and contracts

The harness consumes the resolved [effective setup](../architecture.md#effective-setup) (deployment, bags, tools and policy, knowledge versions), a task and an execution `thread_id`; it emits run events, checkpoint ids and captured model requests into the application run record. Routes: `/v1/agent-runs` (start, get, `cancel`, `interrupt-decision`), `/v1/agent-tools`, `/v1/chat/conversations` (create, list, get, `start`, `cancel`, `interrupt-decision`, `transcript`). Run lifecycle uses the shared `RunLifecycleStatus` (`queued`, `running`, `cancel_requested`, `cancelled`, `completed`, `failed`) from [contracts](../contracts.md). A Deep Agents `interrupt_on` pause keeps the run `running` and records `pending_interrupt`; it is not a new lifecycle status.

## Behaviour

**Harness.** `HarnessService.start` resolves the effective setup, then calls `create_deep_agent` with the model adapter, enabled tools, system prompt, application middleware, the SQLite checkpointer, `permissions=`, `interrupt_on=` and a Deep Agents backend. Enabled tools are visibility (`echo`, `time_now`) plus, when a project folder is bound, Deep Agents `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep` and host-shell `execute`. `task` and `delete` stay out of the enabled catalogue. Product discovery (`GET /v1/agent-tools`) lists the full nine-name catalogue (AGT-005). Selected knowledge versions are loaded as content before the run. Query-time retrieval, when the run names `embedding_deployment_id`, presents `search_knowledge` over a derived in-memory index ([STATE-006](state-recovery.md#state-006)). That tool is auto-presented for the run and is not added to the nine-name discovery catalogue. Knowledge-only runs stay prompt-append.

**System prompt composition.** `compose_system_prompt` prefers `profile.bags.agent.applied['system_prompt']` as the identity. A Chat (or other surface) system prompt must not silently replace it. When both are set and differ, the profile prompt is the base and the surface prompt is appended under `## Surface instructions`. Knowledge content is appended last.

**Host-shell interrupt.** `LocalShellBackend` and `interrupt_on` are attached together, and only when `execute` is presented on a project-bound live run. A write-only or echo-only live run keeps `FilesystemBackend` so Deep Agents does not put a live host shell on the tool node. Middleware also rejects `execute` unless it is presented. When the shell is attached, `interrupt_on` pauses dangerous commands. The harness streams `stream_mode="updates"` until a `__interrupt__` chunk (or `get_state().interrupts`), records `pending_interrupt` and an `interrupt` event, and waits. Desktop Chat and Agent-run show Approve/Deny. `POST .../interrupt-decision` resumes with `Command(resume={"decisions": [...]})` on the same checkpointer thread. Cancel while interrupted reject-resumes then finishes `cancelled`. This is the framework HITL mechanism, not [OQ-011](../open-questions.md#oq-011).

**Harness scratch isolation.** Live runs attach Deep Agents 0.7.15 `CompositeBackend` (`artifacts_root="/"`, longest-prefix routing that strips the matched prefix before forwarding). The default backend is the bound project when one is set (`LocalShellBackend(root_dir=project, virtual_mode=True, inherit_env=True)` only if `execute` is presented, otherwise `FilesystemBackend`), or an in-memory `StateBackend` with no project. Framework internals `/large_tool_results/`, `/conversation_history/` and `/retrieved/` (written by `FilesystemMiddleware` / summarization / retrieve-and-offload when `artifacts_root` is `/`) route to `{data_root}/state/harness/{thread_id}/`, never into the project and never into an invented stand-in folder. Recorded-tool mode still attaches no live backend. Sources: pinned package `deepagents==0.7.15` (`deepagents/backends/composite.py`, `deepagents/backends/local_shell.py`, `deepagents/middleware/filesystem.py`); [Deep Agents backends](https://docs.langchain.com/oss/python/deepagents/backends) (consulted 2026-09-19). The live docs example remounts the project at `/workspace/` and keeps internals on `StateBackend`; this product keeps `/` as the project root so existing `/hello.txt` paths, STATE-002 tests and smoke stay valid, and persists internals under the product data root instead of ephemeral state. Closed [DEV-004](../deviations.md#dev-004).

**Chat without a project.** David's decision (2026-09-19): Chat must work without a project folder. A conversation binds a deployment and optionally a profile and a project folder. With no project bound the harness runs with visibility tools only; filesystem and host-shell tools are absent from that run's enabled list and the Chat view reports `filesystem_tools_available=false` and `shell_tools_available=false`. An explicit request for a filesystem tool without a project is `filesystem_requires_project` (400); `execute` without a project is `shell_requires_project` (400). Binding a project later applies to the next run. Closed [DEV-003](../deviations.md#dev-003).

<a id="chat-continuity"></a>
**Chat continuity.** A *conversation* is the application Chat record (displayed history, bound deployment / profile and optional project, links to runs). An *execution thread* is the LangGraph `thread_id` the harness resumes. A *run* is one harness invocation for one turn. **Continue** = same conversation + same thread + new run; the harness resumes checkpoints, not the transcript. **Fresh** = new conversation + new thread; project files and durable knowledge stay, active context does not. A history edit is display-only: it changes no project file, no thread and no next request; the inspector shows when displayed history and harness active context differ instead of hiding the divergence behind a matching transcript. After restart, continue follows the persisted conversation → thread → run linkage; missing linkage is an explicit gap, never a silent new thread presented as the same conversation. A deployment or profile switch applies to the next run on the same thread; whether the thread can resume across a model change is unproven, so until proven such a switch must be an explicit new attempt rather than a silent continue. No new turn starts while a run on the conversation is `queued`, `running` or `cancel_requested`. An unhealthy or unreachable deployment is reported as `deploy_unhealthy` / `deploy_unreachable` and the run is `failed`; Chat never invents a reply.

**Progress and cancellation.** Harness progress is streamed to the surface over `GET /v1/events` ([API-006](backend-desktop.md#api-006)); a preview or a confident sentence is not completion, and a disconnected client is not evidence a run ended. The harness still reads LangGraph `stream_mode="updates"` and records application `AgentEvent` rows; SSE publishes those rows. A cancel request moves a live run to `cancel_requested` and nothing else; only the worker records `cancelled` once it has stopped. `cancel_requested` is still live for every quiescence check.

**Budgets.** No task-level time, token, call or revision ceilings by default. Framework limits (LangGraph recursion limit, middleware timeouts) are configured explicitly and reported as the real stop reason when hit.

**Definitions.** The backend compiles a Builder definition: configuration connections (profile, tools, skills, memory, environment, access, policy) resolve one agent setup; only workflow connections (next step, typed data/artifact handover) compile into sequencing. The result is a validated definition; the outer graph is built by LangGraph at run time.

## Requirements

<a id="agt-001"></a>
### AGT-001: Use the embedded harness

Run agent tasks with Deep Agents using LangChain components and LangGraph. Chat calls this harness directly, with or without a bound project folder; do not add an application-written model-and-tool loop.

**Acceptance:** Complete a real file-editing task through Chat with a project bound and inspect the execution path to confirm that the harness owns the model/tool iteration. Start a conversation with no project bound and confirm it runs with filesystem tools absent and reported as such.

<a id="wf-001"></a>
### WF-001: Keep configuration links out of execution sequencing

Configuration connections supply model profile, tools, skills, memory, environment, access and execution policy and resolve into one validated Deep Agents setup. Workflow connections define next steps and typed data/artifact handovers; only these compile into workflow sequencing.

**Acceptance:** Compile a mixed configuration/workflow definition and show that configuration links do not become executable workflow steps.

<a id="wf-002"></a>
### WF-002: Make delegation and cycle ownership explicit

Builder invokes Deep Agents as named subgraphs with declared inputs and outputs. Subagents remain child runs within their owning step. Expose delegation scope. General-purpose setups make supported planning and delegation available; specialist steps may explicitly narrow their role. Exactly one owner—the outer graph or agent step—controls each review cycle; do not silently duplicate workflow sequencing inside the harness.

**Acceptance:** Run an outer review loop with a delegating step and inspect the hierarchy. Demonstrate which owner decides to repeat and that the same cycle is not performed twice.

<a id="agt-002"></a>
### AGT-002: Capture the actual model request

Instrument the final model-adapter boundary after context middleware. Link actual instructions, memory/skill versions, retrieved material, available tools, summaries and offloaded content to each call. Expose capture gaps, usage and provenance with configurable local retention/redaction. The capture must agree with the effective setup the harness used. This is request visibility, not access to hidden model reasoning.

**Acceptance:** Capture a request after compaction and compare it with what the adapter sends, accounting explicitly for redaction and any capture gap.

<a id="agt-003"></a>
### AGT-003: Leave task budgets unset by default

Do not impose arbitrary task-level time, token, model/tool-call, reasoning-effort or revision ceilings. Optional budgets are user-selected. Explicitly configure framework/middleware limits and timeouts, support checkpointed continuation, and distinguish actual boundaries from product budgets. A limit or stalled-progress warning is not successful completion; no uncertain action may be replayed silently.

**Acceptance:** Demonstrate work beyond the pinned framework's default limit without hidden quotas, duplicated effects or lost state. Separately exercise a selected budget, cancellation, completion and a real runtime boundary; each must have its actual stop reason. A cancel request must be recorded as `cancel_requested` until the worker confirms stop as `cancelled`.

<a id="agt-004"></a>
### AGT-004: Separate active context from durable knowledge

Use application-versioned user, agent and project memory/skills through configured backends. Automatic writes require explicit scope policy, provenance and concurrent-write handling; protected instructions must not be overwritten. Fresh conversations retain selected project files and durable knowledge without inheriting the previous active context. Selected knowledge versions are loaded as content before the run; referencing an id is not loading. Background consolidation is a visible job under the same policy, not training.

**Acceptance:** Start a fresh conversation against retained files/knowledge, edit and revert a memory version, and exercise a denied or conflicting write. Verify protected instructions are unchanged.

<a id="agt-005"></a>
### AGT-005: Do not silently remove enabled tools

Tool-selection middleware may narrow tools presented for a call, while application discovery keeps the full enabled catalogue accessible. Show selections and allow overrides; selection is context optimisation, not a new access-policy owner.

**Acceptance:** Narrow a call's tool list, then discover an enabled tool outside that list. A denied tool remains denied; an authorised tool is not permanently hidden by the selection.

<a id="agt-006"></a>
### AGT-006: Keep completion evidence distinct from judgement

Attach executable checks, expected artifacts and review criteria where a task has a definition of done. Preserve evidence and distinguish test outcomes from model assessments. Rubric middleware is a beta extension, not a prerequisite for completion checking.

**Acceptance:** Report one executable success/failure, one expected artifact and one model review separately. Verify that removing rubric integration does not remove basic acceptance checks.

## Status and evidence

Rows AGT-001…006, WF-001, WF-002 in [the catalogue](../catalog.json). Chat → tool call → file and thread continuity were seen working live with a tiny model on Linux ([evidence](../evidence/2026-09-19-linux-live-smoke.md)) and with the preferred capability UAT model on David-PC ([evidence](../evidence/2026-09-19-david-pc-managed-inference.md)); those runs predate project-less Chat and CompositeBackend isolation. A later David-PC UAT at `8887f9f` ran a real host-shell `execute` through Chat (approve created a project file; deny did not) and a project-less conversation that refused `execute` ([evidence](../evidence/2026-09-19-david-pc-host-shell.md)). David-PC UAT at `7db7f45` ran a live `search_knowledge` that filled `retrieved_material` and wrote `/retrieved/` under harness scratch ([evidence](../evidence/2026-09-20-david-pc-retrieval.md)); that row is attached on STATE-006, not AGT-002. Compaction capture and cancellation have not been exercised live.

## Open questions

[OQ-004](../open-questions.md#oq-004) run identities, event order and exactly-once; [OQ-006](../open-questions.md#oq-006) retrieval remainder (durable shared index, automatic writes, restore capture gaps) after STATE-006 was built; [OQ-009](../open-questions.md#oq-009) optional middleware; [OQ-011](../open-questions.md#oq-011) Approvals inbox; [OQ-015](../open-questions.md#oq-015) workflow import/export; [OQ-016](../open-questions.md#oq-016) Builder surface. Profile `agent.system_prompt` is preferred over a Chat surface prompt (composed, not silently replaced).
