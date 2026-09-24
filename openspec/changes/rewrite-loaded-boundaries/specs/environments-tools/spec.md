# Spec Delta

## MODIFIED Requirements

### Requirement: ENV-020 - Use native file tools without duplicate mutations

Ordinary Chat SHALL offer Deep Agents built-in `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep` when project file access is selected. `execute` SHALL be offered only when ENV-008 attaches the host shell, and `write_todos` only when planning is selected. The product MUST NOT register another implementation of those tools or custom rename/delete tools. The upstream recursive `delete` and general-purpose `task` MUST NOT be offered in ordinary Chat, including compiled children; named helpers retain their selected invocation path. Application tools that are not file mutations remain `ask_user`, `propose_memory`, `read_attachment`, `echo`, and `time_now`; MCP tools remain supplied by ENV-007.

#### Scenario: No custom file deletion

- **WHEN** ordinary Chat presents project file tools
- **THEN** native read/write/edit/list/search are available as selected while custom rename/delete and recursive `delete` are absent.

#### Scenario: Concurrent same-file edits

- **WHEN** one assistant response requests simultaneous edits to the same path
- **THEN** the built-in guard rejects the conflict before two writes can race.

#### Scenario: No second reader

- **WHEN** the harness is assembled for a project
- **THEN** the file tools are Deep Agents built-ins and the application registers no second tool with their names.
