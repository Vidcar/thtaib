# Delivery feature map

This is the four-layer plan for Local AI Workbench feature delivery. It is not a product novel, not a second architecture, and not a Status board.

**Standing rules (unchanged from [Issue #44](https://github.com/Vidcar/thtaib/issues/44)):** Project Status is agent pipeline state only. Milestone is which delivery an Issue belongs to. No due dates, sprints, or velocity. One Milestone per delivery; close it when that delivery’s Issues are done. Soft “I can…” slogan titles are superseded — the feature name is the title; done-when lives on the GitHub Milestone description. Locked terms are in the [glossary](glossary.md#issue-tracking). The process note is in [governance](../specs/governance.md#project-status-and-delivery-milestones).

**How to use this map.** Feature Milestones [**#3–#12**](https://github.com/Vidcar/thtaib/milestones) are the delivery homes for future Ready Issues. File a focused Issue under the matching feature Milestone; do not open a mega-implementation Issue. Process Milestones (Slice 1, standing rules, this map) are not feature homes. The ordered next work is [Next path](#next-path); [Deferred](#deferred) names later items so they are not silent scope.

Catalogue `implementation_status` on main is `partial` or `planned`. Nothing below is a catalogue `verified` claim.

<a id="next-path"></a>
## Next path

Ordered next slices, in plain English. File one focused Issue when that slice is actually Ready. This is not a board, not a mega-Issue, and not a catalogue `verified` claim.

1. **Agent Chat continuity (implementation)** — after or together with Chat continuity docs. Conversation ↔ execution-thread ↔ run must actually reach the harness ([#37](https://github.com/Vidcar/thtaib/issues/37) area 1). Sibling docs: [#52](https://github.com/Vidcar/thtaib/issues/52).
2. **Effective setup (implementation)** — after continuity. Selected profile and knowledge must change the request, not labels only ([ARCH-003](../specs/architecture.md#arch-003); [#37](https://github.com/Vidcar/thtaib/issues/37) area 2). Sibling docs: [#53](https://github.com/Vidcar/thtaib/issues/53).
3. **Workers / project tools** — only after 1 and 2, and only when [OQ-003](../specs/open-questions.md#oq-003) is locked or explicitly parked blocked. Trust-before-workers still applies ([#37](https://github.com/Vidcar/thtaib/issues/37)).
4. **Model Lab docs** may proceed in parallel with Chat docs. Model Lab **implementation** does not jump the Chat build order above. Sibling docs: [#54](https://github.com/Vidcar/thtaib/issues/54). Model Lab is not Task cases and replay.

<a id="deferred"></a>
## Deferred (named, not Ready)

Named so Access, Optional extras, and later UX are not silent scope. These are **not** Ready Issues. Do not file a mega-Issue from this list.

- **Workers surface** — product UX to authorise command/browser/graphical workers. Distinct from the gated workers/project-tools slice above; still blocked on [OQ-003](../specs/open-questions.md#oq-003).
- **Builder beyond chrome** — canvas, node library, run inspector after Chat/worker contracts ([ADR-0003](../specs/decisions/ADR-0003-builder-v1-chrome.md) is presentation only).
- **Knowledge steer UX** — version, revert, and steer on the existing store. Not a RAG product ([OQ-006](../specs/open-questions.md#oq-006) stays open).
- **Snapshot product UX** — branch / try-another-route beyond Lab restore ([OQ-005](../specs/open-questions.md#oq-005) remainder).
- **Task-case compare / export UX** — [OQ-014](../specs/open-questions.md#oq-014). Not Model Lab.
- **Access / connectors** — approvals, environment policy, guided add-tool. Later/visible. Optional extras stay later/thin ([ARCH-007](../specs/architecture.md#arch-007)).

<a id="integration-handoffs"></a>
## Integration handoffs

Name these when filing or sequencing work. They are handoffs, not permission to merge features.

| Handoff | Rule |
| --- | --- |
| Shared profiles / applied config | Chat, Lab, and Builder share configurations, runs, and artifacts. A surface must not hide its own profile or report equivalence from a name alone. Home: [ARCH-003](../specs/architecture.md#arch-003). |
| Definition ≠ runtime into Builder | [ADR-0003](../specs/decisions/ADR-0003-builder-v1-chrome.md) locks v1 chrome only. [WF-001](../specs/modules/agents-workflows.md#wf-001) behaviour is unchanged: configuration links are not executable steps. The visual graph is not executable authority ([API-002](../specs/modules/backend-desktop.md#api-002)). |
| Task cases → Chat / agent proof | Capture/restore/rerun uses the same Deep Agents harness and model/profile path as Chat. A recorded-tool result is not live proof. Homes: [LAB-001](../specs/modules/lab-evaluation.md#lab-001)…[004](../specs/modules/lab-evaluation.md#lab-004). |
| Model Lab results → profiles / Chat | Hardware-local trait evidence may inform profiles and Chat **without merging features**. Model Lab is not Task cases and replay. See [glossary](glossary.md#model-lab). |
| Trust before real workers | [Issue #37](https://github.com/Vidcar/thtaib/issues/37) order: trust → continuity / effective setup → worker. Slice 1 (#40–#42) landed the trust/contracts/cancel-honesty foundation. Do not broaden host shell/command workers ahead of that order. |

<a id="foundation"></a>
## Foundation remap (pointer only)

Shipped/closed work already attaches toward features. **Do not rewrite closed Issue acceptance criteria.** Reproduce against the implementation tip before treating any closed Issue as finished product proof.

| Closed Issue | Toward |
| --- | --- |
| [#1](https://github.com/Vidcar/thtaib/issues/1) Windows-first scaffold | All features (layout / toolchain) |
| [#3](https://github.com/Vidcar/thtaib/issues/3) managed inference MOD-001…004 | Managed models and inference |
| [#5](https://github.com/Vidcar/thtaib/issues/5) later-decision OQs | Several features (recorded questions, not selections) |
| [#7](https://github.com/Vidcar/thtaib/issues/7) `.scratch/` hygiene | All features (UAT temp) |
| [#9](https://github.com/Vidcar/thtaib/issues/9) preferred capability UAT model | Capability UAT (not a feature Milestone) |
| [#11](https://github.com/Vidcar/thtaib/issues/11) OQ-016 recorded | Builder (chrome question opened) |
| [#12](https://github.com/Vidcar/thtaib/issues/12) harness + MOD-005 | Agent Chat; Project tools (narrower than full worker) |
| [#15](https://github.com/Vidcar/thtaib/issues/15) Lab reuse LAB-001…004 + STATE-003 | Task cases and replay; Snapshots and branching |
| [#17](https://github.com/Vidcar/thtaib/issues/17) STATE-005 store | Knowledge, memory and skills |
| [#19](https://github.com/Vidcar/thtaib/issues/19) root README | Process (product entry) |
| [#21](https://github.com/Vidcar/thtaib/issues/21) CUDA 13.4 pin / default GPU profile | Managed models and inference |
| [#22](https://github.com/Vidcar/thtaib/issues/22) debug-quality Chat | Agent Chat (not polish) |
| [#23](https://github.com/Vidcar/thtaib/issues/23) pack completeness audit | Process |
| [#27](https://github.com/Vidcar/thtaib/issues/27) dual SQLite + app linkage | Agent Chat; Snapshots (STATE-001/002) |
| [#29](https://github.com/Vidcar/thtaib/issues/29) ADR-0003 Builder v1 chrome | Builder (chrome only; not shipped) |
| [#31](https://github.com/Vidcar/thtaib/issues/31) MOD-006 provenance + STATE-004 | Managed models; Project tools (unknown-effect safety) |
| [#32](https://github.com/Vidcar/thtaib/issues/32) advisory product CI | Process / verification |
| [#35](https://github.com/Vidcar/thtaib/issues/35) WF-001 definition compiler | Builder (definition≠runtime compile; not canvas) |
| [#36](https://github.com/Vidcar/thtaib/issues/36) OQ-010 advisory-CI honesty | Process |
| [#40](https://github.com/Vidcar/thtaib/issues/40)–[#42](https://github.com/Vidcar/thtaib/issues/42) Slice 1 trust, contracts, cancel honesty | Agent Chat; Project tools (trust-before-workers) |
| [#44](https://github.com/Vidcar/thtaib/issues/44) Status vs Milestone standing rule | Process |

[Issue #37](https://github.com/Vidcar/thtaib/issues/37) remains the open tracking Issue for remaining end-to-end gaps. Focused follow-ups link to it **and** attach the matching **feature** Milestone (#3–#12), not a second Status board.

<a id="what-we-are-building"></a>
## 1. What we are building

Ten feature Milestones. Titles are the GitHub names already set (#3–#12). Done-when text is copied from those Milestone descriptions.

| GH | Feature | Done when |
| --- | --- | --- |
| [#3](https://github.com/Vidcar/thtaib/milestone/3) | Managed models and inference | I can import/pin a local model, start a managed deployment on my Windows GPU path, and see honest health and applied settings. |
| [#4](https://github.com/Vidcar/thtaib/milestone/4) | Agent Chat | I can work in Chat with trusted desktop↔backend access, continuity that actually reaches the harness, and profiles/knowledge that apply for real — not labels only. |
| [#5](https://github.com/Vidcar/thtaib/milestone/5) | Project tools and workers | I can authorise a real project task that reads/writes files and (when enabled) runs commands, with honest cancel and evidence. |
| [#6](https://github.com/Vidcar/thtaib/milestone/6) | Model Lab | I can run hardware-local model trait/capability tests on my machine (speed/throughput; prefill/decode at context lengths; MTP; quantisation impact; concurrent conversations; memory/needle; tool calling; vision; etc. — catalogue can grow). This is NOT task case replay. Separate from Task cases and replay. |
| [#7](https://github.com/Vidcar/thtaib/milestone/7) | Task cases and replay | I can save a real run as a case, restore starting inputs, rerun recorded- vs live-tool, and compare evidence. Separate from Model Lab ([LAB-001](../specs/modules/lab-evaluation.md#lab-001) separation). |
| [#8](https://github.com/Vidcar/thtaib/milestone/8) | Knowledge, memory and skills | I can version, revert, and steer durable user/agent/project knowledge and skills with clear write policy. |
| [#9](https://github.com/Vidcar/thtaib/milestone/9) | Snapshots and branching | I can branch from a consistent project snapshot and try another route without overwriting the parent attempt. |
| [#10](https://github.com/Vidcar/thtaib/milestone/10) | Builder | I can design workflows visually under ADR-0003 chrome with definition≠runtime and WF-001 behaviour — not chrome-only. |
| [#11](https://github.com/Vidcar/thtaib/milestone/11) | Access, environments and connectors | I can control approvals, environments, and guided add-tool/connectors under my policy. Later/visible. |
| [#12](https://github.com/Vidcar/thtaib/milestone/12) | Optional extras | Optional surfaces (voice, MCP Apps, etc.) until core features are solid. Later/visible/thin. |

<a id="specs-that-already-exist"></a>
## 2. Specs that already exist

Honest map only. Module requirements are `partial` or `planned` in [the catalogue](../specs/catalog.json). Closed Issues are foundation pointers, not rewritten AC.

### Managed models and inference

- **Modules:** [models](../specs/modules/models.md) [MOD-001](../specs/modules/models.md#mod-001)…[006](../specs/modules/models.md#mod-006); [ARCH-004](../specs/architecture.md#arch-004).
- **ADRs:** none model-specific. [ADR-0002](../specs/decisions/ADR-0002-contract-authoring.md) supplies the shared-contract envelope used by deployments.
- **OQs:** [OQ-007](../specs/open-questions.md#oq-007) partial (#3 / #21 / #31); [OQ-013](../specs/open-questions.md#oq-013) open (routing / hybrid).
- **Issues:** closed [#3](https://github.com/Vidcar/thtaib/issues/3), [#21](https://github.com/Vidcar/thtaib/issues/21), [#31](https://github.com/Vidcar/thtaib/issues/31). David-PC UAT of the CUDA/GPU path remains on those Issues’ original local-machine tags.

### Agent Chat

- **Modules:** [AGT-001](../specs/modules/agents-workflows.md#agt-001), [AGT-002](../specs/modules/agents-workflows.md#agt-002), [AGT-004](../specs/modules/agents-workflows.md#agt-004); [STATE-001](../specs/modules/state-recovery.md#state-001)/[002](../specs/modules/state-recovery.md#state-002); [API-001](../specs/modules/backend-desktop.md#api-001)/[004](../specs/modules/backend-desktop.md#api-004); [ARCH-003](../specs/architecture.md#arch-003); [MOD-005](../specs/modules/models.md#mod-005). High-level continuity + UX beyond debug: [Issue #52](https://github.com/Vidcar/thtaib/issues/52) section in [agents and workflows](../specs/modules/agents-workflows.md#high-level-agent-chat-continuity-issue-52) (conversation ↔ execution thread ↔ run; continue vs fresh; history-edit / model-switch effects; what reaches the harness). Persistence intersection: [state and recovery](../specs/modules/state-recovery.md#high-level-agent-chat-continuity-issue-52). That spec does not close [OQ-004](../specs/open-questions.md#oq-004) and is not an implementation.
- **ADRs:** [ADR-0002](../specs/decisions/ADR-0002-contract-authoring.md) (`X-Workbench-Local-Token`).
- **OQs:** [OQ-002](../specs/open-questions.md#oq-002) partial (#40); [OQ-004](../specs/open-questions.md#oq-004) partial (#27 / #31 / #42); [OQ-006](../specs/open-questions.md#oq-006) store-only (#17).
- **Issues:** closed [#12](https://github.com/Vidcar/thtaib/issues/12), [#22](https://github.com/Vidcar/thtaib/issues/22), [#27](https://github.com/Vidcar/thtaib/issues/27), [#40](https://github.com/Vidcar/thtaib/issues/40), [#41](https://github.com/Vidcar/thtaib/issues/41), [#42](https://github.com/Vidcar/thtaib/issues/42). High-level continuity / UX spec [#52](https://github.com/Vidcar/thtaib/issues/52). Open tracker [#37](https://github.com/Vidcar/thtaib/issues/37) areas 1–2 (continuity impl; effective setup). Continuity implementation is [#56](https://github.com/Vidcar/thtaib/issues/56). Debug-quality Chat is not polish.

### Project tools and workers

- **Modules:** [ENV-001](../specs/modules/environments-tools.md#env-001)…[003](../specs/modules/environments-tools.md#env-003); [AGT-005](../specs/modules/agents-workflows.md#agt-005)/[006](../specs/modules/agents-workflows.md#agt-006); [STATE-002](../specs/modules/state-recovery.md#state-002)/[004](../specs/modules/state-recovery.md#state-004); [ARCH-005](../specs/architecture.md#arch-005); [API-003](../specs/modules/backend-desktop.md#api-003)/[005](../specs/modules/backend-desktop.md#api-005).
- **ADRs:** none worker-specific.
- **OQs:** [OQ-003](../specs/open-questions.md#oq-003) open (blocks real shell/browser/graphical workers); [OQ-002](../specs/open-questions.md#oq-002)/[004](../specs/open-questions.md#oq-004) remainders; [OQ-011](../specs/open-questions.md#oq-011) Approvals inbox.
- **Issues:** closed [#12](https://github.com/Vidcar/thtaib/issues/12) and [#22](https://github.com/Vidcar/thtaib/issues/22) landed harness + filesystem tools only (`execute` / `task` excluded). [#31](https://github.com/Vidcar/thtaib/issues/31)/[#42](https://github.com/Vidcar/thtaib/issues/42) landed unknown-effect and harness cancel honesty — not worker-adapter interrupt. [#40](https://github.com/Vidcar/thtaib/issues/40) is the trust prerequisite.

### Model Lab

- **Modules:** [LAB-001](../specs/modules/lab-evaluation.md#lab-001) separates engine measurements (llama-bench) from task evaluation. [MOD-003](../specs/modules/models.md#mod-003)/[006](../specs/modules/models.md#mod-006) and [ARCH-004](../specs/architecture.md#arch-004) cover applied settings and unverified≠incompatible. [OQ-007](../specs/open-questions.md#oq-007) remainder is compatibility evidence, not a Lab UX.
- **ADRs:** none.
- **OQs:** [OQ-007](../specs/open-questions.md#oq-007) remainder; [OQ-014](../specs/open-questions.md#oq-014) is evaluation UX for **task** cases, not this feature.
- **Issues:** no Issue specifies a hardware-local trait catalogue or Model Lab surface. Do not treat [#15](https://github.com/Vidcar/thtaib/issues/15) Lab reuse as Model Lab.

### Task cases and replay

- **Modules:** [lab-evaluation](../specs/modules/lab-evaluation.md) [LAB-001](../specs/modules/lab-evaluation.md#lab-001)…[004](../specs/modules/lab-evaluation.md#lab-004); [STATE-003](../specs/modules/state-recovery.md#state-003). Same harness as Chat ([AGT-001](../specs/modules/agents-workflows.md#agt-001)).
- **ADRs:** none.
- **OQs:** [OQ-005](../specs/open-questions.md#oq-005) partial (#15); [OQ-014](../specs/open-questions.md#oq-014) open (compare/export UX beyond Inspect).
- **Issues:** closed [#15](https://github.com/Vidcar/thtaib/issues/15) — capture → restore → rerun API and optional thin panel. Not Chat/Builder polish. Not Model Lab.

### Knowledge, memory and skills

- **Modules:** [STATE-005](../specs/modules/state-recovery.md#state-005); [AGT-004](../specs/modules/agents-workflows.md#agt-004).
- **ADRs:** none.
- **OQs:** [OQ-006](../specs/open-questions.md#oq-006) store defaults only (#17); RAG / cross-surface sharing unresolved.
- **Issues:** closed [#17](https://github.com/Vidcar/thtaib/issues/17). No Chat memory UI. Store is not a retrieval product.

### Snapshots and branching

- **Modules:** [STATE-003](../specs/modules/state-recovery.md#state-003); Lab restore-into-new-workspace defaults on [#15](https://github.com/Vidcar/thtaib/issues/15).
- **ADRs:** none.
- **OQs:** [OQ-005](../specs/open-questions.md#oq-005) remainder (retention, concurrent writers, environment-snapshot adapters).
- **Issues:** closed [#15](https://github.com/Vidcar/thtaib/issues/15) locked Lab snapshot defaults. Product branch UX beyond Lab restore is not specified.

### Builder

- **Modules:** [WF-001](../specs/modules/agents-workflows.md#wf-001) (compiler on [#35](https://github.com/Vidcar/thtaib/issues/35)); [WF-002](../specs/modules/agents-workflows.md#wf-002) planned; [API-002](../specs/modules/backend-desktop.md#api-002); [REG-001](../specs/modules/registry.md#reg-001)…[003](../specs/modules/registry.md#reg-003) planned (no application registry on main).
- **ADRs:** [ADR-0003](../specs/decisions/ADR-0003-builder-v1-chrome.md) v1 chrome only.
- **OQs:** [OQ-016](../specs/open-questions.md#oq-016) remainder (unfinished surface); [OQ-008](../specs/open-questions.md#oq-008) registry; [OQ-015](../specs/open-questions.md#oq-015) import/export.
- **Issues:** closed [#11](https://github.com/Vidcar/thtaib/issues/11), [#29](https://github.com/Vidcar/thtaib/issues/29), [#35](https://github.com/Vidcar/thtaib/issues/35). Builder is not shipped.

### Access, environments and connectors

- **Modules:** [ARCH-005](../specs/architecture.md#arch-005)/[006](../specs/architecture.md#arch-006); [ENV-002](../specs/modules/environments-tools.md#env-002); [REG-002](../specs/modules/registry.md#reg-002)/[004](../specs/modules/registry.md#reg-004); [API-003](../specs/modules/backend-desktop.md#api-003)/[005](../specs/modules/backend-desktop.md#api-005). All of these are `planned` except API-003 `partial`.
- **ADRs:** none for connectors or Approvals inbox.
- **OQs:** [OQ-003](../specs/open-questions.md#oq-003), [OQ-008](../specs/open-questions.md#oq-008), [OQ-011](../specs/open-questions.md#oq-011).
- **Issues:** none filed for this feature surface. Slice 1 trust is a prerequisite, not this delivery.

### Optional extras

- **Modules:** [ARCH-007](../specs/architecture.md#arch-007); [ENV-004](../specs/modules/environments-tools.md#env-004)…[006](../specs/modules/environments-tools.md#env-006) planned.
- **ADRs:** none.
- **OQs:** [OQ-009](../specs/open-questions.md#oq-009) (voice / MCP Apps / interpreter / MCP-as-bus).
- **Issues:** closed [#5](https://github.com/Vidcar/thtaib/issues/5) recorded the questions. No optional surface is a core prerequisite.

<a id="specs-still-needed"></a>
## 3. Specs still needed

Write these as focused docs/ADR/OQ resolutions **before** treating the matching feature as specified. Do not invent catalogue `verified` rows to fill a gap.

| Gap | Feature home | Why it is a gap |
| --- | --- | --- |
| Model Lab UX / trait catalogue | Model Lab | No surface, runner list, or evidence shape for hardware-local traits (speed, context, MTP, quant, concurrent chats, needle, tools, vision). [LAB-001](../specs/modules/lab-evaluation.md#lab-001) only splits engine measurements from task evaluation. |
| Agent Chat UX | Agent Chat | High-level continuity + UX beyond debug is specified on [#52](https://github.com/Vidcar/thtaib/issues/52) ([agents and workflows](../specs/modules/agents-workflows.md#high-level-agent-chat-continuity-issue-52)). [#22](https://github.com/Vidcar/thtaib/issues/22) remains debug-quality. Continuity implementation is [#37](https://github.com/Vidcar/thtaib/issues/37) area 1 / [#56](https://github.com/Vidcar/thtaib/issues/56). This is not Chat polish and not effective setup ([#53](https://github.com/Vidcar/thtaib/issues/53)). |
| Tools / workers surface | Project tools and workers | Enabled catalogue is visibility + filesystem tools. No product surface for authorising command/browser/graphical workers. [OQ-003](../specs/open-questions.md#oq-003) still blocks real workers. |
| Builder beyond chrome ADR | Builder | [ADR-0003](../specs/decisions/ADR-0003-builder-v1-chrome.md) is presentation. Canvas, node library, run-inspector wiring, and product UAT need an implementation Issue with matching spec — not a chrome-only claim. |
| Access / connectors | Access, environments and connectors | No UX for approvals, environment policy, or guided add-tool/connectors. [OQ-011](../specs/open-questions.md#oq-011) and [OQ-003](../specs/open-questions.md#oq-003) are unresolved. |
| Lab results → profiles / Chat | Model Lab **and** Task cases (handoff, not merge) | No spec for how trait evidence or case comparisons update shared profiles without hiding a per-surface setting ([ARCH-003](../specs/architecture.md#arch-003)). |
| Effective setup contract | Agent Chat (also Lab / Builder consumers) | High-level contract is recorded under [ARCH-003 effective setup](../specs/architecture.md#effective-setup-contract) ([Issue #53](https://github.com/Vidcar/thtaib/issues/53)). Apply-for-real (selected profile and knowledge version must affect the actual request) remains [#37](https://github.com/Vidcar/thtaib/issues/37) area 2. [REG-005](../specs/modules/registry.md#reg-005) is still `planned`. |
| Project / workspace ownership | Agent Chat; Snapshots | Whether Chat requires a project directory, and who owns workspaces across surfaces, is unset ([#37](https://github.com/Vidcar/thtaib/issues/37) area 5). |
| Files / images disposition | Agent Chat; Optional extras | Revision 0.5 mentions Chat files/images; voice stays [OQ-009](../specs/open-questions.md#oq-009). Attachment handling needs an explicit disposition, not a silent default. |
| Task-case compare / export UX | Task cases and replay | [OQ-014](../specs/open-questions.md#oq-014) — datasets, scorers, compare-runs, export beyond Inspect building blocks. |
| Snapshot product UX | Snapshots and branching | Lab restore-to-new-workspace exists; a product “try another route” surface and [OQ-005](../specs/open-questions.md#oq-005) remainder do not. |
| Knowledge steer UX | Knowledge, memory and skills | Store API + debug panel exist. Version/revert/steer in Chat (or a dedicated surface) is out of scope of [#17](https://github.com/Vidcar/thtaib/issues/17). [OQ-006](../specs/open-questions.md#oq-006) sharing/RAG stays open. |
| Registry as integration authority | Builder; Access / connectors | [REG-001](../specs/modules/registry.md#reg-001)…[004](../specs/modules/registry.md#reg-004) planned; [OQ-008](../specs/open-questions.md#oq-008) blocks stored graphs and third-party adapters. |
| Workflow import / export | Builder | [OQ-015](../specs/open-questions.md#oq-015) — interchange, not a second runtime. |
| Event contracts / reconnection | Agent Chat; Project tools | [OQ-002](../specs/open-questions.md#oq-002)/[004](../specs/open-questions.md#oq-004) remainders; `shared-event-contracts` unbound; [CTT-002](../specs/contracts.md) planned. |
| Run observability outside Lab | Agent Chat; Task cases | [OQ-012](../specs/open-questions.md#oq-012). LangSmith is not the product home. |
| Multi-model / hybrid routing | Managed models and inference | [OQ-013](../specs/open-questions.md#oq-013). Model manager owns it; no second inference engine. |

<a id="implementation-slices"></a>
## 4. Implementation slices

Per-feature reminders, not the ordered next work — that is [Next path](#next-path). Subsequent focused Issues under the **feature** Milestone. Not a mega-implementation Issue. Trust-before-workers ([#37](https://github.com/Vidcar/thtaib/issues/37) order) still applies.

### Managed models and inference (Milestone #3)

- Remaining [OQ-007](../specs/open-questions.md#oq-007) evidence on David-PC (capability claims, setting-mapping). Do not mark catalogue `verified` from unit tests.
- Applied-settings fidelity across Chat / Lab / (later) Builder — [ARCH-003](../specs/architecture.md#arch-003) / [MOD-003](../specs/modules/models.md#mod-003).
- [OQ-013](../specs/open-questions.md#oq-013) routing only after the core managed path is solid.

### Agent Chat (Milestone #4)

- Continuity implementation: conversation ↔ execution-thread ↔ run against the [#52](https://github.com/Vidcar/thtaib/issues/52) high-level mapping ([#37](https://github.com/Vidcar/thtaib/issues/37) area 1 / [#56](https://github.com/Vidcar/thtaib/issues/56)).
- Effective setup: profile and knowledge actually reach the harness ([#37](https://github.com/Vidcar/thtaib/issues/37) area 2 / [#53](https://github.com/Vidcar/thtaib/issues/53) spec). Do not merge with this continuity spec.
- Agent Chat UX beyond debug-quality [#22](https://github.com/Vidcar/thtaib/issues/22) — high-level IA is on [#52](https://github.com/Vidcar/thtaib/issues/52); polish still follows the two implementation slices above, not instead of them.
- Event reconnection remainder ([OQ-002](../specs/open-questions.md#oq-002)) as its own slice when continuity needs it.

### Project tools and workers (Milestone #5)

- **After** trust (Slice 1 landed) **and** Chat continuity / effective setup.
- First authorised worker environment ([OQ-003](../specs/open-questions.md#oq-003)) — one declared environment, not every platform.
- Tools / workers surface (spec first if still missing).
- Worker-adapter cancel / recover truth ([ENV-003](../specs/modules/environments-tools.md#env-003)) — harness honesty [#42](https://github.com/Vidcar/thtaib/issues/42) is not this slice.

### Model Lab (Milestone #6)

- Model Lab UX / trait catalogue spec (required before runners).
- Hardware-local trait slices on David-PC (catalogue can grow; one trait family per Issue is fine).
- Results informing profiles / Chat — handoff only; do not merge with Task cases.

### Task cases and replay (Milestone #7)

- Cases as Chat / agent proof (same harness; recorded vs live labelled).
- Lab results → profiles / Chat handoff spec (shared with Model Lab’s inform-without-merge rule).
- [OQ-014](../specs/open-questions.md#oq-014) compare / export when Inspect building blocks are no longer enough.

### Knowledge, memory and skills (Milestone #8)

- Steer / write-policy UX on the existing [STATE-005](../specs/modules/state-recovery.md#state-005) store.
- [OQ-006](../specs/open-questions.md#oq-006) sharing / retrieval only after an approved decision — not a silent RAG project.

### Snapshots and branching (Milestone #9)

- Product branch UX on the [#15](https://github.com/Vidcar/thtaib/issues/15) restore-to-new-workspace defaults.
- [OQ-005](../specs/open-questions.md#oq-005) remainder (retention, environment snapshot) as a separate slice.

### Builder (Milestone #10)

- After proven Chat / worker contracts ([#37](https://github.com/Vidcar/thtaib/issues/37) step 3) — do not prioritise canvas polish over execution evidence.
- Builder beyond chrome: React Flow canvas, node library, run inspector, product UAT.
- Definition≠runtime into the surface ([WF-001](../specs/modules/agents-workflows.md#wf-001) already compiles; [API-002](../specs/modules/backend-desktop.md#api-002) still applies).
- [WF-002](../specs/modules/agents-workflows.md#wf-002) delegation / cycle ownership when the canvas exists.
- [OQ-015](../specs/open-questions.md#oq-015) import / export later.

### Access, environments and connectors (Milestone #11)

- Access / connectors spec first (later/visible).
- [OQ-011](../specs/open-questions.md#oq-011) Approvals inbox — not a LangGraph interrupt.
- Environment policy UX after [OQ-003](../specs/open-questions.md#oq-003) selects the first worker model.

### Optional extras (Milestone #12)

- Thin / later. File under this Milestone only for an optional surface that must not become a core prerequisite ([ARCH-007](../specs/architecture.md#arch-007), [OQ-009](../specs/open-questions.md#oq-009)).
