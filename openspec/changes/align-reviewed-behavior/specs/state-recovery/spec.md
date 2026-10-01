# Spec Delta

## ADDED Requirements

### Requirement: STATE-025 - Download a Markdown transcript

Chat SHALL let the person download a Markdown transcript. The transcript SHALL include message text, one activity line per tool action the chat shows, including failed and rejected actions, copied as that line is shown, and retained file names only. The product MUST NOT add a second scanner to rewrite that line. It MUST NOT include thinking text, full tool output, project source, or model weights. It MUST NOT restore the app. The file SHALL include a one-line note that it is not a restore. The on-screen Reasoning and tools toggle SHALL be display only and MUST NOT change the download. Deleting the chat MUST NOT delete a transcript file already downloaded. Whole-chat delete SHALL ask first. The confirmation SHALL say that project files and model files stay. The confirmation MUST NOT say that backups are retained. Archive SHALL remain available on the conversation list. Advanced JSON export MUST NOT be offered.

#### Scenario: Download contents

- **WHEN** a person downloads a Markdown transcript from a chat that shows messages, failed and rejected tool actions, and retained files
- **THEN** the file MUST include the message text, one activity line per shown tool action, and retained file names only
- **AND** it MUST omit thinking text, full tool output, project source, and model weights, and MUST include a one-line note that it is not a restore
- **AND** the Reasoning and tools toggle MUST NOT change those contents, and the file MUST NOT restore the app.

#### Scenario: Delete chat

- **WHEN** a person deletes a chat after downloading its transcript
- **THEN** the app MUST ask first, the confirmation MUST say that project files and model files stay, and the confirmation MUST NOT say that backups are retained
- **AND** the transcript file already downloaded MUST remain on disk.

#### Scenario: Archive

- **WHEN** a person uses the conversation list
- **THEN** Archive MUST remain available
- **AND** advanced JSON export MUST NOT be offered.

## MODIFIED Requirements

### Requirement: STATE-001 - Keep application records and execution checkpoints separate

The application SHALL keep application records in application.sqlite and LangGraph checkpoint bytes in checkpoints.sqlite. Files SHALL hold models, projects, versioned knowledge bodies, artifacts and logs. The product MUST NOT keep a stored copy of the request the model received. Application run records SHALL link profiles, deployments, environments, agent setup, parent and child runs, steps, threads, checkpoint ids, applied settings, evidence, optional budgets and recovery outcomes. Interaction identity mappings and durable public projection/replay records SHALL reuse application persistence; checkpoints SHALL remain execution authority accessed only through supported public APIs. The application SHALL store checkpoint ids and MUST NOT read or write checkpointer tables. A selected id or frontend projection MUST NOT claim a value was loaded, applied or completed.

#### Scenario: Follow persisted run

- WHEN a persisted run is followed after backend restart
- THEN application records MUST locate its checkpoint ids, interaction identities and related files
- AND the application MUST NOT read or write private checkpointer tables or invoke the model simply to rebuild the display.

### Requirement: STATE-002 - Do not confuse history with the working project

The backend SHALL own thread identities, checkpoint namespaces and displayed history. The readable archive MAY retain more history than compacted runtime context. Hydration SHALL preserve that history while identifying the checkpoint as execution authority. Deep Agents file tools SHALL target project storage; conversation-state and harness internal paths MUST NOT substitute for the working project. A display-only history edit MUST NOT restore, delete, fork, or reset project files or execution state. Retry and Edit are the rewind specified for this chat. They move this chat's checkpoint and MUST NOT restore project files. History, project files, and external effects SHALL remain distinct. A project snapshot MUST NOT be required to explain or continue a chat. Rewind MUST NOT restore project files.

Legacy history without IDs SHALL preserve chronological order and repeated-message multiplicity. Runtime identity SHALL use durable identity/provenance or reliable ordered alignment, never an earlier equal-text match alone. Ambiguous records SHALL retain deterministic display-only identity and the original readable archive. Content blocks, reasoning and checkpoint tool calls/results SHALL retain their meaningful ordering relative to confidently matched turns.

#### Scenario: History edit

- WHEN displayed history is changed after a project-bound file-writing turn
- THEN project files MUST remain unchanged by that display edit
- AND harness-internal paths MUST NOT appear in the project or be reconstructed from edited display history.

#### Scenario: Existing compacted conversation

- WHEN a pre-migration conversation is reopened after its runtime context was compacted
- THEN its full retained readable history, project/settings references and checkpoint association MUST survive
- AND continuation MUST use the existing checkpoint rather than replaying the archive.

#### Scenario: Repeated text with compacted suffix

- WHEN an ID-less transcript contains repeated user or assistant text and execution retains only a suffix
- THEN registration and repeated reopening MUST preserve exact readable chronology and multiplicity
- AND stable established identities, content blocks, reasoning and tool outcomes MUST survive without duplicate outcomes or a model/tool invocation.

