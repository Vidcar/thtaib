# Spec Delta

## MODIFIED Requirements

### Requirement: AGT-019 - Offer only named helpers

Ordinary Chat SHALL keep the general-purpose helper disabled. A person SHALL be able to name saved agents as helpers on a conversation. When that list is empty, no helper tool is offered. When it names agents, only those agents are offered, each with the frozen setup shown in the list, and none of them can gain permissions the conversation does not have. The setup popover SHALL show a Helpers section. Empty copy SHALL say this chat will not hand work to another agent. Each chosen helper is a row with its name and model, and it can be removed. Choosing a helper does not start it.

#### Scenario: No helpers configured

- **WHEN** a conversation has an empty helpers list
- **THEN** the model cannot call a helper
- **AND** the setup section says no helper will be used.

#### Scenario: Named helper cannot widen access

- **WHEN** a conversation names one saved agent and that agent attempts a tool the conversation is not allowed
- **THEN** the tool is refused
- **AND** the activity row shows that helper by name.

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
