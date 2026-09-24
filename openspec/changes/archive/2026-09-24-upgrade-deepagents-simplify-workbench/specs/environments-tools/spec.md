# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: ENV-009 - Route approval classes through one interrupt path

In Ask, every presented host-shell call and protected MCP write/destructive action SHALL pause through the shared interrupt path unless an explicitly saved action/resource grant matches. In Full access, selected enabled tools MAY skip approval; disabled tools and mandatory restrictions remain enforced. Grants SHALL follow AGT-008 and never enable an unselected tool. Host execution MUST NOT be described as sandboxed by its project directory. Typed MCP elicitation SHALL remain a typed response in the ordered interrupt batch, not an approve/reject payload. No command-prefix parser SHALL grant implicit shell approval.

#### Scenario: Read-only and destructive actions

- **WHEN** a read-only shell command or destructive MCP action is attempted in Ask
- **THEN** it pauses under its exact typed interrupt identity unless an explicit matching grant applies.

#### Scenario: Ambiguous read-only prefix

- **WHEN** a shell command begins with a familiar read-only name or includes quoting, expansion or composition
- **THEN** Ask applies the same approval check to the entire command; no prefix parser can authorize it.

## REMOVED Requirements

### Requirement: ENV-020 - Offer built-in file tools and only two custom file mutations

**Reason**: Custom one-file rename/delete and duplicate file-mutation presentation are retired; recursive upstream delete remains excluded from ordinary Chat.

**Migration**: Use Deep Agents built-in read/write/edit/list/search; explicit terminal operations follow Ask or Full access when execute is selected.
