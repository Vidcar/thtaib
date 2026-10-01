# Proposal

## Why

After the merged agent-tool audit correction, three narrower gaps remain. A projectless evidence researcher still fails when tool definitions are set to Always include all. A resources-only MCP server still has to implement tools/list before its resources can be tested. Continuation guidance can say no reader exists when the automatic framework-only line reader is already available.

## What Changes

- Omit unpinned `glob` and `grep` until a project is bound, under both definition-loading preferences, without rewriting the saved selection. Keep unpinned `ls` and `read_file` only as virtual readers for a selected knowledge or capture route, and do not describe them as a project root.
- Keep pinned project reads, skill-required project or shell tools, eager file mutations, and eager shell or preview as hard failures when no project is bound.
- Test MCP connections from negotiated capabilities. List tools only when tools are advertised, and validate resources independently when resources are advertised.
- Distinguish a successful empty tool list, an unsupported optional method, and a failed operation on an advertised capability. Do not treat arbitrary error text as capability evidence, and do not invent tools support.
- Derive retained-result continuation guidance from the same effective reader resolution used at model dispatch, including the framework-only `read_file` path limit, explicit exclusions, and Tools off.
- Keep the stored retention notice as provenance. A later read reports the current run's reader availability separately.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `agents-workflows`: AGT-035 projectless research no longer depends on the definition-loading preference, and a required project capability still fails without a project.
- `environments-tools`: ENV-008 keeps project-free shell, preview, pinned reads, and eager mutations failing; ENV-032 guidance follows the effective reader; ENV-034 tests resources without requiring tools/list.

## Impact

- Backend admission in `agents/harness_presentation.py`, chat preflight, and skill dependency checks.
- MCP connection testing in `connections/service.py`.
- Continuation notices in `agents/tool_results.py` and the framework-reader exclusion in `agents/middleware.py`.
- No desktop contract or saved-setup migration. The six stock template reader selections, the mutation lease, and the backend tool catalogue projection stay as they are.
