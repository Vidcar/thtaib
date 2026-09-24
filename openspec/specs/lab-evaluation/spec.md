# Lab Evaluation

## Purpose

Specify Lab as a measurements-first destination on this machine, with a separate memory test and a small expandable set of exact task challenges. Task replay stays distinct from speed measurements.

## Requirements

### Requirement: LAB-001 - Separate engine measurements from task evaluation

Model Lab SHALL use llama-bench for engine-performance measurements when available. Task challenges SHALL use exact checks and the same Deep Agents harness as normal work. The Lab MUST NOT add a second model-and-tool loop, and it MUST NOT require the Inspect product. A later runner is allowed without replacing checks that already exist. Adjustable Lab testing SHALL inform choices and MUST NOT be required for ordinary model use.

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

Model Lab SHALL keep an application-owned catalogue a person can add to. The first entries are prefill and decode, a single-needle memory test, one direct tool task, one indirect tool task, and a small set of known-answer reasoning tasks. Vision is included only by reusing the Chat image path when the selected bundle already has vision. New entries are versioned tasks in the same catalogue, not a new product and not one documented issue per family. A missing runner SHALL report unavailable. Scores MUST NOT be invented. Claimed context length SHALL come from the existing model probe.

#### Scenario: Missing runner

- WHEN the trait catalogue is inspected and a selected runner is absent
- THEN the missing runner MUST be reported as unavailable
- AND the trait run MUST remain separate from captured task cases.

#### Scenario: Add a challenge later

- **WHEN** a person adds a new reasoning or tool challenge
- **THEN** it appears as another versioned card on the challenges screen
- **AND** earlier results keep the check they were scored with.

### Requirement: LAB-006 - Model Lab UX is trait runs, not case replay

Lab SHALL be one destination with three named views: Measurements, Memory, and Challenges. Measurements is the view that opens first.

The Measurements screen SHALL show the selected model and setup, the probed context as a stated fact, and editable prompt sizes and context depths. The primary action is Run. While running, the screen shows which size is in progress and leaves completed points on the chart. The chart SHALL be a loaded chart component, not a hand-drawn canvas. Prefill and decode are separate series, labelled in tokens per second, with the prompt size or depth on the axis. Saved runs SHALL be listed by model and the settings that differ, and a person SHALL be able to overlay more than one run on the same chart. Deleting a run asks for confirmation and removes that run's points. A failed point stays visible and says why. Unavailable llama-bench is an empty chart with that reason, not a zero.

The Memory screen SHALL edit the needle text and the depth list. The default depths are 0, 25, 50, 75, and 100 percent, each leaving room for the answer. Results are one row per depth: pass or fail, the depth, and the text the model returned. A wrong answer is shown. It is not collapsed into one percentage only.

The Challenges screen SHALL list the small task set as cards. Each card shows the task in plain language, whether it is tool or reasoning, and the exact check. The indirect tool card SHALL describe a task the tool cannot finish alone, such as a conversion the tool does not provide directly. Running one card shows progress and then pass or fail with the observed answer beside the expected check. The screen does not offer case capture, restore, replay, or profile write-back.

None of the three views SHALL require reading raw JSON or internal identifiers for the main path. Applied settings and the command or check remain available on expansion.

#### Scenario: Model Lab walkthrough

- WHEN the Model Lab surface is used for a trait run
- THEN applied settings and evidence MUST be visible
- AND case-capture, restore, replay, profile write-back, and apply controls MUST be absent from that path.

#### Scenario: Compare two setups on one chart

- **WHEN** a person has saved a prefill and decode run for two KV-cache setups of the same model
- **THEN** both can be overlaid, with the setup difference labelled
- **AND** deleting one run removes only that run after confirmation.

### Requirement: LAB-007 - Keep replay writes confined

Recorded replay writes reconstructed `write_file` or `edit_file` bytes only as fixture application inside the replay workspace. Recorded replay SHALL attach no live project, host shell, or retrieval backend. Knowledge routes MAY use scratch or state backend so official memory and skills middleware can download files, but recorded replay MUST NOT write through into durable knowledge.

#### Scenario: Recorded write fixture

- WHEN a recorded replay applies a write fixture
- THEN the write MUST be labelled fixture application and confined to the replay workspace
- AND durable knowledge and live project storage MUST remain unchanged.

### Requirement: LAB-008 - Measure engine traits honestly

Engine measurements SHALL use llama-bench from the managed runtime when available, otherwise report unavailable. A tiny smoke command SHALL prove only runner invocation, not context-performance evidence. Prompt sizes and context depths SHALL be the person's saved settings, not a single hidden default. Context traits SHALL record configured capacity, prompt and past-context occupancy, prefill and decode measurements, applied runtime settings, warmup or cache condition, generated length, repetitions, and resource use. The chart MUST plot those recorded measurements and MUST NOT invent a point the runner did not return.

#### Scenario: Context trait result

- WHEN a context trait is run at a named context size
- THEN measurements MUST include the configured and observed context details and resource use
- AND a smoke-only run MUST NOT be labelled as performance evidence for that context.

### Requirement: LAB-014 - Hold the machine visibly while Lab runs

An active Lab run SHALL hold a backend-owned exclusive reservation. Work already running must finish or be explicitly stopped before Lab starts. The confirmation names that work. While Lab holds the machine, Chat, Workflows, and media SHALL show a calm banner naming the Lab run and offering a way back to it. New work from those surfaces waits or explains the reservation. It MUST NOT start on the same model in secret. Lab's own trials remain allowed. Stopping Lab releases the reservation and says so.

#### Scenario: Chat is busy

- **WHEN** a chat is still replying and a person starts a measurement
- **THEN** Lab asks them to wait or stop that chat
- **AND** the measurement does not start until the machine is free.

#### Scenario: Banner while measuring

- **WHEN** a measurement is running and the person opens Chat
- **THEN** a banner names the measurement and does not look like a send failure
- **AND** sending a new chat turn does not start a second model run.

### Requirement: LAB-015 - Prune excluded project trees during capture

Project and Lab capture SHALL avoid descending into excluded directories. An explicitly empty Lab allowlist SHALL produce an empty file capture. Captured paths SHALL remain within the selected root, and changed files or symlinks that cannot be copied and verified safely SHALL fail capture without publishing a partial snapshot.

#### Scenario: Excluded large tree

- **WHEN** a project contains a large excluded dependency or environment directory
- **THEN** capture does not enumerate that directory's files
- **AND** its included files still restore byte for byte.

#### Scenario: Explicit empty capture and unsafe file

- **WHEN** a Lab capture explicitly selects no files
- **THEN** its file snapshot is empty
- **AND** an unsafe link or changing included file fails a separate capture without publishing partial data.
