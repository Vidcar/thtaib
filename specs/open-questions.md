# Open architecture questions

These are deliberately unresolved. They are not permission for an agent to choose a new architecture silently. Source-derived selections such as llama.cpp, Deep Agents, LangGraph, LangChain and the modular backend are **not** reopened by this list.

All entries are initially **open**. Owners below are responsibility roles, not assertions that particular accounts have been assigned. Resolve an entry by retaining its ID, recording the approved ADR/specification change and linking the evidence; do not delete its history.

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

**Evidence needed:** a declared environment running a real task plus attempts to exceed its selected access boundary. Test explicit authorised host access separately from isolated execution.

<a id="oq-004"></a>
## OQ-004: Run state, events, continuation and uncertain effects

**Owner:** Backend, agent/workflow and persistence boundaries jointly; backend maintains the shared contract. **Blocks:** durable runs, recovery, long-running continuation or cross-process cancellation claims.

Define identities, parent/child linkage, thread/checkpoint namespaces, event ordering/reconnection, state transitions and actual stop reasons. Map framework limits and interrupts to the pinned versions. Define acknowledgement/reconciliation for external effects and when retry, reconnect, resume, restart or human intervention is safe. Do not claim an exactly-once transaction across databases, files and services.

**Evidence needed:** cancellation and crash tests before/after an external effect and checkpoint boundary, plus continuation beyond a measured upstream limit without duplicates.

<a id="oq-005"></a>
## OQ-005: Consistent project snapshots and restoration

**Owner:** Persistence/environment boundary. **Blocks:** project-restoring branches or repeatable Lab starting states.

Choose the snapshot mechanism, quiescent/consistent capture boundary, concurrent writer policy, included/excluded files, metadata and memory/configuration linkage, workspace isolation, retention and restoration validation. Define the boundary between project files and an environment snapshot. Do not assume checkpoints or Git commits capture untracked files, dependencies, services or remote effects.

**Evidence needed:** capture during a controlled execution boundary, restore into a separate workspace, verify included inputs, expose exclusions and show the parent remains unchanged.

<a id="oq-006"></a>
## OQ-006: Memory, skills, retrieval and sensitive context

**Owner:** Persistence/agent boundary. **Blocks:** automatic durable knowledge updates or retention of real sensitive context.

Choose storage representations, scope precedence, protected instructions, versioning/provenance, concurrent-write handling, review/revert, retention/redaction and deletion. Define retrieval/indexing integration separately from durable memory; the source has not selected a retrieval database. Clarify how restored runs use memory versions and what capture gaps are reported.

**Evidence needed:** fresh-context reuse, conflicting writes, denied protected writes, memory revert and a redacted/retained context capture with declared limitations.

<a id="oq-007"></a>
## OQ-007: Compatibility evidence and model lifecycle details

**Status:** partial lifecycle rules are implemented for Issue #3 (failed/interrupted download is not a successful deployment; connected endpoints have no destructive lifecycle; PATH llama-server is unsupported). Full compatibility evidence, capability claims and complete setting-mapping verification remain open.

**Owner:** Model-management boundary. **Blocks:** declaring model capabilities/configurations supported or exposing managed runtime controls as reliable.

Define compatibility-record schemas, evidence provenance, GGUF/companion-file resolution, runtime version identifiers, startup/request setting mapping and unsupported/unknown treatment. Specify cache reuse/interrupted download handling and the lifecycle authority over externally managed endpoints. Determine actual model-adapter parameter support against pinned dependencies.

Implemented now, without closing this question: import jobs that fail or are interrupted do not create a complete bundle or a successful deployment; connected attachments report `scope=connected` and reject start/stop/kill; a compatibility-records stub exists and does not claim support.

**Evidence needed:** a managed model with companion files, a connected service, an unfamiliar model and an applied-setting mismatch exercised through the same recorded path on David-PC.

<a id="oq-008"></a>
## OQ-008: Registry schemas, compatibility and extension loading

**Owner:** Integration-registry boundary. **Blocks:** the first reusable stored graph, third-party adapter or shared definition version.

Define canonical schemas and identifiers, version compatibility/migrations, configuration versus workflow type rules, resource/access invalidation, discovery and extension loading/trust. Select no plugin sandbox or hot-reload mechanism merely from the word registry. Decide how consumers recognise stale definitions.

**Evidence needed:** compatible/incompatible/unverified fixtures, graph reload against a changed definition and a backend rejection after a permission/capability change.

<a id="oq-009"></a>
## OQ-009: Optional experimental integrations

**Owner:** Relevant adapter/harness/desktop boundary. **Blocks:** that optional integration only, not the core application.

Check pinned-version availability and behaviour for rubric/interpreter middleware, background consolidation, MCP Apps host support and future voice. Preserve the source's experimental classification until evidence justifies a reviewed change. Define feature exposure, fallback and policy/event equivalence without creating another execution owner.

**Evidence needed:** optional integration disabled and enabled, ordinary-result fallback where relevant, and real access/cancellation/event checks for all added invocation paths.

<a id="oq-010"></a>
## OQ-010: Product verification commands and test environments

**Owner:** Boundary implementer; architecture maintainers approve stage evidence. **Blocks:** declaring the relevant implementation or build stage verified.

Choose actual unit/contract/integration test locations and commands, platform/environment manifests, live-tool versus recorded fixtures, generated-contract freshness and import-boundary checks. Define repeatable starting inputs and evidence retention without storing secrets or model weights in this pack. No application test framework is supplied or presumed here.

**Evidence needed:** registered commands executed against actual code, negative/failure cases, and traceable results at a concrete revision. A green specification-integrity workflow is not stage acceptance.
