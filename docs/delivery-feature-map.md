# Delivery feature map

The plan for delivering Local AI Workbench, feature by feature, in the order David asked for. Issues are filed under these feature Milestones; Project Status tracks agent pipeline state separately ([glossary](glossary.md#issue-tracking)). Nothing here is a claim that a feature works; that is [the catalogue](../specs/catalog.json).

## Next path

Decided 2026-09-19: return to the Revision 0.5 build order and prove managed inference before more features.

1. **Managed inference proof on David-PC** — done on 2026-09-19 for pin → download → start → health → Chat turn → continuity → stop with the preferred capability UAT model ([evidence](../specs/evidence/2026-09-19-david-pc-managed-inference.md)); the runtime flag and `mmproj` fixes landed in PR #81. Remaining for the first `verified` rows: the clauses each acceptance line still lacks (companion files, an unsupported value, the connected half of MOD-004, project-less Chat) and the official mmproj for vision.
2. **Real-model CI smoke tier** — landed in PR #82; runs on every pull request. Remaining: make `real-model-smoke` a required check (maintainer action) and start recording its runs as `ci-smoke` evidence rows.
3. **Project storage hardening and streaming** — keep harness scratch out of the project folder ([DEV-004](../specs/deviations.md#dev-004)); stream run events instead of polling ([DEV-005](../specs/deviations.md#dev-005)); Chat without a project folder ([DEV-003](../specs/deviations.md#dev-003)); fix the profile `system_prompt` override; capture `llama-server` logs instead of discarding them.
4. **First worker environment** — Windows host shell with approvals on Deep Agents `permissions=`, `interrupt_on=` and `LocalShellBackend` ([OQ-003](../specs/open-questions.md#oq-003)).
5. **Retrieval research** — what LangChain's supported retrieval components deliver with little custom code; then specify under [OQ-006](../specs/open-questions.md#oq-006).
6. **Model Lab runners** (llama-bench and a tool-calling probe) on David-PC, then **Builder**.

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
| Knowledge, memory and skills | [STATE-005](../specs/modules/state-recovery.md#state-005), [AGT-004](../specs/modules/agents-workflows.md#agt-004) | OQ-006 |
| Snapshots and branching | [STATE-003](../specs/modules/state-recovery.md#state-003) | OQ-005 |
| Builder | [WF-001/002](../specs/modules/agents-workflows.md#wf-001), [API-002](../specs/modules/backend-desktop.md#api-002), [REG-001…003](../specs/modules/registry.md), [ADR-0003](../specs/decisions/ADR-0003-builder-v1-chrome.md) | OQ-008, OQ-015, OQ-016 |
| Access, environments and connectors | [ARCH-005/006](../specs/architecture.md#arch-005), [ENV-002](../specs/modules/environments-tools.md#env-002), [REG-002/004](../specs/modules/registry.md#reg-002), [API-003/005](../specs/modules/backend-desktop.md#api-003) | OQ-003, OQ-008, OQ-011 |
| Optional extras | [ARCH-007](../specs/architecture.md#arch-007), [ENV-004…006](../specs/modules/environments-tools.md#env-004) | OQ-009 |

## Handoffs between features

Chat, Lab and Builder share profiles, runs and artifacts through the [effective setup](../specs/architecture.md#effective-setup) rule; no surface hides its own profile. Task cases use the same harness and model path as Chat; a recorded-tool result is not live proof. Model Lab informs the user, never the profiles. Trust before workers: same-machine trust and continuity landed first; host-shell workers build on them. Builder consumes definitions the backend compiles; the canvas is never the executor.

## Specs still needed

Write these before treating the feature as specified: host-shell approval flow and surface (OQ-003); retrieval requirement after the LangChain research (OQ-006); Chat UX beyond debug quality; Builder canvas, node library and run inspector beyond the chrome ADR; access and connectors UX (OQ-011); task-case compare and export (OQ-014); event contracts and reconnection (OQ-002/004); run observability outside Lab (OQ-012); registry schemas (OQ-008); persistence convergence ADR (OQ-017). [Issue #37](https://github.com/Vidcar/thtaib/issues/37) remains the tracking issue for end-to-end gaps.
