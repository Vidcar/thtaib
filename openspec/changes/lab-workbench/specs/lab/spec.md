# Spec Delta

## Purpose

Define the Lab destination and the rules Performance, Memory, and Challenges share: where it sits, what a benchmark is allowed to change, and how results are kept, stopped, and deleted.

## ADDED Requirements

### Requirement: LAB-101 - Open Lab from the sidebar

Lab SHALL be a sidebar destination. Opening Lab SHALL show Performance first, with Memory and Challenges available from that destination. Performance, Memory, and Challenges SHALL use the same compact type, focus, and help treatment as the other sidebar destinations. Lab MUST NOT open onto the older case-capture screen.

#### Scenario: Lab opens on Performance

- **WHEN** a person selects Lab in the sidebar
- **THEN** Performance is the view they see
- **AND** Memory and Challenges are available without leaving Lab

#### Scenario: Empty Performance

- **WHEN** Performance has no saved benchmark and no prompt length is selected
- **THEN** the charts are empty
- **AND** the screen says that a model and at least one prompt length are required before a benchmark can start

### Requirement: LAB-102 - Keep benchmark settings unsaved

A Lab benchmark SHALL start from a saved model configuration and SHALL let the person change the controls that benchmark exposes. Those changes MUST NOT be written to the saved configuration, to Chat, or to the saved maximum-loaded-models limit. Using a setup outside Lab remains a change made on the Models page.

#### Scenario: Benchmark does not change the saved configuration

- **WHEN** a person changes context size for a benchmark and then opens that configuration on the Models page
- **THEN** the saved configuration still has its previous context size
- **AND** the saved maximum-loaded-models limit is unchanged

### Requirement: LAB-103 - Keep results until deleted

Performance, Memory, and Challenge results SHALL be stored in the local application data for this computer until the person deletes them. They MUST NOT be written into the repository and MUST NOT be copied into a Chat conversation. Delete SHALL ask for confirmation and SHALL remove only the selected result. Closing Lab or the application SHALL NOT discard results.

#### Scenario: Results survive restart

- **WHEN** a person completes a benchmark, closes the application, and opens Lab again
- **THEN** that benchmark is still listed
- **AND** it is not present as a Chat conversation

#### Scenario: Delete one result

- **WHEN** a person confirms deletion of one benchmark
- **THEN** that benchmark and its chart points are gone
- **AND** other saved Lab results remain

### Requirement: LAB-104 - Show finished measurements and stop cleanly

While a Lab run is in progress, each finished measurement SHALL appear immediately. Stop SHALL keep measurements that have already finished and SHALL skip measurements that have not started. A failed measurement SHALL show the reason and MUST NOT be displayed as a zero result. A failure to load the model SHALL stop the run without inventing later measurements.

#### Scenario: Stop mid-run

- **WHEN** three prompt lengths are selected and the person stops after the first finishes
- **THEN** the finished length remains visible with its reported speeds
- **AND** the lengths that had not started are not given speeds

#### Scenario: One length fails

- **WHEN** a later prompt length fails after an earlier length succeeded
- **THEN** the failed length shows the reason
- **AND** the earlier length's speeds stay as reported
