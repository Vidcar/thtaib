# Lab and evaluation

[Architecture](../architecture.md) · [Status and evidence](../catalog.json) · [Decisions](../decisions/changelog.md)

## Purpose

Two separate features share this module. **Model Lab** presents data and charts that answer hardware-local questions about a model on David's machine (speed, context behaviour, tool calling, vision) so he can understand its behaviour; it is read-only towards the rest of the product. **Task cases and replay** saves a real run as a case, restores its starting inputs and reruns it with recorded or live tools so evidence can be compared. They must not merge.

## Boundaries and ownership

llama-bench measures engine performance. Inspect AI supplies task-evaluation building blocks. The Lab owns cases, trait runs, starting-state restoration, evidence and comparison, and calls the same model manager, profiles and Deep Agents harness as normal work; it never adds an evaluation agent loop. Source: [Revision 0.5, pages 4 and 6](../sources/README.md#application-infrastructure) and [build checks](../sources/README.md#build-order).

## Interfaces and contracts

Routes under `/v1/lab/`: `workspaces` (create, list, get, files), `cases/capture`, `cases/{id}` (get, `export`, `restore`, `rerun`), `snapshots/{id}`, `results`, `engine-measurements`. A **case** links starting snapshot, task, profile and deployment ids, dependency versions, knowledge version refs, tool fixtures and acceptance checks. A **case result** links applied settings, deviations, artifacts and executable versus model-review outcomes. A **trait run** links bundle, deployment, profile, trait ids, applied settings, runner identity (or `unavailable`), measurements or failures and resource observations. Exact runner and scorer adapters are unselected.

## Behaviour

**Replay matching.** Consume the first unused fixture with equal tool name and canonical arguments: sorted keys, omitted `None`, path-like values normalized to POSIX without a leading `/`. Missing, exhausted or mismatched captures fail with `recorded_fixture_missing`, `recorded_fixture_exhausted` or `recorded_fixture_arg_mismatch`; never fall back to live execution. Reconstructed `write_file` / `edit_file` bytes are labelled fixture application and confined to the replay workspace.

**Task cases.** Capture from a real run reuses the run's `starting` snapshot; a run without one reports `starting_snapshot_unavailable` rather than presenting current files as inputs. Restore goes to a new workspace and a linked branch run ([state and recovery](state-recovery.md)). Rerun is labelled `recorded-tool` or `live-tool`. Recorded mode attaches no live project, host-shell, or retrieval backend; knowledge routes may use scratch or `StateBackend` so official `memory=` / `skills=` middleware can `download_files`. Fixtures match by tool name and canonical arguments, and a missing, exhausted or mismatched fixture fails the run with a recorded deviation. Matched write fixtures apply only inside the replay workspace and must not write-through into STATE-005. Live-tool mode uses `FilesystemBackend` bound to project storage and stays labelled `live-tool`; when `memory=` is attached, official `/memories/**` writes write-through like Chat. Missing snapshots, external dependencies or permissions are reported, never replaced with convenient inputs. Export sanitises or blocks detectable secrets in task text, tool fixtures and included files using the knowledge redaction detector; filename exclusions alone are not sufficient; `secret_scan_clean` is true only when nothing was detected; stored local cases and snapshots are not rewritten by export. Restoring inputs never promises identical model output.

**Engine measurements.** llama-bench from the managed runtime when present; otherwise `unavailable`. Scores are never invented. A fixed smoke command such as `llama-bench -p 16 -n 8` proves only that the runner can invoke the binary; it is not context-performance evidence and must not be labelled as performance at a configured 64K/256K context. Context traits record configured capacity, actual prompt/past-context occupancy, prefill/decode measurements, applied runtime settings, warmup/cache condition, generated length, repetitions and resource use.

<a id="trait-catalogue"></a>
**Model Lab trait catalogue.** A growing list of hardware-local questions, one family per issue, each keeping applied settings, measurements or failures, resource use and unavailable-versus-failed. Starting families: speed/throughput and prefill/decode at named context sizes (llama-bench); MTP cost; quantisation impact across recorded quants; concurrent conversations; memory/needle at long context; tool calling on the [MOD-005](models.md#mod-005) path; vision with the official mmproj in the same bundle. A trait run selects a bundle, deployment and profile; it never restores a task workspace. Capability traits use the [preferred capability UAT model](../../docs/glossary.md#preferred-capability-uat-model); tiny models are smoke only. Testing informs the user's choices and is never a prerequisite for using a model ([ARCH-004](../architecture.md#arch-004)). **Model Lab never writes back into shared profiles and has no one-click apply** (product owner decision, 2026-09-19): it presents measurements, failures and charts; any profile change is made by the user in the Models surface.

## Requirements

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

Keep recorded-tool tests separate from live-tool tests. Exclude or redact secrets from reusable cases before export, using the same detector as context captures. Do not promise identical model outputs or label a recorded response as proof of a current live integration.

**Acceptance:** Run both modes, inspect their labels and fixtures, and verify a secret-bearing value is excluded or safely redacted before case export.

<a id="lab-004"></a>
### LAB-004: Preserve interpretable evidence

Expose answers, failures, resource use, artifacts and checks rather than scores alone. Preserve applied configuration, distinguish executable checks from model judgement, and make profile differences visible across Lab, Chat and Workflows.

**Acceptance:** Compare two case runs with a changed setting; inspect actual configuration and evidence for each outcome, including one failing executable check.

<a id="lab-005"></a>
### LAB-005: Publish an extensible hardware-local trait catalogue

Keep an application-owned catalogue of hardware-local model traits that can be measured on David's machine, starting from the families in the [trait catalogue](#trait-catalogue) and growing one family per issue. llama-bench covers engine-performance traits when present. Capability traits are not llama-bench stubs and not Inspect task-case replay. A missing runner reports unavailable; scores are never invented.

**Acceptance:** Inspect the catalogue and show the starting families, the growth path for a new family, and that a missing runner is reported as unavailable. Show that a trait run is not a captured task case and is not filed under the Task cases Milestone.

<a id="lab-006"></a>
### LAB-006: Model Lab UX is trait runs, not case replay

The Model Lab surface lets David select a bundle, running deployment and profile, choose one or more traits, run them locally and inspect interpretable evidence as data and charts (measurements, failures, applied settings, resource use, unavailable reasons). It has no capture, restore or rerun control and no write-back or one-click apply into shared profiles. The thin Lab panel remains the Task cases debug surface.

**Acceptance:** Walk the Model Lab surface: start a trait run, see applied settings and evidence, and confirm there is no case-capture / restore / replay control and no profile write-back or apply control on that path. Contrast with the Task cases path ([LAB-002](#lab-002)…[004](#lab-004)).

## Status and evidence

Status is owned by rows LAB-001...006 in [the catalogue](../catalog.json).

## Open questions

[OQ-005](../open-questions.md#oq-005) snapshot policy remainder; [OQ-009](../open-questions.md#oq-009) optional grading; [OQ-012](../open-questions.md#oq-012) observability outside Lab; [OQ-014](../open-questions.md#oq-014) task-case evaluation UX beyond Inspect.
