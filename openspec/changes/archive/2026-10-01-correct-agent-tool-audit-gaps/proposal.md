# Proposal

## Why

The 1 October reassessment of the closed agent-tools audit found five remaining gaps: project-mutation admission can stall the worker pool, the desktop can save a broader tool selection than backend Standard, the evidence-researcher template cannot run without a project, stock workflows cannot use the retained-result reader they recommend, and a resource-only connection is treated as unready when it has no tools. These are corrective gaps in current main, not a new harness.

## What Changes

- Admit project mutations without parking asynchronous waiters on the blocking worker pool the active mutation needs. Native edits and structured apply keep one per-project gate. Recheck cancellation, eligibility and the applicable grant after the wait, before the effect.
- Make the backend catalogue the source of Standard membership, groups and Plan eligibility. A Standard-to-explicit edit starts from that selection. Catalogue failure does not invent a list. Existing saved setups are not rewritten.
- Make the evidence-researcher template genuinely project-optional: document, reference and retained-result reading, with public-web tools only from an already selected built-in connection. Project discovery stays available when a project is bound and is not pinned for a projectless run.
- Select `read_tool_result` on new stock templates that consume retained evidence, and make continuation notices name only an accepted reader or the real limitation.
- Treat a successful empty tool manifest as ready when the tested protocol capability says so, and admit resource-only connections in both loading modes. Unsupported resources, failed tests and disabled or revoked connections stay distinct.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agents-workflows`: project-optional research templates, retained-result selection on new templates, and trusted public-web tools of an already selected built-in connection when tools are not off.
- `environments-tools`: contention-safe project-mutation admission, backend-owned Standard/group/Plan projection, continuation guidance that matches the accepted readers, and capability-based connection readiness for resource-only servers.

## Impact

Backend mutation admission, tool catalogue projection, setup templates, filesystem admission, retained-result notices, connection readiness and the desktop agent-tool editor. Generated connection records gain an optional tested-capability list. No new tool catalogue, framework, model setting, dependency or silent rewrite of saved setups. The active `consolidate-product-contract` change and archived audit resolutions stay untouched.
