## ADDED Requirements

### Requirement: STATE-TOKEN - Keep tokens only while a turn is unfinished

A turn that is still running SHALL keep its token rows so a disconnect can continue. When that turn's answer is in the saved transcript, the token rows and older snapshots for that turn SHALL be removed. The latest display snapshot and the execution checkpoint SHALL remain. Archive and removing a project SHALL NOT remove these rows. Deleting a chat SHALL still remove that chat's rows. Existing finished chats SHALL be collapsed once, and the freed database space SHALL be reclaimed. The collapse SHALL NOT delete the chats.

#### Scenario: A saved answer drops its token rows

- WHEN a chat turn is saved into the transcript
- THEN its token rows and older snapshots are removed
- AND the chat, its latest snapshot, and its checkpoint remain

#### Scenario: Archive and remove-project do not delete the log

- WHEN a person archives a chat or removes a project from the sidebar
- THEN the chat and its saved answer remain available
- AND those actions do not by themselves delete the token log

#### Scenario: A running turn can still resume

- WHEN a reply is still running and the desktop reconnects
- THEN continuation uses the token rows written for that live turn
