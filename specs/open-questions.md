# Open architecture questions

Design choices not yet made. Recording a question is not permission to choose silently; source-derived selections (llama.cpp, Deep Agents, LangGraph, LangChain, one FastAPI backend, one Electron desktop) are not reopened here. Resolve a question with an [ADR](decisions/README.md) or a [changelog](decisions/changelog.md) entry and matching specification edits; keep the ID and mark it resolved. Defaults already decided under a question are in the changelog, not repeated here. No product question is currently waiting on David.

<a id="oq-001"></a>
## OQ-001: Repository layout, versions and reproducible setup

**Status:** resolved for layout and toolchain ([architecture](architecture.md#repository-layout-and-toolchain), Issue #1). **Remaining:** a clean install and build on David-PC has not been recorded as evidence.

<a id="oq-002"></a>
## OQ-002: Desktop/backend trust and communication

**Status:** partially decided (same-machine shared secret and loopback bind, Issue #40). **Owner:** backend/desktop boundary. **Blocks:** any event streaming or reconnection claim; treating a remote backend as supported.

Open: the event transport (SSE or WebSocket) and reconnection contract to replace polling; remaining origin/IPC checks; whether remote backend access is ever supported. **Evidence needed:** reconnect behaviour under a dropped client and a real Electron ↔ backend pairing on David-PC.

<a id="oq-003"></a>
## OQ-003: Worker protocol, isolation and access policy

**Status:** partially decided — the first environment is the **Windows host shell with approvals**, built on Deep Agents `permissions=` / `interrupt_on=` and `LocalShellBackend`; WSL and Docker later (product owner decision, 2026-09-19, [changelog](decisions/changelog.md#2026-09-19--product-owner-decisions-project-chat)). **Owner:** environment/tool boundary. **Blocks:** browser or graphical execution; WSL, Docker or remote workers; sensitive mounts and installation rights beyond the approved host-shell policy.

Open: the approval flow for host-shell commands (what is auto-allowed, what interrupts, how a decision is recorded); command and path validation; what the host shell exposes versus what later environments isolate; cancellation and teardown truth; worker identity for later remote environments. MCP is discovery and invocation, not isolation. **Evidence needed:** a real task through the host shell with an approval granted and one denied, plus an attempt to exceed the approved boundary, on David-PC.

<a id="oq-004"></a>
## OQ-004: Run state, events, continuation and uncertain effects

**Status:** partially decided (two databases and linkage #27; effects ledger #31; cancel honesty #42; Chat thread reuse #56). **Owner:** backend, agent and persistence boundaries jointly. **Blocks:** durable-run claims beyond the recorded linkage.

Open: identity formats and parent/child semantics beyond conversation → thread → run; event ordering and reconnection; remaining state transitions and stop reasons; whether the same thread can resume after a model or adapter change; exactly-once across databases, files and services. **Evidence needed:** cancel and crash tests around an external effect and a checkpoint boundary; continuation beyond a measured framework limit without duplicates.

<a id="oq-005"></a>
## OQ-005: Consistent project snapshots and restoration

**Status:** partially decided (directory snapshot #15; starting snapshot #65; restore integrity #66). **Owner:** persistence/environment boundary. **Blocks:** snapshot policy beyond the recorded defaults.

Open: retention; concurrent-writer handling beyond "fail if live"; environment-snapshot adapters; the boundary between project files and an environment snapshot. **Evidence needed:** capture at a controlled boundary, restore into a separate workspace, exclusions visible, parent unchanged, on David-PC.

<a id="oq-006"></a>
## OQ-006: Memory, skills, retrieval and sensitive context

**Status:** partially decided (knowledge store #17; capture privacy #64; content loaded before run #57). **Retrieval/RAG is in the first usable version if it can be delivered through LangChain's supported retrieval components with little custom code** (product owner decision, 2026-09-19, [changelog](decisions/changelog.md#2026-09-19--product-owner-decisions-project-chat)) — a decision pending research, not yet a requirement. **Owner:** persistence/agent boundary. **Blocks:** automatic durable-knowledge writes without a scope policy; a decision that knowledge is shared across surfaces; any retrieval implementation before the research is recorded.

Next step: research the pinned LangChain retrieval components (document loaders, text splitters, vector stores and retrievers, and how Deep Agents `memory` / `skills` interact with them), record what is deliverable with little custom code, then write the requirement and its acceptance check here and in [state and recovery](modules/state-recovery.md). Still open: whether knowledge and retrieval are shared across Chat, Lab and Builder or surface-local; what capture gaps a restored run must report. Retrieved documents are neither durable project memory nor training. **Evidence needed:** a retrieval path that is not a second knowledge owner, and a redacted, retained capture on a real David-PC workload.

<a id="oq-007"></a>
## OQ-007: Compatibility evidence and model lifecycle details

**Status:** partially decided (CUDA pin and default profile #21; provenance records #31; deployment ownership #62). **Owner:** model-management boundary. **Blocks:** declaring any model capability or runtime control supported.

Open: complete startup and per-request setting mapping against the pinned llama.cpp (see [DEV-002](deviations.md#dev-002)); companion-file (`mmproj`) resolution; using `llama-server` `/props` for reported capabilities; cache reuse and interrupted downloads; lifecycle authority over external endpoints. **Evidence needed:** managed model with companion files, a connected service, an unfamiliar model and an applied-setting mismatch, all on David-PC.

<a id="oq-008"></a>
## OQ-008: Registry schemas, compatibility and extension loading

**Status:** open. **Owner:** integration-registry boundary. **Blocks:** the first stored graph, third-party adapter or shared definition version.

Open: canonical schemas and identifiers, version compatibility and migration, invalidation of stale definitions, discovery and trust of extensions, skills/plugins discovery UX. No plugin sandbox or hot reload follows from the word "registry". **Evidence needed:** compatible/incompatible/unverified fixtures; reload against a changed definition; rejection after a permission change.

<a id="oq-009"></a>
## OQ-009: Optional experimental integrations

**Status:** open. **Owner:** relevant adapter/harness/desktop boundary. **Blocks:** that integration only.

Open: rubric and interpreter middleware (beta upstream), background consolidation, MCP Apps host support, voice and multimodal surfaces, and whether MCP is the default tool bus or optional. All stay optional ([ARCH-007](architecture.md#arch-007)). **Evidence needed:** each integration disabled and enabled with the same access, cancellation and event behaviour.

<a id="oq-010"></a>
## OQ-010: Product verification commands and test environments

**Status:** partially decided (required CI checks on public `main`, Issue #76; two-tier evidence model, 2026-09-19). **Owner:** boundary implementer. **Blocks:** calling a build stage verified.

Open: import-boundary check; integration-test location and the real-model CI smoke tier; live-tool versus recorded fixtures as gates; David-PC UAT procedure and evidence retention. **Evidence needed:** registered commands run against real code at a recorded commit, including failure cases.

<a id="oq-011"></a>
## OQ-011: Durable product Approvals inbox

**Status:** open. **Owner:** backend/desktop and agent boundaries. **Blocks:** presenting approvals that survive reconnect and restart.

A LangGraph interrupt or Deep Agents `interrupt_on` is the mechanism; the product inbox (persistence, notification, presentation) is undesigned. **Evidence needed:** an approval that stays actionable after client disconnect and backend restart, with bypass denied on every path.

<a id="oq-012"></a>
## OQ-012: Run observability outside Lab

**Status:** open. **Owner:** backend, agent and Lab boundaries. **Blocks:** product-wide traces, token/cost accounting and parent/child observability.

Local traces, token and cost visibility and attribution outside Lab cases are undesigned. LangSmith or any hosted tracer is not the product home. **Evidence needed:** a local parent/child run with retained trace and cost fields and a statement of what is not captured.

<a id="oq-013"></a>
## OQ-013: Multi-model routing and hybrid deployments

**Status:** open. **Owner:** model-management boundary. **Blocks:** routing a task across models; mixing local GGUF with remote OpenAI-compatible endpoints.

The model manager stays the owner and llama.cpp the local engine; no second inference stack. **Evidence needed:** one routed or hybrid path that still uses deployment records with local and remote scopes distinguished.

<a id="oq-014"></a>
## OQ-014: Evaluation UX beyond Inspect

**Status:** open. **Owner:** Lab boundary. **Blocks:** a task-case evaluation UX (datasets, scorers, compare-runs, export) beyond Inspect building blocks. Model Lab ([LAB-006](modules/lab-evaluation.md#lab-006)) is a separate feature.

<a id="oq-015"></a>
## OQ-015: Workflow definition import and export

**Status:** open. **Owner:** agent/workflow and registry boundaries. **Blocks:** shipping import/export. Interchange only; LangGraph remains the runtime and an imported graph is not executable authority without backend validation ([WF-001](modules/agents-workflows.md#wf-001)).

<a id="oq-016"></a>
## OQ-016: Builder canvas and chrome UX

**Status:** partially decided for v1 chrome ([ADR-0003](decisions/ADR-0003-builder-v1-chrome.md), draft). **Owner:** desktop and agent boundaries. **Blocks:** presenting Builder as a product surface.

Open: the React Flow canvas, node library, run-inspector wiring and UAT. The visual graph is never executable authority ([API-002](modules/backend-desktop.md#api-002)). **Evidence needed:** an implementation issue with matching specification, tests and live evidence.

<a id="oq-017"></a>
## OQ-017: One persistence strategy for application records

**Status:** open; recommendation recorded. **Owner:** persistence boundary. **Blocks:** any new durable record family; any record-schema change that would need a migration.

Today runs, chat and the effects ledger live in `application.sqlite`, while bundles, profiles, deployments, import jobs, compatibility overrides, knowledge versions and Lab cases are JSON files under `state\` written by full atomic replace, with no file locking and no schema migration path. Two patterns mean two sets of failure modes and no place to put a migration. **Recommendation:** SQLite for all application records (one `application.sqlite`, versioned schema with an explicit migration step), files only for weights, workspaces, snapshots, artifacts and knowledge content bodies. This is a persistence-strategy change and needs an ADR; the migration is not part of the pack slimming. **Evidence needed:** a migration from the existing JSON stores that preserves every record and is reversible until cutover.
