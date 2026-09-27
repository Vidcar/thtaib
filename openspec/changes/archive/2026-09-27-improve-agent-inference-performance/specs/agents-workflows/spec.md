## MODIFIED Requirements

### Requirement: AGT-026 - Supply a bounded authorized project outline

Project chats with authorized file reading SHALL offer an optional outline capped at 1024 estimated tokens, showing relevant paths, declarations and headings. It SHALL respect exclusions and project boundaries, remain derived and disposable, label partial coverage, and yield context space to user input when the run starts. Tools-off and project-free requests MUST NOT receive it.

The outline SHALL reuse existing project exclusions and the actual enclosing repository's ignore rules. It SHALL use bounded file discovery and confined reads with a disposable bounded cache, not a durable repository index or unrestricted traversal. A project folder ignored by its enclosing repository MAY therefore have an empty outline.

An admitted run's outline SHALL be labelled as its initial project snapshot and remain stable across model/tool continuations. Project changes SHALL remain available through appended tool results and fresh authorized reads, without rebuilding early system context after each tool. A subsequent run SHALL take a fresh bounded snapshot. Native context recovery SHALL remain available if the optional snapshot contributes to an overflow.

#### Scenario: Project changes during a run
- **WHEN** a tool adds or renames a declaration or file during an admitted run
- **THEN** the initial outline remains unchanged in subsequent model requests and the changed project facts are available through the tool history and authorized reads.

#### Scenario: Changed project and limited context
- **WHEN** a new run starts after project files change or has insufficient room for its optional outline
- **THEN** its fresh outline reflects the current project and is reduced or omitted without blocking the user's request.

## ADDED Requirements

### Requirement: AGT-027 - Preserve retained visual context across tool continuations

Verified retained tool images SHALL be reconstructed at deterministic positions associated with their canonical tool results while those results remain in the active conversation context. An unrelated later tool SHALL NOT silently remove the previous image from the model-visible history. Capture references SHALL remain durable; raw image bytes SHALL remain bounded and excluded from checkpoints. Native compaction SHALL count active visual context and may remove or summarize it at an explicit context boundary. Failed capability checks and unavailable captures SHALL retain truthful text fallback.

#### Scenario: Screenshot followed by another tool
- **WHEN** a verified screenshot is followed by an assistant call and an unrelated tool result
- **THEN** the prior image remains at its original position in the next model request, preserving the unchanged prefix.

#### Scenario: Compaction removes older capture context
- **WHEN** native context compaction removes the older screenshot tool results
- **THEN** their images are no longer reconstructed, and the remaining visual context is counted under the same request budget.
