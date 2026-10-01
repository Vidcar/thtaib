# Lab Evaluation

## Purpose

Case capture, case restore, and recorded-tool replay are removed. Loaded-model Performance, Memory, and Challenges remain specified by the lab, lab-speed, lab-memory, and lab-challenges contracts.

## Requirements

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

### Requirement: LAB-007 - Keep replay writes confined

Recorded replay writes reconstructed `write_file` or `edit_file` bytes only as fixture application inside the replay workspace. Recorded replay SHALL attach no live project, host shell, or retrieval backend. Knowledge routes MAY use scratch or state backend so official memory and skills middleware can download files, but recorded replay MUST NOT write through into durable knowledge.

#### Scenario: Recorded write fixture

- WHEN a recorded replay applies a write fixture
- THEN the write MUST be labelled fixture application and confined to the replay workspace
- AND durable knowledge and live project storage MUST remain unchanged.

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
