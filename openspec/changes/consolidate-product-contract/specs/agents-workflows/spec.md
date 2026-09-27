# Spec Delta

## MODIFIED Requirements

### Requirement: WF-012 - Present a canvas that matches the running workflow

Workflows SHALL be one destination. The screen SHALL show a step palette, a canvas, and an inspector for the selected step. The palette SHALL offer these steps, using ordinary names: sequence, branch, parallel and join, repeat, run an agent, run another workflow, ask a person, typed input, and a registered direct action. A step does nothing until it is placed and the person starts the workflow. The inspector edits that step's setup in the same controls used elsewhere, including the named agent or workflow it calls. A grader is a workflow or agent step the person placed, not a hidden reviewer.

Invalid steps SHALL show the reason on the step before a run starts. Run and a history of earlier runs sit above the canvas. During a run, the active step is marked, and waiting for a person uses the same approval or question card as Chat. Stopping names the work that will stop. An imported graph MUST NOT run arbitrary code. Automatic schedules are not part of this screen. A later schedule would be another step, not a ban on adding one.

The canvas SHALL be the loaded React Flow editor. It MUST NOT be a second workflow engine. The main path MUST NOT require reading raw graph JSON.

#### Scenario: Place a grader and run it

- **WHEN** a person places an agent step and a second workflow step labelled as grading, then starts the workflow
- **THEN** those steps run in the order shown
- **AND** the grader does not run unless it was placed.

#### Scenario: Invalid step is visible

- **WHEN** a branch has no outgoing path
- **THEN** the step shows that reason and the workflow does not pretend to start
- **AND** the canvas remains editable.

#### Scenario: Imported code is refused

- **WHEN** an imported graph contains an arbitrary code step
- **THEN** that step is rejected
- **AND** no code from the graph is executed.
