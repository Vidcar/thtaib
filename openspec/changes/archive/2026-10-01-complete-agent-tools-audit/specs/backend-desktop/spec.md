## ADDED Requirements

### Requirement: API-056 - Present deliberate scoped autonomy and reusable workflows

The desktop SHALL expose a distinct project file-change approval with its project, operations, exclusions, duration and revocation, separately from existing exact-action approvals. It SHALL accurately describe which actions a grant covers. Settings SHALL permit inspecting/revoking both grant kinds. Agents and Knowledge SHALL provide opt-in setup templates and bundled conditional runtime skills as drafts/installations using the existing editors, selections and versioning. Suggested Chat-owned modes/access/window requirements SHALL remain visible guidance and SHALL NOT be silently granted by a template.

#### Scenario: Approve scoped file changes
- **WHEN** the person creates an explicit project file-change scope in Settings
- **THEN** subsequent matching selected Create/Edit actions use that scope while excluded paths and other operations retain their own approval
- **AND** Settings displays and can revoke the resulting scope; an already pending approval keeps its exact-action response choices.

#### Scenario: Choose a template
- **WHEN** a person chooses a reusable agent template or installs a bundled skill
- **THEN** they can inspect its actual choices in existing authoring controls before using it, with current unrelated records preserved.
