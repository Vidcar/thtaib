# Lab and evaluation integration

[Specification index](../README.md) · [Status and evidence](../catalog.json)

## Ownership, scope and source

llama-bench measures engine performance. Inspect AI supplies task-evaluation building blocks. The application Lab owns cases, starting-state restoration, evidence and comparisons, sharing records with Chat/Builder. Source: [revision 0.5, pages 4 and 6](../sources/README.md#application-infrastructure) and [build checks](../sources/README.md#build-order).

## Public contracts and collaboration

A captured case links initial project snapshot, task, profiles, dependency versions, selected memory/skills, tool fixtures and acceptance checks. A case result links applied settings, deviations, artifacts and executable/model-review outcomes. Exact dataset/scorer adapters are not selected here.

The Lab calls the same agent harness and model/profile paths as normal work. It does not add an evaluation-specific agent loop. Restoring an input state does not guarantee an identical model output.

## Lifecycle and failure

Capture a case from a real run, restore its initial inputs into an appropriate workspace, execute it in recorded-tool or live-tool mode, and preserve outcome/deviations. Missing snapshots, external dependencies or permissions must be reported rather than silently replaced with convenient inputs.

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

## Unresolved details

[OQ-005](../open-questions.md#oq-005) covers restorable starting states; [OQ-010](../open-questions.md#oq-010) covers fixtures, reproducible environment manifests and acceptance commands. Optional beta grading support is tracked separately under [OQ-009](../open-questions.md#oq-009).
