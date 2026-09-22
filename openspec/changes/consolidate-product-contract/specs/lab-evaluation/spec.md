# Spec Delta

## MODIFIED Requirements

### Requirement: LAB-001 - Separate engine measurements from task evaluation

Model Lab SHALL use llama-bench for engine-performance measurements when available. Task challenges SHALL use exact checks and the same Deep Agents harness as normal work. The Lab MUST NOT add a second model-and-tool loop, and it MUST NOT require the Inspect product. A later runner is allowed without replacing checks that already exist. Adjustable Lab testing SHALL inform choices and MUST NOT be required for ordinary model use.

#### Scenario: Engine versus task result

- WHEN an engine measurement and agent task evaluation are compared
- THEN their inputs and results MUST remain distinct
- AND the task path MUST use the shared harness rather than a separate loop.

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

### Requirement: LAB-008 - Measure engine traits honestly

Engine measurements SHALL use llama-bench from the managed runtime when available, otherwise report unavailable. A tiny smoke command SHALL prove only runner invocation, not context-performance evidence. Prompt sizes and context depths SHALL be the person's saved settings, not a single hidden default. Context traits SHALL record configured capacity, prompt and past-context occupancy, prefill and decode measurements, applied runtime settings, warmup or cache condition, generated length, repetitions, and resource use. The chart MUST plot those recorded measurements and MUST NOT invent a point the runner did not return.

#### Scenario: Context trait result

- WHEN a context trait is run at a named context size
- THEN measurements MUST include the configured and observed context details and resource use
- AND a smoke-only run MUST NOT be labelled as performance evidence for that context.

## ADDED Requirements

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
