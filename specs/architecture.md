# Architecture

[Specification index](README.md) · [Status and evidence](catalog.json)

## Scope and source

The application is a Windows-first, local-first workbench with one coherent desktop experience. This document extracts the technical baseline from revision 0.5, principally [technical components](sources/README.md#technical-components), [application infrastructure](sources/README.md#application-infrastructure), and [integration registry](sources/README.md#integration-registry). It does not select package versions, deployment transports or schema fields the source leaves unresolved.

## Ownership map

| Boundary | Owner | What crosses the boundary |
| --- | --- | --- |
| Model catalogue, files, compatibility, profiles and deployments | Application model manager | Bundle/profile/deployment records and an inference endpoint |
| Inference, tokenisation and chat-template rendering | llama.cpp / llama-server | Model requests, responses, tool-call requests and runtime observations |
| Agent loop, active context, planning and delegation | Deep Agents using LangChain and LangGraph | Resolved agent setup, task inputs, tools, model adapter and run events |
| Outer workflow sequence, branches, loops and checkpoints | LangGraph | Validated workflow definition, typed step data and checkpoint references |
| Shell, browser, graphical access and external jobs | Application workers and tool adapters | Authorised execution requests, progress, results and side-effect records |
| APIs, resources, jobs, approvals, shared records and presentation events | Python / FastAPI backend | Typed desktop requests, run information, approvals and artifacts |
| User controls and visual workflow editing | Electron / React / TypeScript / React Flow | Definitions and user actions; never a second execution graph |
| Persistence and restoration links | Application storage plus LangGraph checkpointer | Application records, checkpoint identities, files and snapshot manifests |
| Engine and task evaluation | llama-bench / Inspect AI, coordinated by the Lab | Cases, restored inputs, measurements, checks and evidence |

Each boundary has one behavioural owner. A module may contain several internal components without becoming a separate service.

## Dependency direction

The desktop communicates with the backend. Backend coordination resolves records, definitions and policy, then invokes model management, the harness/workflow integration or worker adapters. Model adapters call existing inference endpoints. Tool adapters call workers or external services. Storage retains records and references; it does not acquire an agent loop.

Framework-specific objects should remain at their integration boundary rather than become the application's universal persisted format. Scaffold source and lockfile paths are bound in [the repository map](repository-map.json). Remaining contract, registry and test locations stay unbound until their `required_before` trigger. See [contracts](contracts.md) for the proposed authoring convention.

Do not read this logical map as a proposal for a message broker, microservices, a remote control plane or additional orchestration framework. None is selected by the source.

## Requirements and acceptance checks

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

Models, Lab, Chat and Builder share configurations, runs and artifacts. A surface must not substitute its own hidden profile or report equivalence solely from a shared profile name.

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

## Focused specifications

Use [models](modules/models.md), [agents and workflows](modules/agents-workflows.md), [environments and tools](modules/environments-tools.md), [state and recovery](modules/state-recovery.md), [registry](modules/registry.md), [backend and desktop](modules/backend-desktop.md), and [Lab integration](modules/lab-evaluation.md).

Exact technical choices still to be made are in [open questions](open-questions.md). Builder canvas chrome and per-node override presentation remain [OQ-016](open-questions.md#oq-016); [ARCH-003](#arch-003) still prefers shared profiles and does not select that chrome. Implementation status and evidence belong only in [the catalogue](catalog.json); this document describes intended architecture.
