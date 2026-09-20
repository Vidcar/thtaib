# Open architecture questions

Remaining design uncertainty, grouped by owner. Settled behavior belongs in the linked contracts, implementation status/evidence in [the catalogue](catalog.json), and working rules in [AGENTS.md](../AGENTS.md). Remove resolved questions after repairing incoming links; Git preserves their history. These questions do not authorize additional work in the current packet.

<a id="oq-002"></a>
## OQ-002: Desktop/backend trust and communication

**Owner:** backend/desktop. Remaining origin/IPC checks and whether remote backend access should ever be supported. Local binding alone is not security. Same-machine trust and SSE are settled in [API-001](modules/backend-desktop.md#api-001) and [API-006](modules/backend-desktop.md#api-006). Validate dropped-client reconnect and a real Electron/backend pairing before broader support claims.


<a id="oq-003"></a>
## OQ-003: Worker protocol, isolation and access policy

**Owner:** environments/tools. Decide executable/network access, credential delivery, sensitive mounts, installation rights and identities for later isolated or remote workers; define their cancellation/teardown guarantees. The existing [host-shell policy](modules/environments-tools.md#behaviour) and [MCP tools](modules/environments-tools.md#env-007) do not establish isolation. The durable inbox is [OQ-011](#oq-011).

[Host-shell evidence](evidence/2026-09-19-david-pc-host-shell.md) records HTTP approve/deny and no-project rejection. Remaining live checks include Electron approval, cancellation while interrupted, attempts beyond approved access, and host-versus-isolated behavior when later workers arrive.


<a id="oq-004"></a>
## OQ-004: Run state, continuation and uncertain effects

**Owner:** backend, agents and persistence. Resolve parent/child identities beyond conversation/thread/run, remaining transitions/stop reasons, model or adapter changes on a resumed thread, and recovery across databases, files and services. [STATE-001/002](modules/state-recovery.md#state-001) and [API-006](modules/backend-desktop.md#api-006) define current linkage/event ordering; they make no cross-service exactly-once promise. Validate crash/cancel at external-effect and checkpoint boundaries, plus continuation beyond a measured framework limit without duplicates.


<a id="oq-005"></a>
## OQ-005: Snapshot policy beyond directory copies

**Owner:** persistence/environments. Decide retention, concurrent-writer handling beyond rejection while live, environment adapters and the boundary between project files and environment state. [STATE-003](modules/state-recovery.md#state-003) defines current capture/restore. Validate controlled capture, separate restore, visible exclusions and unchanged parent on Windows; checkpoints/git commits alone do not capture services, dependencies or remote effects.


<a id="oq-006"></a>
## OQ-006: Memory, retrieval and restored context

**Owner:** persistence/agents. Decide whether a durable retrieval index or Deep Agents store is ever shared across surfaces (v1 creates neither), and what restored-context gaps must be reported for retrieval, memory/skills loading and memory write-through. Current decisions live in [STATE-005](modules/state-recovery.md#state-005), [STATE-006](modules/state-recovery.md#state-006) and [AGT-004](modules/agents-workflows.md#agt-004).

[Retrieval evidence](evidence/2026-09-20-david-pc-retrieval.md) records fail-closed cases and live offload under harness scratch. Remaining evidence includes recorded replay without a live index, other failure codes, Electron selectors, Lab/Agent-run paths, live memory/skills loading and write-through. Do not create another knowledge owner to resolve a capture gap.


<a id="oq-007"></a>
## OQ-007: Compatibility evidence and lifecycle details

**Owner:** models. Resolve how runtime observations and tested adjustments support capability claims, and validate remaining reasoning/template controls against the pinned runtime. Refine cache/recovery behavior for interrupted downloads and lifecycle boundaries for connected endpoints without granting ownership. [Models](modules/models.md) owns the contracts. Evidence must cover managed companions, a connected service, an unfamiliar model and an applied-setting mismatch; startup or `/props` alone is not capability proof.


<a id="oq-008"></a>
## OQ-008: Registry schemas, compatibility and extension loading

**Status:** open. **Owner:** integration-registry boundary. **Blocks:** the first stored graph, third-party adapter or shared definition version.

Open: canonical schemas and identifiers, version compatibility and migration, invalidation of stale definitions, discovery and trust of extensions, skills/plugins discovery UX. No plugin sandbox or hot reload follows from the word "registry". **Evidence needed:** compatible/incompatible/unverified fixtures; reload against a changed definition; rejection after a permission change.

<a id="oq-009"></a>
## OQ-009: Optional integrations

**Owner:** adapter/harness/desktop boundaries. Remaining choices cover rubric/interpreter middleware, background consolidation, [MCP Apps hosting](modules/environments-tools.md#env-005), voice and multimodal surfaces. Speech recognition and text-to-speech are separate choices; transcription alone does not deliver voice conversation. Each integration must preserve access, cancellation and events when enabled, while core paths work with it disabled. The ordinary MCP integration decision is settled in [ENV-007](modules/environments-tools.md#env-007), not reopened here.


<a id="oq-010"></a>
## OQ-010: Remaining verification coverage

**Owner:** the affected component. Decide the import-boundary check, broader managed Windows/worker integration coverage, live-versus-recorded fixture gates, UAT procedure/evidence retention, and whether real-model smoke should ever be required. These are future choices, not CI restructuring in this packet. Optional MCP plumbing belongs on the existing smoke path with in-process FastMCP; browser/GitHub capability checks require Windows UAT under [ENV-007](modules/environments-tools.md#env-007).

Read-only protection verification on 2026-09-20 confirmed strict `main` protection with exactly the four Ubuntu checks in [commands](commands.md#ci). Removing retired Windows check names is no longer a maintainer action. Current test tiers and verification rules remain in [commands](commands.md) and [verification](verification.md).


<a id="oq-011"></a>
## OQ-011: Durable product Approvals inbox

**Status:** open. **Owner:** backend/desktop and agent boundaries. **Blocks:** presenting approvals that survive reconnect and restart.

A LangGraph interrupt or Deep Agents `interrupt_on` is the mechanism; the product inbox (persistence, notification, presentation) is undesigned. **Evidence needed:** an approval that stays actionable after client disconnect and backend restart, with bypass denied on every path.

<a id="oq-012"></a>
## OQ-012: Run observability outside Lab

**Status:** open. **Owner:** backend, agent and Lab boundaries. **Blocks:** product-wide traces, token/cost accounting and parent/child observability.

Local traces, token and cost visibility and attribution outside Lab cases are undesigned. LangSmith or any hosted tracer is not the product home. **Evidence needed:** a local parent/child run with retained trace and cost fields and a statement of what is not captured.

<a id="oq-013"></a>
## OQ-013: Multi-model routing and hybrid deployments

**Status:** open. **Owner:** model-management boundary. **Blocks:** routing a task across models; mixing local GGUF with remote OpenAI-compatible endpoints.

The model manager stays the owner and llama.cpp the local engine; no second inference stack. **Evidence needed:** one routed or hybrid path that still uses deployment records with local and remote scopes distinguished.

<a id="oq-014"></a>
## OQ-014: Evaluation UX beyond Inspect

**Status:** open. **Owner:** Lab boundary. **Blocks:** a task-case evaluation UX (datasets, scorers, compare-runs, export) beyond Inspect building blocks. Model Lab ([LAB-006](modules/lab-evaluation.md#lab-006)) is a separate feature. No second evaluation engine; Inspect is not assumed to be the whole Lab UX. **Evidence needed:** a documented compare or export path that preserves applied configuration and distinguishes executable checks from model judgement, with adapters named only after a reviewed decision.

<a id="oq-015"></a>
## OQ-015: Workflow definition import and export

**Status:** open. **Owner:** agent/workflow and registry boundaries. **Blocks:** shipping import/export. Interchange only; LangGraph remains the runtime and an imported graph is not executable authority without backend validation ([WF-001](modules/agents-workflows.md#wf-001)). **Evidence needed:** a round-trip or rejected import against a registered definition with configuration links still excluded from execution sequencing.

<a id="oq-016"></a>
## OQ-016: Workflows canvas and inspection UX

**Owner:** desktop/agents. Resolve canvas, node-library and run-inspector interaction beyond the historical **Builder** chrome in [ADR-0003](decisions/ADR-0003-builder-v1-chrome.md). Validate the interface with matching contract checks and live use. The visual graph remains a definition rather than executable authority ([API-002](modules/backend-desktop.md#api-002)).


<a id="oq-017"></a>
## OQ-017: Remaining metadata migration

**Owner:** persistence. Storage choice is settled in [ADR-0005](decisions/ADR-0005-application-record-storage.md); the existing run/Chat JSON cutover is [already part of startup](commands.md#not-yet-available). Remaining work concerns inference, compatibility, Lab and knowledge metadata, not a new persistence authority.

Determine the family inventory and safe cutover sequence. Validate a migrated copy against every original record/reference, restart, interrupted import and rollback. Retain original JSON and a database backup until validated. This does not gate ordinary fixes, additive fields, model setup, Chat, capability evidence or memory write-through. Current boundaries are in [architecture](architecture.md#persistence).