#### Scenario: Explain or continue without a project snapshot

- WHEN a chat is explained, continued, or rewound and no project copy exists
- THEN retained history and the conversation checkpoint MUST be sufficient
- AND rewind MUST NOT restore project files, while history, project files, and external effects stay distinct.

### Requirement: STATE-005 - Version durable knowledge and enforce its write policy

Durable knowledge SHALL preserve user, agent, and project scopes; `memory`, `skill`, and `protected_instruction` kinds; provenance; append-only versions; and reversible edits through new versions. Writes SHALL name an expected base version and report conflicts. Protected instructions SHALL reject agent-origin writes. Skill creation, edit, and import SHALL require valid native `SKILL.md` content with a matching name and nonempty description; the body SHALL be materialized unchanged. A starter template MAY assist creation. Package name collisions SHALL be explicit, and an imported script MUST NOT execute during import.

#### Scenario: Knowledge write policy

- WHEN memory is edited, reverted, concurrently updated, or a protected instruction is overwritten by an agent
- THEN version history, conflict behavior, and protected-instruction rejection MUST be enforced.

#### Scenario: Native skill validation

- **WHEN** a person creates, edits or imports a skill package
- **THEN** invalid `SKILL.md` name/description or a name collision is rejected before materialization
- **AND** a valid body is stored unchanged without running bundled scripts or converting freeform notes.

### Requirement: STATE-010 - Delete deliberately while preserving shared dependencies

Conversations, sent originals and verified retained outputs SHALL remain until deliberate dependency-aware deletion. The product does not keep a stored copy of the request the model received. Staging cleanup must not erase submitted assets. Deletion SHALL preview affected and retained sessions, runs, checkpoints, scratch, originals and outputs; coordinate active work and use supported checkpoint APIs. Surviving conversations and workflows retain needed shared content. Library files, project source files, model files, committed knowledge, remote copies, and records another conversation needs MUST NOT be incidentally deleted. Removing backup, and deleting a chat, MUST NOT delete an application backup file or a JSON export the person already has on disk. A downloaded transcript SHALL stay on disk and MUST NOT be deleted by chat deletion. This protection MUST NOT bring the Backup feature back. Deletion of a chat SHALL wait until that chat's own work has stopped. Unlink, archive, delete and diagnostic cleanup have distinct effects; secure physical erasure or complete forgetting MUST NOT be claimed.

#### Scenario: Shared asset deletion

- **WHEN** a deleted conversation shares checkpoints/assets with retained consumers
- **THEN** the preview and cleanup preserve required references and state accurately what remains
- **AND** library files, project files, model files, records another conversation needs, a downloaded transcript, an application backup file, and a JSON export the person already has on disk MUST stay.

### Requirement: STATE-018 - Archive immediately and delete a chat without its project files

Archiving a conversation SHALL remove it from the active list and from active search at once. It remains available under archived conversations and can be reopened. Permanently deleting a chat SHALL remove that chat's history, drafts, queue, and its own run records after confirmation. The confirmation SHALL say project files and model files stay. The confirmation MUST NOT say that backups are retained. Project files MUST remain byte for byte. Deletion waits until that chat's own work has stopped. Shared records another conversation still needs are kept, and the confirmation says so when that is the case.

#### Scenario: Archive from the active list

- WHEN a person archives the conversation they are reading
- THEN it leaves the active list immediately
- AND they can reopen it from archived conversations.

#### Scenario: Delete a project chat

- WHEN a person confirms deletion of a chat whose project contains files the agent wrote
- THEN the chat history is gone
- AND those project files are still in the project folder
- AND the confirmation said project files and model files stay and did not say that backups are retained.

### Requirement: STATE-021 - Finalize runs and snapshots safely

Execution settlement SHALL be persisted before the run is treated as finished, and restart recovery SHALL use that settlement without rerunning model or tool effects. The application MUST NOT copy the project before or after a run. Branching SHALL NOT be offered. A missing project copy MUST NOT be a reason to refuse rewind. Rewind SHALL use the conversation checkpoint only and MUST NOT restore project files.

#### Scenario: Another run does not wait for a project copy

- WHEN one run is settling while another run makes progress
- THEN the second run MUST NOT wait for a project copy
- AND the first run publishes one terminal outcome from its saved settlement.

#### Scenario: Terminal write retry while another worker is live

- WHEN one run's terminal record write fails transiently while another worker remains active
- THEN recovery retries the settled run without marking the owned worker orphaned
- AND each run publishes at most one confirmed terminal outcome.

#### Scenario: Concurrent run during capture

- **WHEN** one run is settling while another run makes progress
- **THEN** the second run does not wait for a project copy
- **AND** the first run publishes one terminal outcome from its saved settlement.

#### Scenario: Restart or capture failure

- **WHEN** the application restarts after execution settles and no project copy exists
- **THEN** finalization uses the saved outcome without replaying model or tool effects
- **AND** a missing project copy does not refuse rewind and does not restore files.

