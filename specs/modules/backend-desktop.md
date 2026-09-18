# Backend and desktop boundary

[Specification index](../README.md) · [Status and evidence](../catalog.json)

## Ownership, scope and source

Python/FastAPI owns APIs, jobs, resources, run events, approvals, artifacts, optional budgets and shared records, hosting the harness and workflow integrations. Electron/React/TypeScript presents the application; React Flow edits workflows. Source: [revision 0.5, page 6](../sources/README.md#application-infrastructure).

## Public contracts and collaboration

The desktop sends typed definitions and user actions, then displays backend state, progress, evidence and approvals. Model management supplies deployments; the agent/workflow integration owns task execution; adapters own external jobs; the backend coordinates these without introducing another agent loop. Pydantic/JSON Schema validate data; application rules validate capabilities and policy.

No HTTP routes, event transport, IPC arrangement, authentication mechanism or public port is selected here. Resolve these at the contract boundary before connecting a privileged desktop to real execution. Proposed contract generation is in [contracts](../contracts.md).

## Lifecycle and failure

Represent what is active, queued, resource-constrained, awaiting intervention or failing. Handle backend startup/reconnection and external service failure without inventing successful work. Events and recorded results must distinguish a request being accepted from an action finishing. Exact event envelopes and durable state transitions remain open.

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

**Acceptance:** Follow a real task through progress, intervention, cancellation or failure to its persisted outcome. Compare visible state and evidence with actual execution records.

<a id="api-005"></a>
### API-005: Keep provisioning distinct from job execution

The environment manager provisions workers/access, maps project storage and manages teardown. Docker Compose manages container services; adapters own jobs inside them.

**Acceptance:** Provision a worker, execute a tracked job and tear down through the appropriate owners. Verify that service readiness is not reported as task completion.

## Unresolved details

[OQ-002](../open-questions.md#oq-002) blocks privileged API/desktop connectivity until authentication, origin/IPC trust, event reconnection and transport are specified. [OQ-001](../open-questions.md#oq-001) records the scaffold layout, manifests and packaging owner; a provisional loopback health endpoint does not close that trust question. [OQ-004](../open-questions.md#oq-004) covers state/events and [OQ-010](../open-questions.md#oq-010) covers remaining product test locations.
