# Architecture

[Working rules](README.md) · [Status and evidence](catalog.json) · [Decisions](decisions/README.md)

Local AI Workbench is a Windows-first, local-first desktop workbench for running models and agent work on one machine. This document states intended architecture: boundaries, process model, ownership between application code and upstream frameworks, persistence and permissions. Implementation status lives only in [the catalogue](catalog.json). The original vision is [Revision 0.5](sources/README.md); exact choices the source left open are in [open questions](open-questions.md).

## Ownership map

| Boundary | Owner | What crosses the boundary |
| --- | --- | --- |
| Model catalogue, files, compatibility, profiles and deployments | Application model manager ([models](modules/models.md)) | Bundle / profile / deployment records and an inference endpoint |
| Inference, tokenisation, chat-template rendering, context capacity | llama.cpp / llama-server | Model requests and responses, tool-call requests, runtime observations |
| Agent loop, active context, planning, delegation, file tools | Deep Agents on LangChain and LangGraph ([agents and workflows](modules/agents-workflows.md)) | Resolved agent setup, task inputs, tools, model adapter, run events |
| Outer workflow sequence, branches, loops, checkpoints | LangGraph | Validated workflow definition, typed step data, checkpoint references |
| Shell, browser, graphical access and external jobs | Application workers and tool adapters ([environments and tools](modules/environments-tools.md)) | Authorised execution requests, progress, results, side-effect records |
| APIs, jobs, approvals, shared records, presentation events | Python / FastAPI backend ([backend and desktop](modules/backend-desktop.md)) | Typed desktop requests, run information, approvals, artifacts |
| User controls and visual workflow editing | Electron / React / TypeScript / React Flow | Definitions and user actions; never a second execution graph |
| Persistence and restoration links | Application storage plus the LangGraph checkpointer ([state and recovery](modules/state-recovery.md)) | Application records, checkpoint identities, files, snapshot manifests |
| Integration definitions, capabilities and consumers | Application registry ([registry](modules/registry.md)) | Versioned definitions consumed by React Flow, LangChain and LangGraph |
| Engine and task evaluation | llama-bench / Inspect AI, coordinated by the Lab ([Lab](modules/lab-evaluation.md)) | Cases, restored inputs, measurements, checks, evidence |

Each boundary has one behavioural owner. The application owns configuration, lifecycle, visibility and connecting contracts; it does not reimplement what an upstream framework already provides. Before designing against llama.cpp, LangChain, LangGraph or Deep Agents, read the documentation for the pinned version ([upstream register](sources/upstream.md)) and prefer the framework's own mechanism (for example Deep Agents backends, `memory`, `skills`, `permissions` and `interrupt_on`) over an application copy of it.

## Process model

- **Backend**: one Python 3.12 FastAPI process (`apps/backend`, package `workbench_backend`) bound to `127.0.0.1:8000`. It hosts the Deep Agents harness in-process (one daemon thread per run), the model manager, Lab, knowledge and chat services. Non-loopback binds are refused.
- **Managed inference**: `llama-server` child processes started, health-probed and stopped by the model manager, each with a recorded process identity. A connected endpoint is an external OpenAI-compatible server the workbench attaches to but never starts or kills.
- **Desktop**: one Electron application (`apps/desktop`). The main process holds the shared secret and injects `X-Workbench-Local-Token` on backend requests; the sandboxed renderer never sees it. React Flow edits definitions; the backend executes them.
- **Workers** (not yet implemented): shell, browser and graphical execution run in declared environments with their own adapters. Docker Compose (`infra/docker-compose.yml`, currently empty) manages container services, not application jobs.

The desktop talks only to the backend. The backend resolves records, definitions and policy, then invokes the model manager, the harness or worker adapters. Model adapters call existing inference endpoints. Storage keeps records and references and never acquires an agent loop. Framework objects stay at their integration boundary rather than becoming the application's persisted format. No message broker, microservice split or remote control plane is selected.

## Repository layout and toolchain

`apps/backend/` (uv, `pyproject.toml`, `uv.lock`), `apps/desktop/` (pnpm, Node ≥22 <25, Electron + Vite + React + TypeScript + React Flow, electron-builder NSIS for packaging), root `specs/`, `scripts/`, `tests/specs/`. Bound paths are in [the repository map](repository-map.json); working commands in [commands](commands.md). Dependency versions live in the lockfiles, not in prose.

