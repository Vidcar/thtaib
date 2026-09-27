# Spec Delta

## ADDED Requirements

### Requirement: STATE-024 - Preserve chat-specific browser profiles without inventing live state

Each conversation's owned browser profile SHALL preserve sign-ins across normal close and application restart while remaining isolated from other chats and the ordinary browser profile. Live pages, control and unfinished effects SHALL remain distinct from retained profiles, captures and downloads. Backup SHALL quiesce owned browser processes before copying included profile data and preserve existing credential-exclusion and sensitive-content choices. Reset and deliberate chat deletion SHALL clear only that chat's stopped owned browser profile; project files, weights, retained copies with surviving dependencies and other profiles MUST remain intact. Restart MUST NOT silently resume or replay an uncertain action.

#### Scenario: Relaunch after normal close
- **WHEN** a person reopens a chat browser after a clean application shutdown
- **THEN** the dedicated profile retains sign-ins while new live pages are started explicitly and no earlier action is repeated.

#### Scenario: Reset or delete one chat
- **WHEN** a person confirms browser reset or deletes a stopped chat
- **THEN** only its owned browser profile is removed and another chat's sign-ins, project files and model weights remain unchanged.

#### Scenario: Backup an active browser
- **WHEN** an application backup includes browser profile data
- **THEN** the browser is quiesced and its included/excluded sensitive data is identified without claiming that retained profile bytes represent live pages or resumed work.
