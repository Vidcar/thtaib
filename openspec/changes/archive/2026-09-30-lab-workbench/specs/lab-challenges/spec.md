# Spec Delta

## Purpose

Specify Challenges as a list the person can extend: each challenge has a plain-language task and an exact check, and the list can grow without a new screen.

## ADDED Requirements

### Requirement: CHL-001 - List challenges as cards

Challenges SHALL be a list of cards on the Challenges view. The list SHALL include one echo challenge when Lab first has no challenges, so the view is not empty. A person SHALL be able to add a challenge by entering the task and its check. The list SHALL be able to grow past fifty challenges. Deleting the last challenge SHALL show how to add one. A challenge run SHALL use the same agent loop as Chat and MUST NOT add a second loop. It SHALL NOT create a Chat conversation.

#### Scenario: First visit includes the echo challenge

- **WHEN** a person opens Challenges and none have been saved
- **THEN** the echo challenge is listed
- **AND** the view tells them how to add another

#### Scenario: An added challenge appears as a card

- **WHEN** a person saves a new challenge with a task and a check
- **THEN** it appears as its own card
- **AND** earlier cards remain

### Requirement: CHL-002 - Check words and tool calls

A challenge check SHALL be able to require text in the answer, a call to echo, a call to time_now, or a combination of text and one of those tools. A challenge that requires neither text nor a tool MUST NOT be saved. During a challenge, echo and time_now SHALL be the only tools offered, and calls to them MUST NOT raise an approval card. The card SHALL show the task, the check, whether it passed, the model's answer, and which of those tools was called. A missing required word or a missing required tool call SHALL fail the challenge. time_now SHALL be labeled Clock. A tool that exists only for one challenge MUST NOT be required by this contract.

#### Scenario: Words without the tool fail

- **WHEN** a challenge requires both a code in the answer and an echo call, and the model writes the code without calling echo
- **THEN** the card fails
- **AND** it shows the answer and that echo was not called

#### Scenario: Echo does not ask for approval

- **WHEN** a challenge run calls echo
- **THEN** the call completes without an approval card
- **AND** no tool other than echo or time_now is offered

### Requirement: CHL-003 - Keep results with the challenge that ran

Running one card SHALL show progress and then pass or fail. The stored result SHALL include the task and the check used for that run. Editing the task or the check afterwards MUST NOT change stored results. A new run after an edit SHALL be scored with the edited task and check.

#### Scenario: An edit does not rewrite an old result

- **WHEN** a challenge has a stored pass and the person changes its expected text
- **THEN** the stored result still shows the check it was scored with
- **AND** a later run uses the edited check

### Requirement: CHL-004 - Include an echo challenge

The included echo challenge SHALL ask the model to call echo with one fixed code and to include that code in the answer. Its check SHALL require both that code and an echo call. The person SHALL be able to delete it like any other challenge.

#### Scenario: The included challenge rejects a typed code

- **WHEN** the model answers with the fixed code and does not call echo
- **THEN** the included challenge fails
- **AND** the card shows that echo was not called