#### Scenario: Restart after settlement

- WHEN the application restarts after execution settles
- THEN finalization uses the saved outcome without replaying model or tool effects
- AND a missing project copy MUST NOT refuse rewind, which uses the conversation checkpoint only and does not restore files.

#### Scenario: Rewind without a project copy

- WHEN a person rewinds a settled chat and no project copy exists
- THEN rewind uses the conversation checkpoint only
- AND branching is not offered and project files are not restored.

### Requirement: STATE-024 - Preserve chat-specific browser profiles without inventing live state

Each conversation's owned browser profile SHALL preserve sign-ins across normal close and application restart while remaining isolated from other chats and the ordinary browser profile. Live pages, control and unfinished effects SHALL remain distinct from retained profiles, captures and downloads. There SHALL be no application backup, and browser sign-ins MUST NOT be included in one. Reset and deliberate chat deletion SHALL clear only that chat's stopped owned browser profile; project files, weights, retained copies with surviving dependencies and other profiles MUST remain intact. Restart MUST NOT silently resume or replay an uncertain action.

#### Scenario: Relaunch after normal close
- **WHEN** a person reopens a chat browser after a clean application shutdown
- **THEN** the dedicated profile retains sign-ins while new live pages are started explicitly and no earlier action is repeated.

#### Scenario: Reset or delete one chat
- **WHEN** a person confirms browser reset or deletes a stopped chat
- **THEN** only its owned browser profile is removed and another chat's sign-ins, project files and model weights remain unchanged.

#### Scenario: Backup an active browser
- **WHEN** a person looks for an application backup of the browser profile
- **THEN** there is no application backup
- **AND** sign-ins stay in that chat's profile until a confirmed reset.

### Requirement: STATE-004 - Do not promise rollback of external effects

A saved chat point SHALL NOT undo external actions or restore a whole environment unless an adapter explicitly supports it. The product MUST NOT copy the project to undo those actions. External effects without acknowledgement after crash, reconnect, or restart SHALL remain `unknown` until reconciled with authoritative evidence. Unknown operations MUST NOT be silently replayed. `cancel_requested` SHALL remain live until confirmed stop.

#### Scenario: Crash after external effect

- WHEN a crash occurs between external effect dispatch and local acknowledgement
- THEN recovery MUST report uncertainty or reconcile against authoritative evidence
- AND it MUST NOT treat a cancel request as confirmed stop or permission to replay.

#### Scenario: Desktop control outcome is uncertain after dispatch
- **WHEN** a desktop control action is dispatched and acknowledgement times out or the target window identity changes before its result is verified
- **THEN** its durable outcome SHALL remain uncertain and require inspection or explicit acknowledgement before dependent continuation
- **AND** it SHALL NOT be converted to an ordinary correctable tool failure or automatically replayed; a refusal before dispatch remains distinguishable.

### Requirement: STATE-008 - Keep harness scratch out of project and durable stores

Harness-internal files, including large tool results, conversation history, retrieval offloads, materialized memory files, and materialized skill files, SHALL route to harness scratch under the product data root or state backend. They MUST NOT appear in the project, knowledge store, or invented stand-in folders. An accepted memory SHALL create a versioned knowledge record. Scratch files MUST NOT become that record, and there SHALL be no automatic write-through.

#### Scenario: Harness file routing

- WHEN a live run materializes memory, skills, retrieval output, or filesystem middleware files
- THEN those paths MUST resolve under harness scratch or state backend
- AND project storage and durable knowledge bodies MUST remain separate
- AND a memory suggestion does not become a knowledge record until the person accepts it.

## REMOVED Requirements

### Requirement: STATE-003 - Pair branches with consistent project snapshots
**Reason**: The app does not copy a project before or after a run, does not create a second workspace, and does not make a second task wait.
**Migration**: Several chats, helpers, and later workflow agents may use one folder. One write to a file finishes before the next write to that same file. A read of that file waits for the write. Other work continues. An uncertain command pauses only that task. Git is the person's file history. The app does not create a commit, branch, or worktree to separate tasks. Rewind uses the conversation checkpoint and does not restore files.

### Requirement: STATE-011 - Back up manually and restore to a clean verified destination
**Reason**: Application backup and restore are removed.
**Migration**: Chats live in the app until deleted. The person may download a Markdown transcript. There is no restore of the app database and no backup of browser sign-ins.

### Requirement: Operational observation excludes diagnostic capture processing
**Reason**: The product does not persist diagnostic copies of the request the model received, so routine reads have no capture body to process.
**Migration**: Operational screens read run state without a stored request dump. Deep Agents may still keep its own scratch note of summarized turns. That note is not a request inspector.

### Requirement: Incremental diagnostic privacy enforcement
**Reason**: There is no persisted model-request capture to fingerprint or re-redact.
**Migration**: Do not add a redaction setting or a paste-a-capture box. The next-message preview is not a stored capture.
