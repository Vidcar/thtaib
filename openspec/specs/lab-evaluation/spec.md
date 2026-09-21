# Lab Evaluation

## Purpose

Specify two separate Lab features: Model Lab trait runs for hardware-local model behavior on David's machine, and task cases/replay for saving, restoring, rerunning, and comparing real task evidence.

## Requirements

### Requirement: LAB-001 - Separate engine measurements from task evaluation

Model Lab SHALL use llama-bench for engine-performance measurements when available. Task evaluation SHALL use Inspect AI building blocks and the same Deep Agents harness as normal work. The Lab MUST NOT add a second model-and-tool loop. Adjustable Lab testing SHALL inform choices and MUST NOT be required for ordinary model use.

#### Scenario: Engine versus task result

- WHEN an engine measurement and agent task evaluation are compared
- THEN their inputs and results MUST remain distinct
- AND the task path MUST use the shared harness rather than a separate loop.

### Requirement: LAB-002 - Capture and restore actual starting inputs

Task cases SHALL save the initial project snapshot, task, profile and deployment ids, dependency versions, knowledge versions, tool fixtures, and acceptance checks. Capture from a real run SHALL reuse the run's starting snapshot. A run without one MUST report starting snapshot unavailable rather than presenting current files as original inputs. Restore SHALL create a new workspace and linked branch run.

#### Scenario: Rerun from original inputs

- WHEN a real task is saved as a case, the working project changes, and the case is rerun
- THEN rerun MUST use the recorded initial state
- AND restored versions and unavoidable deviations MUST be visible.

### Requirement: LAB-003 - Distinguish recorded-tool and live-tool evaluation

Recorded-tool and live-tool evaluations SHALL be labelled and kept separate. Recorded-tool replay SHALL consume the first unused fixture with equal tool name and canonical arguments, and missing, exhausted, or mismatched fixtures SHALL fail with explicit deviations. Recorded mode MUST NOT fall back to live execution. Case export SHALL sanitize or block detectable secrets in task text, tool fixtures, and included files.

#### Scenario: Fixture mismatch and secret export

- WHEN recorded replay lacks a matching fixture or export detects a secret
- THEN replay MUST fail with a recorded fixture deviation and no live fallback
- AND export MUST redact or block the secret before reusable case output.

### Requirement: LAB-004 - Preserve interpretable evidence

Lab results SHALL expose answers, failures, resource use, artifacts, checks, applied configuration, and deviations rather than scores alone. Executable checks SHALL remain distinct from model judgement. Profile differences across Lab, Chat, and Workflows SHALL be visible.

#### Scenario: Compare changed setting

- WHEN two case runs differ by a setting
- THEN applied configuration and evidence for each outcome MUST be inspectable
- AND at least one failing executable check MUST remain distinct from model review.

### Requirement: LAB-005 - Publish an extensible hardware-local trait catalogue

Model Lab SHALL keep an application-owned catalogue of hardware-local model traits, beginning with speed/throughput, prefill/decode at named contexts, MTP cost, quantization impact, concurrent conversations, long-context memory/needle, tool calling on the model-adapter path, and vision with the official projector in the same bundle. New trait families SHALL be added one family per issue. A missing runner SHALL report unavailable; scores MUST NOT be invented.

#### Scenario: Missing runner

- WHEN the trait catalogue is inspected and a selected runner is absent
- THEN the missing runner MUST be reported as unavailable
- AND the trait run MUST remain separate from captured task cases.

### Requirement: LAB-006 - Model Lab UX is trait runs, not case replay

The Model Lab surface SHALL let the user select a bundle, running deployment, profile, and traits; run them locally; and inspect measurements, failures, applied settings, resource use, unavailable reasons, and charts. It SHALL NOT expose case capture, restore, replay, profile write-back, or one-click apply controls. The thin Lab panel MAY remain the Task cases debug surface.

#### Scenario: Model Lab walkthrough

- WHEN the Model Lab surface is used for a trait run
- THEN applied settings and evidence MUST be visible
- AND case-capture, restore, replay, profile write-back, and apply controls MUST be absent from that path.

### Requirement: LAB-007 - Keep replay writes confined

Recorded replay writes reconstructed `write_file` or `edit_file` bytes only as fixture application inside the replay workspace. Recorded replay SHALL attach no live project, host shell, or retrieval backend. Knowledge routes MAY use scratch or state backend so official memory and skills middleware can download files, but recorded replay MUST NOT write through into durable knowledge.

#### Scenario: Recorded write fixture

- WHEN a recorded replay applies a write fixture
- THEN the write MUST be labelled fixture application and confined to the replay workspace
- AND durable knowledge and live project storage MUST remain unchanged.

### Requirement: LAB-008 - Measure engine traits honestly

Engine measurements SHALL use llama-bench from the managed runtime when available, otherwise report unavailable. A tiny smoke command SHALL prove only runner invocation, not context-performance evidence. Context traits SHALL record configured capacity, prompt and past-context occupancy, prefill and decode measurements, applied runtime settings, warmup/cache condition, generated length, repetitions, and resource use.

#### Scenario: Context trait result

- WHEN a context trait is run at a named context size
- THEN measurements MUST include the configured and observed context details and resource use
- AND a smoke-only run MUST NOT be labelled as performance evidence for that context.
