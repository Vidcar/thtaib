# environments-tools delta

## MODIFIED Requirements

### Requirement: ENV-009 - Route approval classes through one interrupt path

Automatic host-shell allowance SHALL be limited to the configured small read-only prefix set without shell metacharacters, or an explicitly saved matching action/resource grant. Other protected shell and MCP write/destructive actions SHALL pause through the shared interrupt path and record approval class. Grants SHALL follow AGT-008 and never enable an unselected tool or weaken mandatory restrictions. Host execution MUST NOT be described as sandboxed by its project directory. MCP elicitation SHALL remain a distinct typed input/resume operation, not an approve/reject command payload.

The read-only policy SHALL preserve validation against the actual `LocalShellBackend` shell execution semantics. A matching command prefix alone is insufficient: quoted, expanded, compound, redirected, unknown-option and ambiguous forms MUST NOT inherit automatic read-only approval. An explicit grant must match the actual action/resource under AGT-008 rather than reuse a misleading prefix parse.

#### Scenario: Read-only and destructive actions

- **WHEN** read-only shell and destructive MCP actions are attempted
- **THEN** only actions permitted by the current read-only policy or explicit matching grant proceed; other protected calls pause under their own typed interrupt identity.

#### Scenario: Ambiguous read-only prefix

- **WHEN** a command begins with a read-only name but includes quoting, expansion, an unrecognised option or shell composition
- **THEN** it requires approval unless an explicit valid grant matches the actual action and resource; prefix matching does not bypass the existing shell safeguards.
