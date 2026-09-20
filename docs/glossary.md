# Glossary

Terminology for [the product vision](../thtaib-vision.md) and [contracts](../specs/README.md). Implementation status belongs in [the catalogue](../specs/catalog.json).

## Product

**thtaib** — the intended product and repository. **Local AI Workbench** remains the desktop name and application data directory name.

**Workflows** — the intended visual agent-process area. **Agent run / Builder** are existing UI and legacy specification terms. The Agent-run panel exposes the embedded harness; the visual editor's graph is a definition, never executable authority ([WF-001](../specs/modules/agents-workflows.md#wf-001)).

**Chat** — the conversation surface, with or without a project folder. **Embedded harness** — the shared Deep Agents implementation used by Chat and agent workflow steps.

**Managed inference** — the application owns the pinned runtime and server process. **Connected endpoint** — an external server the application never starts, stops or kills. **Health ≠ ownership** — a healthy endpoint does not prove process ownership.

**Model bundle** — the manifest of quantisation, shards, companions, source revision, hashes and local paths. **Run profile** — saved startup, per-request and agent settings. **Running deployment** — a managed process or connected endpoint; a profile is not a deployment ([models](../specs/modules/models.md)).

**Startup / per-request / agent bags** — settings groups with separate application points. **Selected ≠ loaded ≠ applied** — a chosen reference, resident content and values actually sent are different facts ([effective setup](../specs/architecture.md#effective-setup)). **Unverified ≠ incompatible** — missing evidence is not known incompatibility.

**Conversation / execution thread / run** — the Chat record, LangGraph thread and one harness invocation. **Continue** reuses conversation and thread with a new run; **Fresh** creates both anew without erasing project files or durable knowledge. Displayed history is not execution context ([STATE-002](../specs/modules/state-recovery.md#state-002)).

**`cancel_requested` / `cancelled`** — requested stop versus confirmed stop. **Unknown-effect safety** — an unacknowledged external effect is never silently repeated after recovery ([STATE-004](../specs/modules/state-recovery.md#state-004)).

**Application directory snapshot** — a quiescent copy of allowlisted project files; neither a git commit nor rollback of external actions ([STATE-003](../specs/modules/state-recovery.md#state-003)).

**Durable knowledge** — versioned memories, skills and protected instructions. **Memory write-through** — harness memory edits becoming durable versions under the same owner. **Retrieval / RAG** — query-time search over a derived index, not a second store or training ([STATE-005/006](../specs/modules/state-recovery.md#state-005)).

<a id="model-lab"></a>
**Model Lab** — hardware-local trait and capability testing with measurements, outputs and failures. It does not automatically modify profiles ([LAB-005/006](../specs/modules/lab-evaluation.md#lab-005)).

<a id="task-cases-and-replay"></a>
**Task cases and replay** — restore starting inputs and compare **recorded-tool** fixture replay with **live-tool** execution. Recorded replay dispatches no live tools and is not live proof. **Trait catalogue** — Model Lab questions, distinct from task cases ([Lab contracts](../specs/modules/lab-evaluation.md)).

**Workers** — declared execution environments. **MCP server** — optional extra tools, not a worker or isolation. **MCP Apps** — interactive panels, distinct from ordinary MCP connectivity ([environments and tools](../specs/modules/environments-tools.md)).

**`X-Workbench-Local-Token`** — the desktop-to-backend secret header injected by Electron main; the renderer never holds it. **Product data** — durable application files and databases outside the repository ([architecture](../specs/architecture.md#persistence)).

## Verification

**David-PC** — David's Windows machine, used for managed CUDA and capability UAT. CI and tiny-model smoke prove scoped plumbing, not general model capability ([verification](../specs/verification.md)).

<a id="preferred-capability-uat-model"></a>
**Preferred capability UAT model (Qwen3.8-27B UD-IQ4_XS)** — `unsloth/Qwen3.8-27B-GGUF`, `Qwen3.8-27B-UD-IQ4_XS.gguf`, with the same repository's projector for vision and a pinned revision in its bundle. Reuse installed weights by path. Tiny models are for smoke/process tests, not reply or capability acceptance.

**`planned` / `built` / `verified`** — specified; implemented with automated checks; established by scoped live evidence. Exact rules live in [verification](../specs/verification.md).

**Scratch workspace** — gitignored root `.scratch/` for disposable development and UAT data; working rules live in [AGENTS.md](../AGENTS.md).

<a id="issue-tracking"></a>
## Issue tracking

**Project Status** — delivery state such as Backlog, In progress or Done. **Milestone** — the feature an issue belongs to. These organise work; they do not establish implementation or verification status.
