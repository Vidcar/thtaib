# Open architecture questions

These are deliberately unresolved. They are not permission for an agent to choose a new architecture silently. Source-derived selections such as llama.cpp, Deep Agents, LangGraph, LangChain and the modular backend are **not** reopened by this list.

All entries are initially **open**. Owners below are responsibility roles, not assertions that particular accounts have been assigned. Resolve an entry by retaining its ID, recording the approved ADR/specification change and linking the evidence; do not delete its history.

Later-decision product topics are recorded here so they stay visible: amend [OQ-003](#oq-003), [OQ-006](#oq-006), [OQ-008](#oq-008) and [OQ-009](#oq-009); add [OQ-011](#oq-011) through [OQ-015](#oq-015). Builder canvas and chrome UX is [OQ-016](#oq-016) — v1 chrome is locked in [ADR-0003](decisions/ADR-0003-builder-v1-chrome.md); the implementation remainder stays open. Recording a topic is not a selection, a silent default, or an ADR. Real choices use [the decision template](templates/decision.md) and maintainer approval.

Issue #23 audited this list against revision 0.5 and implemented main work. [OQ-007](#oq-007) CUDA pin / default GPU profile / valued `flash_attn` mapping **landed as a partial** on [Issue #21](https://github.com/Vidcar/thtaib/issues/21) / [PR #24](https://github.com/Vidcar/thtaib/pull/24); [MOD-006](modules/models.md#mod-006) provenance-capable records **landed as a further partial** on [Issue #31](https://github.com/Vidcar/thtaib/issues/31); managed deployment ownership (duplicate start + PID identity) **landed as a further partial** on [Issue #62](https://github.com/Vidcar/thtaib/issues/62); full evidence and capability claims stay open. [OQ-004](#oq-004) dual application/checkpointer SQLite + app linkage **landed as a partial** on [Issue #27](https://github.com/Vidcar/thtaib/issues/27); [STATE-004](modules/state-recovery.md#state-004) unknown-effect safety **landed as a further partial** on [Issue #31](https://github.com/Vidcar/thtaib/issues/31); cancel request versus confirmed stop **landed as a further partial** on [Issue #42](https://github.com/Vidcar/thtaib/issues/42); Chat conversation↔thread↔run reuse **landed as a further partial** on [Issue #56](https://github.com/Vidcar/thtaib/issues/56); identities beyond that link, event-order/reconnection and exactly-once stay open. [OQ-002](#oq-002) same-machine shared-secret + loopback bind **landed as a partial** on [Issue #40](https://github.com/Vidcar/thtaib/issues/40); event reconnection and remote backend stay open. [OQ-016](#oq-016) v1 chrome **landed as a partial** on [Issue #29](https://github.com/Vidcar/thtaib/issues/29) / [ADR-0003](decisions/ADR-0003-builder-v1-chrome.md); the unfinished Builder surface stays open and is not a shipped claim. Debug-quality Chat for [AGT-001](modules/agents-workflows.md#agt-001) lands with [Issue #22](https://github.com/Vidcar/thtaib/issues/22) — Agent-run is not Chat, and this is not finished Chat polish. [OQ-010](#oq-010) registered backend/desktop CI jobs on [Issue #32](https://github.com/Vidcar/thtaib/issues/32). [Issue #36](https://github.com/Vidcar/thtaib/issues/36) recorded the earlier private-free advisory-only hosting stance; [Issue #76](https://github.com/Vidcar/thtaib/issues/76) supersedes that hosting decision — the repository is public and those jobs (plus shared-contract freshness) are merge-blocking required checks on public `main`. Green required CI is not catalogue `verified` and not build-stage acceptance. There is **no Pro ask**. Remaining product gates stay open.

<a id="oq-001"></a>
## OQ-001: Repository layout, versions and reproducible setup

**Status:** layout and toolchain pins are recorded for the Windows-first scaffold ([Issue #1](https://github.com/Vidcar/thtaib/issues/1)). Remaining evidence is UAT on David-PC. This does not close the [OQ-002](open-questions.md#oq-002) remainder (event reconnection / remote backend).

**Owner:** Backend/desktop maintainers. **Blocks:** first application scaffold or dependency installation represented as the supported setup.

Inspect any existing repository first. The supported scaffold is now:

- Layout: `apps/backend/`, `apps/desktop/`; keep root `specs/`, `scripts/`, `tests/specs/`.
- Python **3.12.x** via **uv**; `apps/backend/pyproject.toml` and `apps/backend/uv.lock`; import path `workbench_backend` under `apps/backend/src/`.
- Node **≥22 <25** (develop on 24); **pnpm**; `apps/desktop/package.json` and `apps/desktop/pnpm-lock.yaml`.
- Desktop stack: Electron + Vite + React + TypeScript + React Flow, pinned in the desktop lockfile.
- Shared-contract OpenAPI→TS generator: pinned **openapi-typescript 7.13.0** in the desktop lockfile ([ADR-0002](decisions/ADR-0002-contract-authoring.md) / [Issue #41](https://github.com/Vidcar/thtaib/issues/41)). This does not close this question.
- Windows packaging: desktop-owned **electron-builder** (NSIS). The package script is registered; an installer is not required for this milestone.
- Docker: stub `infra/docker-compose.yml` only; no product services.

Bound map entries: `backend-source`, `desktop-source`, `python-dependency-manifest`, `python-lockfile`, `desktop-dependency-manifest`, `desktop-lockfile`, `runtime-manifest`, `compatibility-records`, plus the Slice 1 shared-contract bindings (`shared-python-contracts`, `generated-json-schemas`, `openapi-export`, `generated-desktop-client`, `contract-generator`, `contract-tests`). Working commands are in [commands.md](commands.md). Terms are in [the glossary](../docs/glossary.md).

**Evidence needed:** a clean setup and minimal backend/desktop build on the claimed platform (David-PC). Do not infer this from the specification checker's Python version.

<a id="oq-002"></a>
## OQ-002: Desktop/backend trust and communication

**Status:** partially constrained by [Issue #40](https://github.com/Vidcar/thtaib/issues/40) for same-machine shared-secret authentication and loopback bind. The question stays open.

**Owner:** Backend/desktop boundary. **Blocks:** remaining trust claims — event streaming/reconnection, remaining origin/IPC details, or treating a remote backend as supported.

Issue #40 locked these defaults. They are recorded in [backend and desktop](modules/backend-desktop.md#locked-milestone-defaults-issue-40-partial-oq-002). Do not invent a remote-backend or renderer-held secret:

- Secret file: `%LOCALAPPDATA%\LocalAIWorkbench\state\desktop_backend_shared_secret` (or the portable `state\` sibling). Never in the repository.
- Header: `X-Workbench-Local-Token` imported from the Issue #41 / ADR-0002 envelope. Electron **main** injects; the renderer does not hold the secret.
- Bind: `127.0.0.1` only (v1). Remote backend is unsupported.
- Unauthenticated / wrong-token clients receive 401/403 on privileged `/v1` routes, including Chat, Lab and project-file operations. `GET /health` remains a public smoke identity. CORS is not authorisation.

The remainder stays open. Choose event streaming/reconnection, remaining origin/IPC checks, and whether remote backend access is ever supported; remote workers do not automatically imply an internet-exposed backend. The source names FastAPI and Electron but does not select those remaining controls.

**Evidence needed:** denied unauthorised requests (executable unit checks exist for the locked defaults), reconnect behaviour, and a real Electron main ↔ backend pairing on David-PC. An API bound locally must not be assumed secure solely because it is local. Unit checks are not that UAT evidence.

<a id="oq-003"></a>
## OQ-003: Worker protocol, isolation and access policy

**Owner:** Environment/tool boundary. **Blocks:** real shell/browser/graphical execution, sensitive file mounts or installation permissions.

Define worker identity/authentication, command/filesystem/browser protocol, host versus container/WSL/remote paths, permission enforcement, approvals, cancellation, teardown and support per platform. Decide exactly what a disposable environment isolates and what it exposes. Establish path validation, executable/network access and credential delivery. These are necessary security details, not features supplied automatically by Docker or MCP.

This is the isolation question. Tool/worker sandbox isolation — what a disposable environment isolates versus exposes, including host versus container/WSL/remote — stays here; do not open a second isolation OQ. MCP standardises discovery and invocation; it is not an isolation boundary and does not supply worker sandboxing. Whether MCP is the default tool bus or an optional integration is [OQ-009](#oq-009), not a silent default here.

**Evidence needed:** a declared environment running a real task plus attempts to exceed its selected access boundary. Test explicit authorised host access separately from isolated execution.

<a id="oq-004"></a>
## OQ-004: Run state, events, continuation and uncertain effects

**Status:** partially constrained by [Issue #27](https://github.com/Vidcar/thtaib/issues/27) for the dual application/checkpointer SQLite pair and app-owned run→checkpoint-id→file linkage, by [Issue #31](https://github.com/Vidcar/thtaib/issues/31) for [STATE-004](modules/state-recovery.md#state-004) unknown-effect safety, by [Issue #42](https://github.com/Vidcar/thtaib/issues/42) for cancel request versus confirmed stop, and by [Issue #56](https://github.com/Vidcar/thtaib/issues/56) for Chat conversation↔thread↔run reuse. The question stays open.

**Owner:** Backend, agent/workflow and persistence boundaries jointly; backend maintains the shared contract. **Blocks:** remaining durable-run claims — identities beyond the locked linkage, event ordering/reconnection, state transitions, or exactly-once.

Issue #27 locked these defaults for [STATE-001](modules/state-recovery.md#state-001) and [STATE-002](modules/state-recovery.md#state-002). They are recorded in [state and recovery](modules/state-recovery.md#locked-milestone-defaults-issue-27-partial-oq-004). Do not invent a second persistence owner or mutate checkpointer private tables:

- Separate `%LOCALAPPDATA%\LocalAIWorkbench\application.sqlite` and `checkpoints.sqlite`.
- Application records are the system of record for runs, chat linkage, profile/deployment refs, checkpoint id links and file/artifact refs.
- LangGraph owns checkpoint bytes. The application stores checkpoint ids only.
- JSON run/chat linkage under `state\` migrates to the application DB; after cutover there is no dual-write SoR.
- Chat history is not the working project; filesystem tools write project storage only.

Issue #31 additionally locked these [STATE-004](modules/state-recovery.md#state-004) defaults, recorded in [state and recovery](modules/state-recovery.md#locked-milestone-defaults-issue-31-state-004):

- Application-owned external-effect ledger in `application.sqlite` (`dispatched` / `acknowledged` / `unknown` / `reconciled` / `failed`).
- Reconnect/resume/restart after a missing acknowledgement reports uncertainty and does not silently repeat the operation.
- Snapshots do not roll back external effects (`rollback_promise=none`). Unresolved side effects are preserved.

Issue #42 additionally locked harness cancel honesty, recorded in [agents and workflows](modules/agents-workflows.md#locked-milestone-defaults-issue-42-cancel-honesty) and the [STATE-004 intersection](modules/state-recovery.md#locked-milestone-defaults-issue-42-cancel-honesty):

- Cancel request is `cancel_requested` (still live). Confirmed stop is `cancelled`.
- Quiescence / idle checks treat `cancel_requested` as live. No false quiescence.
- Recovery of an unknown effect linked to a `cancel_requested` run reports uncertainty and does not silently replay. The request is not acknowledgement.

Issue #56 additionally locked Chat conversation↔thread↔run reuse, recorded in [agents and workflows](modules/agents-workflows.md#locked-milestone-defaults-issue-56-chat-continuity) and [state and recovery](modules/state-recovery.md#locked-milestone-defaults-issue-56-chat-continuity):

- One Chat conversation owns one LangGraph `thread_id`. Each follow-up is a new harness run on that thread.
- Fresh conversation allocates a new thread. Project files and permitted durable knowledge stay.
- History edits are display-only. A model/profile switch continues the same thread on the next run.

The remainder stays open. Define identities beyond that linkage, parent/child semantics, remaining thread/checkpoint namespaces, event ordering/reconnection, remaining state transitions and actual stop reasons beyond this cancel pair. Map framework limits and interrupts to the pinned versions. Exactly-once across databases, files and services is still not claimed. Worker-adapter interrupt/cancel truth remains [ENV-003](modules/environments-tools.md#env-003).

[Issue #52](https://github.com/Vidcar/thtaib/issues/52) records the high-level [conversation ↔ execution-thread ↔ run](modules/agents-workflows.md#high-level-agent-chat-continuity-issue-52) product mapping (continue vs fresh; history-edit / model-switch effects; what reaches the harness). That mapping does **not** close this question: identity formats, resume across a model / adapter change, event-order / reconnection and exactly-once stay open. It is not a claim that current Chat implements continuity.

A durable product Approvals inbox is [OQ-011](#oq-011); a framework interrupt is not that inbox. Run observability outside Lab is [OQ-012](#oq-012). Builder v1 chrome locks Run/Stop, canvas highlight and a run inspector in [ADR-0003](decisions/ADR-0003-builder-v1-chrome.md); run-state semantics stay this question. Those chrome locks do not reopen this run-state contract.

**Evidence needed:** cancellation and crash tests before/after an external effect and checkpoint boundary, plus continuation beyond a measured upstream limit without duplicates. Executable unit checks for the dual-DB + linkage defaults are not that remainder evidence. UAT of the locked defaults remains local-machine-required on David-PC.

<a id="oq-005"></a>
## OQ-005: Consistent project snapshots and restoration

**Status:** partially constrained by [Issue #15](https://github.com/Vidcar/thtaib/issues/15) for Lab reuse and [Issue #66](https://github.com/Vidcar/thtaib/issues/66) for restore integrity. The question stays open.

**Owner:** Persistence/environment boundary. **Blocks:** remaining snapshot policy beyond the locked defaults — retention, concurrent-writer details beyond “fail if live tools are writing”, environment-snapshot adapters, and any mechanism other than the application-owned directory snapshot.

Issue #15 locked these defaults for LAB-001…004 and STATE-003. They are recorded in [Lab integration](modules/lab-evaluation.md#locked-milestone-defaults-issue-15-partial-oq-005) and [state and recovery](modules/state-recovery.md). Do not invent a different snapshot mechanism:

- Application-owned directory snapshot of the allowlisted project workspace at a quiescent capture boundary (fail if live tools are still writing; `cancel_requested` is still live).
- Store under `%LOCALAPPDATA%\LocalAIWorkbench\cases\` and `snapshots\`. Not git-commit-as-snapshot.
- Restore into a new workspace directory; linked branch run; never overwrite the parent.
- Include allowlisted project files, task, profile/deployment ids, dependency versions, memory/skill/protected-instruction version refs, tool fixtures and acceptance checks.
- Exclude secrets, weights/GGUF, `.scratch`, `.venv`, `node_modules` and env credentials.
- No full environment restore this milestone; record exclusions.

[Issue #66](https://github.com/Vidcar/thtaib/issues/66) additionally locked restore integrity for that directory snapshot. Recorded in [Lab integration](modules/lab-evaluation.md#locked-milestone-defaults-issue-66-restore-integrity) and [state and recovery](modules/state-recovery.md#locked-milestone-defaults-issue-66-restore-integrity):

- The captured tree directory must exist. A missing tree fails even when `included_files` is empty. An intentionally empty snapshot keeps an empty tree.
- Restore verifies every recorded path/sha256/size, rejects unexpected tree files, stages into a new workspace, and registers success only after validation. Failed staging is discarded.

Choose remaining snapshot policy: retention, concurrent writer details beyond the quiescent-capture fail, environment-snapshot adapters, and any mechanism other than the application-owned directory snapshot. Restore integrity for missing-tree / hash-mismatch / unexpected-file failure is no longer an open choice. Define the boundary between project files and an environment snapshot. Do not assume checkpoints or Git commits capture untracked files, dependencies, services or remote effects.

**Evidence needed:** capture during a controlled execution boundary, restore into a separate workspace, verify included inputs, expose exclusions and show the parent remains unchanged. UAT of the locked defaults remains local-machine-required on David-PC.

<a id="oq-006"></a>
## OQ-006: Memory, skills, retrieval and sensitive context

**Status:** partially constrained by [Issue #17](https://github.com/Vidcar/thtaib/issues/17) for the STATE-005 store. The question stays open.

**Owner:** Persistence/agent boundary. **Blocks:** automatic durable knowledge updates without an explicit scope policy, a retrieval/RAG product, or a decision that knowledge is shared across Chat, Lab and Builder versus surface-local.

Issue #17 locked the application-owned store defaults recorded in [state and recovery](modules/state-recovery.md#locked-milestone-defaults-issue-17-partial-oq-006). Those defaults do **not** select RAG, a shared index, or cross-surface sharing:

- Store under `%LOCALAPPDATA%\LocalAIWorkbench\knowledge\` (not checkpointer tables, not git).
- Versioned records with user/agent/project scopes, memory/skill/protected_instruction kinds, provenance and append-only history.
- Optimistic concurrency via expected `base_version`; mismatch is an explicit conflict.
- Protected instructions reject agent-origin writes; automatic agent writes need an explicit scope policy.
- Context-capture retention duration and redaction mode are local config; default is retain with secrets redacted.
- Backend API and an optional thin debug panel. Knowledge version ids are referenceable from Lab cases and harness setup.
- [Issue #64](https://github.com/Vidcar/thtaib/issues/64) applies that same capture policy to persisted AGT-002 diagnostic copies and requires Lab case export to sanitize or block detectable unsafe content. Conversation/checkpoint retention stays a separate operational policy. This does not select RAG or close the remainder of this question.

The remainder stays open. Choose retrieval/indexing integration separately from durable memory; the source has not selected a retrieval database. Clarify whether retrieval/RAG and durable knowledge are shared across Chat, Lab and Builder or remain surface-local, and what capture gaps a restored run must report beyond version refs. [AGT-004](modules/agents-workflows.md#agt-004) already separates active context from durable knowledge; it does not select a retrieval product, a shared index, or per-surface stores. Do not add RAG as a silent default or a second knowledge owner. [Issue #53](https://github.com/Vidcar/thtaib/issues/53) records that selected knowledge version refs must be loaded through those configured backends before a run ([effective setup](architecture.md#effective-setup-contract)). [Issue #57](https://github.com/Vidcar/thtaib/issues/57) loads that content into the harness system prompt. That is not a retrieval product and does not close this question.

**Evidence needed:** fresh-context reuse across surfaces if sharing is selected, a retrieval path that is not a second knowledge owner, and a redacted/retained context capture with declared limitations on a real David-PC workload. Executable unit checks for the locked store defaults are not that RAG/sharing evidence.

<a id="oq-007"></a>
## OQ-007: Compatibility evidence and model lifecycle details

**Status:** partial lifecycle and Windows CUDA defaults are implemented for [Issue #3](https://github.com/Vidcar/thtaib/issues/3) and [Issue #21](https://github.com/Vidcar/thtaib/issues/21). Provenance-capable compatibility records and the unverified≠incompatible distinction landed as a further partial on [Issue #31](https://github.com/Vidcar/thtaib/issues/31). Managed deployment ownership (serialized lifecycle, duplicate-start idempotence, process identity before destructive stop) landed as a further partial on [Issue #62](https://github.com/Vidcar/thtaib/issues/62). Full compatibility evidence, capability claims and complete setting-mapping verification remain open. This does not close the question.

**Owner:** Model-management boundary. **Blocks:** declaring model capabilities/configurations supported or exposing managed runtime controls as reliable.

Define compatibility-record schemas, evidence provenance, GGUF/companion-file resolution, runtime version identifiers, startup/request setting mapping and unsupported/unknown treatment. Specify cache reuse/interrupted download handling and the lifecycle authority over externally managed endpoints. Determine actual model-adapter parameter support against pinned dependencies.

Implemented now, without closing this question:

- Issue #3: import jobs that fail or are interrupted do not create a complete bundle or a successful deployment; connected attachments report `scope=connected` and reject start/stop/kill; a compatibility-records stub exists and does not claim support; PATH llama-server is unsupported.
- Issue #21: managed Windows NVIDIA hosts pin llama.cpp **b11045** CUDA 13.4 (`llama-b11045-bin-win-cuda-13.4-x64.zip` + `cudart-llama-bin-win-cuda-13.4-x64.zip`); NVIDIA absence is a clear error (no silent GPU claim); default GPU profile is `ctx_size` 65536, `n_gpu_layers` -1, valued `flash_attn`; `flash_attn` serializes as `--flash-attn on|off|auto` only; `local_executable` pins the full runtime directory; pin-while-running is reject or stop-first. Locked defaults are in [models](modules/models.md#locked-milestone-defaults-issue-21-partial-oq-007).
- Issue #31: versioned compatibility records carry requirements, supported capabilities/controls, recommendations, sources and validation evidence; publisher guidance, tested adjustments and user overrides stay separate; unverified ≠ known incompatible ≠ tested; unfamiliar models are not excluded for being unverified. Locked defaults are in [models](modules/models.md#locked-milestone-defaults-issue-31-partial-oq-007). This is not catalogue `verified`.
- Issue #53: the shared [effective setup contract](architecture.md#effective-setup-contract) records the three bags and selected ≠ loaded ≠ applied. It does not close complete setting-mapping verification or capability claims.
- Issue #57: the selected profile per-request bag is sent on the outbound adapter request; selected knowledge content is loaded into the harness. Startup mismatch, unsupported keys and capture gaps stay visible. This does not close complete setting-mapping verification or capability claims.
- Issue #62: per-deployment start/stop/health/reconcile are serialized; a verified-owned live deployment is returned on duplicate start; `process_identity` (pid, create_time, executable) is verified before destructive stop; a newly launched process that exits while another answers the endpoint is not recorded as a healthy owned deployment; restart re-adopts a matching process or clears ownership without killing a mismatched PID; connected endpoints stay non-destructive. Locked defaults are in [models](modules/models.md#locked-milestone-defaults-issue-62-deployment-ownership). This is not catalogue `verified` and is not David-PC UAT.

Multi-model routing and hybrid local GGUF / remote OpenAI-compatible deployments are [OQ-013](#oq-013). The model manager remains the owner; do not add a second inference engine.

**Evidence needed:** a managed model with companion files, a connected service, an unfamiliar model and an applied-setting mismatch exercised through the same recorded path on David-PC. CUDA/GPU/`flash_attn` product UAT remains [Issue #21](https://github.com/Vidcar/thtaib/issues/21) on David-PC; this pack audit is not that evidence.

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

**Status:** **partial.** Specification-integrity commands remain registered. Backend unittest, desktop type-check/build and shared-contract freshness are registered local commands and GitHub Actions jobs; exact status-check names are in [commands CI scope](commands.md#ci-scope). Those jobs exist **and** are merge-blocking required checks on public `main` (strict tip). They are not catalogue `verified` evidence and not build-stage acceptance. This does not close the question.

**Hosting / required-check decision (locked, [Issue #76](https://github.com/Vidcar/thtaib/issues/76); supersedes the [Issue #36](https://github.com/Vidcar/thtaib/issues/36) private-free / advisory-only hosting stance):** the repository is **public**. Classic branch protection on `main` requires the status checks listed in [commands CI scope](commands.md#ci-scope) with strict tip. Pro is unnecessary. There is **no open ask for David** to upgrade to Pro. Do not frame a Pro upgrade as a product requirement. Closed #36 acceptance-criteria history is unchanged; this entry records the later public + required-checks decision.

**Owner:** Boundary implementer; architecture maintainers approve stage evidence. **Blocks:** declaring the relevant implementation or build stage verified. The listed required checks do **not** close remaining product gates and are not an open David action.

Remaining choices: import-boundary checks, integration-test locations, live-tool versus recorded fixtures as product gates, platform/environment manifests, and David-PC UAT environments. Shared-contract generation/freshness is registered on [Issue #41](https://github.com/Vidcar/thtaib/issues/41) and is a required check on public `main`; it is not catalogue `verified` and not build-stage acceptance. Define repeatable starting inputs and evidence retention without storing secrets or model weights in this pack. Do not invent those missing gates as silent defaults. Do not invent extra required checks beyond the live list in [commands CI scope](commands.md#ci-scope).

**Evidence needed:** registered commands executed against actual code, negative/failure cases, and traceable results at a concrete revision. A green specification-integrity workflow is not stage acceptance. A green backend-unittest, desktop-typecheck-build or shared-contract-freshness job is not stage acceptance either. Green required CI is merge enforcement for those named checks; it is not catalogue `verified` and not product verification of remaining gates.

<a id="oq-011"></a>
## OQ-011: Durable product Approvals inbox

**Owner:** Backend/desktop and agent/workflow boundaries jointly; backend maintains the shared contract. **Blocks:** presenting a durable product Approvals inbox, or treating a framework interrupt as that inbox.

Human-in-the-loop approvals that survive reconnect, restart and a closed editor remain unresolved as a product surface. LangGraph interrupts and Deep Agents intervention hooks are framework mechanisms; they are not the Approvals inbox. [OQ-004](#oq-004) covers run-state, interrupt mapping and when human intervention is safe; it does not select inbox persistence, notification, or desktop presentation. [REG-004](modules/registry.md#reg-004) still requires one run hierarchy and that approvals cannot be bypassed; it does not design the inbox. Builder v1 chrome in [ADR-0003](decisions/ADR-0003-builder-v1-chrome.md) / [OQ-016](#oq-016) is not this inbox.

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

Datasets, scorers, compare-runs presentation and export beyond the Lab's Inspect-backed cases remain unresolved. [Lab integration](modules/lab-evaluation.md) already owns cases, restoration and evidence; it does not select dataset/scorer adapters or a comparison/export product. Do not add a second evaluation engine or treat Inspect as a complete Lab UX. The Model Lab surface is [LAB-006](modules/lab-evaluation.md#lab-006) (trait runs, not case replay); this question is **task-case** UX, not Model Lab.

**Evidence needed:** a documented compare or export path that preserves applied configuration and distinguishes executable checks from model judgement, with adapters named only after a reviewed decision.

<a id="oq-015"></a>
## OQ-015: Workflow definition import and export

**Owner:** Agent/workflow and integration-registry boundaries jointly. **Blocks:** shipping workflow import/export as a product feature.

Import and export of workflow definitions — including LangGraph JSON and any later adapters — remain unresolved. This is a definition interchange question, not a second runtime: LangGraph remains the outer-workflow owner and React Flow remains the definition editor. [OQ-008](#oq-008) covers registry schemas, version compatibility and discovery; it does not select an interchange format. Do not treat an imported graph as executable authority without backend validation.

**Evidence needed:** a round-trip or rejected import against a registered definition, with configuration links still excluded from execution sequencing ([WF-001](modules/agents-workflows.md#wf-001)).

<a id="oq-016"></a>
## OQ-016: Builder canvas and chrome UX

**Status:** v1 chrome is **partially decided** in [ADR-0003](decisions/ADR-0003-builder-v1-chrome.md). The question stays open for the unfinished Builder surface. This is not a Builder-shipped claim.

**Owner:** Desktop and agents/workflows boundaries jointly. **Blocks:** shipping Builder as a finished product surface.

[ADR-0003](decisions/ADR-0003-builder-v1-chrome.md) locks these **v1 chrome** choices. They are presentation only. Do not invent a different default look, and do not treat the ADR as an implemented canvas.

1. TooGraph-inspired cues, **original** layout (inspiration only — not a fork/pixel clone).
2. Grid, zoom, minimap, multi-select.
3. Icon rail + searchable node library.
4. Expanded nodes with inline prompt editor.
5. Run/Stop + canvas highlight + run inspector. Run-state semantics stay [OQ-004](#oq-004). A durable Approvals inbox stays [OQ-011](#oq-011).
6. Colour+label **workflow** edges; config via node badge/popover **not** a canvas config edge. [WF-001](modules/agents-workflows.md#wf-001) behaviour is unchanged: configuration links must not become executable workflow steps.
7. Inherit workflow profile/deployment; explicit per-node override only. [ARCH-003](architecture.md#arch-003) behaviour is unchanged: do not hide a per-node profile or silently default every slider on every node.

The remainder is an implementation Issue / unfinished surface: the React Flow Builder canvas, node library, run-inspector wiring, and product UAT. [API-002](modules/backend-desktop.md#api-002) still requires that the visual graph is not executable authority. The locked stack is not reopened.

TooGraph-ish cues remain **inspiration only**. TooGraph is not a pixel target and not a fork. Do not copy CDF/TooGraph, and do not treat a visual mock as a working integration.

**Evidence needed:** a later implementation Issue with matching specification, tests and evidence before Builder is presented as a finished product surface. [ADR-0003](decisions/ADR-0003-builder-v1-chrome.md) records chrome only. A TooGraph screenshot, mockup resemblance, or unpublished preference is not implementation evidence.
