# Agents and workflows

[Specification index](../README.md) · [Status and evidence](../catalog.json)

## Ownership, scope and source

Deep Agents owns each agent's model/tool loop and active context. LangGraph owns its runtime and Builder's outer graph. LangChain supplies adapters and interfaces. Source: [revision 0.5, page 5](../sources/README.md#agents-and-workflows) and [the connection rules on page 7](../sources/README.md#integration-registry).

## Public contracts and collaboration

Consume a resolved agent setup, model adapter, enabled tool/file backends, selected memory/skill versions and task criteria. Emit events into the backend's run hierarchy and link checkpoints through [state and recovery](state-recovery.md). Builder supplies typed step inputs/outputs; Chat invokes the same harness without requiring an outer workflow.

Memory content/versioning is application-owned; consumption and active-context management are harness responsibilities. Retrieved documents are neither durable project memory nor model training. Retrieval/index storage selection remains open.

## Lifecycle and failure

The backend exposes start, progress, intervention, pause/cancel and recovery as supported by the integration. Exactly how interrupts, threads, checkpoints and continuation map to a pinned framework version must be tested before claiming resumability. A disconnected client is not evidence a run ended. A cancel request is not a confirmed stop: `cancel_requested` means work may still be running; `cancelled` is the confirmed stop. Do not silently replay uncertain tool effects during recovery.

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

**Acceptance:** Demonstrate work beyond the pinned framework's default limit without hidden quotas, duplicated effects or lost state. Separately exercise a selected budget, cancellation, completion and a real runtime boundary; each must have its actual stop reason. A cancel request must be recorded as `cancel_requested` until the worker confirms stop as `cancelled`.

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

Resolve [OQ-004](../open-questions.md#oq-004) for state/continuation semantics. [OQ-006](../open-questions.md#oq-006) remains open for retrieval/RAG and cross-surface sharing; Issue #17 locked only the [STATE-005 store defaults](state-recovery.md#locked-milestone-defaults-issue-17-partial-oq-006) that [AGT-004](#agt-004) consumes. [OQ-011](../open-questions.md#oq-011) covers the durable product Approvals inbox. [OQ-015](../open-questions.md#oq-015) covers workflow import/export. [OQ-016](../open-questions.md#oq-016) records Builder v1 chrome as partially decided in [ADR-0003](../decisions/ADR-0003-builder-v1-chrome.md); the remainder is the unfinished Builder surface. [WF-001](#wf-001) behaviour is unchanged. Evaluate optional middleware under [OQ-009](../open-questions.md#oq-009). Exact constructor arguments, graph APIs and middleware defaults are version-specific and are not prescribed here.

The [AGT-001](#agt-001) Chat surface lands as debug-quality Chat on [Issue #22](https://github.com/Vidcar/thtaib/issues/22). Issue #12 delivered the embedded harness and an Agent-run debug panel. Agent-run is not Chat. This is not finished Chat polish.

[Issue #52](https://github.com/Vidcar/thtaib/issues/52) records the high-level [Agent Chat continuity and UX](#high-level-agent-chat-continuity-issue-52) product mapping (conversation ↔ execution thread ↔ run; continue vs fresh; history-edit / model-switch effects; what reaches the harness). That mapping does **not** close [OQ-004](../open-questions.md#oq-004) and is not a claim that current Chat implements continuity. Implementation is a later Agent Chat Issue ([#56](https://github.com/Vidcar/thtaib/issues/56) / [#37](https://github.com/Vidcar/thtaib/issues/37) area 1). Effective setup (selected vs loaded vs applied) is a sibling spec, not this section.

The [WF-001](#wf-001) backend definition compiler lands with [Issue #35](https://github.com/Vidcar/thtaib/issues/35): configuration connections resolve one Deep Agents setup, and only workflow connections compile into sequencing. That is not a Builder-shipped claim. v1 chrome remains locked in [ADR-0003](../decisions/ADR-0003-builder-v1-chrome.md) (config via node badge/popover, not a canvas config edge); [WF-001](#wf-001) behaviour is unchanged. [ARCH-003](../architecture.md#arch-003) is not reopened. The Agent-run panel is still not Builder. [WF-002](#wf-002) (delegation and cycle ownership) is deferred to Wave 2 and is not implemented here.

<a id="locked-milestone-defaults-issue-42-cancel-honesty"></a>
## Locked milestone defaults (Issue #42; cancel honesty / partial OQ-004)

These defaults are authorised by [Issue #42](https://github.com/Vidcar/thtaib/issues/42). They satisfy honest harness cancel request versus confirmed stop. They do **not** close [OQ-004](../open-questions.md#oq-004): identities, event-order/reconnection, exactly-once, worker-adapter interrupt truth and continuation beyond measured framework limits stay open.

- **Statuses:** `queued`, `running`, `cancel_requested`, `cancelled`, `completed`, `failed` from the [Issue #41](https://github.com/Vidcar/thtaib/issues/41) shared `RunLifecycleStatus`. Harness `AgentRun.status` is that enum. This slice does not reimplement the OpenAPI→TS generator.
- **Cancel request:** `POST /v1/agent-runs/{id}/cancel` (and Chat's cancel path through the same harness) transitions a live run to `cancel_requested`. `finished_at` stays unset. This is not a confirmed stop.
- **Confirmed stop:** the worker records `cancelled` only after it has stopped (or never started) because cancel was requested.
- **Quiescence:** `cancel_requested` is still live. Lab capture and “safe to treat the workspace as idle” must fail while any run for that workspace is `queued`, `running` or `cancel_requested`.
- **STATE-004 intersection:** a cancel request is not evidence that an in-flight external effect finished. Recovery still reports uncertainty and does not silently replay. See [STATE-004 locked defaults](state-recovery.md#locked-milestone-defaults-issue-42-cancel-honesty).
- **Not claimed:** full OQ-004 close; worker-adapter interrupt ([ENV-003](environments-tools.md#env-003)); durable Approvals inbox; host execute.

<a id="high-level-agent-chat-continuity-issue-52"></a>
## High-level Agent Chat continuity and UX (Issue #52)

These defaults are authorised by [Issue #52](https://github.com/Vidcar/thtaib/issues/52) as the high-level product spec for Agent Chat continuity and UX beyond [debug-quality Chat](../../docs/glossary.md#debug-quality-chat). They satisfy the documentation gap in [#37](https://github.com/Vidcar/thtaib/issues/37) area 1 (conversation ↔ execution-thread ↔ run; continue vs fresh; history-edit / model-switch effects; inspector honesty). They do **not** close [OQ-004](../open-questions.md#oq-004): identities, event-order/reconnection and exactly-once stay open. They do not rewrite closed [Issue #22](https://github.com/Vidcar/thtaib/issues/22) acceptance. They are not a catalogue `verified` claim and not an implementation.

Homes: [AGT-001](#agt-001), [AGT-002](#agt-002), [AGT-004](#agt-004); [STATE-001](state-recovery.md#state-001)/[STATE-002](state-recovery.md#state-002); [API-001](backend-desktop.md#api-001)/[API-004](backend-desktop.md#api-004); [ARCH-003](../architecture.md#arch-003) shared records only. Related: [#12](https://github.com/Vidcar/thtaib/issues/12), [#22](https://github.com/Vidcar/thtaib/issues/22), [#27](https://github.com/Vidcar/thtaib/issues/27), [#42](https://github.com/Vidcar/thtaib/issues/42). Implementation: [#56](https://github.com/Vidcar/thtaib/issues/56). Do not blur [Model Lab](../../docs/glossary.md#model-lab) or [Task cases and replay](../../docs/glossary.md#task-cases-and-replay). Effective setup (profile/knowledge actually applied) is [Issue #53](https://github.com/Vidcar/thtaib/issues/53), not this section.

### Conversation, execution thread and run

| Record | Owner | Meaning |
| --- | --- | --- |
| **Conversation** | Application Chat records in `application.sqlite` | Chat-surface identity: displayed history, bound project / deployment / profile refs, and links to runs. Not the working project. Not the harness loop. |
| **Execution thread** | Application-owned thread identity; LangGraph owns checkpoint bytes | Continuation identity the harness resumes. This is what **continue** uses. Exact namespace and identifier format stay [OQ-004](../open-questions.md#oq-004). |
| **Run** | Application run record plus harness lifecycle | One harness invocation (one turn). Status, events and checkpoint-id links live here. A run belongs to one conversation and one execution thread. |

- One conversation has zero or more runs. Listing historical run ids is not proof those runs share an execution thread.
- **Continue** = same conversation + same execution thread + new run.
- **Fresh** = new conversation (or an explicit reset that creates one) + new execution thread + no previous active context.
- The Agent-run debug panel is not a conversation and is not Chat.
- Deep Agents / LangGraph remain the loop. Do not add an application-written conversation or agent loop that replays the transcript as a substitute for the execution thread.

**Current code is not this mapping.** Debug-quality Chat stores a transcript and starts a new harness run with the latest task only; the reviewed path assigns a new thread per run. Displayed transcript is therefore not continued execution context. That is the [#37](https://github.com/Vidcar/thtaib/issues/37) area 1 gap. This section defines the intended relationship; it does not claim the current path implements it.

### Continue versus fresh

**Continue** is the normal follow-up on an existing conversation:

- Reuse the conversation and its execution thread. Start a new run for the new user turn.
- The harness resumes the intended active context through that thread / checkpoints, independently of the displayed transcript.
- After backend restart, reopen and continue use the persisted conversation → thread → run linkage ([STATE-001](state-recovery.md#state-001)). Missing linkage is an explicit gap, not a silent new thread presented as the same conversation.
- Do not start another turn while a run on that conversation is `queued`, `running` or `cancel_requested`.

**Fresh** is an explicit user action (New conversation):

- New conversation and new execution thread. Previous active context is not inherited ([AGT-004](#agt-004)).
- Selected project files and permitted durable knowledge are retained. Fresh does not delete or restore project files ([STATE-002](state-recovery.md#state-002)).
- Clearing only the desktop panel without creating a new conversation record is not the product Fresh action.

### What reaches the harness

On **continue** the harness receives:

- Resume of the execution thread / checkpoints (active context).
- The new user turn.
- The bound deployment and project workspace.
- Selected profile and knowledge version **references**. Whether those references are loaded or applied is the effective-setup contract ([Issue #53](https://github.com/Vidcar/thtaib/issues/53) / [ARCH-003](../architecture.md#arch-003) / [REG-005](registry.md#reg-005)); this section does not close that.
- Enabled tools that target project storage ([STATE-002](state-recovery.md#state-002)).
- The same cancel path as any other harness run ([Issue #42](https://github.com/Vidcar/thtaib/issues/42)).

On **continue** the harness does **not** receive the displayed transcript as a substitute for the execution thread, and it does not receive a second application-written agent loop.

On **fresh** the harness receives a new execution thread and the new turn only. Previous conversation active context is omitted. Project files and permitted durable knowledge remain available under the same [AGT-004](#agt-004) / [STATE-005](state-recovery.md#state-005) rules.

[AGT-002](#agt-002) remains the home for what the adapter actually sent. A stored reference or a visible transcript line is not that capture.

### History-edit effects

- Displayed history is application-owned ([STATE-002](state-recovery.md#state-002)). Editing or clearing it alone neither restores nor deletes project files.
- A display-only edit does not silently become the next model request. Continue after a display-only edit still resumes the execution thread.
- The inspector must show when displayed history and harness active context differ. Do not hide that divergence behind a matching transcript.
- If the user wants the edited history to become execution context, that is an explicit **new attempt** (new execution thread / linked branch), not a silent rewrite of the live thread. The exact branch / checkpoint mechanism stays [OQ-004](../open-questions.md#oq-004) / [STATE-003](state-recovery.md#state-003).
- A “start new attempt from edited history” control is not specified as shipped UX here. Until an implementation Issue adds it, history replace remains display-only.

### Model-switch effects

- Changing the selected deployment or profile on a conversation applies to the **next** run, not retroactively to past runs.
- A switch does not rewrite displayed history or project files.
- Selecting a profile or deployment is not proof the next request applied those settings. That proof is [Issue #53](https://github.com/Vidcar/thtaib/issues/53).
- Whether the same execution thread can continue after a model / adapter change is **open** ([OQ-004](../open-questions.md#oq-004) remainder / pinned-framework compatibility). Until an implementation Issue proves resume across that change, a switch that cannot resume the thread must be an explicit new attempt, not a silent continue.
- A model switch is not Fresh: the conversation and project may be retained. Resume of active context across the switch is the open part.

### Inspector honesty and UX beyond debug

Chat is a first-class surface, not the Agent-run debug panel. Beyond debug-quality Chat, the surface must:

- Distinguish conversation, execution thread and current / past runs when those identities exist, and show a gap when they do not.
- Label **continue** versus **fresh**.
- Show run lifecycle honestly (`cancel_requested` is still live; `cancelled` is confirmed stop; no false idle).
- Stream harness progress. A preview or model-confidence line is not completion ([API-004](backend-desktop.md#api-004)).
- Not present displayed transcript as proof the harness has that context.
- Not present profile or knowledge ids as applied ([Issue #53](https://github.com/Vidcar/thtaib/issues/53)).
- Support: open / continue a conversation; explicit Fresh; compose a turn; stream; cancel; see displayed history labelled as history; bind deployment, profile and project workspace.

This is not Chat polish (rich editor, token chrome, themes) and not a finished product claim.

### Open gaps (honest)

Leave these visible. Do not treat this section as closing them.

| Gap | Home |
| --- | --- |
| Exact thread / checkpoint identity format, parent/child semantics, event-order / reconnection, exactly-once | [OQ-004](../open-questions.md#oq-004) remainder |
| Event streaming / reconnection | [OQ-002](../open-questions.md#oq-002) remainder |
| Resume of the same execution thread after a model / adapter change | Open under [OQ-004](../open-questions.md#oq-004); product rule above (explicit new attempt until proven) |
| “New attempt from edited history” control and branch pairing | [OQ-004](../open-questions.md#oq-004) / [STATE-003](state-recovery.md#state-003); not shipped here |
| Selected vs loaded vs applied profile / knowledge | [Issue #53](https://github.com/Vidcar/thtaib/issues/53); [ARCH-003](../architecture.md#arch-003); [REG-005](registry.md#reg-005); [OQ-006](../open-questions.md#oq-006)/[007](../open-questions.md#oq-007) remainders |
| Files / images in Chat; project-free Chat; workspace ownership across surfaces | [#37](https://github.com/Vidcar/thtaib/issues/37) area 5; [delivery feature map](../../docs/delivery-feature-map.md#specs-still-needed) |
| Knowledge steer UX | Milestone #8; [#17](https://github.com/Vidcar/thtaib/issues/17) out of scope |
| Durable Approvals inbox | [OQ-011](../open-questions.md#oq-011) |
| Run observability outside Lab | [OQ-012](../open-questions.md#oq-012) |
| Command / browser / graphical workers | [OQ-003](../open-questions.md#oq-003); Milestone #5 |
| Builder | [OQ-016](../open-questions.md#oq-016) |
| Model Lab; Task cases and replay | Separate features; do not merge |

**Not claimed:** catalogue `verified`; current Chat continuity; closing [OQ-004](../open-questions.md#oq-004); effective setup; workers; Builder; Model Lab; Chat polish.
