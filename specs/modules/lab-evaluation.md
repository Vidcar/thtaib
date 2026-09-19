# Lab and evaluation integration

[Specification index](../README.md) · [Status and evidence](../catalog.json)

## Ownership, scope and source

llama-bench measures engine performance. Inspect AI supplies task-evaluation building blocks. The application Lab owns two product features that must not merge: [Model Lab](../../docs/glossary.md#model-lab) (hardware-local trait/capability tests) and [Task cases and replay](../../docs/glossary.md#task-cases-and-replay) (capture, restore, rerun). Cases, starting-state restoration, evidence and comparisons share records with Chat/Builder. Source: [revision 0.5, pages 4 and 6](../sources/README.md#application-infrastructure) and [build checks](../sources/README.md#build-order). [Issue #54](https://github.com/Vidcar/thtaib/issues/54) records the Model Lab catalogue and UX below; it is not a revision 0.5 extraction and does not close [OQ-007](../open-questions.md#oq-007) or [OQ-014](../open-questions.md#oq-014).

## Public contracts and collaboration

A captured case links initial project snapshot, task, profiles, dependency versions, selected memory/skills, tool fixtures and acceptance checks. A case result links applied settings, deviations, artifacts and executable/model-review outcomes. Exact dataset/scorer adapters are not selected here.

A Model Lab trait run links a selected bundle, deployment and profile, one or more catalogue trait ids, applied settings, runner identity (or unavailable), measurements or failures, and resource observations. It is not a captured case. Exact runner and wire schemas are not selected here.

The Lab calls the same model/profile paths as normal work. Task cases also call the shared agent harness. Both consume the shared [effective setup contract](../architecture.md#effective-setup-contract); neither keeps a hidden Lab profile or treats stored ids as applied bags. The Lab does not add an evaluation-specific agent loop. Restoring an input state does not guarantee an identical model output. A trait run does not restore a task workspace. Capture / restore / rerun remains Task cases and replay, not Model Lab.

## Lifecycle and failure

Capture a case from a real run, restore its initial inputs into an appropriate workspace, execute it in recorded-tool or live-tool mode, and preserve outcome/deviations. Missing snapshots, external dependencies or permissions must be reported rather than silently replaced with convenient inputs.

A Model Lab trait run selects a managed bundle/deployment/profile and one or more catalogue traits, executes the matching local runners on David's machine, and preserves interpretable evidence. Missing runners, runtime or weights must be reported unavailable rather than replaced with invented scores. Trait runs do not capture, restore or replay a task workspace.

<a id="locked-milestone-defaults-issue-15-partial-oq-005"></a>
## Locked milestone defaults (Issue #15; partial OQ-005)

These defaults are authorised by [Issue #15](https://github.com/Vidcar/thtaib/issues/15). They do not close [OQ-005](../open-questions.md#oq-005) or [OQ-014](../open-questions.md#oq-014).

- **Snapshot:** application-owned directory snapshot of the allowlisted project workspace at a quiescent capture boundary. Capture fails if live tools or harness runs are still writing. `cancel_requested` is still live — do not treat a cancel request as a quiescent boundary. Store under `%LOCALAPPDATA%\LocalAIWorkbench\cases\` and `snapshots\`. Git commits are not snapshots.
- **Restore / branch:** restore into a new workspace directory and a linked branch run. Never overwrite the parent workspace or the original attempt.
- **Include:** allowlisted project files, task, profile and deployment ids, dependency versions, memory/skill/protected-instruction version refs from the [STATE-005 store](state-recovery.md#locked-milestone-defaults-issue-17-partial-oq-006), tool fixtures and acceptance checks. Knowledge version ids use the same reference pattern as profile and deployment ids. This does not select RAG.
- **Exclude:** secrets, weights/GGUF, `.scratch`, `.venv`, `node_modules` and env credentials.
- **Environment:** no full environment restore this milestone; record exclusions.
- **Engine:** llama-bench via the managed runtime when present; otherwise report unavailable. Do not invent scores. This stub is not the Model Lab catalogue or surface ([LAB-005](#lab-005)/[006](#lab-006)).
- **Task evaluation:** Inspect AI building blocks plus the existing Deep Agents harness / [MOD-005](models.md#mod-005). Same model, profile and harness paths. No second evaluation agent loop.
- **Surface:** minimal Lab API and an optional thin Lab panel. Not Chat or Builder polish. That panel is Task cases debug, not the Model Lab surface ([LAB-006](#lab-006)).
- **Modes:** recorded-tool and live-tool are labelled. A recorded result is not proof of a current live integration.

## Requirements and acceptance checks

<a id="lab-001"></a>
### LAB-001: Separate engine measurements from task evaluation

Use llama-bench for engine performance and Inspect AI for tasks. Agent tests call Deep Agents without a second model-and-tool loop. Adjustable Lab testing informs choices; it is not a prerequisite for ordinary model use.

**Acceptance:** Compare an engine measurement and an agent task evaluation, showing their different inputs/results and the shared harness used for the task.

<a id="lab-002"></a>
### LAB-002: Capture and restore actual starting inputs

Save the initial project snapshot, task, profiles, dependency versions, memory/skills, tool fixtures and acceptance checks. Restore the case and record deviations rather than assume that the latest project state matches the original run.

**Acceptance:** Save a real task as a case, change the working project, then rerun from the recorded initial state. Show the restored versions and any unavoidable deviation.

<a id="lab-003"></a>
### LAB-003: Distinguish recorded-tool and live-tool evaluation

Keep recorded-tool tests separate from live-tool tests. Exclude secrets from reusable cases. Do not promise identical model outputs or label a recorded response as proof of a current live integration.

**Acceptance:** Run both modes, inspect their labels and fixtures, and verify a secret-bearing value is excluded or safely redacted before case export.

<a id="lab-004"></a>
### LAB-004: Preserve interpretable evidence

Expose answers, failures, resource use, artifacts and checks rather than scores alone. Preserve applied configuration, distinguish executable checks from model judgement, and make profile differences visible across Lab, Chat and Builder.

**Acceptance:** Compare two case runs with a changed setting; inspect actual configuration and evidence for each outcome, including one failing executable check.

<a id="locked-high-level-defaults-issue-54-model-lab"></a>
## Locked high-level defaults (Issue #54; Model Lab ≠ Task cases)

These defaults are authorised by [Issue #54](https://github.com/Vidcar/thtaib/issues/54). They do not close [OQ-007](../open-questions.md#oq-007) or [OQ-014](../open-questions.md#oq-014). They do not implement runners, add a second evaluation loop, or merge Model Lab with Task cases (Milestone #7).

- **Feature:** hardware-local model trait / capability testing on David's machine. Not save-a-job-and-replay.
- **Catalogue:** extensible. Illustrative families are in [the trait catalogue](#model-lab-trait-catalogue). Adding a family is a focused Model Lab Issue, not a Task cases Issue.
- **Engine traits:** llama-bench via the managed runtime when present (the [Issue #15](https://github.com/Vidcar/thtaib/issues/15) stub). Report unavailable; do not invent scores.
- **Capability traits:** local probes against the same managed bundle, deployment and profile path. Not Inspect case replay, not a second agent loop, and not Chat.
- **Surface:** Model Lab UX is trait selection, run and evidence. The optional thin Lab panel from Issue #15 remains the Task cases debug path.
- **Use:** testing informs choices; it is not a prerequisite for ordinary model use ([ARCH-004](../architecture.md#arch-004), [LAB-001](#lab-001)).
- **Handoff:** results may later inform profiles and Chat without merging features ([ARCH-003](../architecture.md#arch-003)). That write-back contract is not specified here.
- **Build order:** this spec may parallel Chat docs. Model Lab implementation does not jump Chat build order.

<a id="model-lab-trait-catalogue"></a>
## Model Lab trait catalogue

The catalogue is a growing list of hardware-local questions, not a closed benchmark suite and not a task-case library. Families below are illustrative. A missing runner is `unavailable`; invented scores are forbidden.

| Family | What it asks on this machine | Typical runner kind | Explicitly not |
| --- | --- | --- | --- |
| Speed / throughput | Tokens/sec and latency for the selected bundle and settings | llama-bench (engine) | A Chat job replay |
| Prefill / decode at context lengths | Prefill versus decode at named context sizes | llama-bench / engine | A restored workspace |
| MTP | Multi-token prediction cost or behaviour on this host | Engine or capability probe | A captured task case |
| Quantisation impact | Same prompt and settings across recorded quants | Compare trait runs | Task-case compare / export ([OQ-014](../open-questions.md#oq-014)) |
| Concurrent conversations | Several parallel chats versus one | Capability / load probe | Harness case restore |
| Memory / needle | Retrieve a planted fact at long context | Capability probe | An Inspect scorer product |
| Tool calling | The model emits a usable tool call | Capability probe on the [MOD-005](models.md#mod-005) path | Recorded-tool case replay |
| Vision | Image in, honest result or unsupported | Capability probe; official mmproj in the same bundle | Chat polish or voice ([OQ-009](../open-questions.md#oq-009)) |

<a id="model-lab-catalogue-growth"></a>
### Catalogue growth path

1. Name the family in this catalogue with its runner kind and the evidence it must keep (applied settings, measurements or failures, resource use, unavailable-versus-failed).
2. File one focused Issue under Model Lab Milestone #6. One trait family per Issue is fine.
3. Implement the runner against the shared model-manager path. Report unavailable when the runtime, weights or companion files are missing. Never invent scores. Unverified remains distinguishable from incompatible ([ARCH-004](../architecture.md#arch-004), [MOD-006](models.md#mod-006)).
4. Do not attach the family to Task cases Milestone #7. Do not reuse capture / restore / rerun as the runner.

Capability UAT for reply, tool-calling, MTP or vision-related traits uses the [preferred capability UAT model](../../docs/glossary.md#preferred-capability-uat-model) when those traits are claimed. Tiny models remain smoke-only.

<a id="lab-005"></a>
### LAB-005: Publish an extensible hardware-local trait catalogue

Keep an application-owned catalogue of hardware-local model traits that can be measured on David's machine. The illustrative families in [the trait catalogue](#model-lab-trait-catalogue) are the starting set; the catalogue can grow by the [growth path](#model-lab-catalogue-growth). llama-bench covers engine-performance traits when present. Capability traits (tool calling, vision, needle, concurrency) are not llama-bench stubs and are not Inspect task-case replay. A missing runner reports unavailable. Do not invent scores. Lab testing is not a prerequisite for ordinary model use.

**Acceptance:** Inspect the catalogue and show the illustrative families, the growth path for a new family, and that a missing runner is reported as unavailable. Show that a trait run is not a captured task case and is not filed under Task cases Milestone #7.

<a id="lab-006"></a>
### LAB-006: Model Lab UX is trait runs, not case replay

The Model Lab surface lets David select a model bundle, running deployment and profile, choose one or more catalogue traits, run them locally, and inspect interpretable evidence (measurements, failures, applied settings, resource use, unavailable reasons). It is not capture, restore or rerun of a real agent job. Recorded-tool versus live-tool is a Task cases mode, not the Model Lab primary path. Results may later inform profiles and Chat without merging features. The existing thin Lab panel remains the Task cases debug surface. Model Lab implementation does not jump Chat build order.

**Acceptance:** Walk the Model Lab surface: start a trait run, see applied settings and evidence, and confirm there is no case-capture / restore / replay control on that path. Contrast with the Task cases path ([LAB-002](#lab-002)…[004](#lab-004)).

## Unresolved details

[OQ-005](../open-questions.md#oq-005) covers restorable starting states; [OQ-010](../open-questions.md#oq-010) covers remaining product gates beyond the registered backend/desktop commands. Optional beta grading support is tracked separately under [OQ-009](../open-questions.md#oq-009). [OQ-012](../open-questions.md#oq-012) covers run observability outside Lab. [OQ-014](../open-questions.md#oq-014) covers **task-case** evaluation UX beyond Inspect (datasets, scorers, compare-runs, export) — not the Model Lab surface in [LAB-006](#lab-006). Debug-quality Chat lands with Issue #22; Builder is not shipped. Lab sharing with those surfaces stays intended, not a finished-product claim.

Exact Model Lab runner adapters, wire contracts and how trait evidence writes back into shared profiles remain unspecified. That profile write-back is a later handoff, not permission to merge Model Lab with Task cases.

**Product feature split:** [Model Lab](../../docs/glossary.md#model-lab) ([LAB-005](#lab-005)/[006](#lab-006)) and [Task cases and replay](../../docs/glossary.md#task-cases-and-replay) ([LAB-002](#lab-002)…[004](#lab-004)) are separate delivery features. This module may describe both. [LAB-001](#lab-001) is the engine-versus-task measurement split; it is not permission to merge those features. See the [delivery feature map](../../docs/delivery-feature-map.md).
