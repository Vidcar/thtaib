# lab-evaluation delta

## MODIFIED Requirements

### Requirement: LAB-002 - Capture and restore actual starting inputs

Task cases SHALL preserve the task, actual initial project snapshot, selected/effective model/profile/deployment configuration, dependency and knowledge versions, selected tools/fixtures and acceptance checks. Capturing a real run SHALL reuse its starting snapshot; missing original inputs remain unavailable, never replaced with current files or the model's answer as ground truth. Restore SHALL create a verified separate workspace and linked branch run, retaining source lineage and unavoidable deviations.

Each trial SHALL freeze actual rerun inputs/configuration and comparison overrides, including omitted versus explicitly empty tools. Recorded dependency versions remain distinct from those actually used. Startup differences SHALL use shared coordinated lifecycle controls, not a selector-only claim. The source project must remain unchanged, checked after terminal evaluation rather than merely after returning a run ID.

#### Scenario: Rerun from original inputs

- **WHEN** a saved source task is rerun after project/profile changes
- **THEN** the trial uses recorded initial inputs in a separate verified workspace, applies explicit overrides through their real owners and reports actual differences.

#### Scenario: Missing original state

- **WHEN** the source run has no starting snapshot
- **THEN** capture reports the gap and does not present current files as its original state.

### Requirement: LAB-005 - Publish an extensible hardware-local trait catalogue

Model Lab SHALL retain an extensible application-owned catalogue for throughput, prefill/decode at named contexts, quantisation, concurrent conversations, long-context retention/needle tasks, adapter-path tool calling and suitable vision/projector setups. Missing runners report unavailable; conditional reasoning, vision or MTP/speculative cases remain untested without a suitable verified setup. Do not invent scores or require a separate issue for each trait family.

MTP/speculative comparisons SHALL verify supported configuration and actual speculative activity before comparing enabled/disabled performance; successful launch or synthetic controls do not prove activation or benefit. A relevant-tool selector comparison is optional when that selector exists and SHALL include total latency, calls/context overhead and task correctness against the same authorised catalogue.

#### Scenario: Missing runner

- **WHEN** a selected trait lacks a runner or suitable setup
- **THEN** the result states unavailable/untested rather than a score or universal incompatibility.

#### Scenario: Speculative comparison

- **WHEN** an MTP comparison is offered
- **THEN** real activity and controlled enabled/disabled evidence are required before claiming a performance difference.

### Requirement: LAB-006 - Model Lab UX is trait runs, not case replay

Model Lab SHALL offer bundle/deployment/profile/trait selection and hardware-local measurements with actual progress, applied settings, units, failures, resources and unavailable reasons. Trait measurement and task-case capture/restore/replay SHALL remain distinct flows; neither is disguised as the other. Task-case controls may remain in their existing separate panel.

Lab SHALL support persistent results, case rename/duplicate/versioned editing/export/dependency-aware deletion, expected-versus-actual/source views and side-by-side answer/quality/performance comparison. The primary journey SHALL be understandable as choose case, choose configurations, run, compare, inspect evidence and deliberately use the tested setup in Chat, without requiring raw JSON, internal identifiers or backend terminology. Use explicit user-selected criteria rather than declare the fastest run universally best. Cases, fixtures, restored workspaces, logs and results follow shared retention/manual-backup policy, protecting sensitive captures and external source projects.

An explicit Use in Chat action SHALL reuse or create a shared profile from the tested immutable configuration with provenance. It MUST NOT automatically write back to an existing profile or mutate an active deployment. Detect later edits/startup mismatches at actual use; attach compatibility findings to the exact tested setup separately from publisher advice and user overrides.

#### Scenario: Model Lab walkthrough

- **WHEN** a user runs a trait test and opens task cases
- **THEN** the two flows remain distinct, show real evidence and retain their own inputs and progress.

#### Scenario: Use tested setup

- **WHEN** a user deliberately chooses Use in Chat and the profile later changes
- **THEN** the tested snapshot/provenance are retained and the next actual setup exposes differences instead of claiming equivalence from the profile ID.

#### Scenario: Lab primary journey

- **WHEN** a user chooses a case, selects configurations, runs it, compares results and inspects evidence
- **THEN** the primary Lab UI explains expected versus actual outcome, evidence and Use in Chat eligibility without requiring raw JSON, internal IDs or backend terminology.

### Requirement: LAB-008 - Measure engine traits honestly

Engine measurements SHALL use the managed llama-bench and inventoried local weights, otherwise report unavailable without downloading an unrelated model. Parse structured per-result output, retaining workload type, actual benchmark build/hardware/model, prompt/past-context depth, repetitions, warm-up/cache conditions, command, stdout/stderr and exit status. Individual samples, averages and variation SHALL be inspectable. Exit success without valid measurements is not measurement success; tiny smoke invocation does not prove named-context performance.

Map supported benchmark-relevant shared settings to the benchmark's own controls. Unsupported/differently represented server settings remain visible, not blindly forwarded or labelled applied. Record configured capacity and actual occupancy where applicable, generated length, prefill/decode and resources. Benchmark context depth and engine rates remain distinct from server context and end-to-end Chat responsiveness, including tokenisation/sampling costs not measured by the engine runner.

#### Scenario: Context trait result

- **WHEN** a benchmark runs at a named context workload
- **THEN** results retain actual depth, configuration, repetitions and evidence; smoke-only output is not promoted to a full context measurement.

#### Scenario: Unsupported mapping

