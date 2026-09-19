# Backend and desktop

[Architecture](../architecture.md) · [Status and evidence](../catalog.json) · [Decisions](../decisions/changelog.md)

## Purpose

One FastAPI backend coordinates records, jobs, approvals and events; one Electron desktop presents them. The desktop edits, the backend executes, and what the user sees is what the records say.

## Boundaries and ownership

Python/FastAPI owns APIs, jobs, resources, run events, approvals, artifacts, optional budgets and shared records, and hosts the harness and workflow integrations. Electron/React/TypeScript presents the application; React Flow edits workflow definitions. Pydantic and JSON Schema validate shapes; application rules validate capability, access and compatibility. Source: [Revision 0.5, page 6](../sources/README.md#application-infrastructure).

## Interfaces and contracts

Privileged routes live under `/v1` (`bundles`, `profiles`, `deployments`, `runtime`, `imports`, `compatibility`, `agent-runs`, `agent-tools`, `chat`, `lab`, `knowledge`, `effects`, `events`); `GET /health` is public. The header envelope `X-Workbench-Local-Token`, the run-lifecycle names and the run-stream envelope (`RunStreamEnvelope`) are generated shared contracts ([contracts](../contracts.md)); the remaining route shapes (including the GET-equivalent `snapshot` record) are module-local Pydantic models mirrored by hand in `apps/desktop/src/renderer/types.ts` until moved onto the generated path. Event/stream contracts are bound (`shared-event-contracts` in [the repository map](../repository-map.json)).

`GET /v1/events` is `text/event-stream` (FastAPI `EventSourceResponse`). Query: exactly one of `run_id` or `conversation_id`. Header: `X-Workbench-Local-Token` (401 missing, 403 wrong); optional `Last-Event-ID` (integer, last received `run_event` seq). SSE `event` names and JSON `data` (`RunStreamEnvelope`):

| `event` | `id` | `data` |
| --- | --- | --- |
| `snapshot` | omitted | `type=snapshot`; `snapshot` is the current GET `/v1/agent-runs/{id}` or GET `/v1/chat/conversations/{id}` record; `run_id` / `conversation_id` / `status` set |
| `run_event` | 1-based `AgentEvent` index on that run | `type=run_event`; `seq`; `event` `{at, kind, detail}`; `status` |
| `stream_end` | omitted | `type=stream_end`; terminal or no live conversation run; response then closes |

Idle live streams use FastAPI keep-alive comments. The stream publishes application `AgentEvent` rows, not raw LangGraph chunks.

## Behaviour

- **Trust.** Shared secret at `state\desktop_backend_shared_secret`, created on first use. Electron main injects the header on loopback requests; the renderer runs with `contextIsolation`, no Node integration and a sandbox, and never holds the secret. Backend binds `127.0.0.1` only. Missing token → 401, wrong token → 403. CORS is not authorisation.
- **State honesty.** Events distinguish a request being accepted from an action finishing. `cancel_requested` is shown as live; `cancelled` is the confirmed stop. Deployment health and connection failures are reported with a classified code and the run is `failed`; no surface invents a completed reply or a finished job.
- **Streaming.** Run progress and events stream from the backend to the desktop over **SSE** (same-machine transport choice under [OQ-002](../open-questions.md#oq-002); WebSockets are not used). A disconnected client is not evidence a run ended. Reconnection sends a fresh `snapshot` of the persisted/in-memory record, then any `run_event` items after `Last-Event-ID`. The desktop subscribes while a run is live. Lab result checks that are not run events may use a slow fallback poll. [DEV-005](../deviations.md#dev-005) (750 ms polling) is closed.
- **Present surfaces.** Models, Deployments and debug-quality Chat, plus optional Agent-run, Lab and Knowledge debug panels that show raw records. Chat is not finished polish; Builder is not shipped.
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

Present run hierarchy, streamed progress, approvals, artifacts, checks, applied configuration and relevant context/knowledge information from shared records/events. Make active, queued, resource-constrained and failing sessions understandable; do not equate model confidence or a preview with completed work.

**Acceptance:** Follow a real task through progress, intervention, cancellation or failure to its persisted outcome. Compare visible state and evidence with actual execution records. Visible cancel state must distinguish `cancel_requested` from confirmed `cancelled`; do not present a requested cancel as idle.

<a id="api-005"></a>
### API-005: Keep provisioning distinct from job execution

The environment manager provisions workers/access, maps project storage and manages teardown. Docker Compose manages container services; adapters own jobs inside them.

**Acceptance:** Provision a worker, execute a tracked job and tear down through the appropriate owners. Verify that service readiness is not reported as task completion.

<a id="api-006"></a>
### API-006: Stream run and conversation events over SSE

One privileged SSE endpoint publishes application run events for an agent run or a Chat conversation. The harness still consumes LangGraph `stream_mode="updates"` and records `AgentEvent` rows; the stream publishes those application events, not raw graph chunks. Auth is the same `X-Workbench-Local-Token` header as other `/v1` routes. `Last-Event-ID` is the last received `run_event` seq (1-based index on that run). Closing the stream does not cancel the run. Cancel stays enabled only while the run is live.

**Acceptance:** Subscribe to `GET /v1/events` for a live run and for a live Chat conversation. Observe an initial `snapshot` then `run_event` items whose kinds match the persisted run record. Disconnect and confirm the run is still live. Reconnect with `Last-Event-ID` and receive a `snapshot` plus only later `run_event` items. Missing token → 401, wrong token → 403. A finished run's Cancel control is not enabled.

## Status and evidence

Rows API-001…006 in [the catalogue](../catalog.json). The 401/403 trust behaviour was seen live on Linux ([evidence](../evidence/2026-09-19-linux-live-smoke.md)) and on David-PC ([evidence](../evidence/2026-09-19-david-pc-managed-inference.md)); the Electron window itself has not been exercised on David-PC. SSE run events are `built` (unit tests), not `verified`.

## Open questions

[OQ-002](../open-questions.md#oq-002) remaining origin/IPC checks and remote access (SSE transport for same-machine run events is decided); [OQ-003](../open-questions.md#oq-003) worker provisioning; [OQ-004](../open-questions.md#oq-004) remaining identity, exactly-once and model-switch continuation; [OQ-011](../open-questions.md#oq-011) Approvals inbox; [OQ-016](../open-questions.md#oq-016) Builder surface.
