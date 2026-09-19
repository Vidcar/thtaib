# Backend and desktop boundary

[Specification index](../README.md) · [Status and evidence](../catalog.json)

## Ownership, scope and source

Python/FastAPI owns APIs, jobs, resources, run events, approvals, artifacts, optional budgets and shared records, hosting the harness and workflow integrations. Electron/React/TypeScript presents the application; React Flow edits workflows. Source: [revision 0.5, page 6](../sources/README.md#application-infrastructure).

## Public contracts and collaboration

The desktop sends typed definitions and user actions, then displays backend state, progress, evidence and approvals. Model management supplies deployments; the agent/workflow integration owns task execution; adapters own external jobs; the backend coordinates these without introducing another agent loop. Pydantic/JSON Schema validate data; application rules validate capabilities and policy.

Issue #40 locks the same-machine shared-secret header and loopback bind recorded below. Event transport, remaining IPC origin checks and remote backend access are not selected here. Resolve those remainders at the contract boundary before claiming a finished trust model. Proposed contract generation is in [contracts](../contracts.md); Issue #41 owns the generated header envelope name `X-Workbench-Local-Token`.

## Lifecycle and failure

Represent what is active, queued, resource-constrained, awaiting intervention or failing. Handle backend startup/reconnection and external service failure without inventing successful work. Events and recorded results must distinguish a request being accepted from an action finishing. A cancel request is `cancel_requested` (still live); confirmed stop is `cancelled`. Exact event envelopes and remaining durable state transitions stay [OQ-004](../open-questions.md#oq-004).

## Requirements and acceptance checks

<a id="api-001"></a>
### API-001: Coordinate without replacing execution owners

The backend owns APIs, jobs, resource scheduling, events, approvals, artifacts and optional budgets while hosting Deep Agents and LangGraph. Its coordination must not become a second agent or workflow engine.

**Acceptance:** Trace a desktop task through the backend to the harness/graph and worker. Verify that job tracking does not duplicate the harness's reasoning/tool loop or LangGraph sequence.

<a id="api-002"></a>
### API-002: Edit in the desktop, execute in the backend

Electron/React presents controls, previews, context/evidence, memory editing, branches and tool panels. React Flow edits definitions. Backend validation and LangGraph execute workflows; the visual graph is not executable authority by itself.

**Acceptance:** Submit an invalid definition outside the visual editor and confirm backend rejection. Demonstrate that a successful screen interaction corresponds to a real backend action or is explicitly labelled a mock.

<a id="api-003"></a>
### API-003: Separate type validity from permission and capability

Use Pydantic and JSON Schema for data/configuration validation. Application rules enforce capabilities, access and connector compatibility; a schema-valid object alone is not authorisation or proof of operational support.

**Acceptance:** Send a well-typed but unauthorised or incompatible request and verify it is rejected at the relevant execution boundary.

<a id="api-004"></a>
### API-004: Expose real state and evidence

Present run hierarchy, progress, approvals, artifacts, checks, applied configuration and relevant context/knowledge information from shared records/events. Make active, queued, resource-constrained and failing sessions understandable; do not equate model confidence or a preview with completed work.

**Acceptance:** Follow a real task through progress, intervention, cancellation or failure to its persisted outcome. Compare visible state and evidence with actual execution records. Visible cancel state must distinguish `cancel_requested` from confirmed `cancelled`; do not present a requested cancel as idle.

<a id="api-005"></a>
### API-005: Keep provisioning distinct from job execution

The environment manager provisions workers/access, maps project storage and manages teardown. Docker Compose manages container services; adapters own jobs inside them.

**Acceptance:** Provision a worker, execute a tracked job and tear down through the appropriate owners. Verify that service readiness is not reported as task completion.

## Unresolved details

[OQ-002](../open-questions.md#oq-002) is **partially** constrained by [Issue #40](https://github.com/Vidcar/thtaib/issues/40) for same-machine shared-secret + loopback bind. Event streaming/reconnection, origin/IPC remainder, and remote backend access stay open. [OQ-001](../open-questions.md#oq-001) records the scaffold layout, manifests and packaging owner. [OQ-004](../open-questions.md#oq-004) covers state/events and [OQ-010](../open-questions.md#oq-010) covers remaining product test locations. [OQ-011](../open-questions.md#oq-011) covers the durable product Approvals inbox; a framework interrupt is not that inbox. [OQ-016](../open-questions.md#oq-016) records Builder v1 chrome as partially decided in [ADR-0003](../decisions/ADR-0003-builder-v1-chrome.md); the remainder is the unfinished surface.

Present desktop surfaces are Models, Deployments, debug-quality Chat, and optional Agent-run / Lab / Knowledge debug panels. Builder is not shipped. [API-002](#api-002) still requires the visual graph not to be executable authority. The [AGT-001](agents-workflows.md#agt-001) Chat tab is [Issue #22](https://github.com/Vidcar/thtaib/issues/22) and is not finished polish. Worker provisioning in [API-005](#api-005) stays [OQ-003](../open-questions.md#oq-003).

<a id="locked-milestone-defaults-issue-40-partial-oq-002"></a>
## Locked milestone defaults (Issue #40; partial OQ-002)

These defaults are authorised by [Issue #40](https://github.com/Vidcar/thtaib/issues/40). They satisfy the same-machine trust prerequisite for privileged Chat/Lab/project-file routes. They do **not** close [OQ-002](../open-questions.md#oq-002): event reconnection, remaining origin/IPC details, and remote backend access stay open. They are not a catalogue `verified` claim. David-PC UAT remains required.

- **Secret file:** `%LOCALAPPDATA%\LocalAIWorkbench\state\desktop_backend_shared_secret` (or the same filename under the portable product `state\` directory). Created on first use if missing. Never stored in the repository.
- **Header:** `X-Workbench-Local-Token` from the Issue #41 / ADR-0002 shared-contract envelope (`workbench_backend.contracts.auth`). Electron **main** injects the header on loopback backend requests. The renderer must not hold or send the secret.
- **Bind:** `127.0.0.1` only (v1). Non-loopback hosts are refused at process start. Remote backend is unsupported.
- **Unauthenticated / wrong token:** privileged routes, including Chat, Lab, project-file / workspace-file operations, knowledge, harness, effects, compatibility and model-manager `/v1` routes, return **401** (missing token) or **403** (wrong token). `GET /health` stays public for smoke identity. CORS is not authorisation.
- **Not claimed:** remote desktop/backend pairing, event-stream reconnection, a second auth scheme, or that UAT on David-PC has been run.
