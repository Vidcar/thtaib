# Delivery feature map

The plan for delivering Local AI Workbench, feature by feature, in the order David asked for. Issues are filed under these feature Milestones; Project Status tracks agent pipeline state separately ([glossary](glossary.md#issue-tracking)). Nothing here is a claim that a feature works; that is [the catalogue](../specs/catalog.json).

## Next path

This is the canonical ordered next path. Keep the usable local model and Chat journey ahead of roadmap expansion. Current acceptance contracts and requirement status live in [the spec index](../specs/README.md) and [catalogue](../specs/catalog.json); completed PR history belongs in Git, not another status log.

1. Make model configuration, capability evidence and Chat dependable together: guided Hugging Face repo / variant / companion selection, immutable revision capture, complete bundle records, model-aware defaults, visible requested/resolved/sent/runtime-observed settings, managed start, conversation continuation, cancellation and reopening. Capability probes record provenance, inputs, runtime/template/companion/configuration identity, outcomes and opt-outs; absence of a probe is `untested`, not incompatibility. Re-run live checks when those paths change; use [commands](../specs/commands.md) for the normal local loop.
2. Preserve existing project file tasks and host-shell approvals while extending Chat on the same shared setup: child-policy-safe delegation, conversation-adjacent context/reasoning controls with honest managed reload impact, and the minimum durable memory path already specified in [OQ-006](../specs/open-questions.md#oq-006) (official `memory=` loading plus live-tool `/memories/**` write-through into Knowledge versions). Keep retrieval derived and optional; do not turn this into a large RAG, background consolidation or second knowledge-store project.
3. Resume Lab, Builder and optional connector work only after the shared model/configuration/evidence path is honest enough for Chat. The fixed tiny-model smoke and any `llama-bench -p 16 -n 8` style check are plumbing, not capability or context-performance evidence. Builder keeps intended LangGraph cycles, per-owning-agent setup and configuration-versus-workflow links specified, but the current compiler is partial validation and still rejects cycles.
4. Add optional integrations in place rather than as prerequisites: voice covers transcription, speech output and conversational interaction through established local components; MCP servers and MCP Apps remain optional extensions; cloud or remote providers may be added later without blocking the local path.
5. Migrate existing JSON metadata only after the inventory, backup, interrupted-import and rollback checks in [OQ-017](../specs/open-questions.md#oq-017). The storage choice is settled; migration is unfinished and is not a gate for the Chat-first path.

**Single next delivery:** implement cancellable, rerunnable tool/vision capability checks through the existing compatibility service, keyed to the exact bundle/runtime/configuration and preserving user opt-outs. First prove a real structured tool round-trip; then an actual image request. Unknown results must not block ordinary Chat.

The harness lifecycle stays together until a concrete change justifies extracting a responsibility. Its existing setup, middleware, retrieval and filesystem adapters are the extension points; do not split it just to reduce line count.

Grounding for continuation: **keep** the Windows-first single backend/desktop architecture, upstream ownership boundaries and shared effective setup; **correct** stale UI paths that ask ordinary users for commit SHAs or silently choose ambiguous projectors; **defer** richer Builder execution, full snapshot branching and background consolidation until the local model and Chat base is solid; **retire** the universal 64K default, silent projector selection and storage-migration-first gate. Tiny-model smoke remains valuable plumbing evidence, distinct from capability checks.

## Features

| Milestone | Feature | Done when |
| --- | --- | --- |
| [#3](https://github.com/Vidcar/thtaib/milestone/3) | Managed models and inference | I can import/pin a local model, start a managed deployment on my Windows GPU path, and see honest health and applied settings. |
| [#4](https://github.com/Vidcar/thtaib/milestone/4) | Agent Chat | I can work in Chat — with or without a project folder — with trusted desktop↔backend access, continuity that reaches the harness, and profiles/knowledge that apply for real. |
| [#5](https://github.com/Vidcar/thtaib/milestone/5) | Project tools and workers | I can authorise a real project task that reads/writes files and runs commands in the Windows host shell with approvals, with honest cancel and evidence. |
| [#6](https://github.com/Vidcar/thtaib/milestone/6) | Model Lab | I can run hardware-local model trait tests on my machine and read the results as data and charts. It never changes my profiles. Not task-case replay. |
| [#7](https://github.com/Vidcar/thtaib/milestone/7) | Task cases and replay | I can save a real run as a case, restore starting inputs, rerun recorded- versus live-tool, and compare evidence. |
| [#8](https://github.com/Vidcar/thtaib/milestone/8) | Knowledge, memory and skills | I can version, revert and steer durable user/agent/project knowledge and skills with a clear write policy; retrieval if LangChain delivers it cheaply. |
| [#9](https://github.com/Vidcar/thtaib/milestone/9) | Snapshots and branching | I can branch from a consistent project snapshot and try another route without overwriting the parent attempt. |
| [#10](https://github.com/Vidcar/thtaib/milestone/10) | Builder | I can design workflows visually under the ADR-0003 chrome with definition ≠ runtime and WF-001 behaviour. |
| [#11](https://github.com/Vidcar/thtaib/milestone/11) | Access, environments and connectors | I can control approvals, environments and guided add-tool/connectors under my policy. |
| [#12](https://github.com/Vidcar/thtaib/milestone/12) | Optional extras | Optional surfaces (voice, MCP Apps, interpreter) after the core is solid. |

## Where each feature is specified

| Feature | Requirements | Open questions |
| --- | --- | --- |
| Managed models and inference | [MOD-001…006](../specs/modules/models.md), [ARCH-004](../specs/architecture.md#arch-004) | OQ-007, OQ-013, OQ-017 |
| Agent Chat | [AGT-001…004](../specs/modules/agents-workflows.md), [STATE-001/002](../specs/modules/state-recovery.md), [API-001/004](../specs/modules/backend-desktop.md), [ARCH-003](../specs/architecture.md#arch-003), [MOD-005](../specs/modules/models.md#mod-005) | OQ-002, OQ-004 |
| Project tools and workers | [ENV-001…003](../specs/modules/environments-tools.md), [AGT-005/006](../specs/modules/agents-workflows.md#agt-005), [STATE-004](../specs/modules/state-recovery.md#state-004), [ARCH-005](../specs/architecture.md#arch-005), [API-003/005](../specs/modules/backend-desktop.md#api-003) | OQ-003, OQ-011 |
| Model Lab | [LAB-005/006](../specs/modules/lab-evaluation.md#lab-005), [LAB-001](../specs/modules/lab-evaluation.md#lab-001) | OQ-007 |
| Task cases and replay | [LAB-001…004](../specs/modules/lab-evaluation.md), [STATE-003](../specs/modules/state-recovery.md#state-003) | OQ-005, OQ-014 |
| Knowledge, memory and skills | [STATE-005](../specs/modules/state-recovery.md#state-005), [STATE-006](../specs/modules/state-recovery.md#state-006), [AGT-004](../specs/modules/agents-workflows.md#agt-004) | OQ-006 |
| Snapshots and branching | [STATE-003](../specs/modules/state-recovery.md#state-003) | OQ-005 |
| Builder | [WF-001/002](../specs/modules/agents-workflows.md#wf-001), [API-002](../specs/modules/backend-desktop.md#api-002), [REG-001…003](../specs/modules/registry.md), [ADR-0003](../specs/decisions/ADR-0003-builder-v1-chrome.md) | OQ-008, OQ-015, OQ-016 |
| Access, environments and connectors | [ARCH-005/006](../specs/architecture.md#arch-005), [ENV-002](../specs/modules/environments-tools.md#env-002), [ENV-007](../specs/modules/environments-tools.md#env-007), [REG-002/004](../specs/modules/registry.md#reg-002), [API-003/005](../specs/modules/backend-desktop.md#api-003) | OQ-003, OQ-008, OQ-011 |
| Optional extras | [ARCH-007](../specs/architecture.md#arch-007), [ENV-004…006](../specs/modules/environments-tools.md#env-004) | OQ-009 |

## Handoffs between features

Chat, Lab and Builder share profiles, runs and artifacts through the [effective setup](../specs/architecture.md#effective-setup) rule; no surface hides its own profile. Task cases use the same harness and model path as Chat; a recorded-tool result is not live proof. Model Lab informs the user, never the profiles. Trust before workers: same-machine trust and continuity landed first; host-shell workers build on them. Builder consumes definitions the backend compiles; the canvas is never the executor.
