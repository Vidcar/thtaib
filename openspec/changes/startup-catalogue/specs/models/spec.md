## ADDED Requirements

### Requirement: MODEL-WARM - Warm one chat model after the catalogue is requested

After the desktop has requested the project list and the chat list, it SHALL start the preferred stopped managed chat model through the existing managed start path. It SHALL start at most one model. A model that is already running SHALL be left as it is. A connected endpoint SHALL NOT be started. The catalogue MUST NOT wait for this start. Failure SHALL leave the lists in place and SHALL be visible from the existing status dot hover and the existing error notice.

#### Scenario: Lists do not wait for the model

- WHEN the application opens with a stopped managed chat model
- THEN projects and chats can appear while that model is still starting
- AND the status dot hover says that the model is starting

#### Scenario: An already running model is not started again

- WHEN a managed chat model is already running
- THEN the desktop does not start a second model
