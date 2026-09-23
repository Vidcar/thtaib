# Spec Delta

## MODIFIED Requirements

### Requirement: ARCH-011 - Leave a door for a later feature

A capability this contract does not include SHALL be described as not in this contract. It MUST NOT be described as forbidden unless it would break a safety rule, such as running arbitrary code from an imported graph or sending audio to an unsaved address. A later image, voice, schedule, evaluation, or helper feature SHALL extend the existing endpoint, workflow step, Lab catalogue, or saved agent. It MUST NOT add a second agent loop, a second workflow engine, or a second media store.

#### Scenario: Voice cloning is later

- **WHEN** a later change adds voice cloning
- **THEN** it uses the saved speech endpoint or another application the person configures
- **AND** the current dictation and spoken-reply controls remain the way speech is used until that change exists.
