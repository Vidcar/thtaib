# state-recovery delta

## ADDED Requirements

All requirements below SHALL retain the verified `repair-local-interaction-boundaries` guarantees: repeated-text legacy chronology and multiplicity, stable or deterministic display identity, narrow idempotent repair, preserved later/partial/tool output and display-edit replay cutovers, with no hidden-message resurrection or execution replay. The prerequisite does not implement retained uploads, deletion or backup features.

### Requirement: STATE-009 - Retain authorized files and verify actual outputs

One retained-file/artifact contract SHALL identify origin, session/project/access scope, storage ownership, content type, size/hash, observation time and source run/tool where applicable. Mutable project references SHALL be distinct from immutable retained upload/output snapshots; access and mutable identity are rechecked on open/reuse. Old path-only records remain unverified until checked. Tool arguments/model-written paths are attempted operations, not artifacts: successful result and required file observations establish outputs. Scratch/history/offloads are not project outputs.

Chat SHALL support text/code picker and drag/drop, actual content/encoding/limit validation, removable staging and attachment-only turns. Sent originals are retained session-scoped by default without a project or automatic knowledge promotion. Fitting source-labelled content SHALL enter current-user input even with tools off. Larger material requires authorized scoped reading or an actionable capacity outcome, not silent truncation or tool/host authority. Copy bytes only for deliberate retention; persist attachment provenance across reopening.

A shared Library SHALL browse retained attachments and verified outputs across authorized conversations/projects with scope filters and original conversation/project provenance. Inline reply entries and the on-demand Files panel SHALL use the same records and distinguish retained copies from mutable project references. Supported preview/open/save/reuse/delete actions SHALL preserve access checks and dependency-aware deletion. Library MUST NOT create a second artifact authority, grant additional access or indiscriminately catalogue project files; later project and media views extend this contract.

#### Scenario: Attachment with tools off

- **WHEN** a non-project turn contains only a fitting supported text/code attachment
- **THEN** the retained authorized original and labelled content are usable without enabling filesystem/shell/retrieval tools.

#### Scenario: Attempt versus verified output

- **WHEN** a write fails or a previously observed project file changes
- **THEN** no successful artifact is invented and stale content verification is not reused.

#### Scenario: Find a retained output from another conversation

- **WHEN** a user filters Library by project and opens or reuses an older retained output
- **THEN** its source conversation/project and retained-versus-mutable identity remain visible, current access is checked and reuse does not move the source session or grant project access.

### Requirement: STATE-010 - Delete deliberately while preserving shared dependencies

Conversations, sent originals and verified retained outputs SHALL remain until deliberate dependency-aware deletion. Diagnostics SHALL have separately inspectable collection/retention controls; staging cleanup must not erase submitted assets. Deletion SHALL preview affected/retained sessions, runs, branches, checkpoints, scratch, originals, outputs and diagnostics; coordinate active work and use supported checkpoint APIs. Surviving branches, Lab cases and Workflows retain needed shared content. Project source files, committed knowledge, remote copies and earlier backups/exports MUST NOT be incidentally deleted. Unlink, archive, delete and diagnostic cleanup have distinct effects; secure physical erasure or complete forgetting MUST NOT be claimed.

#### Scenario: Shared asset deletion

- **WHEN** a deleted conversation shares checkpoints/assets with retained consumers
- **THEN** the preview and cleanup preserve required references and state accurately what remains, including external/backup copies.

### Requirement: STATE-011 - Back up manually and restore to a clean verified destination

The system SHALL provide readable conversation export and a separate on-demand versioned application backup; no automatic backup schedule is required or activated. Backup SHALL consistently capture application records, compatible checkpoints, retained assets and linkage through verified snapshot/quiescence handling, with manifests/integrity checks. Exclude credentials by default, flag sensitive content and distinguish included bytes from external project/model references.

Restore SHALL use a clean application-data destination, validate data/checkpoint/runtime compatibility and integrity, retain branch/asset linkage and expose missing models, project paths and credential bindings. Reconcile runs without restarting uncertain effects. Later knowledge, setup, Lab, Workflow and media records extend this same format. A readable export or inconsistent live database copy is not a restorable application backup.

#### Scenario: Backup and restore

- **WHEN** an on-demand backup is restored with some external dependencies absent
- **THEN** integrity and linkage are verified in a clean root, missing dependencies are shown and no uncertain action is automatically replayed.
