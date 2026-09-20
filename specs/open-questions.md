# Open architecture questions

Design choices not yet made. Recording a question is not permission to choose silently; source-derived selections (llama.cpp, Deep Agents, LangGraph, LangChain, one FastAPI backend, one Electron desktop) are not reopened here. Resolve a question with an [ADR](decisions/README.md) or a [changelog](decisions/changelog.md) entry and matching specification edits; keep the ID and mark it resolved. Defaults already decided under a question are in the changelog, not repeated here. No product question is currently waiting on David.

<a id="oq-001"></a>
## OQ-001: Repository layout, versions and reproducible setup

**Status:** resolved for layout and toolchain ([architecture](architecture.md#repository-layout-and-toolchain), Issue #1). **Remaining:** a clean install and build on David-PC has not been recorded as evidence.

<a id="oq-002"></a>
## OQ-002: Desktop/backend trust and communication

**Status:** partially decided (same-machine shared secret and loopback bind, Issue #40; SSE for same-machine run/chat events, [changelog](decisions/changelog.md)). **Owner:** backend/desktop boundary. **Blocks:** treating a remote backend as supported.

Decided for this machine: one `GET /v1/events` SSE stream (`run_id` or `conversation_id`), same `X-Workbench-Local-Token` header, FastAPI `EventSourceResponse`, reconnect `snapshot` then only `run_event`s newer than that snapshot ([API-006](modules/backend-desktop.md#api-006)). WebSockets are not the transport. Open: remaining origin/IPC checks; whether remote backend access is ever supported. An API bound locally must not be assumed secure solely because it is local. **Evidence needed:** reconnect behaviour under a dropped Electron client and a real Electron ↔ backend pairing on David-PC.

<a id="oq-003"></a>
## OQ-003: Worker protocol, isolation and access policy

**Status:** partially decided — the first environment is the **Windows host shell with approvals**, built on Deep Agents `permissions=` / `interrupt_on=` and `LocalShellBackend`; WSL and Docker later (product owner decision, 2026-09-19, [changelog](decisions/changelog.md#2026-09-19--product-owner-decisions-project-chat)). Host-shell approval flow for that environment is specified in [environments and tools](modules/environments-tools.md) (auto-allow read-only prefixes; otherwise `interrupt_on`; decisions on the run via `POST .../interrupt-decision`; no invented home cwd). **Owner:** environment/tool boundary. **Blocks:** browser or graphical execution; WSL, Docker or remote workers; sensitive mounts and installation rights beyond the approved host-shell policy.

Open: executable and network access and credential delivery; what the host shell exposes versus what later environments isolate; cancellation and teardown truth beyond reject-then-cancel on an interrupt; worker identity for later remote environments. MCP is discovery and invocation, not isolation. Chat browser access through the Playwright MCP product server is [ENV-007](modules/environments-tools.md#env-007), not an isolated browser worker, and does not close this question. A durable Approvals inbox remains [OQ-011](open-questions.md#oq-011). **Evidence recorded:** David-PC Chat HTTP approve and deny, plus no-project `shell_requires_project`, at `8887f9f` ([evidence](evidence/2026-09-19-david-pc-host-shell.md)). **Evidence still needed:** Electron Approve/Deny; cancel-while-interrupted on this machine; an attempt to exceed the approved boundary beyond the no-project 400; explicitly authorised host access versus isolated execution when later environments arrive.

<a id="oq-004"></a>
## OQ-004: Run state, events, continuation and uncertain effects

**Status:** partially decided (two databases and linkage #27; effects ledger #31; cancel honesty #42; Chat thread reuse #56). **Owner:** backend, agent and persistence boundaries jointly. **Blocks:** durable-run claims beyond the recorded linkage.

Open: identity formats and parent/child semantics beyond conversation → thread → run; remaining state transitions and stop reasons; whether the same thread can resume after a model or adapter change; exactly-once across databases, files and services. For this stream, event order is the append order of application `AgentEvent` rows; `run_event` seq is that 1-based index. After a reconnect `snapshot`, only later seq values stream ([API-006](modules/backend-desktop.md#api-006)). That is not an exactly-once claim across a backend restart. **Evidence needed:** cancel and crash tests around an external effect and a checkpoint boundary; continuation beyond a measured framework limit without duplicates.

<a id="oq-005"></a>
## OQ-005: Consistent project snapshots and restoration

**Status:** partially decided (directory snapshot #15; starting snapshot #65; restore integrity #66). **Owner:** persistence/environment boundary. **Blocks:** snapshot policy beyond the recorded defaults.

Open: retention; concurrent-writer handling beyond "fail if live"; environment-snapshot adapters; the boundary between project files and an environment snapshot. Do not assume checkpoints or git commits capture untracked files, dependencies, services or remote effects. **Evidence needed:** capture at a controlled boundary, restore into a separate workspace, exclusions visible, parent unchanged, on David-PC.

<a id="oq-006"></a>
## OQ-006: Memory, skills, retrieval and sensitive context

**Status:** partially decided (knowledge store #17; capture privacy #64; content loaded before run #57; retrieval v1 built 2026-09-20; memory/skills loading specified 2026-09-20; memory write-through specified 2026-09-20). **Research recorded 2026-09-19:** query-time RAG **is** in the first usable version, delivered through LangChain / Deep Agents retrieval components with little custom code ([changelog](decisions/changelog.md#2026-09-19--oq-006-retrieval-research-include-rag-in-v1); product owner's 2026-09-19 "if" is satisfied). Implemented as [STATE-006](modules/state-recovery.md#state-006) (`built`, not `verified`). **Research recorded 2026-09-20:** Deep Agents `memory=` / `skills=` replace the memory/skill system-prompt append ([changelog](decisions/changelog.md#2026-09-20--oq-006-memory-and-skills-replace-prompt-append); [AGT-004](modules/agents-workflows.md#agt-004), [STATE-005](modules/state-recovery.md#state-005)). Loading is `built`, not `verified`. **Research recorded 2026-09-20:** official `edit_file` / `write_file` on `/memories/**` write through to STATE-005 so David can see agent memories in Knowledge ([changelog](decisions/changelog.md#2026-09-20--oq-006-memory-edit_file-writes-through-to-knowledge); product owner, Chat-first auto-save, 2026-09-20). Write-through is specified, not implemented, not `verified`. Catalogue rows stay `built`. **Owner:** persistence/agent boundary. **Blocks:** a decision that a *durable* retrieval index or Deep Agents store is shared across surfaces; implementing a second knowledge store or a workbench-written retriever or memory middleware.

v1 retrieval shape: agentic retrieve-and-offload — `RecursiveCharacterTextSplitter`, `InMemoryVectorStore`, `OpenAIEmbeddings` against llama-server `POST /v1/embeddings`, a LangChain `@tool` that `similarity_search`es and writes chunks to `/retrieved/` on the existing `CompositeBackend` (harness scratch, never the project). The STATE-005 store stays the durable source; the vector index is derived per run. Retrieved documents are neither durable project memory nor training. Retrieval is requested only via `embedding_deployment_id`; missing or unloaded embedders fail closed.

v1 memory/skills loading: selected `memory` versions are always-load via `create_deep_agent(memory=)` (`MemoryMiddleware` + `/memories/` files); selected `skill` versions are progressive disclosure via `create_deep_agent(skills=["/skills/"])` (`SkillsMiddleware` + `SKILL.md`). Materialized files are derived per run on the existing composite (harness scratch), not a `StoreBackend` and not the `knowledge\` JSON tree. Protected instructions stay in `system_prompt=` / `compose_system_prompt` — the official memory fragment tells the model those files are untrusted data it may `edit_file`.

v1 memory write-through: a successful live-tool official `edit_file` / `write_file` on `/memories/**` becomes a new STATE-005 version (kind `memory`, `actor=agent`, `run_id` set) that Knowledge lists. That is the explicit automatic-write policy. Scratch `/memories/` stays derived and is discarded with the run; the durable copy is the new version. HTTP agent-origin `/v1/knowledge` writes still require `scope_policies`. Skills stay non-writable. Chat live-tool always attaches `memory=` (selected paths, or `/memories/user/chat.md` if none) so the official save prompt is present without a Knowledge form. Current code still leaves `/memories/` edits run-local until the write-through implementation PR.

Product-default dedicated embedding GGUF (operator registers and starts a deployment; the file is not a `bundle_*` record and the product does not start llama-server because the file exists): official `Qwen/Qwen3-Embedding-0.6B-GGUF` @ `370f27d7550e0def9b39c1f16d3fbaa13aa67728`, file `Qwen3-Embedding-0.6B-Q8_0.gguf`, SHA-256 `06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439`, 639150592 bytes. On David-PC the file is already at `%LOCALAPPDATA%\LocalAIWorkbench\models\Qwen3-Embedding-0.6B-Q8_0.gguf`. Recommended pooling for this GGUF is `last`.

Still open: whether a durable retrieval index or Deep Agents store is ever shared across Chat, Lab and Builder (v1 creates none); what capture gaps a restored run must report when retrieval, `memory=` / `skills=`, or write-through ran. **Evidence recorded:** David-PC Chat HTTP fail-closed (missing / chat-as-embedder / unloaded) and live `search_knowledge` writing `/retrieved/` under harness scratch at `7db7f45` ([evidence](evidence/2026-09-20-david-pc-retrieval.md)). **Evidence still needed:** recorded-tool replay without a live index; remaining fail-closed codes; Electron selectors; Lab / Agent-run HTTP; live `memory=` / `skills=` UAT (ordinary Chat with memory + skill + protected; project-less skill `read_file`; skill write denied); live write-through (not yet implemented). Unit tests with `DeterministicFakeEmbedding` are not retrieval evidence. Catalogue STATE-006, STATE-005 and AGT-004 stay `built`.

<a id="oq-007"></a>
## OQ-007: Compatibility evidence and model lifecycle details

**Status:** partially decided (CUDA pin and default profile #21; provenance records #31; deployment ownership #62; `load_mode`, `--mmproj` and `server_props` #81). **Owner:** model-management boundary. **Blocks:** declaring any model capability or runtime control supported.

Open: turning recorded `server_props` and tested adjustments into compatibility records and capability claims; the remaining startup and per-request controls (reasoning format, chat-template kwargs, thinking controls) against the pinned llama.cpp; cache reuse and interrupted downloads (pin currently re-downloads unconditionally); lifecycle authority over external endpoints. **Evidence needed:** a managed model with companion files, a connected service, an unfamiliar model and an applied-setting mismatch, all on David-PC (managed start without companions was seen live on 2026-09-19).

<a id="oq-008"></a>
## OQ-008: Registry schemas, compatibility and extension loading

**Status:** open. **Owner:** integration-registry boundary. **Blocks:** the first stored graph, third-party adapter or shared definition version.

Open: canonical schemas and identifiers, version compatibility and migration, invalidation of stale definitions, discovery and trust of extensions, skills/plugins discovery UX. No plugin sandbox or hot reload follows from the word "registry". **Evidence needed:** compatible/incompatible/unverified fixtures; reload against a changed definition; rejection after a permission change.

<a id="oq-009"></a>
## OQ-009: Optional experimental integrations

**Status:** partially decided — MCP is an **optional extra tool source**, not the default or only tool bus (product owner decision, 2026-09-20, [changelog](decisions/changelog.md#2026-09-20--oq-009-mcp-expansion-framework-first-servers-browser-and-github)). The durable expansion framework and the first two product servers (`browser`, `github`) are specified as [ENV-007](modules/environments-tools.md#env-007) (`planned`, not implemented, not `verified`). **Owner:** relevant adapter/harness/desktop boundary. **Blocks:** that integration only.

**Research recorded 2026-09-20:** the official client on the pinned stack is `langchain.mcp.MCPAdapter` via `langchain[mcp]` (`langchain==1.4.2`, extra pulls `fastmcp>=4.0.1,<5`). Do not add standalone `langchain-mcp-adapters`. Do not remake an MCP host. Tools from `list_tools()` merge into the existing `create_deep_agent(tools=)` list. MCP is not isolation ([OQ-003](open-questions.md#oq-003)); the Windows host shell remains the first worker. First product servers: official Playwright MCP (`@playwright/mcp`, pinned) and official GitHub remote MCP (`https://api.githubcopilot.com/mcp/` with a PAT). Core Chat must run with MCP disabled ([ARCH-007](architecture.md#arch-007)).

Still open: rubric and interpreter middleware (beta upstream), background consolidation, MCP Apps host support ([ENV-005](modules/environments-tools.md#env-005)), voice and multimodal surfaces. Voice means transcription, speech output and conversational interaction through established local components; transcription alone is not complete voice Chat. All stay optional. **Evidence needed:** each integration disabled and enabled with the same access, cancellation and event behaviour. ENV-007 evidence is in-process FastMCP plumbing plus David-PC Chat UAT of browser and GitHub; none exists yet.

<a id="oq-010"></a>
## OQ-010: Product verification commands and test environments

**Status:** partially decided (required CI checks on public `main`, Issue #76; two-tier evidence model, 2026-09-19; real-model smoke tier bound and registered, PR #82; GitHub CI slimmed to a Linux thin gate, product-owner decision 2026-09-20). **Owner:** boundary implementer. **Blocks:** calling a build stage verified.

Open: import-boundary check; integration tiers beyond the bound real-model smoke (managed Windows CUDA deployment, workers); MCP plumbing, when ENV-007 is implemented, is an in-process FastMCP check on the existing smoke tier rather than a new required workflow — Playwright/GitHub stay David-PC UAT; live-tool versus recorded fixtures as gates; David-PC UAT procedure and evidence retention; making `real-model-smoke` a required check (maintainer action); removing the retired Windows spec-integrity and Windows shared-contract-freshness names from classic branch protection (maintainer action). **Evidence needed:** registered commands run against real code at a recorded commit, including failure cases.

The 2026-09-20 slim does not return to Issue #36 advisory-only CI. Required Linux checks remain the merge gate. Windows GitHub jobs still run on matching paths and are not dropped. David-PC is the real Windows and capability check. Green unit tests are not catalogue `verified`.

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

**Status:** open. **Owner:** Lab boundary. **Blocks:** a task-case evaluation UX (datasets, scorers, compare-runs, export) beyond Inspect building blocks. Model Lab ([LAB-006](modules/lab-evaluation.md#lab-006)) is a separate feature. No second evaluation engine; Inspect is not assumed to be the whole Lab UX. **Evidence needed:** a documented compare or export path that preserves applied configuration and distinguishes executable checks from model judgement, with adapters named only after a reviewed decision.

<a id="oq-015"></a>
## OQ-015: Workflow definition import and export

**Status:** open. **Owner:** agent/workflow and registry boundaries. **Blocks:** shipping import/export. Interchange only; LangGraph remains the runtime and an imported graph is not executable authority without backend validation ([WF-001](modules/agents-workflows.md#wf-001)). **Evidence needed:** a round-trip or rejected import against a registered definition with configuration links still excluded from execution sequencing.

<a id="oq-016"></a>
## OQ-016: Builder canvas and chrome UX

**Status:** partially decided for v1 chrome ([ADR-0003](decisions/ADR-0003-builder-v1-chrome.md), draft). **Owner:** desktop and agent boundaries. **Blocks:** presenting Builder as a product surface.

Open: the React Flow canvas, node library, run-inspector wiring and UAT. The visual graph is never executable authority ([API-002](modules/backend-desktop.md#api-002)). **Evidence needed:** an implementation issue with matching specification, tests and live evidence.

<a id="oq-017"></a>
## OQ-017: One persistence strategy for application records

**Status:** storage choice resolved by the technical owner, 2026-09-20; migration remains unfinished. **Owner:** persistence boundary. **Decision:** [application record storage](decisions/ADR-0005-application-record-storage.md). New durable application record families use `application.sqlite`; existing JSON families keep their current format until an inventory-checked migration is ready.

**Remaining check:** inventory inference, compatibility, Lab and knowledge record families; migrate a copy of existing data; compare every record and reference; exercise restart, interrupted import and rollback before cutover. Retain original JSON and a database backup until the migration is validated. This does not block ordinary fixes, additive fields in existing stores, guided model setup, Chat continuity, capability evidence, or the minimum `/memories/**` write-through path. Current storage boundaries live in [architecture](architecture.md#persistence).
