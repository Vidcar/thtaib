# Spec Delta

## MODIFIED Requirements

### Requirement: LAB-004 - Preserve interpretable evidence

Lab results SHALL expose answers, failures, resource use, artifacts, checks, applied configuration, and deviations rather than scores alone. Executable checks SHALL remain distinct from model judgement. Profile differences across Lab, Chat, and Workflows SHALL be visible.

#### Scenario: Compare changed setting

- **WHEN** a Performance, Memory, or Challenges result is shown, rather than two case runs
- **THEN** it shows the outcome and the applied configuration, not a score alone
- **AND** an executable check stays distinct from model judgement.

## REMOVED Requirements

### Requirement: LAB-002 - Capture and restore actual starting inputs
**Reason**: Case capture is removed. The person does not save a task case, restore a copied workspace, or rerun from a stored project copy.
**Migration**: Performance, Memory, and Challenges remain the Lab destination. Project files stay where they are. Git remains the person's file history.

### Requirement: LAB-003 - Distinguish recorded-tool and live-tool evaluation
**Reason**: Recorded-tool replay exists only for case capture.
**Migration**: Agent runs use live tools. No case export remains.

### Requirement: LAB-007 - Keep replay writes confined
**Reason**: There is no recorded replay workspace.
**Migration**: Live file tools continue to use the bound project. They do not write into a case workspace.

### Requirement: LAB-015 - Prune excluded project trees during capture
**Reason**: The product no longer copies a project tree for a case or a run.
**Migration**: No capture skip-list remains. Project files stay in the selected folder.
