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

The shared high-level contract is [effective setup](#effective-setup-contract). Selecting a profile or knowledge version is not proof it was loaded or applied.

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

Exact technical choices still to be made are in [open questions](open-questions.md). Builder v1 chrome is recorded in [ADR-0003](decisions/ADR-0003-builder-v1-chrome.md); the [OQ-016](open-questions.md#oq-016) remainder is the unfinished Builder surface, not a reopen of that chrome. [ARCH-003](#arch-003) still prefers shared profiles; the shared rule is the [effective setup contract](#effective-setup-contract). v1 chrome does not change that behaviour. Implementation status and evidence belong only in [the catalogue](catalog.json); this document describes intended architecture.

On main after Issue #23's inspection: one backend and one desktop scaffold, managed inference, the embedded harness, Lab reuse, durable knowledge, and the Issue #21 Windows CUDA 13.4 pin / default GPU profile / valued `flash_attn` mapping. Debug-quality Chat for [AGT-001](modules/agents-workflows.md#agt-001) lands with [Issue #22](https://github.com/Vidcar/thtaib/issues/22); it is not finished Chat polish and not Builder. Those CUDA defaults do not close [OQ-007](open-questions.md#oq-007). The dual application/checkpointer SQLite pair and app-owned run→checkpoint-id linkage land with [Issue #27](https://github.com/Vidcar/thtaib/issues/27) as a partial [OQ-004](open-questions.md#oq-004). [Issue #31](https://github.com/Vidcar/thtaib/issues/31) lands [MOD-006](modules/models.md#mod-006) provenance-capable records (still not closing OQ-007) and [STATE-004](modules/state-recovery.md#state-004) unknown-effect safety (still not closing OQ-004 identities, event-order or exactly-once). [Issue #35](https://github.com/Vidcar/thtaib/issues/35) lands the [WF-001](modules/agents-workflows.md#wf-001) backend definition compiler (configuration links resolve setup only; they are not executable steps). That is not a Builder-shipped claim and does not reopen [ARCH-003](#arch-003). [WF-002](modules/agents-workflows.md#wf-002) stays deferred. [Issue #41](https://github.com/Vidcar/thtaib/issues/41) / [ADR-0002](decisions/ADR-0002-contract-authoring.md) lands the generated `X-Workbench-Local-Token` envelope. [Issue #40](https://github.com/Vidcar/thtaib/issues/40) implements the partial [OQ-002](open-questions.md#oq-002) same-machine shared-secret + loopback bind (Electron main injects that header). That is not remote-backend support and does not close event reconnection. [Issue #42](https://github.com/Vidcar/thtaib/issues/42) lands harness cancel honesty (`cancel_requested` vs confirmed `cancelled`; no false quiescence) as a further [OQ-004](open-questions.md#oq-004) partial; it does not close identities, event-order or exactly-once. [Issue #53](https://github.com/Vidcar/thtaib/issues/53) records the high-level [effective setup contract](#effective-setup-contract) under [ARCH-003](#arch-003). That is a specification, not an apply-for-real implementation or catalogue `verified` claim. [Issue #54](https://github.com/Vidcar/thtaib/issues/54) records the [Model Lab](../docs/glossary.md#model-lab) trait catalogue and UX ([LAB-005](modules/lab-evaluation.md#lab-005)/[006](modules/lab-evaluation.md#lab-006)); that is not Task cases and replay and does not jump Chat implementation.

<a id="effective-setup-contract"></a>
## Effective setup contract (Issue #53)

This is the shared high-level contract for [ARCH-003](#arch-003). Chat, Lab and Builder consume the same resolved setup. Agent-run is not a second contract. This section does not author a wire schema, close [OQ-006](open-questions.md#oq-006) or [OQ-007](open-questions.md#oq-007), or select retrieval/RAG.

Detailed homes stay where they are. This contract stitches them; it does not copy their rules.

| Concern | Authoritative home |
| --- | --- |
| Three settings bags; requested versus applied; unsupported / overridden / unverified | [MOD-003](modules/models.md#mod-003) |
| Selected profile is not a running deployment; applied startup lives on the deployment | [MOD-004](modules/models.md#mod-004) |
| Adapter sends the applied per-request bag; it does not start inference | [MOD-005](modules/models.md#mod-005) |
| Configuration links resolve one Deep Agents setup; they are not executable steps | [WF-001](modules/agents-workflows.md#wf-001) |
| Capture the actual model request after middleware | [AGT-002](modules/agents-workflows.md#agt-002) |
| Durable knowledge versus active context; protected-instruction write policy | [AGT-004](modules/agents-workflows.md#agt-004) |
| Run records persist profile, deployment, agent setup and applied settings | [STATE-001](modules/state-recovery.md#state-001) |
| Versioned knowledge / skill / protected-instruction refs | [STATE-005](modules/state-recovery.md#state-005) |
| Repeat validation immediately before execution | [REG-002](modules/registry.md#reg-002) |
| Expose effective controls, applied values and actual limits | [REG-005](modules/registry.md#reg-005) |

<a id="resolve-before-run"></a>
### Resolve before run

The backend resolves one effective setup **before** the harness starts work. A stored graph, Chat start, Lab restore/rerun or later Builder run uses that same resolve step. Editing a definition is not a substitute for run-start validation: deployment, environment, access or configuration may have changed.

The resolved setup includes the bound deployment, the three settings bags, enabled tools and policy, and the selected memory / skill / protected-instruction versions. Configuration connections supply those facts ([WF-001](modules/agents-workflows.md#wf-001)); they do not become workflow steps.

Unknown, missing or incompatible refs fail closed. Do not start with a silent default profile, a different deployment, or empty knowledge because a label looked familiar.

<a id="startup-per-request-agent-bags"></a>
### Startup, per-request and agent bags

Keep the three bags separate ([MOD-003](modules/models.md#mod-003)):

- **Startup** — process-lifetime llama-server / connected-endpoint settings. Applied only when a deployment is started or attached. Selecting a profile on an already-running server does not rewrite that process's loaded startup.
- **Per-request** — generation settings for this model call (sampling, stop, token limits, and other request-scoped controls the adapter may forward).
- **Agent** — harness setup for this run (instructions, presented tools, iteration/budget fields the application owns).

A value in the wrong bag is unsupported there, not silently moved. Runtime-specific supported controls stay representable. Compatibility provenance ([MOD-006](modules/models.md#mod-006)) is not a fourth bag.

<a id="selected-loaded-applied"></a>
### Selected ≠ loaded ≠ applied

These are three inspectable facts. A shared profile **name** is none of them.

| Fact | Meaning |
| --- | --- |
| **Selected** | The user or surface named a profile, deployment, knowledge version, tool set or policy. IDs and refs are selected facts. |
| **Loaded** | What is actually resident: the running deployment process (its applied startup), knowledge/skill content in the configured backends, and constructed tools. |
| **Applied** | What reached the model request or harness after defaults, explicit overrides, unsupported-key drop and runtime-required overrides. |

Recording `profile_id` or a knowledge version id is selected only. Inspecting a live process or the outbound request is how loaded and applied are proven. [MOD-004](modules/models.md#mod-004): a saved profile is not a running deployment.

<a id="harness-inspector-agree"></a>
### Harness and inspector agree

The harness consumes the resolved setup. The inspector, run record and [AGT-002](modules/agents-workflows.md#agt-002) capture show the **same** selected, loaded and applied facts. An inspector must not invent applied values from a selected name.

Show unsupported, overridden and unverified values, plus startup mismatch (selected profile startup ≠ loaded deployment startup). Report genuine capture gaps and redaction. After compaction, the capture still names the versions and bags that were actually used.

Builder, when added, consumes this contract. Inherit the workflow profile/deployment; an explicit per-node override is visible and is not a hidden surface profile ([ADR-0003](decisions/ADR-0003-builder-v1-chrome.md)).

<a id="effective-setup-precedence"></a>
### Precedence

High-level order inside each bag. Exact key lists stay in [MOD-003](modules/models.md#mod-003); this is not a second schema.

1. Known defaults for that bag.
2. Selected profile / definition values for that bag.
3. Explicit run or surface overrides.
4. Runtime-required overrides (for example an allocated listen port), recorded as overridden.
5. Requested keys that are not known for that bag stay unsupported and are not applied.

Per-node Builder overrides replace the inherited profile for that node only when explicit. User-override provenance in a compatibility record ([MOD-006](modules/models.md#mod-006)) remains a separate inspectable list; it is not a silent rewrite of applied bags.

<a id="effective-setup-knowledge"></a>
### Knowledge and skill refs are not RAG

Selected [STATE-005](modules/state-recovery.md#state-005) version ids must be loaded through the configured memory/skill backends before the run. Referencing an id, listing it on a capture, or proving the id exists is not loaded content.

This contract does not select retrieval, an index, or cross-surface sharing. Those remain [OQ-006](open-questions.md#oq-006). Protected-instruction and write-policy rules in [AGT-004](modules/agents-workflows.md#agt-004) still apply. Do not add a retrieval product to satisfy effective setup.

<a id="effective-setup-gaps"></a>
### Honest gaps

This section is intended behaviour. Catalogue rows for [ARCH-003](#arch-003), [MOD-003](modules/models.md#mod-003) and [REG-005](modules/registry.md#reg-005) stay `partial` or `planned`. Issue #53 does not implement apply-for-real and is not catalogue `verified`.

On the inspected path ([Issue #37](https://github.com/Vidcar/thtaib/issues/37) area 2): the harness validates and records `profile_id` and knowledge version refs; the model adapter reads the **deployment** per-request bag; knowledge refs are existence-checked without loading their content into Deep Agents memory/skill configuration. Selected is not yet loaded or applied. Reproduce against the implementation tip before treating that observation as current.

Still open, and not closed by this contract:

- Complete setting-mapping verification and capability claims — [OQ-007](open-questions.md#oq-007).
- Retrieval/RAG and whether knowledge is shared across surfaces — [OQ-006](open-questions.md#oq-006).
- Application registry as integration authority — [REG-001](modules/registry.md#reg-001)…[005](modules/registry.md#reg-005) planned; [OQ-008](open-questions.md#oq-008).
- Conversation ↔ thread ↔ run continuity — [Issue #37](https://github.com/Vidcar/thtaib/issues/37) area 1 / [Issue #52](https://github.com/Vidcar/thtaib/issues/52), not this contract.
- Exact generated wire types for the resolved setup — [contracts](contracts.md); module-local Pydantic is not a second semantic home.

Apply-for-real implementation stays a later Agent Chat slice under [Issue #37](https://github.com/Vidcar/thtaib/issues/37). Conversation continuity and Model Lab trait catalogue are sibling specs, not this document.
