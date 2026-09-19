# Backend and desktop

[Architecture](../architecture.md) · [Status and evidence](../catalog.json) · [Decisions](../decisions/changelog.md)

## Purpose

One FastAPI backend coordinates records, jobs, approvals and events; one Electron desktop presents them. The desktop edits, the backend executes, and what the user sees is what the records say.

## Boundaries and ownership

Python/FastAPI owns APIs, jobs, resources, run events, approvals, artifacts, optional budgets and shared records, and hosts the harness and workflow integrations. Electron/React/TypeScript presents the application; React Flow edits workflow definitions. Pydantic and JSON Schema validate shapes; application rules validate capability, access and compatibility. Source: [Revision 0.5, page 6](../sources/README.md#application-infrastructure).

## Interfaces and contracts

Privileged routes live under `/v1` (`bundles`, `profiles`, `deployments`, `runtime`, `imports`, `compatibility`, `agent-runs`, `agent-tools`, `chat`, `lab`, `knowledge`, `effects`); `GET /health` is public. The header envelope `X-Workbench-Local-Token` and the run-lifecycle names are generated shared contracts ([contracts](../contracts.md)); the remaining route shapes are module-local Pydantic models mirrored by hand in `apps/desktop/src/renderer/types.ts` until moved onto the generated path. Event/stream contracts are unbound (`shared-event-contracts` in [the repository map](../repository-map.json)).

## Behaviour

- **Trust.** Shared secret at `state\desktop_backend_shared_secret`, created on first use. Electron main injects the header on loopback requests; the renderer runs with `contextIsolation`, no Node integration and a sandbox, and never holds the secret. Backend binds `127.0.0.1` only. Missing token → 401, wrong token → 403. CORS is not authorisation.
- **State honesty.** Events distinguish a request being accepted from an action finishing. `cancel_requested` is shown as live; `cancelled` is the confirmed stop. Deployment health and connection failures are reported with a classified code and the run is `failed`; no surface invents a completed reply or a finished job.
- **Present surfaces.** Models, Deployments and debug-quality Chat, plus optional Agent-run, Lab and Knowledge debug panels that show raw records. Chat is not finished polish; Builder is not shipped. Progress currently reaches the desktop by polling; streaming and reconnection are open ([OQ-002](../open-questions.md#oq-002)).
- **Provisioning versus execution.** The environment manager (future) provisions workers, maps project storage and tears down; adapters own jobs inside them; Compose manages container services. Service readiness is never reported as task completion.

## Requirements

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

Use Pydantic and JSON Schema for data/configuration validation. Application rules enforce capabilities, access and connector compatibility; a schema-valid object alone is not authorisation or proof of operational support. Privileged routes require the same-machine shared secret.

**Acceptance:** Send a well-typed but unauthorised or incompatible request and verify it is rejected at the relevant execution boundary.

<a id="api-004"></a>
### API-004: Expose real state and evidence

Present run hierarchy, progress, approvals, artifacts, checks, applied configuration and relevant context/knowledge information from shared records/events. Make active, queued, resource-constrained and failing sessions understandable; do not equate model confidence or a preview with completed work. Visible cancel state distinguishes `cancel_requested` from confirmed `cancelled`.

**Acceptance:** Follow a real task through progress, intervention, cancellation or failure to its persisted outcome. Compare visible state and evidence with actual execution records.

<a id="api-005"></a>
### API-005: Keep provisioning distinct from job execution

The environment manager provisions workers/access, maps project storage and manages teardown. Docker Compose manages container services; adapters own jobs inside them.

**Acceptance:** Provision a worker, execute a tracked job and tear down through the appropriate owners. Verify that service readiness is not reported as task completion.

## Status and evidence

Rows API-001…005 in [the catalogue](../catalog.json). The 401/403 trust behaviour was seen live on Linux ([evidence](../evidence/2026-09-19-linux-live-smoke.md)); Electron pairing has not been exercised on David-PC.

## Open questions

[OQ-002](../open-questions.md#oq-002) event streaming, reconnection and remote access; [OQ-003](../open-questions.md#oq-003) worker provisioning; [OQ-004](../open-questions.md#oq-004) event envelopes; [OQ-011](../open-questions.md#oq-011) Approvals inbox; [OQ-016](../open-questions.md#oq-016) Builder surface.
