# Spec Delta

## ADDED Requirements

### Requirement: API-039 - Show settled execution while saving project state

After graph execution settles, a project-bound run SHALL expose a durable saving phase until its final project capture is committed or declared unavailable. Chat and Agent run SHALL show “Saving project state” during that phase and disable Stop. A Stop request during saving MUST return `run_finalizing` and MUST NOT change the settled execution outcome. Exactly one terminal outcome SHALL be published after finalization.

#### Scenario: Stop after execution settled

- **WHEN** a project-bound run has entered saving and a person presses Stop or sends a Stop request
- **THEN** the run keeps its settled outcome and the request reports `run_finalizing`
- **AND** Chat and Agent run show saving until one terminal outcome appears.

### Requirement: API-040 - Keep measurements independent of generated output

Replaceable generation measurements SHALL NOT delay answer tokens, change model exceptions or cancellation, or determine the execution outcome. The final valid measurement available for a request SHALL be included in its terminal record. Message, tool, lifecycle and audit events SHALL retain ordered durable delivery. If essential interaction persistence fails, dispatch SHALL stop with an explicit `interaction_persistence_failed` outcome rather than reporting a model failure or silently dropping events.

#### Scenario: Measurement publisher stalls

- **WHEN** measurement publication stalls or fails while a model streams a token or raises an error
- **THEN** the token or original error reaches execution independently of the publisher
- **AND** the terminal record retains the latest valid measurement available.

#### Scenario: Essential projection cannot persist

- **WHEN** a native message or tool event cannot be durably recorded
- **THEN** further dispatch stops and the run reports `interaction_persistence_failed`
- **AND** it does not claim the model caused that failure.

### Requirement: API-041 - Replay according to each subscription

A hydrated root view SHALL continue after the cursor paired with its saved state without briefly replacing its in-progress answer with older tokens. A newly opened same-filter or wider subscription SHALL receive its available matching message, tool, lifecycle and namespace history, while existing subscribers SHALL skip events at or before their own cursor. A reconnect SHALL continue after the last complete event consumed by that stream handle; an incomplete frame MUST be replayed. Synthetic recovery events SHALL carry stable identities. Existing chats with unavailable historical detail SHALL say that detail is unavailable rather than inventing it.

#### Scenario: Open details during an active answer

- **WHEN** a hydrated answer is in progress and a new tool or nested-namespace selector opens
- **THEN** the answer remains visible and continues from its saved cursor
- **AND** the new selector receives available matching prior and live events without duplicates.

#### Scenario: Disconnect inside a frame

- **WHEN** a stream disconnects after an event ID but before the complete event frame
- **THEN** its reconnect cursor remains before that event
- **AND** the completed event is delivered once.