- **WHEN** a server setting has no equivalent benchmark control
- **THEN** the difference is reported rather than silently forwarded or claimed applied.

## ADDED Requirements

### Requirement: LAB-009 - Reserve execution exclusively for a Lab batch

An active Lab batch SHALL hold a backend-owned exclusive execution reservation. Existing unrelated work must finish or be explicitly cancelled and confirmed stopped before acquisition; do not silently interrupt it. While held, reject or visibly queue all unrelated Chat, Workflow and media work. The batch's own trials, authorised concurrent tests and required human input remain allowed. Every implemented execution path SHALL enforce the reservation, not only the Lab UI.

Lab's exclusive-use state SHALL be visible wherever it blocks work, including Chat, Workflows, media and shared activity/attention surfaces. The message SHALL identify Lab as the owner, distinguish waiting from unavailable, and offer only actions supported by the current ownership and cancellation state.

Release on confirmed completion/cancellation/failure cleanup; restart SHALL reconcile unfinished work and unknown external effects before granting incompatible use. Ordinary concurrency outside Lab remains supported. Service readiness, returned job IDs or a cancel request do not establish terminal evaluation or free resources.

#### Scenario: Unrelated request during Lab

- **WHEN** an ordinary Chat or media request arrives while a batch owns execution
- **THEN** it waits or is rejected with the Lab reason while authorised batch-owned trials may run.

#### Scenario: Interrupted batch

- **WHEN** a batch fails, is cancelled or the backend restarts
- **THEN** owned work is reconciled and resources are released only on evidence sufficient for safe reuse.

### Requirement: LAB-010 - Run genuine Inspect evaluations through the shared agent

Task evaluation SHALL start and await the same configured Deep Agents driver as ordinary work from a real, locked-version-compatible Inspect evaluation. Explicitly select the intended local setup and avoid an unrelated environment-default model or second generation/tool loop. Preserve real Inspect logs and sample/epoch links to application runs/results through supported APIs; link adapter/harness evidence explicitly because wrapper logging does not automatically observe external calls. Existing application checks are not renamed Inspect scores.

The shared `@langchain/react` run-observation boundary may present live run state and tool activity. It does not own Inspect execution, sample/scorer semantics, Lab measurements or durable result linkage; Lab SHALL preserve those application-owned records and verify actual outcomes independently.

Start serially and use only supported evaluation concurrency. Cancellation, timeout and failure cleanup SHALL reach every owned harness run and release safe resources. Tool approvals and user-input interrupts retain normal identity/policy; Lab MUST NOT auto-approve to finish a test. Application termination remains distinct from unconfirmed host/remote termination.

#### Scenario: Inspect-owned sample

- **WHEN** an evaluation sample executes a tool-using local task
- **THEN** Inspect awaits the shared harness and retains actual logs plus sample/run/evidence linkage.

#### Scenario: Approval and cancel

- **WHEN** an evaluation pauses for permission and is then cancelled
- **THEN** normal policy still applies and cancellation reaches owned runs without inventing remote stop.

### Requirement: LAB-011 - Score versioned outcomes rather than activity

The initial case catalogue SHALL include known-answer text, harmless live tool execution, an authorised disposable-file task, a document question with known supporting passages, schema-defined extraction with expected values, and instruction retention through long-conversation compaction. Inputs, expectations and deterministic scorers SHALL be versioned; editing creates a revision without rewriting earlier results.

Checks SHALL assess actual answers, arguments/results, final file content, supporting source ranges, expected structured values and retained instructions as appropriate. Text presence, a tool name or schema validity alone is not task correctness. Incorrect answers, execution errors, unavailable/unassessable outcomes and schema failures remain distinct with explanations/evidence; missing outcomes are not fabricated zeroes or passes. Human-defined expectations precede any optional model judge. Recorded replay is labelled and cannot prove live integration.

#### Scenario: Schema-valid wrong value

- **WHEN** extraction returns valid JSON containing an incorrect expected value
- **THEN** schema success and outcome failure remain separate with the actual value and explanation.

#### Scenario: Revised expectations

- **WHEN** a case scorer or expected answer changes
- **THEN** new runs use a new case revision and previous outcomes remain immutable.

### Requirement: LAB-012 - Define comparison measurements and later-stage test ownership

Comparisons SHALL use versioned tasks, fresh inputs, declared output limits/repetitions/cache conditions and recorded intentional setup differences. Keep failures visible; a fixed seed does not guarantee identical output. Separate engine rates, lifecycle wait/loading, dispatch, first reasoning, first visible answer, tool/approval time and total agent duration. Count tokens from supplied/measured usage, not stream chunks. Memory observations SHALL identify process/device, collection method, interval and units; peaks are labelled sampled and unavailable GPU telemetry remains unavailable.

Cold start, already-loaded and model-switch/reload cases remain separate from benchmark warm-up. This stage SHALL save a reproducible independent-session load test and run a real serial baseline; change 06 owns concurrent execution. Save the Chat → media → Chat measurement case and boundaries here; change 08 owns its real execution. Both later tests are Lab-owned under exclusivity, not unrelated work sneaking into an active batch.

#### Scenario: Controlled comparison

- **WHEN** two trials differ in setup or loading condition
- **THEN** their evidence identifies all intentional differences, timing boundaries, failures and measurement limitations.

#### Scenario: Later-stage case

- **WHEN** concurrency or real media infrastructure is not yet implemented
- **THEN** the reproducible definition/baseline remains saved with execution assigned to its later change, not a fabricated pass or a blocker preventing that change from starting.
