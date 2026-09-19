# Open architecture questions

These are deliberately unresolved. They are not permission for an agent to choose a new architecture silently. Source-derived selections such as llama.cpp, Deep Agents, LangGraph, LangChain and the modular backend are **not** reopened by this list.

All entries are initially **open**. Owners below are responsibility roles, not assertions that particular accounts have been assigned. Resolve an entry by retaining its ID, recording the approved ADR/specification change and linking the evidence; do not delete its history.

Later-decision product topics are recorded here so they stay visible and unresolved: amend [OQ-003](#oq-003), [OQ-006](#oq-006), [OQ-008](#oq-008) and [OQ-009](#oq-009); add [OQ-011](#oq-011) through [OQ-015](#oq-015). Builder canvas and chrome UX is [OQ-016](#oq-016). Recording a topic is not a selection, a silent default, or an ADR. Real choices later use [the decision template](templates/decision.md) and maintainer approval.

<a id="oq-001"></a>
## OQ-001: Repository layout, versions and reproducible setup

**Status:** layout and toolchain pins are recorded for the Windows-first scaffold ([Issue #1](https://github.com/Vidcar/thtaib/issues/1)). Remaining evidence is UAT on David-PC. This does not close [OQ-002](open-questions.md#oq-002).

**Owner:** Backend/desktop maintainers. **Blocks:** first application scaffold or dependency installation represented as the supported setup.

Inspect any existing repository first. The supported scaffold is now:

- Layout: `apps/backend/`, `apps/desktop/`; keep root `specs/`, `scripts/`, `tests/specs/`.
- Python **3.12.x** via **uv**; `apps/backend/pyproject.toml` and `apps/backend/uv.lock`; import path `workbench_backend` under `apps/backend/src/`.
- Node **≥22 <25** (develop on 24); **pnpm**; `apps/desktop/package.json` and `apps/desktop/pnpm-lock.yaml`.
- Desktop stack: Electron + Vite + React + TypeScript + React Flow, pinned in the desktop lockfile.
- Windows packaging: desktop-owned **electron-builder** (NSIS). The package script is registered; an installer is not required for this milestone.
- Docker: stub `infra/docker-compose.yml` only; no product services.

Bound map entries: `backend-source`, `desktop-source`, `python-dependency-manifest`, `python-lockfile`, `desktop-dependency-manifest`, `desktop-lockfile`, `runtime-manifest`, `compatibility-records`. Working commands are in [commands.md](commands.md). Terms are in [the glossary](../docs/glossary.md).

**Evidence needed:** a clean setup and minimal backend/desktop build on the claimed platform (David-PC). Do not infer this from the specification checker's Python version.

<a id="oq-002"></a>
## OQ-002: Desktop/backend trust and communication

**Owner:** Backend/desktop boundary. **Blocks:** connecting a privileged API or desktop to real tools, files or credentials.

Choose local transport/IPC, API authentication and origin checks, Electron trust boundaries, secret handling, event streaming/reconnection and endpoint exposure. Define whether remote backend access is supported; remote workers do not automatically imply an internet-exposed backend. The source names FastAPI and Electron but does not select these controls.

**Evidence needed:** contract fixtures plus denied unauthorised requests, reconnect behaviour and a real desktop/backend interaction. An API bound locally must not be assumed secure solely because it is local.

<a id="oq-003"></a>
## OQ-003: Worker protocol, isolation and access policy

**Owner:** Environment/tool boundary. **Blocks:** real shell/browser/graphical execution, sensitive file mounts or installation permissions.

Define worker identity/authentication, command/filesystem/browser protocol, host versus container/WSL/remote paths, permission enforcement, approvals, cancellation, teardown and support per platform. Decide exactly what a disposable environment isolates and what it exposes. Establish path validation, executable/network access and credential delivery. These are necessary security details, not features supplied automatically by Docker or MCP.

This is the isolation question. Tool/worker sandbox isolation — what a disposable environment isolates versus exposes, including host versus container/WSL/remote — stays here; do not open a second isolation OQ. MCP standardises discovery and invocation; it is not an isolation boundary and does not supply worker sandboxing. Whether MCP is the default tool bus or an optional integration is [OQ-009](#oq-009), not a silent default here.

**Evidence needed:** a declared environment running a real task plus attempts to exceed its selected access boundary. Test explicit authorised host access separately from isolated execution.

<a id="oq-004"></a>
## OQ-004: Run state, events, continuation and uncertain effects

**Owner:** Backend, agent/workflow and persistence boundaries jointly; backend maintains the shared contract. **Blocks:** durable runs, recovery, long-running continuation or cross-process cancellation claims.

Define identities, parent/child linkage, thread/checkpoint namespaces, event ordering/reconnection, state transitions and actual stop reasons. Map framework limits and interrupts to the pinned versions. Define acknowledgement/reconciliation for external effects and when retry, reconnect, resume, restart or human intervention is safe. Do not claim an exactly-once transaction across databases, files and services.

A durable product Approvals inbox is [OQ-011](#oq-011); a framework interrupt is not that inbox. Run observability outside Lab is [OQ-012](#oq-012). Builder canvas run affordances (Run/stop; active step on the canvas versus a run inspector) are [OQ-016](#oq-016). Those questions do not reopen this run-state contract.

**Evidence needed:** cancellation and crash tests before/after an external effect and checkpoint boundary, plus continuation beyond a measured upstream limit without duplicates.

<a id="oq-005"></a>
## OQ-005: Consistent project snapshots and restoration

**Status:** partially constrained by [Issue #15](https://github.com/Vidcar/thtaib/issues/15) for Lab reuse. The question stays open.

**Owner:** Persistence/environment boundary. **Blocks:** remaining snapshot policy beyond the locked defaults — retention, concurrent-writer details beyond “fail if live tools are writing”, environment-snapshot adapters, and any mechanism other than the application-owned directory snapshot.

Issue #15 locked these defaults for LAB-001…004 and STATE-003. They are recorded in [Lab integration](modules/lab-evaluation.md#locked-milestone-defaults-issue-15-partial-oq-005) and [state and recovery](modules/state-recovery.md). Do not invent a different snapshot mechanism:

- Application-owned directory snapshot of the allowlisted project workspace at a quiescent capture boundary (fail if live tools are still writing).
- Store under `%LOCALAPPDATA%\LocalAIWorkbench\cases\` and `snapshots\`. Not git-commit-as-snapshot.
- Restore into a new workspace directory; linked branch run; never overwrite the parent.
- Include allowlisted project files, task, profile/deployment ids, dependency versions, memory/skill version refs, tool fixtures and acceptance checks.
- Exclude secrets, weights/GGUF, `.scratch`, `.venv`, `node_modules` and env credentials.
- No full environment restore this milestone; record exclusions.

Choose the snapshot mechanism, quiescent/consistent capture boundary, concurrent writer policy, included/excluded files, metadata and memory/configuration linkage, workspace isolation, retention and restoration validation. Define the boundary between project files and an environment snapshot. Do not assume checkpoints or Git commits capture untracked files, dependencies, services or remote effects.

**Evidence needed:** capture during a controlled execution boundary, restore into a separate workspace, verify included inputs, expose exclusions and show the parent remains unchanged. UAT of the locked defaults remains local-machine-required on David-PC.

<a id="oq-006"></a>
## OQ-006: Memory, skills, retrieval and sensitive context

**Owner:** Persistence/agent boundary. **Blocks:** automatic durable knowledge updates or retention of real sensitive context.

Choose storage representations, scope precedence, protected instructions, versioning/provenance, concurrent-write handling, review/revert, retention/redaction and deletion. Define retrieval/indexing integration separately from durable memory; the source has not selected a retrieval database. Clarify how restored runs use memory versions and what capture gaps are reported.

Whether retrieval/RAG and durable knowledge are shared across Chat, Lab and Builder or remain surface-local is unresolved. [AGT-004](modules/agents-workflows.md#agt-004) already separates active context from durable knowledge; it does not select a retrieval product, a shared index, or per-surface stores. Do not add RAG as a silent default or a second knowledge owner.

**Evidence needed:** fresh-context reuse, conflicting writes, denied protected writes, memory revert and a redacted/retained context capture with declared limitations.

<a id="oq-007"></a>
## OQ-007: Compatibility evidence and model lifecycle details

**Status:** partial lifecycle rules are implemented for Issue #3 (failed/interrupted download is not a successful deployment; connected endpoints have no destructive lifecycle; PATH llama-server is unsupported). Full compatibility evidence, capability claims and complete setting-mapping verification remain open.

**Owner:** Model-management boundary. **Blocks:** declaring model capabilities/configurations supported or exposing managed runtime controls as reliable.

Define compatibility-record schemas, evidence provenance, GGUF/companion-file resolution, runtime version identifiers, startup/request setting mapping and unsupported/unknown treatment. Specify cache reuse/interrupted download handling and the lifecycle authority over externally managed endpoints. Determine actual model-adapter parameter support against pinned dependencies.

Implemented now, without closing this question: import jobs that fail or are interrupted do not create a complete bundle or a successful deployment; connected attachments report `scope=connected` and reject start/stop/kill; a compatibility-records stub exists and does not claim support.

Multi-model routing and hybrid local GGUF / remote OpenAI-compatible deployments are [OQ-013](#oq-013). The model manager remains the owner; do not add a second inference engine.

**Evidence needed:** a managed model with companion files, a connected service, an unfamiliar model and an applied-setting mismatch exercised through the same recorded path on David-PC.

<a id="oq-008"></a>
## OQ-008: Registry schemas, compatibility and extension loading

**Owner:** Integration-registry boundary. **Blocks:** the first reusable stored graph, third-party adapter or shared definition version.

Define canonical schemas and identifiers, version compatibility/migrations, configuration versus workflow type rules, resource/access invalidation, discovery and extension loading/trust. Select no plugin sandbox or hot-reload mechanism merely from the word registry. Decide how consumers recognise stale definitions.

The product UX for discovering skills and plugins on the application registry is unresolved. Discovery, trust and loading remain this question; do not invent a second plugin marketplace.

Workflow definition import/export is [OQ-015](#oq-015). That question is not a second runtime and does not reopen LangGraph as the workflow owner.

**Evidence needed:** compatible/incompatible/unverified fixtures, graph reload against a changed definition and a backend rejection after a permission/capability change.

<a id="oq-009"></a>
## OQ-009: Optional experimental integrations

**Owner:** Relevant adapter/harness/desktop boundary. **Blocks:** that optional integration only, not the core application.

Check pinned-version availability and behaviour for rubric/interpreter middleware, background consolidation, MCP Apps host support and future voice. Preserve the source's experimental classification until evidence justifies a reviewed change. Define feature exposure, fallback and policy/event equivalence without creating another execution owner.

Whether MCP is the default tool bus or an optional integration remains open. MCP Apps host support stays experimental until evidence justifies a reviewed change. MCP is not isolation; worker sandboxing stays [OQ-003](#oq-003).

Voice and multimodal product surfaces stay optional and experimental ([ARCH-007](architecture.md#arch-007)). Do not make them prerequisites for the core model and agent experience. Adapter-level multimodal parameter support under [MOD-005](modules/models.md#mod-005) is not a selected voice or multimodal product.

**Evidence needed:** optional integration disabled and enabled, ordinary-result fallback where relevant, and real access/cancellation/event checks for all added invocation paths.

<a id="oq-010"></a>
## OQ-010: Product verification commands and test environments

**Owner:** Boundary implementer; architecture maintainers approve stage evidence. **Blocks:** declaring the relevant implementation or build stage verified.

Choose actual unit/contract/integration test locations and commands, platform/environment manifests, live-tool versus recorded fixtures, generated-contract freshness and import-boundary checks. Define repeatable starting inputs and evidence retention without storing secrets or model weights in this pack. No application test framework is supplied or presumed here.

**Evidence needed:** registered commands executed against actual code, negative/failure cases, and traceable results at a concrete revision. A green specification-integrity workflow is not stage acceptance.

<a id="oq-011"></a>
## OQ-011: Durable product Approvals inbox

**Owner:** Backend/desktop and agent/workflow boundaries jointly; backend maintains the shared contract. **Blocks:** presenting a durable product Approvals inbox, or treating a framework interrupt as that inbox.

Human-in-the-loop approvals that survive reconnect, restart and a closed editor remain unresolved as a product surface. LangGraph interrupts and Deep Agents intervention hooks are framework mechanisms; they are not the Approvals inbox. [OQ-004](#oq-004) covers run-state, interrupt mapping and when human intervention is safe; it does not select inbox persistence, notification, or desktop presentation. [REG-004](modules/registry.md#reg-004) still requires one run hierarchy and that approvals cannot be bypassed; it does not design the inbox. Builder canvas chrome is [OQ-016](#oq-016); it is not this inbox.

**Evidence needed:** an approval that remains visible and actionable after client disconnect and backend restart, distinguished from a transient framework interrupt, with denied bypass through agent, workflow and panel paths.

<a id="oq-012"></a>
## OQ-012: Run observability outside Lab

**Owner:** Backend, agent/workflow and Lab boundaries jointly; backend maintains the shared contract. **Blocks:** claiming product-wide traces, token/cost accounting or parent/child observability as a finished surface outside Lab.

Local run traces, token and cost visibility, and parent/child attribution outside Lab cases remain unresolved. [OQ-004](#oq-004) covers identities, events and linkage; [Lab integration](modules/lab-evaluation.md) owns evaluation evidence. LangSmith is not the product home for this observability. Do not add a remote observability control plane or treat an upstream tracing vendor as the workbench record.

**Evidence needed:** a local parent/child run with token/cost or trace fields retained without a Lab case, plus an explicit statement of what is not captured. A LangSmith project or similar hosted trace is not that evidence.

<a id="oq-013"></a>
## OQ-013: Multi-model routing and hybrid deployments

**Owner:** Model-management boundary. **Blocks:** routing a task across multiple models, or treating hybrid local GGUF and remote OpenAI-compatible endpoints as a second inference engine.

Whether and how the workbench routes among models, and how managed local GGUF deployments combine with connected remote OpenAI-compatible endpoints, remain unresolved. The application model manager owns bundles, profiles and deployments ([models](modules/models.md)); llama.cpp remains the local inference owner. [OQ-007](#oq-007) covers compatibility evidence and connected-endpoint lifecycle; it does not select a router. Do not add another inference engine or silently wire remote OpenAI as a second stack.

**Evidence needed:** one routed or hybrid path that still uses the model manager's deployment records, with local and remote scopes distinguished, and no second inference process started by an adapter or desktop.

<a id="oq-014"></a>
## OQ-014: Evaluation UX beyond Inspect

**Owner:** Lab/evaluation boundary. **Blocks:** a product evaluation UX beyond Inspect AI building blocks.

Datasets, scorers, compare-runs presentation and export beyond the Lab's Inspect-backed cases remain unresolved. [Lab integration](modules/lab-evaluation.md) already owns cases, restoration and evidence; it does not select dataset/scorer adapters or a comparison/export product. Do not add a second evaluation engine or treat Inspect as a complete Lab UX.

**Evidence needed:** a documented compare or export path that preserves applied configuration and distinguishes executable checks from model judgement, with adapters named only after a reviewed decision.

<a id="oq-015"></a>
## OQ-015: Workflow definition import and export

**Owner:** Agent/workflow and integration-registry boundaries jointly. **Blocks:** shipping workflow import/export as a product feature.

Import and export of workflow definitions — including LangGraph JSON and any later adapters — remain unresolved. This is a definition interchange question, not a second runtime: LangGraph remains the outer-workflow owner and React Flow remains the definition editor. [OQ-008](#oq-008) covers registry schemas, version compatibility and discovery; it does not select an interchange format. Do not treat an imported graph as executable authority without backend validation.

**Evidence needed:** a round-trip or rejected import against a registered definition, with configuration links still excluded from execution sequencing ([WF-001](modules/agents-workflows.md#wf-001)).

<a id="oq-016"></a>
## OQ-016: Builder canvas and chrome UX

**Owner:** Desktop and agents/workflows boundaries jointly. **Blocks:** shipping Builder as a finished product surface.

Builder look-and-feel and canvas chrome remain unresolved. Recording this question is not a selection, a silent default, or an ADR. Do not invent chrome so implementation can proceed as if finished, and do not treat a missing mockup as a reason to leave the question unrecorded.

The following are unknowns. None is selected:

1. Canvas chrome — grid, zoom, minimap, selection and multi-select.
2. Left icon rail information architecture and node-library search.
3. Node anatomy — title, ports, compact versus expanded presentation, and where prompt and model live.
4. Edge presentation — colour or label by kind. This is presentation only; it is not a second type system.
5. Run affordances — Run and stop controls, and whether an active step is shown on the canvas, in a run inspector, or both. Run-state semantics stay [OQ-004](#oq-004). A durable Approvals inbox stays [OQ-011](#oq-011).
6. Visual distinction between configuration links and workflow links. [WF-001](modules/agents-workflows.md#wf-001) already locks the behaviour: configuration links must not become executable workflow steps. How that distinction looks on the canvas is unresolved.
7. Profile and deployment binding versus per-node overrides. [ARCH-003](architecture.md#arch-003) already prefers shared profiles across Models, Lab, Chat and Builder. Do not silently default every slider on every node, and do not invent a hidden per-node profile.

TooGraph-ish cues — an icon rail, a searchable node library, compact nodes, coloured or labelled edges, a minimap — are **inspiration only**. TooGraph is not a pixel target and not a fork. Do not copy CDF/TooGraph, and do not treat a visual mock as a working integration.

React Flow remains the definition editor; the visual graph is not executable authority ([API-002](modules/backend-desktop.md#api-002)). The locked stack is not reopened.

**Evidence needed:** a maintainer-approved chrome decision, recorded as an ADR and matching specification, before Builder is presented as a finished product surface. A TooGraph screenshot, mockup resemblance, or unpublished preference is not that evidence.
