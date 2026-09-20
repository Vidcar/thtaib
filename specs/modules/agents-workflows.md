# Agents and workflows

[Architecture](../architecture.md) · [Status and evidence](../catalog.json) · [Decisions](../decisions/changelog.md)

## Purpose

Run agent tasks through the embedded Deep Agents harness, keep Chat continuity honest, and compile Workflows definitions so that configuration and execution connections stay distinct. **Agent run / Builder** remain existing UI and legacy contract terminology.

## Boundaries and ownership

Deep Agents owns each agent's model/tool loop and active context. LangGraph owns the runtime, checkpoints and the outer workflow graph. LangChain supplies model, message and tool interfaces. The application owns the resolved setup, knowledge versions, run records, lifecycle visibility and cancellation semantics. Chat, Lab and Agent-run call the same harness; nothing in the application replays a transcript or loops over tools itself. Source: [Revision 0.5, page 5](../sources/README.md#agents-and-workflows) and [page 7](../sources/README.md#integration-registry).

## Interfaces and contracts

The harness consumes the resolved [effective setup](../architecture.md#effective-setup) (deployment, bags, tools and policy, knowledge versions), a task and an execution `thread_id`; it emits run events, checkpoint ids and captured model requests into the application run record. Routes: `/v1/agent-runs` (start, get, `cancel`, `interrupt-decision`), `/v1/agent-tools`, `/v1/chat/conversations` (create, list, get, `start`, `cancel`, `interrupt-decision`, `transcript`). Run lifecycle uses the shared `RunLifecycleStatus` (`queued`, `running`, `cancel_requested`, `cancelled`, `completed`, `failed`) from [contracts](../contracts.md). A Deep Agents `interrupt_on` pause keeps the run `running` and records `pending_interrupt`; it is not a new lifecycle status.

## Behaviour

**Baseline configuration and continuity.** Chat start requests distinguish omitted optional bindings (unchanged), a value (set), and explicit JSON `null` (clear). Clearing project access detaches both project and workspace and removes stale project retrieval paths; it does not erase earlier messages or checkpoint content. Historical runs retain their original configuration. Conversation turn admission and mutations are coordinated per conversation. Terminal assistant replies are merged durably and idempotently through the application store, including completion before turn linkage is saved; readers do not own persistence. Display-only history replacement remains intentional and is never replayed as model context.

**Unavailable bindings and restart.** A detached connection leaves Chat history readable with `deploy_missing`; a later turn requires deliberate model selection. Connected health observations update availability without granting process ownership. Persisted live runs without an owned worker become failed/orphaned with external effects unresolved, rather than remaining busy indefinitely. Checkpoint-backed pending approvals stay actionable through the existing Deep Agents decision mechanism, with one reserved continuation owner. Cancelling a known waiting approval rejects that pending command; interrupted external work is never silently replayed or described as confirmed stopped.

**Applied settings and request evidence.** The agent profile keys `tools_enabled` and `max_iterations` are unsupported, retained as requested with an explanation, and excluded from applied values. `system_prompt`, supported per-request generation settings and explicit `max_steps` retain their real consumers; optional budgets stay unset. Model captures distinguish preparation, each observed transport attempt, an actual HTTP response and normal handler return. Failure paths retain retries under the same redaction/retention policy and rethrow the original error. A transport observation is not proof of server receipt; a scripted model response is not an HTTP response.

**Knowledge materialization.** Selected memories use `/memories/{scope}/{entry_id}.md`; skills use `/skills/{slug}/SKILL.md` with Agent Skills YAML `name` and `description`, matching the directory slug. Pass `skills=["/skills/"]`; omit an unbound memory/skills kwarg rather than passing `[]`. Fail closed with `skill_materialize_invalid`, `skill_name_collision` or `knowledge_materialize_failed`. Official memory files are untrusted editable data, so protected instructions must stay outside that mechanism. Request capture observes the outbound request after MemoryMiddleware; unread skill bodies remain off the wire.

**Intended Chat memory defaults.** The write-through design attaches `memory=` to every live-tool Chat (selected paths, otherwise `/memories/user/chat.md`) and presents `edit_file` / `write_file` only for `/memories/**`, including project-free Chat. `filesystem_tools_available` still describes the project. Lab and Agent-run do not force a default memory file. Successful durable writes update conversation/run `memory_version_refs` for the next turn. This is intent; the current scratch-only gap remains [DEV-006](../deviations.md#dev-006).

**Harness.** `HarnessService.start` resolves the effective setup, then calls `create_deep_agent` with the model adapter, enabled tools, system prompt, application middleware, the SQLite checkpointer, `permissions=`, `interrupt_on=`, a Deep Agents backend, and - when those kinds are selected - official `memory=` and `skills=`. Current implemented tools are visibility (`echo`, `time_now`) plus official planning (`write_todos` through `TodoListMiddleware` when selected), and, when a project folder is bound, Deep Agents `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep` and host-shell `execute`; `delete`, `task` and general delegation are not presented today. Product discovery (`GET /v1/agent-tools`) lists the current product catalogue (AGT-005), including planning, and must not imply unsupported delegation. Planning uses upstream middleware state for the run, not an application-owned planning store. Delegation remains deferred until child setup propagation, Workbench middleware inheritance, permissions and run hierarchy are verified; specialist setups may still narrow tools. Selected knowledge versions are loaded as content before the run: `memory` versions through `memory=` (`MemoryMiddleware`), `skill` versions through `skills=` (`SkillsMiddleware`), protected instructions through `system_prompt=`. Query-time retrieval, when the run names `embedding_deployment_id`, presents `search_knowledge` over a derived in-memory index ([STATE-006](state-recovery.md#state-006)). That tool is auto-presented for the run and is not added to the discovery catalogue. The planned MCP path (not implemented) uses selected `mcp_server_ids` and official `langchain.mcp.MCPAdapter` to discover server tools and they merge into the same `tools=` list, namespaced `{slug}_{tool}`, also not added to the local discovery catalogue ([ENV-007](environments-tools.md#env-007)). Knowledge-only runs do not fail closed and do not stuff memory or skill bodies into `compose_system_prompt`. A successful live-tool official `edit_file` / `write_file` on `/memories/**` write-throughs a STATE-005 memory version (specified, not implemented).

**System prompt composition.** `compose_system_prompt` prefers `profile.bags.agent.applied['system_prompt']` as the identity. A Chat (or other surface) system prompt must not silently replace it. When both are set and differ, the profile prompt is the base and the surface prompt is appended under `## Surface instructions`. Protected-instruction content is appended after that. Memory and skill bodies are not appended here; Deep Agents injects them via `memory=` / `skills=`.

**Host-shell interrupt.** `LocalShellBackend` and `interrupt_on` are attached together, and only when `execute` is presented on a project-bound live run. A write-only or echo-only live run keeps `FilesystemBackend` so Deep Agents does not put a live host shell on the tool node. Middleware also rejects `execute` unless it is presented. When the shell is attached, `interrupt_on` pauses dangerous commands. The harness streams `stream_mode="updates"` until a `__interrupt__` chunk (or `get_state().interrupts`), records `pending_interrupt` and an `interrupt` event, and waits. Desktop Chat and Agent-run show Approve/Deny. `POST .../interrupt-decision` resumes with `Command(resume={"decisions": [...]})` on the same checkpointer thread. Cancel while interrupted reject-resumes then finishes `cancelled`. MCP tool approvals compose into the same `interrupt_on` map; MCP elicitation resumes with `Command(resume={"responses": …})` and a distinct `pending_interrupt.kind`. This is the framework HITL mechanism, not [OQ-011](../open-questions.md#oq-011).

**Harness scratch isolation.** Live runs attach Deep Agents 0.7.15 `CompositeBackend` (`artifacts_root="/"`, longest-prefix routing that strips the matched prefix before forwarding). The default backend is the bound project when one is set (`LocalShellBackend(root_dir=project, virtual_mode=True, inherit_env=True)` only if `execute` is presented, otherwise `FilesystemBackend`), or an in-memory `StateBackend` with no project. Framework internals `/large_tool_results/`, `/conversation_history/` and `/retrieved/` (written by `FilesystemMiddleware` / summarization / retrieve-and-offload when `artifacts_root` is `/`) and derived knowledge files `/memories/` and `/skills/` (written by the harness for `memory=` / `skills=`) route to `{data_root}/state/harness/{thread_id}/`, never into the project, never into `knowledge\`, and never into an invented stand-in folder. Recorded-tool mode still attaches no live project, host-shell, retrieval backend, or MCP adapter; knowledge routes may use scratch or `StateBackend` so official memory/skills middleware can `download_files`. Sources: pinned package `deepagents==0.7.15` (`deepagents/backends/composite.py`, `deepagents/backends/local_shell.py`, `deepagents/middleware/filesystem.py`, `deepagents/middleware/memory.py`, `deepagents/middleware/skills.py`); [Deep Agents backends](https://docs.langchain.com/oss/python/deepagents/backends), [memory](https://docs.langchain.com/oss/python/deepagents/memory) and [skills](https://docs.langchain.com/oss/python/deepagents/skills) (consulted 2026-09-20 against the 0.7.15 wheel). The live docs example remounts the project at `/workspace/` and keeps internals on `StateBackend`; this product keeps `/` as the project root so existing `/hello.txt` paths, STATE-002 tests and smoke stay valid, and persists internals under the product data root instead of ephemeral state. Closed [DEV-004](../deviations.md#dev-004).

**Chat without a project.** Chat binds a deployment and optionally a profile/project. Without a project, visibility and selected planning tools are available; project file and shell tools are absent. Selected memory/skills add read access to their derived routes. Skill bodies stay immutable through tools. Memory write-through and MCP extra tools are specified extensions, not currently enabled project-free write access or connected MCP behavior. Explicit requests for project file/shell tools without a project fail with actionable errors. There is no invented project directory. Optional project ownership stays with shared application workspace records; Chat, Lab and Workflows reuse it.

<a id="chat-continuity"></a>
**Chat continuity.** A *conversation* is the application Chat record (displayed history, bound deployment / profile and optional project, links to runs). An *execution thread* is the LangGraph `thread_id` the harness resumes. A *run* is one harness invocation for one turn. **Continue** = same conversation + same thread + new run; the harness resumes checkpoints, not the transcript. **Fresh** = new conversation + new thread; project files and durable knowledge stay, active context does not. A history edit is display-only: it changes no project file, no thread and no next request; the inspector shows when displayed history and harness active context differ instead of hiding the divergence behind a matching transcript. After restart, continue follows the persisted conversation → thread → run linkage; missing linkage is an explicit gap, never a silent new thread presented as the same conversation. A deployment or profile switch applies to the next run on the same thread; whether the thread can resume across a model change is unproven, so until proven such a switch must be an explicit new attempt rather than a silent continue. No new turn starts while a run on the conversation is `queued`, `running` or `cancel_requested`. An unhealthy or unreachable deployment is reported as `deploy_unhealthy` / `deploy_unreachable` and the run is `failed`; Chat never invents a reply.

**Progress and cancellation.** Harness progress is streamed to the surface over `GET /v1/events` ([API-006](backend-desktop.md#api-006)); a preview or a confident sentence is not completion, and a disconnected client is not evidence a run ended. The harness still reads LangGraph `stream_mode="updates"` and records application `AgentEvent` rows; SSE publishes those rows. A cancel request moves a live run to `cancel_requested` and nothing else; only the worker records `cancelled` once it has stopped. `cancel_requested` is still live for every quiescence check.

**Budgets.** Product task-level time, token, call or revision ceilings are optional and unset by default. Per-request generation limits are separate. Current code maps explicit `max_steps` to LangGraph recursion limits; absent that override it still inherits a framework boundary. Long-run acceptance must demonstrate supported checkpointed continuation past measured framework boundaries when user budgets permit, stop at an explicit user budget, and report actual stop reasons. Precise technical stop-reason reporting remains required follow-up (DEV-006). Do not substitute a huge recursion constant, application retry loop or unsupported unlimited-task claim.

**Definitions.** The backend compiles a workflow definition: configuration connections (profile, tools, skills, memory, environment, access, policy) resolve the owning agent or step setup; only workflow connections (next step, typed data/artifact handover) compile into sequencing. Current implementation is a partial compiler that validates definitions; it is not a shipped Workflows editor and must not be described as full workflow execution. A blanket "all cycles invalid" rule is not the permanent architecture: intentional review cycles are allowed only when exactly one owner controls the repeat and LangGraph execution, typed inputs/outputs, policy and observable run hierarchy are connected.

## Requirements

<a id="agt-001"></a>
### AGT-001: Use the embedded harness

Run agent tasks with Deep Agents using LangChain components and LangGraph. Chat calls this harness directly, with or without a bound project folder; do not add an application-written model-and-tool loop.

**Acceptance:** Complete a real file-editing task through Chat with a project bound and inspect the execution path to confirm that the harness owns the model/tool iteration. Start a conversation with no project bound and confirm it runs with filesystem tools absent and reported as such.

<a id="wf-001"></a>
### WF-001: Keep configuration links out of execution sequencing

Configuration connections supply model profile, tools, skills, memory, environment, access and execution policy and resolve per owning agent or step, with explicit inheritance and overrides. Workflow connections define next steps and typed data/artifact handovers; only these compile into workflow sequencing.

**Acceptance:** Compile a mixed configuration/workflow definition with at least two owning agents or steps. Show that configuration links affect the intended owner setup without becoming executable workflow steps or flattening every agent into one global setup.

<a id="wf-002"></a>
### WF-002: Make delegation and cycle ownership explicit

Workflows invoke Deep Agents as named subgraphs with declared inputs and outputs. Subagents remain child runs within their owning step. Expose delegation scope. General-purpose setups make supported planning and delegation available; specialist setups and explicit user choices may narrow them. Every child receives the intended model, tools, context policy and access restrictions without escalation. Exactly one owner—the outer LangGraph workflow or its agent step—controls each review cycle; do not duplicate sequencing inside the harness. Current planning is wired through `TodoListMiddleware`; delegation and declared workflow cycles remain implementation gaps, not exceptions to this intended behavior.

**Acceptance:** Run an outer review loop with a delegating step and inspect the hierarchy. Demonstrate which owner decides to repeat and that the same cycle is not performed twice.

<a id="agt-002"></a>
### AGT-002: Capture the actual model request

Instrument the final model-adapter boundary after context middleware (including official `MemoryMiddleware` and `SkillsMiddleware` when those kwargs are passed). Link actual instructions, memory/skill versions, retrieved material, available tools, summaries and offloaded content to each call. Memory bodies and the skill index must appear in the captured / outbound request; unread skill bodies must not. Expose capture gaps, usage and provenance with configurable local retention/redaction. The capture must agree with the effective setup the harness used. This is request visibility, not access to hidden model reasoning.

**Acceptance:** Capture a request after compaction and compare it with what the adapter sends, accounting explicitly for redaction and any capture gap.

<a id="agt-003"></a>
### AGT-003: Leave task budgets unset by default

Do not impose arbitrary task-level time, token, model/tool-call, reasoning-effort or revision ceilings. Optional budgets are user-selected. Explicitly configure framework/middleware limits and timeouts, support checkpointed continuation, and distinguish actual boundaries from product budgets. A limit or stalled-progress warning is not successful completion; no uncertain action may be replayed silently.

**Acceptance:** Demonstrate work beyond the pinned framework's default limit when user budgets permit, using checkpointed continuation without hidden quotas, duplicated effects or lost state. Separately exercise a selected budget, cancellation, completion and a real runtime boundary; each must have its actual stop reason. A cancel request must be recorded as `cancel_requested` until the worker confirms stop as `cancelled`.

<a id="agt-004"></a>
### AGT-004: Separate active context from durable knowledge

Use application-versioned user, agent and project memory/skills through configured backends. Automatic writes require explicit scope policy, provenance and concurrent-write handling; protected instructions must not be overwritten. The named policy is live-tool official `edit_file` / `write_file` on `/memories/**` writing through to STATE-005 kind `memory` (`actor=agent`, `run_id` set) so Knowledge shows the new version; HTTP agent-origin writes still require `scope_policies`. Fresh conversations retain selected project files and durable knowledge without inheriting the previous active context. Selected knowledge versions are loaded as content before the run; referencing an id is not loading. Kind `memory` is loaded through official Deep Agents `memory=` (always-load files under `/memories/` on the run composite). Kind `skill` is loaded through official `skills=` (progressive disclosure of `/skills/{slug}/SKILL.md`) and stays non-writable. Kind `protected_instruction` is loaded through `system_prompt=` / `compose_system_prompt`, not `memory=`. Derived backend files are discarded with the run and are not a second store; a memory write-through updates conversation and run `memory_version_refs` so the next turn rematerializes the new version. Background consolidation is a visible job under the same policy, not training. Write-through is specified, not implemented.

**Acceptance:** Start a fresh conversation against retained files/knowledge, edit and revert a memory version, and exercise a denied or conflicting write. Verify protected instructions are unchanged.

<a id="agt-005"></a>
### AGT-005: Do not silently remove enabled tools

Tool-selection middleware may narrow tools presented for a call, while application discovery keeps the current enabled product catalogue accessible and distinguishes implemented planning from deferred delegation. Show selections and allow supported overrides; selection is context optimisation, not a new access-policy owner.

**Acceptance:** Narrow a call's tool list, then discover an enabled tool outside that list. A denied tool remains denied; an authorised tool is not permanently hidden by the selection.

<a id="agt-006"></a>
### AGT-006: Keep completion evidence distinct from judgement

Attach executable checks, expected artifacts and review criteria where a task has a definition of done. Preserve evidence and distinguish test outcomes from model assessments. Rubric middleware is a beta extension, not a prerequisite for completion checking.

**Acceptance:** Report one executable success/failure, one expected artifact and one model review separately. Verify that removing rubric integration does not remove basic acceptance checks.

## Status and evidence

Status is owned by rows AGT-001...006, WF-001 and WF-002 in [the catalogue](../catalog.json).

## Open questions

[OQ-004](../open-questions.md#oq-004) run identities, event order and exactly-once; [OQ-006](../open-questions.md#oq-006) remainder (durable shared index or store, restore capture gaps) after STATE-006 was built and memory/skills loading and write-through were specified; [OQ-009](../open-questions.md#oq-009) remaining optional middleware (MCP expansion is specified as [ENV-007](environments-tools.md#env-007), not implemented); [OQ-011](../open-questions.md#oq-011) Approvals inbox; [OQ-015](../open-questions.md#oq-015) workflow import/export; [OQ-016](../open-questions.md#oq-016) Workflows surface.
