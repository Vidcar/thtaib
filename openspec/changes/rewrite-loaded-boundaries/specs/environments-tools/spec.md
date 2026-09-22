# Spec Delta

## ADDED Requirements

### Requirement: ENV-020 - Offer built-in file tools and only two custom file mutations

Ordinary Chat's file tools SHALL be the Deep Agents built-ins `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep`. `execute` SHALL be offered only when ENV-008 attaches the host shell. `write_todos` SHALL be offered only when planning is selected. The only custom file mutations SHALL be `rename_file`, which renames one regular file without overwriting a destination, and `delete_file`, which deletes one regular file. The product MUST NOT register a second copy of the built-in filesystem tools.

The upstream recursive `delete` tool and the general-purpose `task` tool MUST NOT be offered in ordinary Chat. Extra tools passed into the harness are additive and MUST NOT be treated as removing a built-in. Removal SHALL use the upstream exclusion or the filesystem middleware tool list, including for a compiled child. Application tools that are not file mutations remain `ask_user`, `propose_memory`, `read_attachment`, `echo`, and `time_now`. MCP tools remain those supplied by ENV-007.

#### Scenario: Model sees one delete

- **WHEN** ordinary Chat with a project presents file tools
- **THEN** `delete_file` is the delete the model can call
- **AND** the recursive `delete` tool and `task` are not offered, including to a child.

#### Scenario: No second reader

- **WHEN** the harness is assembled for a project
- **THEN** `read_file`, `write_file`, `edit_file`, `ls`, `glob`, and `grep` are the built-in tools
- **AND** the application does not register another tool of the same name.