## Persistence

Product data lives under `%LOCALAPPDATA%\LocalAIWorkbench\` on Windows (`~/.local/share/LocalAIWorkbench/` on Linux, overridable with `WORKBENCH_DATA_ROOT`): `models\`, `runtimes\`, `state\`, `cases\`, `snapshots\`, `workspaces\`, `knowledge\`, `logs\`, `application.sqlite` and `checkpoints.sqlite`. Never the repository, never `.scratch/`.

- `application.sqlite` is the application system of record for runs, chat conversations and transcripts, checkpoint-id links, external-effect ledger rows and file references.
- `checkpoints.sqlite` belongs to the LangGraph SQLite checkpointer. The application stores checkpoint ids and never reads or writes its tables directly.
- Files hold weights, project workspaces, knowledge versions, snapshots and artifacts; records link to them.
- Bundles, profiles, deployments, import jobs, compatibility overrides and Lab cases are currently JSON files under `state\` with atomic replace, no locking and no migrations. Converging all application records on SQLite is [OQ-017](open-questions.md#oq-017) (recommended); it is a persistence-strategy decision and needs an ADR before implementation.

Displayed chat history is not the working project and not the harness execution context ([STATE-002](modules/state-recovery.md#state-002)). Snapshots are application-owned directory copies, not git commits, and never undo external effects.

## Permissions and trust

- Same-machine trust: privileged `/v1` routes require the shared-secret header; missing token → 401, wrong token → 403; `GET /health` is public. CORS is not authorisation. Remote backend access is unsupported.
- Autonomy and access are independent choices. Permissions and approvals are enforced in tools and workers, not in prompts, and every invocation path (agent tool, workflow adapter, interpreter, panel) gets the same policy outcome and child-run attribution.
- A working directory is not a security boundary; MCP is not isolation. The first worker environment is the Windows host shell with approvals, built on Deep Agents `permissions=`, `interrupt_on=` and `LocalShellBackend` (product owner decision, 2026-09-19); WSL and Docker follow later. Host-shell approval uses the framework interrupt (auto-allow read-only prefixes; otherwise pause; Chat and Agent-run Approve/Deny). Remaining worker questions are [OQ-003](open-questions.md#oq-003); a durable Approvals inbox is [OQ-011](open-questions.md#oq-011).
- Secrets, weights and private project data never enter the repository; diagnostic captures follow the knowledge capture policy ([STATE-005](modules/state-recovery.md#state-005)).

<a id="effective-setup"></a>
## Effective setup

Chat, Lab, Agent-run and (later) Builder consume one resolved setup; none keeps a hidden profile. The rule is shared here; the details stay in [MOD-003](modules/models.md#mod-003), [MOD-004](modules/models.md#mod-004), [MOD-005](modules/models.md#mod-005), [WF-001](modules/agents-workflows.md#wf-001), [AGT-002](modules/agents-workflows.md#agt-002), [AGT-004](modules/agents-workflows.md#agt-004), [STATE-001](modules/state-recovery.md#state-001), [STATE-005](modules/state-recovery.md#state-005), [REG-002](modules/registry.md#reg-002) and [REG-005](modules/registry.md#reg-005).

- **Resolve before run.** The backend resolves the bound deployment, the three settings bags, enabled tools and policy, and the selected knowledge / skill / protected-instruction versions before the harness starts. A stored graph, a Chat start, a Lab restore or rerun and a later Builder run all use that same resolve step; editing a definition is not a substitute for run-start validation, because deployment, environment, access or configuration may have changed. Unknown, missing or incompatible refs fail closed; there is no silent default profile or empty knowledge.
- **Three bags.** *Startup* settings apply when a deployment is started or attached; selecting a profile never rewrites a running server. *Per-request* settings are sent on each model call. *Agent* settings configure the harness. A value in the wrong bag is unsupported there, not moved.
- **Selected ≠ loaded ≠ applied.** Selected is a name or id. Loaded is what is resident: the running process's startup, knowledge content in the configured backends, constructed tools. Applied is what reached the model request or harness after defaults, overrides, unsupported-key drop and runtime-required overrides. Only inspecting the live process or the outbound request proves loaded and applied.
- **Precedence inside each bag:** bag defaults → selected profile or definition → explicit run or surface override → runtime-required override (recorded as overridden). Unknown keys stay unsupported. The agent bag `system_prompt` is the profile identity; a Chat or other surface prompt is composed under it (`## Surface instructions`) and must not silently replace it.
- **Harness and inspector agree.** The run record, the inspector and the captured model request show the same selected, loaded and applied facts, including unsupported, overridden and unverified values, startup mismatch between selected profile and loaded deployment, capture gaps and redaction.
- **Knowledge refs are loaded content; retrieval is a derived index.** Selected versions are loaded through the configured backends before the run (STATE-005). Query-time RAG is in the first usable version as LangChain / Deep Agents retrieve-and-offload over a per-run `InMemoryVectorStore` ([STATE-006](modules/state-recovery.md#state-006), [OQ-006](open-questions.md#oq-006)). Retrieval is requested only by naming a loaded dedicated embedding deployment; a GGUF file on disk is not that deployment and missing embedders fail closed. The vector index is not a second knowledge owner.

## Requirements

<a id="arch-001"></a>
### ARCH-001: One modular backend

Keep application responsibilities in one Python backend, with separately managed external processes where required. The desktop edits definitions; the backend executes them. Docker Compose manages container services, not a competing application job scheduler.

**Acceptance:** Inspect the dependency/process map and demonstrate that desktop actions reach the backend-owned execution path. Record any process split as a reviewed decision.

<a id="arch-002"></a>
### ARCH-002: One owner for execution

Use llama.cpp for supported inference, Deep Agents for each agent loop, LangGraph for runtime and outer workflows, and LangChain for model/message/tool interfaces. The application owns configuration, lifecycle, visibility and connecting contracts, not another implementation of those loops.

**Acceptance:** Trace one model call, one tool execution and one outer workflow step to their designated owners. Reject a second application-written agent loop.

<a id="arch-003"></a>
### ARCH-003: Shared records across surfaces

Models, Lab, Chat and Builder share configurations, runs and artifacts through the [effective setup](#effective-setup) rule. A surface must not substitute its own hidden profile or report equivalence solely from a shared profile name. Selecting a profile or knowledge version is not proof it was loaded or applied.

**Acceptance:** Carry a profile between the relevant surfaces and compare the recorded applied settings, deployment and environment, including visible differences.

<a id="arch-004"></a>
### ARCH-004: Expose capability without pretending certainty

Guidance and progressive disclosure simplify the interface without silently removing supported model or agent capabilities. Unfamiliar models and unverified capabilities remain distinguishable from known incompatibility. Testing is not a prerequisite to model use.

**Acceptance:** Check known-compatible, known-incompatible and unverified configurations. Verify that supported advanced controls remain available and unsupported settings are explained.

<a id="arch-005"></a>
### ARCH-005: One access and event model

All invocation paths share the selected access policy and a common run hierarchy. Enforce permissions in tools and workers, not solely in prompts. Autonomy and access are independent choices.

**Acceptance:** Follow an action through an agent tool, workflow adapter and enabled alternative invocation path; compare approval behaviour and parent/child run attribution.

<a id="arch-006"></a>
### ARCH-006: Extend through the registry

New supported integrations register their definitions, capabilities, configuration, execution behaviour and presentation integration with the application-owned versioned registry. React Flow, LangChain and LangGraph consume that integration model; none independently defines it.

**Acceptance:** Introduce a representative adapter through the registry and demonstrate compatible presentation, validation and execution without introducing an alternative integration authority.

<a id="arch-007"></a>
### ARCH-007: Optional extensions stay optional

Background consolidation, beta rubric/interpreter integrations, MCP Apps and voice extend the same contracts. They must not become prerequisites for the core model and agent experience.

**Acceptance:** Run the core inference and agent acceptance paths with these extensions disabled or absent; report unavailable optional capabilities rather than fail core startup.

## Build order

Revision 0.5 fixes the order and it stands: first prove **managed inference** (MOD-001…006) end to end on David-PC; second a **complete agent task** through Chat with real files, workers, capture, approvals, cancellation and recovery (AGT, WF, ENV, STATE-001/002/004); third **reuse and experimentation** (STATE-003, STATE-005, STATE-006, LAB); fourth **optional integrations** (ARCH-007, ENV-005/006, REG-004). Long-run acceptance exercises AGT-003 beyond framework defaults without hidden quotas, duplicated actions or lost state.
