# Design

## Context

See proposal.md for motivation. Harness assembly appends `/retrieved/` to `framework_read_paths` even when `read_file` is selected. Middleware treats any nonempty list as exclusive and overrides the reader description. Native routed backends already enforce project containment and knowledge/capture scope.

## Goals / Non-Goals

Restore authorized reads without widening the automatically supplied reader. Retain upstream tools and existing backend permissions; do not change model settings or add reader implementations.

## Decisions

- Populate restricted paths only when a non-recorded run has tools but no selected `read_file`; then include retrieval when enabled. An empty list accompanies ordinary selected reading.
- Use the same selected-tool distinction at middleware authorization and description boundaries. This also prevents an existing saved run's retrieval-only list from narrowing its selected reader.
- Keep tools-off and Plan checks before route authorization. Keep prefix/traversal checks for the automatic reader and native backend containment for selected reading.
- Use existing schema fields rather than adding a permission flag or public type. Presence of the selected reader is already the authoritative distinction.

## Risks / Trade-offs

- A blanket exemption could grant project access to result-only reading: test both selected and automatic readers, including bound-project runs with file access omitted.
- A description-only fix would leave dispatch broken: exercise synchronous and asynchronous wrappers and actual native routed reads.

## Migration Plan

No data migration. Run local gates and an isolated two-turn real-model Chat, deliver through the repository workflow, then refresh only an idle established backend. Preserve weights, model/router processes, settings, saved chats and drafts. Rollback is a normal revert and idle refresh.
